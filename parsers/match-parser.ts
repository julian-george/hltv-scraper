import fs from "fs";
import { CheerioAPI, load } from "cheerio";
import config from "config";
import { getEventByHltvId } from "../services/event-service.js";
import { getPlayerByHltvId } from "../services/player-service.js";
import { getMapByHltvId } from "../services/map-service.js";
import { createMatch, getMatchByHltvId } from "../services/match-service.js";
import { createUnplayedMatch } from "../services/unplayedmatch-service.js";
import puppeteerGet from "../scrape-client.js";
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
  if (played) {
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
              console.log(
                "Map ID " + mapId + " already in database, skipping."
              );
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
        rankings,
        players,
      });
      return;
    }
    try {
      return await createUnplayedMatch({
        hltvId,
        title,
        eventId,
        date,
        format,
        online,
        matchType,
        rankings,
        players,
      });
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
