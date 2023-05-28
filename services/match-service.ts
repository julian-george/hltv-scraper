import Match, { matchSchema } from "../models/Match.js";
import { queryWrapper, insertWrapper } from "../scrape-util.js";

export const getMatchByHltvId = async (id: number) => {
  const match = await queryWrapper(() => Match.findOne({ hltvId: id }));
  if (!match) return null;
  else return match;
};

export const createMatch = async (match) => {
  return await queryWrapper(() =>
    Match.findOneAndUpdate({ hltvId: match.hltvId }, match, { upsert: true })
  );
};
