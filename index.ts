import axios from "axios";
import fs from "fs";
import { load } from "cheerio";
import mongoose from "mongoose";
import dotenv from "dotenv";
import express from "express";
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

if (process.env.SCRAPE_CACHED) {
  parseResults(load(fs.readFileSync("cached/results-browser.html")));
} else {
  scrapeClient(`/results?offset=${RESULT_OFFSET}`, true)
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
