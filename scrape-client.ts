import puppeteer from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";
puppeteer.use(StealthPlugin());

const headersToRemove = [
  "host",
  "user-agent",
  "accept",
  "accept-encoding",
  "content-length",
  "forwarded",
  "x-forwarded-proto",
  "x-forwarded-for",
  "x-cloud-trace-context",
];
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
// if (process.env.PUPPETEER_SKIP_CHROMIUM_DOWNLOAD)
//   options.executablePath = "/usr/bin/chromium-browser";
if (process.env.PUPPETEER_HEADFUL) options.headless = false;
// if (process.env.PUPPETEER_USERDATADIR)
//   options.userDataDir = process.env.PUPPETEER_USERDATADIR;
if (process.env.PUPPETEER_PROXY)
  options.args.push(`--proxy-server=${process.env.PUPPETEER_PROXY}`);
let browser = null;
export const getPuppeteerClient = async () => {
  if (!browser) browser = await puppeteer.launch(options);
  return browser;
};

// much of this function comes from the npm package "pupflare"
const puppeteerGet = async (url: string) => {
  await new Promise((resolve, reject) =>
    setTimeout(() => {
      resolve(true);
    }, Math.random() * 2000 + 1000)
  );
  const currBrowser = await getPuppeteerClient();
  url = BASE_URL + url;
  console.log("Scraping", url);
  let responseBody;
  let responseData;
  let responseHeaders;
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

  await client.on("Network.requestIntercepted", async (e) => {
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
    while (responseBody.includes("challenge-running") && tryCount <= 10) {
      const newResponse = await page.waitForNavigation({
        timeout: 30000,
        waitUntil: "domcontentloaded",
      });
      if (newResponse) response = newResponse;
      responseBody = await response.text();
      responseData = await response.buffer();
      tryCount++;
    }
    responseHeaders = await response.headers();
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
