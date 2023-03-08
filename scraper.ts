import fs from "fs";
import dotenv from "dotenv";
import { CheerioAPI, load } from "cheerio";
import { createEvent, getEventByHltvId } from "./services/event-service";
import { createPlayer, getPlayerByHltvId } from "./services/player-service";
import { createMap, getMapByHltvId } from "./services/map-service";
import { createMatch, getMatchByHltvId } from "./services/match-service";
import puppeteerGet from "./scrape-client";

dotenv.config();

// If true, scrapes cached pages saved in ../cached
const CACHED = !!process.env.SCRAPE_CACHED;
// If true, stops adding new matches to queue once already-traversed one is reached
const ABORT_UPON_DUPLICATE = process?.env?.ABORT_UPON_DUPLICATE || 0;
// If true, traverses already added matches to get any submodels that could have had errors
const TRAVERSE_ADDED_MATCHES = process?.env?.TRAVERSE_ADDED_MATCHES || 0;

// Practically deprecated, maybe useful for testing
const RESULT_LIMIT = Infinity;
const PLAYER_LIMIT = Infinity;

export const parseMatch = async (
  $: CheerioAPI,
  matchId: number,
  matchUrl: string
) => {
  const componentExecutors: (() => Promise<boolean>)[] = [];
  // const startTime = Date.now();
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
  let eventId = null;
  if (!eventLink) {
    console.error("No event link");
  } else {
    const eventUrl = eventLink.attribs["href"];
    eventId = Number(eventUrl.split("/")[2]);
    const event = await getEventByHltvId(eventId);
    if (!event) {
      const eventExecutor = async () => {
        const eventPage = !CACHED
          ? await puppeteerGet(eventUrl, matchUrl)
          : fs.readFileSync("cached/event-page.html");
        if (!fs.existsSync("cached/event-page.html")) {
          fs.writeFile("cached/event-page.html", eventPage, (err) => {
            if (err) throw err;
          });
        }
        if (eventPage) await parseEvent(load(eventPage), eventId);
        return true;
      };
      componentExecutors.push(eventExecutor);
    }
  }

  const playerLinks = $("div#all-content > table.totalstats")
    .find("td.players > div.flagAlign > a")
    .toArray()
    .slice(0, CACHED ? 1 : PLAYER_LIMIT);
  // const plfayersStartTime = Date.now();
  for (const playerLink of playerLinks) {
    const playerUrl = playerLink.attribs["href"];
    const playerId = Number(playerUrl.split("/")[2]);
    const playerExecutor = async () => {
      const player = await getPlayerByHltvId(playerId);
      if (player) {
        // console.log(
        //   "Player ID " + playerId + " already in database, skipping."
        // );
        return true;
      }
      const playerPage = !CACHED
        ? await puppeteerGet(playerUrl, matchUrl)
        : fs.readFileSync("cached/player-page.html");
      if (!fs.existsSync("cached/player-page.html")) {
        fs.writeFile("cached/player-page.html", playerPage, (err) => {
          if (err) throw err;
        });
      }
      if (playerPage) await parsePlayer(load(playerPage), playerId);
      return true;
    };
    componentExecutors.push(playerExecutor);
  }
  const rankings = {
    firstTeam:
      Number(
        $($("div.teamRanking > a")[0])
          .text()
          .replace(/[^0-9\.-]+/g, "")
      ) || null,
    secondTeam:
      Number(
        $($("div.teamRanking > a")[1])
          .text()
          .replace(/[^0-9\.-]+/g, "")
      ) || null,
  };
  let mapLinks = $(
    "div.mapholder > div > div.results-center > div.results-center-stats > a"
  ).toArray();
  const handleMaps = async (links, referUrl: string): Promise<boolean> => {
    const mapPromises: Promise<boolean>[] = [];
    for (const mapLink of links) {
      mapPromises.push(
        new Promise(async (resolve, reject) => {
          const mapUrl = mapLink.attribs["href"];
          const mapId = Number(mapUrl.split("/")[4]);
          const map = await getMapByHltvId(mapId);
          if (map) {
            console.log("Map ID " + mapId + " already in database, skipping.");
            resolve(true);
            return true;
          }
          const mapPage = !CACHED
            ? await puppeteerGet(mapUrl, referUrl)
            : fs.readFileSync("cached/map-page.html");
          if (!fs.existsSync("cached/map-page.html")) {
            fs.writeFile("cached/map-page.html", mapPage, (err) => {
              if (err) throw err;
            });
          }
          if (mapPage)
            parseMap(load(mapPage), mapId, matchId, rankings, mapUrl)
              .catch((err) => {
                console.error(
                  "Error while parsing map ID " +
                    mapId +
                    ", reason: '" +
                    err +
                    "'."
                );
              })
              .finally(() => {
                resolve(true);
              });
          // resolve(true);
        })
      );
    }
    return Promise.all(mapPromises)
      .then(() => {
        return true;
      })
      .catch(() => {
        return false;
      });
  };
  if (mapLinks.length == 0) {
    // fallback method of getting map stats, since some pages' map stats can only be accessed w/ the "Detailed Stats" button
    const statsLink = $("div.stats-detailed-stats > a")[0];
    if (statsLink) {
      const statsUrl = statsLink.attribs["href"];
      if (statsUrl.includes("mapstatsid")) {
        mapLinks = [statsLink];
      } else {
        const statsExecutor = async () => {
          const statsPage = !CACHED
            ? await puppeteerGet(statsUrl, matchUrl)
            : fs.readFileSync("cached/stats-page.html");
          if (!fs.existsSync("cached/stats-page.html")) {
            fs.writeFile("cached/stats-page.html", statsPage, (err) => {
              if (err) throw err;
            });
          }
          if (statsPage) {
            try {
              const links = await parseMatchStats(load(statsPage));
              await handleMaps(links, statsUrl);
            } catch (e) {
              console.error("Error while parsing stats", e);
            }
          }
          return true;
        };
        componentExecutors.push(statsExecutor);
      }
    } else {
      console.error(`No maps available for match`, matchId);
    }
  } else {
    const handleMapExecutor = async () => {
      return await handleMaps(mapLinks, matchUrl);
    };
    componentExecutors.push(handleMapExecutor);
  }
  const componentPromises = componentExecutors.map((executor) => executor());
  await Promise.all(componentPromises);
  if (CACHED) {
    console.log("New match", {
      hltvId,
      title,
      eventId,
      date,
      format,
      online,
      matchType,
    });
    return;
  }
  if (TRAVERSE_ADDED_MATCHES) {
    const foundMatch = await getMatchByHltvId(hltvId);
    if (foundMatch) return foundMatch;
  }
  try {
    return await createMatch({
      hltvId,
      title,
      eventId,
      date,
      format,
      online,
      matchType,
    });
  } catch (err) {
    if (err.toString().includes("E11000")) {
      console.log("Duplicate match", hltvId);
    } else {
      throw new Error(`Unable to add match ID ${hltvId} to the database:`, err);
    }
  }
};

const parseMatchStats = async ($: CheerioAPI) => {
  return $(".columns > .stats-match-map.inactive").toArray();
};

const parseMap = async (
  $: CheerioAPI,
  mapId: number,
  matchId: number,
  rankings: { firstTeam: number | null; secondTeam: number | null },
  mapUrl: string
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
  const firstWon =
    Number($(scoreContainer.childNodes[0]).text()) >=
    Number($(scoreContainer.childNodes[2]).text());
  if (firstWon) {
    score["teamOne"] = firstTeam;
    score["teamTwo"] = secondTeam;
    teamOneRanking = rankings.firstTeam;
    teamTwoRanking = rankings.secondTeam;
  } else {
    score["teamOne"] = secondTeam;
    score["teamTwo"] = firstTeam;
    teamOneRanking = rankings.secondTeam;
    teamTwoRanking = rankings.firstTeam;
  }
  const mapPerformanceLink = $(
    ".stats-top-menu-item-link:contains('Performance')"
  )[0];
  if (!mapPerformanceLink) {
    console.log("No map performance link for map ID " + mapId);
    return null;
  } else {
    let firstTeamStats = null;
    let secondTeamStats = null;
    const mapPerformanceUrl = mapPerformanceLink.attribs["href"];
    const mapPerformancePage = !CACHED
      ? await puppeteerGet(mapPerformanceUrl, mapUrl, true)
      : fs.readFileSync("cached/map-performance-page.html");
    if (!fs.existsSync("cached/map-performance-page.html")) {
      fs.writeFile(
        "cached/map-performance-page.html",
        mapPerformancePage,
        (err) => {
          if (err) throw err;
        }
      );
    }
    if (!mapPerformancePage) {
      console.log("No map performance page found for map ID: " + mapId);
    } else {
      ({ firstTeamStats, secondTeamStats } = await parseMapPerformance(
        load(mapPerformancePage)
      ));
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
            Number(currRow.find(".st-kdratio").text().replace("%", "")) * 0.01,
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
      teamOneStats = [];
      teamTwoStats = [];
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
    }
  }
  if (!CACHED)
    try {
      return await createMap({
        hltvId: Number(hltvId),
        matchId,
        mapType,
        score,
        teamOneRanking,
        teamTwoRanking,
        teamOneStats,
        teamTwoStats,
      });
    } catch (err) {
      if (err.toString().includes("E11000")) {
        // console.log("Duplicate event ", hltvId);
      } else {
        throw new Error(
          "Unable to add map ID " + hltvId + " to database: ",
          err
        );
      }
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
    teamNum =
      Number(
        $(".eventMeta > tbody > tr > th:contains('Teams')")
          .next("td")[0]
          .attribs["title"].replace(/[^0-9\.-]+/g, "")
      ) || null;
  } catch {}
  let prizePool = null;
  try {
    let prizePoolString = $(
      ".eventMeta > tbody > tr > th:contains('Prize pool')"
    )
      .next("td")[0]
      .attribs["title"].toLocaleLowerCase();
    if (!prizePoolString.includes("spots")) {
      prizePool = Number(prizePoolString.replace(/[^0-9\.-]+/g, "")) || null;
    }
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
        // TODO: what is this???
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
  if (!CACHED)
    try {
      return await createEvent({
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
    } catch (err) {
      if (err.toString().includes("E11000")) {
        // console.log("Duplicate event ", hltvId);
      } else {
        throw new Error(
          "Unable to add event ID " + hltvId + " to database: ",
          err
        );
      }
    }
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
        ? // this checks if the player has passed away
          currentAge.includes("-")
          ? Number(currentAge.split("(")[1].split("-")[0])
          : currentYear - Number(currentAge.replace(/[^0-9\.-]+/g, ""))
        : null;
  } catch {}
  let nationality = null;
  try {
    nationality = $($(".playerRealname > .flag")[0]).attr("title");
    if (!nationality)
      nationality = $($(".player-realname > .flag")[0]).attr("title");
  } catch {}
  if (!CACHED)
    try {
      return await createPlayer({ hltvId, name, birthYear, nationality });
    } catch (err) {
      if (err.toString().includes("E11000")) {
        // console.error("Duplicate player", hltvId);
      } else {
        throw new Error(
          "Unable to add player ID " + hltvId + " to database: ",
          err
        );
      }
    }
};

export const parseResults = async ($: CheerioAPI, resultsUrl: string) => {
  const resultLinks = $("div.allres")
    .find("div.result-con > a")
    .toArray()
    .slice(0, CACHED ? 1 : RESULT_LIMIT);
  const resultExecutors: (() => Promise<boolean>)[] = [];
  for (const resultLink of resultLinks) {
    const resultUrl = resultLink.attribs["href"];
    const matchId = Number(resultUrl.split("/")[2]);
    const match = await getMatchByHltvId(matchId);
    if (match && !TRAVERSE_ADDED_MATCHES) {
      if (ABORT_UPON_DUPLICATE) {
        console.log("Match ID " + matchId + " already in database, aborting.");
        return;
      }
      console.log("Match ID " + matchId + " already in database, skipping.");
      continue;
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
    if (!nextUrl) {
      console.log("You reached the end!");
      return;
    }
    puppeteerGet(nextUrl, resultsUrl, true).then((nextResultsPage) => {
      if (!nextResultsPage) console.error("Unable to find next results page.");
      else {
        parseResults(load(nextResultsPage), nextUrl);
      }
    });
  }
  const resultStart = Date.now();
  // // For debug: if you ever want to test matches sequentially
  // for (const executor of resultExecutors){
  //   await executor()
  // }
  const resultPromises = resultExecutors.map((executor) => executor());
  await Promise.all(resultPromises);
  const resultEnd = Date.now();
  const resultElapsed = Math.round((resultEnd - resultStart) / 10) / 100;
  console.log(
    `Page of results url ${resultsUrl} took ${resultElapsed} seconds!`
  );
};
