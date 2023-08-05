import fs from "fs";
import { CheerioAPI, load } from "cheerio";
import config from "config";
import { getMatchByHltvId } from "./services/match-service.js";
import { getUnplayedMatchByHltvId } from "./services/unplayedmatch-service.js";
import puppeteerGet from "./scrape-client.js";
import { parseMatch } from "./parsers/match-parser.js";
import { ifMapExists } from "./services/map-service.js";

// If true, scrapes cached pages saved in ../cached
const CACHED = config.get("scrapeCached");

// If true, stops adding new matches to queue once already-traversed one is reached
const FINISH_UPON_DUPLICATE = config.get("results.finishUponDuplicate");
// If true, traverses already added matches to get any submodels that could have had errors
const TRAVERSE_ADDED_MATCHES = config.get("results.traverseAdded");

// If true, rescrapes match pages and updates DB accordingly
const OVERWRITE_RESULTS_MATCHES = config.get("results.overwriteMatches");

// Practically deprecated, maybe useful for testing
const RESULT_LIMIT = Infinity;

export const scrapeResults = async ($: CheerioAPI, resultsUrl: string) => {
  let finished = false;
  const resultLinks = $("div.allres")
    .find("div.result-con > a")
    .toArray()
    .slice(0, CACHED ? 1 : RESULT_LIMIT);
  const resultExecutors: (() => Promise<boolean>)[] = [];
  for (const resultLink of resultLinks) {
    const resultUrl = resultLink.attribs["href"];
    const matchId = Number(resultUrl.split("/")[2]);
    const match = await getMatchByHltvId(matchId);
    if (!CACHED && match) {
      if (FINISH_UPON_DUPLICATE) {
        finished = true;
      }
      if (!TRAVERSE_ADDED_MATCHES) {
        console.log(
          `Match ID ` +
            matchId +
            ` already in database, ${
              FINISH_UPON_DUPLICATE ? "finishing" : "skipping"
            }.`
        );
        continue;
      }
    }
    const resultExecutor = async () => {
      const resultPage = !CACHED
        ? await puppeteerGet(resultUrl, resultsUrl)
        : fs.readFileSync("cached/result-page.html");
      if (!fs.existsSync("cached/result-page.html")) {
        fs.writeFile("cached/result-page.html", resultPage, (err) => {
          if (err) throw err;
        });
      }
      if (resultPage)
        await parseMatch(load(resultPage), matchId, resultUrl).catch((err) => {
          console.error(
            "Error while parsing match ID " +
              matchId +
              ", reason: '" +
              err +
              "'."
          );
        });
      return true;
    };
    resultExecutors.push(resultExecutor);
  }
  if (!CACHED) {
    const nextUrl = $("a.pagination-next").attr("href");
    if (!nextUrl) finished = true;
    if (finished) {
      console.log("Finishing now.");
    } else {
      puppeteerGet(nextUrl, resultsUrl, true).then((nextResultsPage) => {
        if (!nextResultsPage)
          console.error("Unable to find next results page.");
        else {
          scrapeResults(load(nextResultsPage), nextUrl);
        }
      });
    }
  }
  const resultStart = Date.now();
  // For debug: if you ever want to test matches sequentially
  for (const executor of resultExecutors) {
    await executor();
  }
  // const resultPromises = resultExecutors.map((executor) => executor());
  // await Promise.all(resultPromises);
  const resultEnd = Date.now();
  const resultElapsed = Math.round((resultEnd - resultStart) / 10) / 100;
  console.log(
    `Page of results url ${resultsUrl} took ${resultElapsed} seconds!`
  );
};

// This determines how many days in the future (including today) that matches will be pulled from. undefined for no limit
const DAYS_TO_SCRAPE = config.get("unplayedMatches.daysToScrape");
const OVERWRITE_UNPLAYED_MATCHES = config.get("unplayedMatches.overwrite");

export const scrapeMatches = async ($: CheerioAPI, matchesUrl: string) => {
  const matchExecutors: (() => Promise<boolean>)[] = [];
  const matchSections = $("div.upcomingMatchesSection").slice(
    0,
    DAYS_TO_SCRAPE
  );
  let matchLinks = $("div.liveMatch > a.match").toArray();
  for (const section of matchSections) {
    matchLinks = [
      ...matchLinks,
      ...$(section)
        .find("div.upcomingMatch > a.match")
        .toArray()
        .filter(
          (matchEle) =>
            $(matchEle).find("div.matchTeamLogoContainer").length == 2
        ),
    ];
  }
  for (const matchLink of matchLinks) {
    const matchUrl = matchLink.attribs["href"];
    const matchId = Number(matchUrl.split("/")[2]);
    if (!OVERWRITE_UNPLAYED_MATCHES) {
      const match = await getUnplayedMatchByHltvId(matchId);
      if (match) {
        console.log(
          "Unplayed match ID " + matchId + " already in database, skipping."
        );
        continue;
      }
    }
    const matchExecutor = async () => {
      const matchPage = !CACHED
        ? await puppeteerGet(matchUrl, matchesUrl)
        : fs.readFileSync("cached/match-page.html");
      if (!fs.existsSync("cached/match-page.html")) {
        fs.writeFile("cached/match-page.html", matchPage, (err) => {
          if (err) throw err;
        });
      }
      if (matchPage)
        await parseMatch(load(matchPage), matchId, matchUrl, false).catch(
          (err) => {
            console.error(
              "Error while parsing match ID " +
                matchId +
                ", reason: '" +
                err +
                "'."
            );
          }
        );
      return true;
    };
    matchExecutors.push(matchExecutor);
  }
  const matchStart = Date.now();
  // For debug: if you ever want to test matches sequentially
  // for (const executor of resultExecutors) {
  //   await executor();
  // }
  const matchPromises = matchExecutors.map((executor) => executor());
  await Promise.all(matchPromises);
  const matchEnd = Date.now();
  const matchElapsed = Math.round((matchEnd - matchStart) / 10) / 100;
  console.log(`New matches took ${matchElapsed} seconds!`);
};
