import Match, { matchSchema } from "../models/Match";
import { queryWrapper } from "../scrape-util";

export const getMatchByHltvId = async (id: number) => {
  const match = await queryWrapper(Match.findOne({ hltvId: id }));
  if (!match) return null;
  else return match;
};

export const createMatch = async (match) => {
  return await Match.create(match);
};
