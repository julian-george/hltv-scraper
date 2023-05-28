import { Schema, SchemaType, SchemaTypes, model } from "mongoose";

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
  matchUrl: String,
  players: {
    firstTeam: [Number],
    secondTeam: [Number],
  },
  betted: {
    type: Object,
    default: {},
  },
  mapNames: {
    type: [String],
    default: [],
  },
  pickedBy: {
    type: String,
    enum: ["teamOne", "teamTwo", null],
    default: null,
  },
});

const UnplayedMatch = model("UnplayedMatch", unplayedMatchSchema);

export default UnplayedMatch;
