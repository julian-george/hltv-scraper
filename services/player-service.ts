import Player from "../models/Player";

export const getPlayerByHltvId = async (id: number) => {
  const players = await Player.find({ hltvId: id });
  if (players.length != 1) return null;
  else return players[0];
};
