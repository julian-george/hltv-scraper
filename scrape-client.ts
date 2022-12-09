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
export const getPuppeteerClient = async () => {
  if (!browser) {
    browser = await puppeteer.launch(options);
  }
  return browser;
};

// much of this function comes from the npm package "pupflare"
const puppeteerGet = async (url: string) => {
  // await new Promise((resolve, reject) =>
  //   setTimeout(() => {
  //     resolve(true);
  //   }, Math.random() * 2000 + 1000)
  // );
  const currBrowser = await getPuppeteerClient();
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
    // page.setCookie({
    //   name: "cf_clearance",
    //   value: "mGQe6AFrg1XCiklUAfJPY9KeZMY7YbsIQwoMD.u9vUQ-1670619282-0-150",
    //   domain: ".hltv.org",
    //   path: "/",
    //   expires: 1702155282.820663,
    //   // size: 72,
    //   httpOnly: true,
    //   secure: true,
    //   // session: false,
    //   sameSite: "None",
    //   sameParty: false,
    //   sourceScheme: "Secure",
    //   sourcePort: 443,
    // });
    // page.setCookie({
    //   name: "cf_chl_2",
    //   value: "f99bfdac701c597",
    //   domain: "www.hltv.org",
    //   path: "/",
    //   expires: 1670622879,
    //   // size: 23,
    //   httpOnly: false,
    //   secure: false,
    //   // session: false,
    //   sameParty: false,
    //   sourceScheme: "Secure",
    //   sourcePort: 443,
    // });
    responseBody = await response.text();
    responseData = await response.buffer();
    // console.log(await page.cookies());
    while (responseBody.includes("challenge-running") && tryCount <= 15) {
      console.log("trying again", tryCount);
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
    // console.log("response no longer running");
    responseHeaders = await response.headers();
    // if (tryCount > 1) {
    //   console.log(responseHeaders);
    // }

    // const cookies = await page.cookies();
    // if (cookies)
    //   cookies.forEach((cookie) => {
    //     const { name, value, secure, expires, domain, ...options } = cookie;
    //     ctx.cookies.set(cookie.name, cookie.value, options);
    //   });
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
