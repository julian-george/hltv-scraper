import { CheerioAPI } from "cheerio";
import config from "config";
import { createPlayer } from "../services/player-service.js";

const CACHED = config.get("scrapeCached");

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
      throw new Error(
        "Unable to add player ID " + hltvId + " to database: ",
        err
      );
    }
};

export default parsePlayer;
