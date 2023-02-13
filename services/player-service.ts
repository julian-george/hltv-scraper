import Player, { playerSchema } from "../models/Player";

export const getPlayerByHltvId = async (id: number) => {
  const player = await Player.findOne({ hltvId: id });
  if (!player) return null;
  else return player;
};

export const createPlayer = async (player) => {
  return await Player.create(player);
};
