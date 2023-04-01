import fs, { fchmod } from "fs";
import { load } from "cheerio";
import mongoose from "mongoose";
// mongoose.set("debug", true);
import dotenv from "dotenv";
import { parseResults, parseMatches } from "./scraper.js";
import puppeteerGet from "./scrape-client.js";

dotenv.config();

const MONGODB_URI = process.env.MONGODB_URI;
const RESULT_OFFSET = process.env.RESULT_OFFSET || 0;
const CACHED = !!process.env.SCRAPE_CACHED;

let connection;

process.on("SIGINT", () => {
  console.log("Disconnecting Mongoose...");
  mongoose.disconnect();
});

(async () => {
  if (!MONGODB_URI) throw new Error("No MongoDB URI given.");
  try {
    connection = await mongoose.connect(MONGODB_URI, {
      keepAlive: true,
      socketTimeoutMS: 10000,
      serverSelectionTimeoutMS: 10000,
      maxPoolSize: 2048,
    });
    console.log("Connected to MongoDB");
  } catch (err) {
    console.error("Failed to connect to MongoDB", err);
    throw err;
  }
  const initialRefererUrl = "https://hltv.org";
  const initialMatchesUrl = `/matches`;
  const cachedMatchesPath = "cached/matches-browser.html";
  try {
    const matchesPage = !CACHED
      ? await puppeteerGet(initialMatchesUrl, initialRefererUrl, true)
      : fs.readFileSync(cachedMatchesPath);
    if (!fs.existsSync(cachedMatchesPath)) {
      fs.writeFile(cachedMatchesPath, matchesPage, (err) => {
        if (err) throw err;
      });
    }
    await parseMatches(load(matchesPage), initialMatchesUrl);
  } catch (err) {
    console.error("Unable to scrape matches browser");
  }
  const initialResultUrl = `/results?offset=${RESULT_OFFSET}`;
  const cachedResultsPath = "cached/results-browser.html";
  try {
    const resultsPage = !CACHED
      ? await puppeteerGet(initialResultUrl, initialRefererUrl, true)
      : fs.readFileSync(cachedResultsPath);
    if (!fs.existsSync(cachedResultsPath)) {
      fs.writeFile(cachedResultsPath, resultsPage, (err) => {
        if (err) throw err;
      });
    }
    await parseResults(load(resultsPage), initialResultUrl);
  } catch (err) {
    console.error("Unable to scrape results browser: ", err);
  }
  console.log("Done scraping, ending now.");
  process.exit(0);
})();
