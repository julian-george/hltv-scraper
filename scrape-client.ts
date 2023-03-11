import fs from "fs";
import puppeteer from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import dotenv from "dotenv";
import { Browser } from "puppeteer";
import { anonymizeProxy } from "proxy-chain";
import { shuffle } from "lodash";
import events from "events";
import { delay } from "./scrape-util";
import "log-timestamp";

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
const browserDict: Record<
  string,
  { ip: string; anonymizedIp: string; numTimeouts: number }
> = {};

let inProgressUrls: Set<string> = new Set();

let allBrowsersCreated = false;

const addNewBrowser = async (headful: boolean) => {
  if (ips.length == 0) {
    console.error("No more IPs available");
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
      // "--user-data-dir=/Users/julian/Library/Application Support/Google/Chrome",
      proxyString,
    ],
  });
  browserDict[newBrowser.process().pid] = { ip, anonymizedIp, numTimeouts: 0 };
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
    currBrowser.process().pid,
    browserDict[currBrowser.process().pid]
  );
  try {
    currBrowser
      .close()
      .then(() => {
        // console.log("Done closing browser.");
      })
      .catch((err) => {
        console.error("Error while closing browser", err);
      });
  } catch (e) {
    console.error("Error while closing browser", e);
  }
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
    await delay(Math.random() * 2500);
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
  await delay(SCRAPE_DELAY);
  inProgressUrls.add(url);
  const fullUrl = BASE_URL + url;
  console.log("Scraping", fullUrl);
  let responseBody;
  let responseData;
  let responseHeaders;
  let responseUrl;
  let page;
  try {
    page = await currBrowser.newPage();
    if (refererUrl)
      page.setExtraHTTPHeaders({ Referer: BASE_URL + refererUrl });
    await page.setRequestInterception(true);
    page.on("request", (request) => {
      if (!request.url().includes("hltv") || request.url().includes("cdn-cgi"))
        request.continue();
      else {
        if (
          ["image", "stylesheet", "script"].includes(request.resourceType())
        ) {
          // if (!request.url().includes("img-cdn.hltv.org"))
          //   console.log(request.url(), request.headers());
          request.abort();
        } else {
          request.continue();
        }
      }
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
    // console.log("response data received");
    responseData = await response.buffer();
    // console.log("response buffer received");
    if (
      responseBody.includes("/img/static/error.png") &&
      responseBody.includes("500")
    ) {
      console.error(`Server error 500 for url ${url}`);
      return null;
    }
    if (
      !responseBody.includes("challenge-running") &&
      !responseBody.includes("© HLTV.org")
    ) {
      console.error(
        `Browser fetching url ${url} was blocked, removing it from the pool now.`
      );
      try {
        await removeBrowser(currBrowser, headful, url);
      } catch (err) {
        console.error("Error while removing browser", err);
      }

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
      console.error(
        `Unable to beat challenge for url ${url}, retrying with new browser`
      );
      (headful ? availableHeadfulBrowsers : availableHeadlessBrowsers).push(
        currBrowser
      );
      inProgressUrls.delete(url);
      return await puppeteerGet(url, refererUrl, true);
    }
    // if (tryCount > 0) console.log(`Beat challenge after ${tryCount} tries`);
    // responseHeaders = await response.headers();
    // responseHeadersToRemove.forEach((header) => delete responseHeaders[header]);
    // console.log("about to close");
    page.close().catch((err) => {
      console.error(`Error while closing page for URL ${url}`, err);
    });
  } catch (error) {
    if (
      error.toString().includes("ERR_TIMED_OUT") ||
      error.toString().includes("ERR_EMPTY_RESPONSE")
    ) {
      if (browserDict[currBrowser.process().pid].numTimeouts < 3) {
        browserDict[currBrowser.process().pid].numTimeouts++;
      } else {
        console.error(
          `Browser fetching url ${url} timed out for the third time: (${error.toString()}), removing it from the pool now.`
        );
        await removeBrowser(currBrowser, headful, url);
      }
      return await puppeteerGet(url, refererUrl, headful);
    } else if (error.toString().includes("ERR_CONNECTION_CLOSED")) {
      console.error(`Browser fetching ${url} failed to connect, retrying.`);
      (headful ? availableHeadfulBrowsers : availableHeadlessBrowsers).push(
        currBrowser
      );
      if (page) page.close();
      return await puppeteerGet(url, refererUrl, headful);
    }
  }
  (headful ? availableHeadfulBrowsers : availableHeadlessBrowsers).push(
    currBrowser
  );
  inProgressUrls.delete(url);
  return responseBody;
};

export default puppeteerGet;
