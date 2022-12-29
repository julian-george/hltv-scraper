import puppeteer from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
import dotenv from "dotenv";
import { Browser } from "puppeteer";

puppeteer.use(StealthPlugin());
dotenv.config();

const responseHeadersToRemove = [
  "Accept-Ranges",
  "Content-Length",
  "Keep-Alive",
  "Connection",
  "content-encoding",
  "set-cookie",
];

const BASE_URL = "https://www.hltv.org";
let options = {
  headless: true,
  args: ["--no-sandbox", "--disable-setuid-sandbox"],
};
if (process.env.HEADFUL) options.headless = false;
let browser: Browser | null = null;
let headfulBrowser: Browser | null = null;
export const getPuppeteerClient = async (headful: boolean = false) => {
  if (!headful) {
    if (!browser) {
      try {
        browser = await puppeteer.launch(options);
      } catch (err) {
        console.error("Error while getting headless client", err);
        return null;
      }
    }
    return browser;
  } else {
    if (!headfulBrowser) {
      try {
        headfulBrowser = await puppeteer.launch({
          ...options,
          headless: false,
        });
      } catch (err) {
        console.error("Error while getting headful client", err);
        return null;
      }
    }
    return headfulBrowser;
  }
};

// much of this function comes from the npm package "pupflare"
const puppeteerGet = async (url: string, headful?: boolean) => {
  // await new Promise((resolve, reject) =>
  //   setTimeout(() => {
  //     resolve(true);
  //   }, Math.random() * 2000 + 1000)
  // );
  if (process.env.FORCE_HEADLESS) headful = false;
  const currBrowser = await getPuppeteerClient(headful);
  if (!currBrowser) return;
  url = BASE_URL + url;
  console.log("Scraping", url);
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

    response = await page.goto(url, {
      timeout: 30000,
      waitUntil: "domcontentloaded",
    });

    responseBody = await response.text();
    responseData = await response.buffer();
    while (responseBody.includes("challenge-running") && tryCount <= 15) {
      const newResponse = await page.waitForNavigation({
        timeout: 0,
        waitUntil: "domcontentloaded",
      });
      if (newResponse) response = newResponse;
      responseBody = await response.text();
      responseData = await response.buffer();
      responseUrl = await response.url();
      tryCount++;
      await page.screenshot({ path: "cf.png", fullPage: true });
    }
    if (tryCount > 0) console.log(`Beat challenge after ${tryCount} tries`);
    responseHeaders = await response.headers();
  } catch (error) {
    console.error(error);
    if (!error.toString().includes("ERR_BLOCKED_BY_CLIENT")) {
      console.error("Error sending request: ", error);
    }
  }

  await page.close();
  responseHeadersToRemove.forEach((header) => delete responseHeaders[header]);
  return responseBody;
};

export default puppeteerGet;
