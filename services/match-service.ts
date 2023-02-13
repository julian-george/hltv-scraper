import Match, { matchSchema } from "../models/Match";

export const getMatchByHltvId = async (id: number) => {
  const match = await Match.findOne({ hltvId: id });
  if (!match) return null;
  else return match;
};

export const createMatch = async (match) => {
  return await Match.create(match);
};
