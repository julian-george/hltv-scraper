import { Schema, model } from "mongoose";

export const playerSchema = new Schema({
  hltvId: {
    type: Number,
    unique: true,
  },
  name: String,
  birthYear: Number,
  nationality: String,
});

const Player = model("Player", playerSchema);

export default Player;
