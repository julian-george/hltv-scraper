import axios from "axios";
import fs from "fs";
import { load } from "cheerio";
import mongoose from "mongoose";
import dotenv from "dotenv";
import { parseResults } from "./scraper";

dotenv.config();

const MONGODB_URI = process.env.MONGODB_URI;

mongoose
  .connect(MONGODB_URI)
  .then(() => {
    console.log("Connected to MongoDB");
  })
  .catch((err) => {
    console.error("Failed to connect to MongoDB", err);
    throw err;
  });

axios.defaults.baseURL = "http://localhost:3000/?url=https://www.hltv.org";
axios.defaults.headers.get["accept-encoding"] = "null";

if (process.env.CACHED) {
  parseResults(load(fs.readFileSync("cached/results-browser.html")));
} else {
  axios.get("/results").then(({ data }) => {
    if (!fs.existsSync("cached/results-browser.html")) {
      fs.writeFile("cached/results-browser.html", data, (err) => {
        if (err) throw err;
      });
    }
    parseResults(load(data));
  });
}
