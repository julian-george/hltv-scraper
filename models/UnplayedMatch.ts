import { Schema, model } from "mongoose";

export const unplayedMatchSchema = new Schema({
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
  teamOneRanking: Number,
  teamTwoRanking: Number,
  players: {
    firstTeam: [Number],
    secondTeam: [Number],
  },
});

const UnplayedMatch = model("UnplayedMatch", unplayedMatchSchema);

export default UnplayedMatch;
