import fs from "fs";
import puppeteer from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import dotenv from "dotenv";
import { Browser } from "puppeteer";
import { anonymizeProxy } from "proxy-chain";
import _ from "lodash";
import events from "events";
import "log-timestamp";
import util from "node:util";
import fetch from "node-fetch";
import config from "config";
import { delay } from "./scrape-util.js";
import { getQueue } from "./queues.js";

dotenv.config();
const CACHED = config.get("scrapeCached");
const NUM_HEADFUL = config.get("browsers.numHeadful");
const MAX_CHALLENGE_TRIES = config.get("browsers.maxChallengeAttempts");
const BROWSER_LIMIT = config.get("browsers.limit");
const FORCE_HEADFUL = config.get("browsers.forceHeadful");
const FORCE_HEADLESS = config.get("browsers.forceHeadless");
const SCRAPE_DELAY = config.get("browsers.scrapeDelay");
const WEBSHARE = config.get("browsers.webshareFormat");
const IP_URL = config.get("browsers.ipUrl");

const SCREEN_HEIGHT = 1400;
const SCREEN_WIDTH = 1680;
// These settings are horribly broken due to chromium's unpredictable "window-size" behavior, just trial and error
const MAX_WINDOW_COLS = 4;
const NUM_WINDOW_ROWS = 9;
// const WINDOW_WIDTH = SCREEN_WIDTH / (BROWSER_LIMIT / NUM_WINDOW_ROWS);
const WINDOW_WIDTH = Math.round(SCREEN_WIDTH / MAX_WINDOW_COLS);
// const WINDOW_HEIGHT = SCREEN_HEIGHT / NUM_WINDOW_ROWS;
const WINDOW_HEIGHT = Math.round(SCREEN_HEIGHT / NUM_WINDOW_ROWS);
const WINDOW_SIZE_FLAG = `--window-size=${WINDOW_WIDTH},${WINDOW_HEIGHT}`;

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

let ips = null;

let availableHeadlessBrowsers: Browser[] = [];
let availableHeadfulBrowsers: Browser[] = [];
const browserDict: Record<
  string,
  {
    ip: string;
    anonymizedIp: string;
    numTimeouts: number;
    slot: number;
    currentUrl: string | null;
    addedDatetime: Date;
  }
> = {};

let inProgressUrls: Set<string> = new Set();
let emptySlots: number[] = [];
let allBrowsersCreated = false;

const timeStarted = Date.now();
let numPagesScraped = 0;

const addNewBrowser = async (headful: boolean) => {
  if (ips.length == 0) {
    console.error("No more IPs available");
    return;
  }
  const slot = emptySlots.pop();
  const positionFlag = `--window-position=${
    (slot % MAX_WINDOW_COLS) * WINDOW_WIDTH
  },${Math.floor(slot / MAX_WINDOW_COLS) * WINDOW_HEIGHT}`;
  const ip = ips.pop();
  const anonymizedIp = await anonymizeProxy("http://" + ip);
  const proxyFlag = `--proxy-server=${anonymizedIp}`;
  const newBrowser = await puppeteer.launch({
    headless: !headful,
    args: [
      // "--no-sandbox",
      // "--disable-setuid-sandbox",
      // "--disable-gpu",
      WINDOW_SIZE_FLAG,
      positionFlag,
      proxyFlag,
    ],
  });
  browserDict[newBrowser.process().pid] = {
    ip,
    anonymizedIp,
    numTimeouts: 0,
    slot,
    currentUrl: null,
    addedDatetime: new Date(),
  };
  (!headful ? availableHeadlessBrowsers : availableHeadfulBrowsers).push(
    newBrowser
  );
};

!CACHED &&
  (async () => {
    if (IP_URL) {
      try {
        ips = await (await fetch(IP_URL))?.text();
      } catch (e) {
        console.error("Failed to download ips, drawing from text file", e);
      }
    }
    if (!ips) {
      ips = fs.readFileSync("ips.txt", { encoding: "utf8" });
    } else {
      fs.writeFileSync("ips.txt", ips);
    }
    ips = ips.split("\n");
    // Removes the empty last line that these text files often have
    ips = ips.filter((ip: string) => ip != "");
    // Ensures that certain IPs don't get used and blocked more than others
    ips = _.shuffle(ips);
    if (WEBSHARE)
      ips = ips.map((ip) => {
        const splitted = ip.split(":");
        return `${splitted[2]}:${splitted[3]}@${splitted[0]}:${splitted[1]}`;
      });
    const browserAdditions: Promise<void>[] = [];
    for (let i = 0; i < BROWSER_LIMIT; i++) {
      emptySlots.push(i);
      const headful = i < NUM_HEADFUL;
      browserAdditions.push(addNewBrowser(headful));
    }
    await Promise.all(browserAdditions);
    allBrowsersCreated = true;
  })();

const removeBrowser = async (currBrowser, headful, url, err) => {
  console.error(
    "Removed browser info:",
    currBrowser.process().pid,
    browserDict[currBrowser.process().pid],
    "Error:",
    err
  );
  emptySlots.push(browserDict[currBrowser.process().pid].slot);
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
  delete browserDict[currBrowser.process().pid];
};

// getQueue.on("add", () => {
//   const queueSize = getQueue.size;
//   if ((queueSize + 1) % 100 == 0)
//     console.error("getQueue size:", queueSize - 1);
// });

// much of this function comes from the npm package "pupflare"
const puppeteerGetInner = async (
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
    console.log("no browsers available for url", url, "waiting");
    await delay(0, 750);
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

  const browserId = currBrowser.process().pid;

  browserDict[browserId].currentUrl = url;

  await delay(SCRAPE_DELAY);
  inProgressUrls.add(url);
  const fullUrl = BASE_URL + url;
  console.log("Scraping", fullUrl);
  let responseBody;
  let responseData;
  let responseHeaders;
  let responseUrl;
  let page;
  let conclude = async (
    removed: boolean = false,
    toReturn: any = undefined
  ) => {
    // console.log(
    //   `conclude ${url}: removed:${removed} toReturn:${toReturn === undefined}`
    // );
    if (!removed) {
      (headful ? availableHeadfulBrowsers : availableHeadlessBrowsers).push(
        currBrowser
      );
      if (page)
        page.close().catch((err) => {
          console.error(`Error while closing page for URL ${url}`, err);
        });
      browserDict[browserId].currentUrl = null;
    }
    inProgressUrls.delete(url);
    if (!(toReturn === undefined)) {
      // Increment number of pages scraped here because successful scraping will always terminate in this clause
      numPagesScraped++;
      return toReturn;
    } else {
      return await puppeteerGetInner(url, refererUrl, headful);
    }
  };
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
      const error = new Error(`Server error 500 for url ${url}`);
      return await conclude(false, null);
    }
    if (
      responseBody.includes("Access denied") &&
      !responseBody.includes("challenge-running") &&
      !responseBody.includes("© HLTV.org")
    ) {
      const error = new Error(`Browser fetching url ${url} was blocked`);
      console.error(`${error.toString()}, removing it from the pool now.`);
      // await page.screenshot({ path: "cf.png", fullPage: true });
      await removeBrowser(currBrowser, headful, url, error);
      return await conclude(true, undefined);
    }
    // TODO: what happens when I get hcaptcha on everything?
    // if (responseBody.includes(`class="hcaptcha-box"`)) {
    //   console.error(`Browser fetching url ${url} encountered hcaptcha.`);
    //   try {
    //     await removeBrowser(currBrowser, headful, url);
    //   } catch (err) {
    //     console.error("Error while removing browser", err);
    //   }

    //   return await retry(true);
    // }
    while (
      (responseBody.includes("challenge-running") ||
        responseBody.includes('<span id="challenge-error-text">')) &&
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
    }
    if (responseBody.includes("challenge-running")) {
      const error = new Error(`Unable to beat challenge for url ${url}`);

      return await conclude(false, undefined);
    }
    // if (tryCount > 0) console.log(`Beat challenge after ${tryCount} tries`);
    // responseHeaders = await response.headers();
    // responseHeadersToRemove.forEach((header) => delete responseHeaders[header]);
    // console.log("about to close");
  } catch (error) {
    if (
      error.toString().includes("ERR_TIMED_OUT") ||
      error.toString().includes("ERR_EMPTY_RESPONSE") ||
      error.toString().includes("ERR_CONNECTION_FAILED") ||
      error.toString().includes("ERR_CONNECTION_CLOSED")
    ) {
      console.error(
        `Browser fetching ${url} timed out for ${
          browserDict[browserId].numTimeouts + 1
        } time`
      );
      if (browserDict[browserId].numTimeouts < 8) {
        browserDict[browserId].numTimeouts++;
        return await conclude(false, undefined);
      } else {
        const removalError = new Error(
          `Browser fetching url ${url} timed out too many times, removing it from the pool now.`
        );
        await removeBrowser(currBrowser, headful, url, error);
        return await conclude(true, undefined);
      }
    } else if (error.toString().includes("ERR_TUNNEL_CONNECTION_FAILED")) {
      console.error(`Proxy connection failed for browser fetching ${url}`);
      await removeBrowser(currBrowser, headful, url, error);
      return await conclude(true, undefined);
    } else {
      console.error(
        `Browser fetching ${url} encountered unknown error:`,
        error
      );
    }
  }
  return await conclude(false, responseBody);
};

const puppeteerGet = async (
  url: string,
  refererUrl?: string,
  headful: boolean = false
) => await getQueue.add(() => puppeteerGetInner(url, refererUrl, headful));

export default puppeteerGet;

["exit"].forEach((eventType) => {
  process.on(eventType, () => {
    console.error("getQueue info: ");
    console.error(`num pending: ${getQueue.pending}`);
    console.error(`size: ${getQueue.size}`);
    console.error(`isPaused: ${getQueue.isPaused}`);
    console.error(`inProgressUrls: ${Array.from(inProgressUrls.values())}`);
    console.error(`browserDict: ${util.inspect(browserDict)}`);
    console.error(
      `availableHeadfulBrowsers size ${availableHeadfulBrowsers.length}`
    );
    const timeEnded = Date.now();
    const minutesScraped = (timeEnded - timeStarted) / 1000 / 60;
    console.error(
      `Scraped per minute: ${_.round(numPagesScraped / minutesScraped, 3)}`
    );
  });
});
