import Map, { mapSchema } from "../models/Map";
import { queryWrapper, insertWrapper } from "../scrape-util";

export const getMapByHltvId = async (id: number) => {
  const map = await queryWrapper(Map.findOne({ hltvId: id }));
  if (!map) return null;
  else return map;
};

export const createMap = async (map) => {
  return await insertWrapper(Map.create(map));
};
