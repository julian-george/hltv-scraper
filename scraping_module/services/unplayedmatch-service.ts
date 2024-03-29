import UnplayedMatch from "../models/UnplayedMatch.js";
import { queryWrapper, insertWrapper } from "../scrape-util.js";

export const getUnplayedMatchByHltvId = async (id: number) => {
  const match = await queryWrapper(() => UnplayedMatch.findOne({ hltvId: id }));
  if (!match) return null;
  else return match;
};

export const deleteUnplayedMatchByHltvId = async (id: number) => {
  const match = await queryWrapper(() =>
    UnplayedMatch.findOneAndDelete({ hltvId: id })
  );
  return match;
};

export const updateUnplayedMatch = async (id: number, updates) => {
  const match = await queryWrapper(() =>
    UnplayedMatch.findOneAndUpdate({ hltvId: id }, updates)
  );
  return match;
};

export const createUnplayedMatch = async (match) => {
  return await insertWrapper(() =>
    UnplayedMatch.findOneAndUpdate({ hltvId: match.hltvId }, match, {
      upsert: true,
    }).exec()
  );
};
