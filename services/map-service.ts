import Map, { mapSchema } from "../models/Map";

export const getMapByHltvId = async (id: number) => {
  const map = await Map.findOne({ hltvId: id });
  if (!map) return null;
  else return map;
};

export const createMap = async (map) => {
  return await Map.create(map);
};
