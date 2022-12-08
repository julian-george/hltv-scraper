import Match, { matchSchema } from "../models/Match";

export const getMatchByHltvId = async (id: number) => {
  const matches = await Match.find({ hltvId: id });
  if (matches.length != 1) return null;
  else return matches[0];
};

export const createMatch = async (match) => {
  return await Match.create(match);
};
