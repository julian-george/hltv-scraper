import { Schema, model } from "mongoose";

export const matchSchema = new Schema({
  hltvId: {
    type: Number,
    unique: true,
  },
  eventId: {
    type: Number,
  },
  title: String,
  date: Date,
  format: String,
  numMaps: Number,
  online: Boolean,
  // i.e. grand final, quarterfinal, swiss stage, etc
  matchType: String,
});

const Match = model("Match", matchSchema);

export default Match;
