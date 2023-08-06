import { CheerioAPI, load } from "cheerio";
import config from "config";
import fs from "fs";
import puppeteerGet from "../scrape-client.js";
import { createMap } from "../services/map-service.js";
import _ from "lodash";

const CACHED = config.get("scrapeCached");

const parseMap = async (
  $: CheerioAPI,
  mapId: number,
  matchId: number,
  rankings: { firstTeam: number | null; secondTeam: number | null },
  mapUrl: string,
  pickedBy: string,
  mapNum: number,
  date: Date
) => {
  const hltvId = mapId;
  let mapType = null;
  try {
    // @ts-ignore
    mapType = $(".match-info-box")[0].childNodes[3].data.trim();
  } catch {}
  let score = null;
  const scoreContainer = $("div.bold:contains('Breakdown')").prev(".right")[0];
  const firstTeam = {};
  const secondTeam = {};
  for (let i = 0; i < scoreContainer.childNodes.length; i++) {
    const childElement = $(scoreContainer.childNodes[i]);
    const isFirstTeam = ((i - 4) / 2) % 2 == 0;
    const childNum = Number(childElement.text());
    if (childElement.hasClass("t-color")) {
      if (isFirstTeam) firstTeam["t"] = childNum;
      else secondTeam["t"] = childNum;
    } else if (childElement.hasClass("ct-color")) {
      if (isFirstTeam) firstTeam["ct"] = childNum;
      else secondTeam["ct"] = childNum;
    } else {
      const dividedText = childElement.text().split(":");
      if (dividedText.length == 2) {
        firstTeam["ot"] = Number(dividedText[0].replace(/[^0-9\.-]+/g, ""));
        secondTeam["ot"] = Number(dividedText[1].replace(/[^0-9\.-]+/g, ""));
      }
    }
  }
  score = {};
  let teamOneRanking = null;
  let teamTwoRanking = null;
  let teamOneStats = null;
  let teamTwoStats = null;
  let players = null;
  const firstWon =
    Number($(scoreContainer.childNodes[0]).text()) >=
    Number($(scoreContainer.childNodes[2]).text());
  if (firstWon) {
    score["teamOne"] = firstTeam;
    score["teamTwo"] = secondTeam;
    teamOneRanking = rankings.firstTeam;
    teamTwoRanking = rankings.secondTeam;
    if (pickedBy == "firstTeam") {
      pickedBy = "teamOne";
    } else if (pickedBy == "secondTeam") {
      pickedBy = "teamTwo";
    }
  } else {
    score["teamOne"] = secondTeam;
    score["teamTwo"] = firstTeam;
    teamOneRanking = rankings.secondTeam;
    teamTwoRanking = rankings.firstTeam;
    if (pickedBy == "firstTeam") {
      pickedBy = "teamTwo";
    } else if (pickedBy == "secondTeam") {
      pickedBy = "teamOne";
    }
  }
  // const mapPerformanceLink = $(
  //   ".stats-top-menu-item-link:contains('Performance')"
  // )[0];
  // if (!mapPerformanceLink) {
  //   console.log("No map performance link for map ID " + mapId);
  //   return null;
  // } else {
  let firstTeamStats = null;
  let secondTeamStats = null;
  // const mapPerformanceUrl = mapPerformanceLink.attribs["href"];
  // const mapPerformancePage = !CACHED
  //   ? await puppeteerGet(mapPerformanceUrl, mapUrl, true)
  //   : fs.readFileSync("cached/map-performance-page.html");
  // if (!fs.existsSync("cached/map-performance-page.html")) {
  //   fs.writeFile(
  //     "cached/map-performance-page.html",
  //     mapPerformancePage,
  //     (err) => {
  //       if (err) throw err;
  //     }
  //   );
  // }
  // if (!mapPerformancePage) {
  //   console.log("No map performance page found for map ID: " + mapId);
  // } else {
  // ({ firstTeamStats, secondTeamStats } = await parseMapPerformance(
  //   load(mapPerformancePage)
  // ));
  firstTeamStats = {};
  secondTeamStats = {};
  players = Object.keys(firstTeamStats).concat(Object.keys(secondTeamStats));
  const tStatRows = $("table.tstats > tbody > tr").toArray();
  const ctStatRows = $("table.ctstats > tbody > tr").toArray();
  const allRows = [...tStatRows, ...ctStatRows];
  for (let i = 0; i < allRows.length; i++) {
    const statAttr = i < tStatRows.length ? "tStats" : "ctStats";
    const currRow = $(allRows[i]);
    const playerId = currRow
      .find("td > div.flag-align > a")[0]
      .attribs["href"].split("/")[3]
      .toString();
    const statObj = {
      //@ts-ignore
      kills: Number(currRow.find(".st-kills")[0].childNodes[0].data),
      hsKills: Number(
        currRow
          .find(".st-kills > span")
          .text()
          .replace(/[^0-9\.-]+/g, "")
      ),
      // @ts-ignore
      assists: Number(currRow.find(".st-assists")[0].childNodes[0].data),
      flashAssists: Number(
        currRow
          .find(".st-assists > span")
          .text()
          .replace(/[^0-9\.-]+/g, "")
      ),
      deaths: Number(currRow.find(".st-deaths").text()),
      kast:
        Math.round(
          Number(currRow.find(".st-kdratio").text().replace("%", "")) * 10
        ) / 1000 || 0,
      adr: Number(currRow.find(".st-adr").text()) || 0,
      fkDiff: Number(
        currRow
          .find(".st-fkdiff")
          .text()
          .replace(/[^0-9\.-]+/g, "")
      ),
      rating: Number(currRow.find(".st-rating").text()),
    };
    if (isNaN(statObj.rating)) {
      throw new Error("NaN value in player statObj");
    }
    if (playerId in firstTeamStats) {
      firstTeamStats[playerId][statAttr] = statObj;
    } else if (playerId in secondTeamStats) {
      secondTeamStats[playerId][statAttr] = statObj;
    }
    // }
    teamOneStats = {};
    teamTwoStats = {};
    if (firstWon) {
      teamOneStats = firstTeamStats;
      teamTwoStats = secondTeamStats;
    } else {
      teamOneStats = secondTeamStats;
      teamTwoStats = firstTeamStats;
    }
  }
  // }
  if (
    _.isEmpty(players) ||
    _.isEmpty(teamOneStats) ||
    _.isEmpty(teamTwoStats)
  ) {
    throw new Error("Empty stats or players for map ID " + hltvId);
  }
  const newMap = {
    hltvId: Number(hltvId),
    matchId,
    mapType,
    score,
    teamOneRanking,
    teamTwoRanking,
    teamOneStats,
    teamTwoStats,
    players,
    pickedBy,
    mapNum,
    date,
  };
  if (!CACHED) {
    try {
      return await createMap(newMap);
    } catch (err) {
      throw new Error("Unable to add map ID " + hltvId + " to database: ", err);
    }
  } else {
    console.log("New map", newMap);
  }
};

const parseMapPerformance = async ($: CheerioAPI) => {
  const firstTeamPlayerIds = $("#ALL-content")
    .find("td.team1 > a")
    .toArray()
    .map((ele) => Number(ele.attribs["href"].split("/")[3]));
  const secondTeamPlayerIds = $("#ALL-content")
    .find("td.team2 > a")
    .toArray()
    .map((ele) => Number(ele.attribs["href"].split("/")[3]));
  const firstTeamKills = $(".team1-player-score")
    .toArray()
    .map((ele) => $(ele).text());
  const secondTeamKills = $(".team2-player-score")
    .toArray()
    .map((ele) => $(ele).text());
  const firstTeamDuels = {};
  const secondTeamDuels = {};
  const tableSize = firstTeamPlayerIds.length * secondTeamPlayerIds.length;
  for (let i = 0; i < firstTeamKills.length; i++) {
    const indexInTable = i % tableSize;
    const firstTeamIndex = indexInTable % firstTeamPlayerIds.length;
    const secondTeamIndex =
      (indexInTable - firstTeamIndex) / firstTeamPlayerIds.length;
    if (i < tableSize) {
      if (firstTeamIndex == 0)
        secondTeamDuels[secondTeamPlayerIds[secondTeamIndex]] = {
          duelMap: {
            all: {},
            firstKill: {},
            awp: {},
          },
        };
      if (secondTeamIndex == 0)
        firstTeamDuels[firstTeamPlayerIds[firstTeamIndex]] = {
          duelMap: {
            all: {},
            firstKill: {},
            awp: {},
          },
        };
    }
    const duelAttr =
      i < tableSize ? "all" : i < tableSize * 2 ? "firstKill" : "awp";
    firstTeamDuels[firstTeamPlayerIds[firstTeamIndex]]["duelMap"][duelAttr][
      secondTeamPlayerIds[secondTeamIndex]
    ] = firstTeamKills[i];
    secondTeamDuels[secondTeamPlayerIds[secondTeamIndex]]["duelMap"][duelAttr][
      firstTeamPlayerIds[firstTeamIndex]
    ] = secondTeamKills[i];
  }
  return { firstTeamStats: firstTeamDuels, secondTeamStats: secondTeamDuels };
};

export default parseMap;
