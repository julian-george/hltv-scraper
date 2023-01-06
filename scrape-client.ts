import fs from "fs";
import puppeteer from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import dotenv from "dotenv";
import { Browser } from "puppeteer";
import { anonymizeProxy } from "proxy-chain";
import { shuffle } from "lodash";
import events from "events";

dotenv.config();
const NUM_HEADFUL = Number(process.env.NUM_HEADFUL);
const MAX_CHALLENGE_TRIES = Number(process.env.MAX_CHALLENGE_TRIES);
const BROWSER_LIMIT = Number(process.env.BROWSER_LIMIT) || 1;
const FORCE_HEADFUL = process.env.FORCE_HEADFUL;
const FORCE_HEADLESS = process.env.FORCE_HEADFUL;
const SCRAPE_DELAY = Number(process.env.SCRAPE_DELAY) || 0;

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
).slice(0, BROWSER_LIMIT);
let availableHeadlessBrowsers: Browser[] = [];
let availableHeadfulBrowsers: Browser[] = [];

let inProgressUrls: Set<string> = new Set();

let allBrowsersCreated = false;

(async () => {
  for (let i = 0; i < ips.length; i++) {
    const isHeadless = i >= NUM_HEADFUL;
    try {
      const proxyString = `--proxy-server=${await anonymizeProxy(
        "http://" + ips[i]
      )}`;
      const newBrowser = await puppeteer.launch({
        headless: isHeadless,
        args: [
          "--no-sandbox",
          "--disable-setuid-sandbox",
          "--disable-gpu",
          proxyString,
        ],
      });
      (isHeadless ? availableHeadlessBrowsers : availableHeadfulBrowsers).push(
        newBrowser
      );
    } catch (err) {
      console.error(`Unable to create browser ${i} with ip ${ips[i]}`, err);
    }
  }
  allBrowsersCreated = true;
})();

// much of this function comes from the npm package "pupflare"
const puppeteerGet = async (url: string, headful: boolean = false) => {
  await new Promise((resolve, reject) =>
    setTimeout(() => {
      resolve(true);
    }, Math.random() * 1000 + SCRAPE_DELAY)
  );
  if (inProgressUrls.has(url)) return;
  if (FORCE_HEADFUL) headful = true;
  if (FORCE_HEADLESS) headful = false;
  while (
    !allBrowsersCreated ||
    (headful ? availableHeadfulBrowsers : availableHeadlessBrowsers).length == 0
  ) {
    const waitPromise = new Promise((resolve) => {
      setTimeout(() => {
        console.log("no browsers available for url", url, "waiting");
        resolve(true);
      }, 5000);
    });
    await waitPromise;
  }

  const currBrowser = (
    headful ? availableHeadfulBrowsers : availableHeadlessBrowsers
  ).shift();
  if (!currBrowser) return;
  inProgressUrls.add(url);
  const fullUrl = BASE_URL + url;
  console.log("Scraping", fullUrl);
  let responseBody;
  let responseData;
  let responseHeaders;
  let responseUrl;

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
    await client.send("Network.continueInterceptedRequest", obj);
    if (e.isDownload) await page.close();
  });
  try {
    let response;
    let tryCount = 0;
    try {
      response = await page.goto(fullUrl, {
        timeout: 30000,
        waitUntil: "domcontentloaded",
      });
    } catch (err) {
      console.error(`Unable to open page ${url}`, err);
      puppeteerGet(url, headful);
      throw err;
    }
    responseBody = await response.text();
    responseData = await response.buffer();
    if (responseBody.includes("Access Denied")) {
      console.error(
        `Browser fetching url ${url} was blocked, removing it from the pool now.`
      );
      return await puppeteerGet(url, headful);
    }
    while (
      responseBody.includes("challenge-running") &&
      tryCount < MAX_CHALLENGE_TRIES
    ) {
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
    if (tryCount == MAX_CHALLENGE_TRIES) {
      if (!headful) {
        console.log(
          `Headless scraping failed for URL ${url}, trying headful scraping.`
        );
        inProgressUrls.delete(url);
        return await puppeteerGet(url, true);
      } else {
        throw new Error(`Unable to beat challenge for url ${url}.`);
      }
    }
    // if (tryCount > 0) console.log(`Beat challenge after ${tryCount} tries`);
    responseHeaders = await response.headers();
    responseHeadersToRemove.forEach((header) => delete responseHeaders[header]);
  } catch (error) {
    console.error(`Error while fetching url ${url}`, error);
    if (!error.toString().includes("ERR_BLOCKED_BY_CLIENT")) {
      console.error("Error sending request: ", error);
    }
  }
  await page.close();
  (headful ? availableHeadfulBrowsers : availableHeadlessBrowsers).push(
    currBrowser
  );
  inProgressUrls.delete(url);
  return responseBody;
};

export default puppeteerGet;
