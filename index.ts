import axios from "axios";
import fs from "fs";
import { load } from "cheerio";
import mongoose from "mongoose";
import dotenv from "dotenv";
import { parseResults } from "./scraper";
import scrapeClient from "./scrape-client";

dotenv.config();

const MONGODB_URI = process.env.MONGODB_URI;
const RESULT_OFFSET = process.env.RESULT_OFFSET || 0;

mongoose
  .connect(MONGODB_URI)
  .then(() => {
    console.log("Connected to MongoDB");
  })
  .catch((err) => {
    console.error("Failed to connect to MongoDB", err);
    throw err;
  });

if (process.env.DISABLE_SCRAPING) {
  const idlePromise = new Promise(async (resolve, reject) => {
    console.log("Scraping disabled");
    setTimeout(() => {
      resolve(true);
    }, 1000000000);
  });
  idlePromise.then(() => {
    console.log("Byebye");
  });
} else {
  if (process.env.SCRAPE_CACHED) {
    parseResults(load(fs.readFileSync("cached/results-browser.html")));
  } else {
    scrapeClient(`/results?offset=${RESULT_OFFSET}`)
      .then((resultsPage) => {
        if (!fs.existsSync("cached/results-browser.html")) {
          fs.writeFile("cached/results-browser.html", resultsPage, (err) => {
            if (err) throw err;
          });
        }
        parseResults(load(resultsPage));
      })
      .catch((err) => {
        console.error(err.message);
      });
  }
}
