import fs from "fs";
import puppeteer from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import dotenv from "dotenv";
import { Browser } from "puppeteer";
import { anonymizeProxy } from "proxy-chain";
import { shuffle } from "lodash";
import events from "events";
import { delay } from "./scrape-util";

dotenv.config();
const NUM_HEADFUL = Number(process.env.NUM_HEADFUL);
const MAX_CHALLENGE_TRIES = Number(process.env.MAX_CHALLENGE_TRIES);
const BROWSER_LIMIT = Number(process.env.BROWSER_LIMIT) || 1;
const FORCE_HEADFUL = process.env.FORCE_HEADFUL;
const FORCE_HEADLESS = process.env.FORCE_HEADLESS;
const SCRAPE_DELAY = Number(process.env.SCRAPE_DELAY) || 0;
const WEBSHARE = !!process.env.WEBSHARE;

events.EventEmitter.defaultMaxListeners = BROWSER_LIMIT + 5;

puppeteer.use(StealthPlugin());

const responseHeadersToRemove = [
  "Accept-Ranges",
  "Content-Length",
  "Keep-Alive",
  "Connection",
  "content-encoding",
  "set-cookie",
];

const BASE_URL = "https://www.hltv.org";

let ips: string[] = shuffle(
  fs.readFileSync("ips.txt", { encoding: "utf8" }).split("\n")
);
if (WEBSHARE)
  ips = ips.map((ip) => {
    const splitted = ip.split(":");
    return `${splitted[2]}:${splitted[3]}@${splitted[0]}:${splitted[1]}`;
  });

let availableHeadlessBrowsers: Browser[] = [];
let availableHeadfulBrowsers: Browser[] = [];
const browserDict: Record<string, { ip: string; anonymizedIp: string }> = {};

let inProgressUrls: Set<string> = new Set();

let allBrowsersCreated = false;

const addNewBrowser = async (headful: boolean) => {
  if (ips.length == 0) {
    console.log("No more IPs available");
    return;
  }
  const ip = ips.pop();
  const anonymizedIp = await anonymizeProxy("http://" + ip);
  const proxyString = `--proxy-server=${anonymizedIp}`;
  const newBrowser = await puppeteer.launch({
    headless: !headful,
    args: [
      "--no-sandbox",
      "--disable-setuid-sandbox",
      "--disable-gpu",
      proxyString,
    ],
  });
  browserDict[newBrowser.process().pid] = { ip, anonymizedIp };
  (!headful ? availableHeadlessBrowsers : availableHeadfulBrowsers).push(
    newBrowser
  );
};

(async () => {
  const browserAdditions: Promise<void>[] = [];
  for (let i = 0; i < BROWSER_LIMIT; i++) {
    const headful = i < NUM_HEADFUL;
    browserAdditions.push(addNewBrowser(headful));
  }
  await Promise.all(browserAdditions);
  allBrowsersCreated = true;
})();

const removeBrowser = async (currBrowser, headful, url) => {
  console.error(
    "Removed browser info:",
    browserDict[currBrowser.process().pid]
  );
  await currBrowser.close();
  await addNewBrowser(headful);
  inProgressUrls.delete(url);
  delete browserDict[currBrowser.process().pid];
};

// much of this function comes from the npm package "pupflare"
const puppeteerGet = async (
  url: string,
  refererUrl?: string,
  headful: boolean = false
) => {
  if (inProgressUrls.has(url)) return;
  if (FORCE_HEADFUL) headful = true;
  if (FORCE_HEADLESS) headful = false;
  while (
    !allBrowsersCreated ||
    (headful ? availableHeadfulBrowsers : availableHeadlessBrowsers).length == 0
  ) {
    // console.log("no browsers available for url", url, "waiting");
    await delay(Math.random() * 5000);
  }

  const currBrowser = (
    headful || availableHeadlessBrowsers.length == 0
      ? availableHeadfulBrowsers
      : availableHeadlessBrowsers
  ).shift();

  if (!currBrowser) {
    console.error("No browser for url ", url);
    return;
  }
  if (!currBrowser?.process() || !currBrowser?.process()?.pid) {
    console.error("No PID for browser scraping url ", url);
    return;
  }
  await delay(Math.random() * 5000 + SCRAPE_DELAY);
  inProgressUrls.add(url);
  const fullUrl = BASE_URL + url;
  console.log("Scraping", fullUrl);
  let responseBody;
  let responseData;
  let responseHeaders;
  let responseUrl;

  try {
    const page = await currBrowser.newPage();
    // if (request.method == "POST") {
    //   await page.removeAllListeners("request");
    //   await page.setRequestInterception(true);
    //   page.on("request", (interceptedRequest) => {
    //     var data = {
    //       method: "POST",
    //       postData: request.rawBody,
    //     };
    //     interceptedRequest.continue(data);
    //   });
    // }
    if (refererUrl)
      page.setExtraHTTPHeaders({ Referer: BASE_URL + refererUrl });
    const client = await page.target().createCDPSession();
    await client.send("Network.setRequestInterception", {
      patterns: [
        {
          urlPattern: "*",
          resourceType: "Document",
          interceptionStage: "HeadersReceived",
        },
      ],
    });

    client.on("Network.requestIntercepted", async (e) => {
      let obj = { interceptionId: e.interceptionId };
      if (e.isDownload) {
        await client
          .send("Network.getResponseBodyForInterception", {
            interceptionId: e.interceptionId,
          })
          .then((result) => {
            if (result.base64Encoded) {
              responseData = Buffer.from(result.body, "base64");
            }
          });
        obj["errorReason"] = "BlockedByClient";
        responseHeaders = e.responseHeaders;
      }
      try {
        await client.send("Network.continueInterceptedRequest", obj);
      } catch (e) {
        console.log("Unable to continue intercepted request ", e);
      }
      if (e.isDownload) await page.close();
    });
    let response;
    let tryCount = 0;
    try {
      response = await page.goto(fullUrl, {
        timeout: 0,
        waitUntil: "domcontentloaded",
      });
    } catch (err) {
      // console.error(`Unable to open page ${url}`, err);
      puppeteerGet(url, refererUrl, headful);
      throw err;
    }
    responseBody = await response.text();
    responseData = await response.buffer();
    if (
      !responseBody.includes("challenge-running") &&
      !responseBody.includes("© HLTV.org")
    ) {
      console.error(
        `Browser fetching url ${url} was blocked, removing it from the pool now.`
      );
      await removeBrowser(currBrowser, headful, url);
      return await puppeteerGet(url, refererUrl, headful);
    }
    while (
      responseBody.includes("challenge-running") &&
      tryCount < MAX_CHALLENGE_TRIES
    ) {
      if (!headful) {
        break;
      }
      const newResponse = await page.waitForNavigation({
        timeout: 0,
        waitUntil: "domcontentloaded",
      });
      if (newResponse) response = newResponse;
      responseBody = await response.text();
      responseData = await response.buffer();
      responseUrl = await response.url();
      tryCount++;
      // if (tryCount > 0) console.log(`try number ${tryCount}`);
      // await page.screenshot({ path: "cf.png", fullPage: true });
    }
    if (responseBody.includes("challenge-running")) {
      console.log(
        `Unable to beat challenge for url ${url}, retrying with new browser`
      );
      (headful ? availableHeadfulBrowsers : availableHeadlessBrowsers).push(
        currBrowser
      );
      inProgressUrls.delete(url);
      return await puppeteerGet(url, refererUrl, true);
    }
    // if (tryCount > 0) console.log(`Beat challenge after ${tryCount} tries`);
    responseHeaders = await response.headers();
    responseHeadersToRemove.forEach((header) => delete responseHeaders[header]);
    await page.close();
  } catch (error) {
    if (error.toString().contains("ERR_TIMED_OUT")) {
      console.error(
        `Browser fetching url ${url} timed out, removing it from the pool now.`
      );
      await removeBrowser(currBrowser, headful, url);
      return await puppeteerGet(url, refererUrl, headful);
    }
    console.error(
      "Failed browser info:",
      browserDict[currBrowser.process().pid]
    );
  }
  (headful ? availableHeadfulBrowsers : availableHeadlessBrowsers).push(
    currBrowser
  );
  inProgressUrls.delete(url);
  return responseBody;
};

export default puppeteerGet;
