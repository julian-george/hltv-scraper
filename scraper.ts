import axios from "axios";
import fs from "fs";
import dotenv from "dotenv";
import { CheerioAPI, load } from "cheerio";
import { getEventByHltvId } from "./services/event-service";
import { getPlayerByHltvId } from "./services/player-service";

dotenv.config();

const CACHED = !!process.env.CACHED;
const RESULT_LIMIT = 2;
const PLAYER_LIMIT = 2;

axios.defaults.baseURL = "https://www.hltv.org";
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

if (!CACHED) {
  axios.get("/results").then(({ data }) => {
    fs.writeFile("cached/results-browser.html", data, (err) => {
      if (err) throw err;
    });
  });
}
export const parseResults = ($: CheerioAPI) => {
  const resultLinks = $("div.result-con > a")
    .toArray()
    .slice(0, CACHED ? 1 : RESULT_LIMIT);
  for (const resultLink of resultLinks) {
    const resultUrl = resultLink.attribs["href"];
    const matchId = Number(resultUrl.split("/")[2]);
    if (CACHED) {
      parseMatch(load(fs.readFileSync("cached/result-page.html")), matchId);
    } else {
      axios.get(resultUrl).then(({ data }) => {
        if (!fs.existsSync("cached/result-page.html")) {
          fs.writeFile("cached/result-page.html", data, (err) => {
            if (err) throw err;
          });
        }
        parseMatch(load(data), matchId);
      });
    }
  }
};

export const parseMatch = async ($: CheerioAPI, matchId: number) => {
  const hltvId = matchId;
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
  console.log({ hltvId, date, format, online, matchType });

  const eventLink = $("div.event > a")[0];
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

  const statsLink = $("div.stats-detailed-stats > a")[0];
  const statsUrl = statsLink.attribs["href"];
  if (CACHED) {
    parseMatchStats(load(fs.readFileSync("cached/stats-page.html")));
  } else {
    const statsPage = (await axios.get(statsUrl)).data;
    if (!fs.existsSync("cached/stats-page.html")) {
      fs.writeFile("cached/stats-page.html", statsPage, (err) => {
        if (err) throw err;
      });
    }
    parseMatchStats(load(statsPage));
  }
};

const parseMatchStats = async ($: CheerioAPI) => {
  const mapLinks = $(".columns > .stats-match-map.inactive");
  for (const mapLink of mapLinks) {
    const mapUrl = mapLink.attribs["href"];
    const mapId = Number(mapUrl.split("/")[4]);
    if (CACHED) {
      parseMap(load(fs.readFileSync("cached/map-page.html")), mapId);
    } else {
      const mapPage = (await axios.get(mapUrl)).data;
      if (!fs.existsSync("cached/map-page.html")) {
        fs.writeFile("cached/map-page.html", mapPage, (err) => {
          if (err) throw err;
        });
      }
      parseMap(load(mapPage), mapId);
    }
  }
};

const parseMap = async ($: CheerioAPI, mapId: number) => {
  const hltvId = mapId;
  let mapType = null;
  try {
    // @ts-ignore
    mapType = $(".match-info-box")[0].childNodes[3].data.trim();
  } catch {}
  let score = null;
  try {
    const scoreContainer = $("div.bold:contains('Breakdown')").prev(
      ".right"
    )[0];
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
    if (
      Number($(scoreContainer.childNodes[0]).text()) >=
      Number($(scoreContainer.childNodes[2]).text())
    ) {
      score["teamOne"] = firstTeam;
      score["teamTwo"] = secondTeam;
    } else {
      score["teamOne"] = secondTeam;
      score["teamTwo"] = firstTeam;
    }
  } catch (err) {
    if (err) console.error(err);
  }
  const mapPerformanceLink = $(
    ".stats-top-menu-item-link:contains('Performance')"
  )[0];
  let duelMap = null;
  try {
    const mapPerformanceUrl = mapPerformanceLink.attribs["href"];
    if (CACHED) {
      duelMap = await parseMapPerformance(
        load(fs.readFileSync("cached/map-performance-page.html"))
      );
    } else {
      const mapPage = (await axios.get(mapPerformanceUrl)).data;
      if (!fs.existsSync("cached/map-performance-page.html")) {
        fs.writeFile("cached/map-performance-page.html", mapPage, (err) => {
          if (err) throw err;
        });
      }
      duelMap = await parseMapPerformance(load(mapPage));
    }
  } catch (err) {
    if (err) console.error(err);
  }
  console.log({ hltvId, mapType, score });
};

const parseMapPerformance = async ($: CheerioAPI) => {
  const firstTeamPlayerIds = $("#ALL-content > td.team1 > a")
    .toArray()
    .map((ele) => Number(ele.attribs["href"].split("/")[3]));
  console.log(firstTeamPlayerIds);
  const firstTeamDuels = {};
  const secondTeamDuels = {};
  return {};
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
  console.log({
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
  console.log({ hltvId, name, birthYear, nationality });
};
