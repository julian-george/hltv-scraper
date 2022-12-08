import Map, { mapSchema } from "../models/Map";

export const getMapByHltvId = async (id: number) => {
  const maps = await Map.find({ hltvId: id });
  if (maps.length != 1) return null;
  else return maps[0];
};

export const createMap = async (map) => {
  return await Map.create(map);
};
