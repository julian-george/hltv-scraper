import { CheerioAPI } from "cheerio";
import config from "config";
import { createEvent } from "../services/event-service.js";

const CACHED = config.get("scrapeCached");

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
    if (!teamNum) {
      teamNum = $("div.teams-attending > div.team-box").length;
    }
  } catch {}
  let prizePool = null;
  try {
    let prizePoolString = $(
      ".eventMeta > tbody > tr > th:contains('Prize pool')"
    )
      .next("td")[0]
      .attribs["title"].toLocaleLowerCase()
      .split(" ")[0];
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
      throw new Error(
        "Unable to add event ID " + hltvId + " to database: ",
        err
      );
    }
};

export default parseEvent;
