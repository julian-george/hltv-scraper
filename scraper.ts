import axios from "axios";
import fs from "fs";
import dotenv from "dotenv";
import { CheerioAPI, load } from "cheerio";
import { createEvent, getEventByHltvId } from "./services/event-service";
import { createPlayer, getPlayerByHltvId } from "./services/player-service";
import { createMap, getMapByHltvId } from "./services/map-service";
import { createMatch, getMatchByHltvId } from "./services/match-service";

dotenv.config();

const CACHED = !!process.env.CACHED;
const RESULT_LIMIT = 2;
const PLAYER_LIMIT = 2;

axios.defaults.baseURL = "http://localhost:3000/?url=https://www.hltv.org";
axios.defaults.headers.get["accept-encoding"] = "null";
axios.interceptors.request.use(
  async (config) => {
    return new Promise((resolve, reject) =>
      setTimeout(() => {
        resolve(config);
      }, Math.random() * 1000 + 4000)
    );
  },
  async (error) => {
    // Do something with request error
    return Promise.reject(error);
  }
);

export const parseMatch = async ($: CheerioAPI, matchId: number) => {
  const hltvId = matchId;
  let title = null;
  try {
    title =
      $(".team1-gradient > a > .teamName").text() +
      " vs. " +
      $(".team2-gradient > a > .teamName").text();
  } catch {}
  let date = null;
  try {
    date = new Date(Number($(".timeAndEvent > .time")[0].attribs["data-unix"]));
  } catch {}
  let format = null;
  try {
    format = $($("div.preformatted-text")[0]).text().split("\n")[0];
  } catch {}
  let matchType = null;
  try {
    matchType = $($("div.preformatted-text")[0]).text().split("* ")[1];
  } catch {}
  let online = null;
  try {
    online = format?.includes("Online");
  } catch {}

  const eventLink = $("div.event > a")[0];
  if (!eventLink) throw new Error("No event link");
  const eventUrl = eventLink.attribs["href"];
  const eventId = Number(eventUrl.split("/")[2]);
  const event = await getEventByHltvId(eventId);
  if (!event) {
    if (CACHED) {
      await parseEvent(
        load(fs.readFileSync("cached/event-page.html")),
        eventId
      );
    } else {
      const eventPage = (await axios.get(eventUrl)).data;
      if (!fs.existsSync("cached/event-page.html")) {
        fs.writeFile("cached/event-page.html", eventPage, (err) => {
          if (err) throw err;
        });
      }
      await parseEvent(load(eventPage), eventId);
    }
  }
  await createMatch({ hltvId, eventId, date, format, online, matchType });

  const playerLinks = $("td.players > .flagAlign > a")
    .toArray()
    .slice(0, CACHED ? 1 : PLAYER_LIMIT);
  for (const playerLink of playerLinks) {
    const playerUrl = playerLink.attribs["href"];
    const playerId = Number(playerUrl.split("/")[2]);
    const player = await getPlayerByHltvId(playerId);
    if (!player) {
      if (CACHED) {
        await parsePlayer(
          load(fs.readFileSync("cached/player-page.html")),
          playerId
        );
      } else {
        const playerPage = (await axios.get(playerUrl)).data;
        if (!fs.existsSync("cached/player-page.html")) {
          fs.writeFile("cached/player-page.html", playerPage, (err) => {
            if (err) throw err;
          });
        }
        await parsePlayer(load(playerPage), playerId);
      }
    }
  }
  const mapLinks = $(
    "div.mapholder > div > div.results-center > div.results-center-stats > a"
  ).toArray();
  if (mapLinks.length == 0) throw new Error("No map stats");
  for (const mapLink of mapLinks) {
    const mapUrl = mapLink.attribs["href"];
    const mapId = Number(mapUrl.split("/")[4]);
    const map = await getMapByHltvId(mapId);
    if (map) {
      console.log("Map ID " + mapId + " already in database, skipping.");
      continue;
    }
    if (CACHED) {
      parseMap(load(fs.readFileSync("cached/map-page.html")), mapId, matchId);
    } else {
      const mapPage = (await axios.get(mapUrl)).data;
      if (!fs.existsSync("cached/map-page.html")) {
        fs.writeFile("cached/map-page.html", mapPage, (err) => {
          if (err) throw err;
        });
      }
      parseMap(load(mapPage), mapId, matchId);
    }
  }
};

const parseMap = async ($: CheerioAPI, mapId: number, matchId: number) => {
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
  const firstWon =
    Number($(scoreContainer.childNodes[0]).text()) >=
    Number($(scoreContainer.childNodes[2]).text());
  if (firstWon) {
    score["teamOne"] = firstTeam;
    score["teamTwo"] = secondTeam;
  } else {
    score["teamOne"] = secondTeam;
    score["teamTwo"] = firstTeam;
  }
  const mapPerformanceLink = $(
    ".stats-top-menu-item-link:contains('Performance')"
  )[0];
  if (!mapPerformanceLink)
    throw new Error("No map performance link for map ID " + mapId);
  let firstTeamStats = null;
  let secondTeamStats = null;
  const mapPerformanceUrl = mapPerformanceLink.attribs["href"];
  if (CACHED) {
    ({ firstTeamStats, secondTeamStats } = await parseMapPerformance(
      load(fs.readFileSync("cached/map-performance-page.html"))
    ));
  } else {
    const mapPage = (await axios.get(mapPerformanceUrl)).data;
    if (!fs.existsSync("cached/map-performance-page.html")) {
      fs.writeFile("cached/map-performance-page.html", mapPage, (err) => {
        if (err) throw err;
      });
    }
    ({ firstTeamStats, secondTeamStats } = await parseMapPerformance(
      load(mapPage)
    ));
  }
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
      kast: Number(currRow.find(".st-kdratio").text().replace("%", "")) * 0.01,
      adr: Number(currRow.find(".st-adr").text()),
      fkDiff: Number(
        currRow
          .find(".st-fkdiff")
          .text()
          .replace(/[^0-9\.-]+/g, "")
      ),
      rating: Number(currRow.find(".st-rating").text()),
    };
    if (playerId in firstTeamStats) {
      firstTeamStats[playerId][statAttr] = statObj;
    } else if (playerId in secondTeamStats) {
      secondTeamStats[playerId][statAttr] = statObj;
    }
  }
  const teamOneStats = [];
  const teamTwoStats = [];
  for (const hltvId of Object.keys(firstTeamStats)) {
    (firstWon ? teamOneStats : teamTwoStats).push({
      ...firstTeamStats[hltvId],
      hltvId,
    });
  }
  for (const hltvId of Object.keys(secondTeamStats)) {
    (firstWon ? teamTwoStats : teamOneStats).push({
      ...secondTeamStats[hltvId],
      hltvId,
    });
  }
  await createMap({
    hltvId: Number(hltvId),
    matchId,
    mapType,
    score,
    teamOneStats,
    teamTwoStats,
  });
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
      (indexInTable - firstTeamIndex) / secondTeamPlayerIds.length;
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

const parseEvent = async ($: CheerioAPI, eventId: number) => {
  const hltvId = eventId;
  let title = null;
  try {
    title = $(".event-hub-title").text();
  } catch {}
  let startDate = null;
  try {
    startDate = new Date(
      Number(
        $(".eventMeta > tbody > tr > th:contains('Start date')")
          .next("td")
          .children("span")[0].attribs["data-unix"]
      )
    );
  } catch {}
  let endDate = null;
  try {
    endDate = new Date(
      Number(
        $(".eventMeta > tbody > tr > th:contains('End date')")
          .next("td")
          .find("span > span")[0].attribs["data-unix"]
      )
    );
  } catch {}
  let teamNum = null;
  try {
    teamNum = Number(
      $(".eventMeta > tbody > tr > th:contains('Teams')")
        .next("td")[0]
        .attribs["title"].replace(/[^0-9\.-]+/g, "")
    );
  } catch {}
  let prizePool = null;
  try {
    prizePool = Number(
      $(".eventMeta > tbody > tr > th:contains('Prize pool')")
        .next("td")[0]
        .attribs["title"].replace(/[^0-9\.-]+/g, "")
    );
  } catch {}
  let location = null;
  let online = null;
  try {
    location = $(".eventMeta > tbody > tr > th:contains('Location')").next(
      "td"
    )[0].attribs["title"];
    online = location.includes("Online");
  } catch {}
  let format = null;
  try {
    format = $(".formats > tbody")
      .children("tr")
      .toArray()
      .reduce((prevObj, currTr) => {
        return {
          ...prevObj,
          [$($(currTr).children("th")[0]).text()]: $(
            $(currTr).children("td")[0]
          )
            .text()
            .replace("\n", " "),
        };
      }, {});
  } catch {}
  let teamRankings = null;
  try {
    teamRankings = $("div.event-world-rank")
      .toArray()
      .map((ele) => Number($(ele).text().replace("#", "")));
    for (let i = teamRankings.length; i < teamNum || 0; i++) {
      teamRankings.push(null);
    }
  } catch {}
  await createEvent({
    hltvId,
    title,
    startDate,
    endDate,
    teamNum,
    prizePool,
    location,
    online,
    format,
    teamRankings,
  });
};

const parsePlayer = async ($: CheerioAPI, playerId: number) => {
  const hltvId = playerId;
  let name = null;
  try {
    name = $($(".playerNickname")[0]).text();
    if (name == "") name = $($(".player-nick")[0]).text();
    if (name == "") name = null;
  } catch (err) {
    console.error("Error extracting player name", err);
  }
  let birthYear = null;
  try {
    const currentYear = new Date().getFullYear();
    let currentAge = $($(".playerAge > .listRight > span")[0]).text();
    if (currentAge == "")
      currentAge = $("b:contains('Age')").next("span").text();
    birthYear =
      currentAge != ""
        ? currentYear - Number(currentAge.replace(/[^0-9\.-]+/g, ""))
        : null;
  } catch {}
  let nationality = null;
  try {
    nationality = $($(".playerRealname > .flag")[0]).attr("title");
    if (!nationality)
      nationality = $($(".player-realname > .flag")[0]).attr("title");
  } catch {}
  await createPlayer({ hltvId, name, birthYear, nationality });
};

export const parseResults = ($: CheerioAPI) => {
  const resultLinks = $("div.result-con > a")
    .toArray()
    .slice(0, CACHED ? 1 : RESULT_LIMIT);
  for (const resultLink of resultLinks) {
    const resultUrl = resultLink.attribs["href"];
    const matchId = Number(resultUrl.split("/")[2]);
    const match = getMatchByHltvId(matchId);
    if (match) {
      console.log("Match ID " + matchId + " already in database, skipping.");
      continue;
    }
    if (CACHED) {
      parseMatch(
        load(fs.readFileSync("cached/result-page.html")),
        matchId
      ).catch((err) => {
        console.log("Unable to parse match ID " + matchId + ", skipping it.");
      });
    } else {
      axios.get(resultUrl).then(async ({ data }) => {
        if (!fs.existsSync("cached/result-page.html")) {
          fs.writeFile("cached/result-page.html", data, (err) => {
            if (err) throw err;
          });
        }
        parseMatch(load(data), matchId).catch((err) => {
          console.log(
            "Unable to parse match ID " +
              matchId +
              ", reason: '" +
              err +
              "', skipping it."
          );
        });
      });
    }
  }
};
