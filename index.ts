import fs from "fs";
import { load } from "cheerio";
import mongoose from "mongoose";
import dotenv from "dotenv";
import { parseResults } from "./scraper";
import puppeteerGet from "./scrape-client";

dotenv.config();

const MONGODB_URI = process.env.MONGODB_URI;
const RESULT_OFFSET = process.env.RESULT_OFFSET || 0;
const CACHED = !!process.env.SCRAPE_CACHED;

(async () => {
  if (!MONGODB_URI) throw new Error("No MongoDB URI given.");
  await mongoose
    .connect(MONGODB_URI, {
      socketTimeoutMS: 10000,
      serverSelectionTimeoutMS: 10000,
      maxPoolSize: 2048,
    })
    .then(() => {
      console.log("Connected to MongoDB");
    })
    .catch((err) => {
      console.error("Failed to connect to MongoDB", err);
      throw err;
    });
  const initialResultUrl = !CACHED
    ? `/results?offset=${RESULT_OFFSET}`
    : "cached/results-browser.html";
  try {
    const resultsPage = !CACHED
      ? await puppeteerGet(initialResultUrl, "https://hltv.org", true)
      : fs.readFileSync("cached/results-browser.html");
    if (!fs.existsSync("cached/results-browser.html")) {
      fs.writeFile("cached/results-browser.html", resultsPage, (err) => {
        if (err) throw err;
      });
    }
    await parseResults(load(resultsPage), initialResultUrl);
  } catch (err) {
    console.log("Unable to scrape results browser: ", err);
  }
})();
