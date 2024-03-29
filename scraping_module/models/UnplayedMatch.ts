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
  mapInfos: {
    type: [Object],
    default: [],
  },
  pickedBy: {
    type: String,
    enum: ["teamOne", "teamTwo", null],
    default: null,
  },
  predictions: {
    type: Object,
    default: null,
  },
  sameOrder: Boolean,
  played: {
    type: Boolean,
    default: false,
  },
});

const UnplayedMatch = model("UnplayedMatch", unplayedMatchSchema);

export default UnplayedMatch;
