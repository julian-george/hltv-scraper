import fs from "fs";
import { CheerioAPI, load } from "cheerio";
import config from "config";
import { getEventByHltvId } from "../services/event-service.js";
import { getPlayerByHltvId } from "../services/player-service.js";
import { getMapByHltvId, updatePick } from "../services/map-service.js";
import { createMatch, getMatchByHltvId } from "../services/match-service.js";
import {
  createUnplayedMatch,
  deleteUnplayedMatchByHltvId,
} from "../services/unplayedmatch-service.js";
import puppeteerGet from "../scrape-client.js";
import formatProcessor from "../processors/match-format.js";
import matchTypeProcessor from "../processors/match-matchtype.js";
import parseEvent from "./event-parser.js";
import parsePlayer from "./player-parser.js";
import parseMap from "./map-parser.js";

const CACHED = config.get("scrapeCached");

const TRAVERSE_ADDED_MATCHES = config.get("results.traverseAdded");

const PLAYER_LIMIT = Infinity;

export const parseMatch = async (
  $: CheerioAPI,
  matchId: number,
  matchUrl: string,
  played: boolean = true
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
    title = title.toLowerCase();
  } catch {}
  let date = null;
  try {
    date = new Date(Number($(".timeAndEvent > .time")[0].attribs["data-unix"]));
  } catch {}
  let numMaps = null;
  try {
    numMaps = $("div.mapholder").length;
  } catch {}
  let format = null;
  try {
    format = $($("div.preformatted-text")[0]).text().split("\n")[0];
  } catch {}
  const formatCategory = formatProcessor(format);
  let matchType = null;
  try {
    matchType = $($("div.preformatted-text")[0])
      .text()
      .split("* ")[1]
      .split(".")[0]
      .split("\n")[0];
  } catch {}
  const matchTypeCategory = matchTypeProcessor(matchType);
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
  let players = {
    firstTeam: [],
    secondTeam: [],
  };
  if (played) {
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
  } else {
    const teamOnePics = $(
      `td.player-image > div.player-compare[data-team-ordinal="1"]`
    );
    const teamTwoPics = $(
      `td.player-image > div.player-compare[data-team-ordinal="2"]`
    );

    if (teamOnePics.length != 5 || teamTwoPics.length != 5) {
      throw new Error(
        `Incomplete player list for unplayed match ID ${matchId}`
      );
    }
    for (const picElement of teamOnePics) {
      players.firstTeam.push(Number(picElement.attribs["data-player-id"]));
    }

    for (const picElement of teamTwoPics) {
      players.secondTeam.push(Number(picElement.attribs["data-player-id"]));
    }
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
  const picks = {};
  // this stuff would ordinarily be handled by map parser but due to desire to not rescrape maps, we are doing it here
  $("div.mapholder > div.results").each((i, mapResultContainer) => {
    let teamPick = null;
    if ($(mapResultContainer).find(".results-left.pick").length > 0) {
      teamPick =
        $(mapResultContainer).find(".results-left.won").length > 0
          ? "teamOne"
          : "teamTwo";
    } else if ($(mapResultContainer).find(".results-right.pick").length > 0) {
      teamPick =
        $(mapResultContainer).find(".results-right.won").length > 0
          ? "teamOne"
          : "teamTwo";
    }
    const mapLink = $(mapResultContainer).find("a.results-stats");
    const mapUrl = mapLink.attr("href");
    if (mapUrl) {
      const mapId = Number(mapUrl.split("/")[4]);
      picks[mapId] = teamPick;
    }
  });

  if (played) {
    let mapLinks = $(
      "div.mapholder > div > div.results-center > div.results-center-stats > a"
    );
    const handleMaps = async (links, referUrl: string): Promise<boolean> => {
      const mapPromises: Promise<boolean>[] = [];
      mapLinks.each((i, mapLink) => {
        mapPromises.push(
          new Promise(async (resolve, reject) => {
            const mapUrl = $(mapLink).attr("href");
            const mapId = Number(mapUrl.split("/")[4]);
            const map = await getMapByHltvId(mapId);
            if (!CACHED && map) {
              console.log(
                "Map ID " + mapId + " already in database, skipping."
              );
              // Having this in here for the time being
              updatePick(mapId, picks[mapId]);
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
              parseMap(
                load(mapPage),
                mapId,
                matchId,
                rankings,
                date,
                mapUrl,
                picks[mapId]
              )
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
      });

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
      const statsLink = $("div.stats-detailed-stats > a");
      if (statsLink.length > 0) {
        const statsUrl = statsLink.attr("href");
        if (statsUrl.includes("mapstatsid")) {
          mapLinks = statsLink;
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
                const links = await parseResultStats(load(statsPage));
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
  }
  const componentPromises = componentExecutors.map((executor) => executor());
  await Promise.all(componentPromises);
  if (played) {
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
    await deleteUnplayedMatchByHltvId(hltvId);
    try {
      return await createMatch({
        hltvId,
        title,
        eventId,
        date,
        format,
        online,
        matchType,
        numMaps,
        matchTypeCategory,
        formatCategory,
      });
    } catch (err) {
      throw new Error(`Unable to add match ID ${hltvId} to the database:`, err);
    }
  } else {
    if (CACHED) {
      console.log("New unplayed match", {
        hltvId,
        title,
        eventId,
        date,
        format,
        online,
        matchType,
        numMaps,
        teamOneRanking: rankings.firstTeam,
        teamTwoRanking: rankings.secondTeam,
        matchUrl,
        players,
      });
      return;
    }
    try {
      const newMatch = await createUnplayedMatch({
        hltvId,
        title,
        eventId,
        date,
        format,
        online,
        matchType,
        numMaps,
        teamOneRanking: rankings.firstTeam,
        teamTwoRanking: rankings.secondTeam,
        matchUrl,
        players,
      });
      return newMatch;
    } catch (err) {
      throw new Error(
        `Unable to add unplayed match ID ${hltvId} to the database:`,
        err
      );
    }
  }
};

const parseResultStats = async ($: CheerioAPI) => {
  return $(".columns > .stats-match-map.inactive").toArray();
};
