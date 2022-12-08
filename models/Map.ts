import { Schema, model, SchemaTypes } from "mongoose";

export const scoreSchema = new Schema({
  teamOne: {
    ct: Number,
    t: Number,
    ot: Number,
  },
  teamTwo: {
    ct: Number,
    t: Number,
    ot: Number,
  },
});

export const playerHalfStatsSchema = new Schema({
  kills: Number,
  hsKills: Number,
  assists: Number,
  flashAssists: Number,
  deaths: Number,
  kast: SchemaTypes.Decimal128,
  adr: SchemaTypes.Decimal128,
  fkDiff: Number,
  rating: SchemaTypes.Decimal128,
});

export const playerStatsSchema = new Schema({
  hltvId: {
    type: Number,
  },
  // formatted {hltvId: #kills against them}
  duelMap: {
    all: {
      type: SchemaTypes.Map,
      of: Number,
    },
    firstKill: {
      type: SchemaTypes.Map,
      of: Number,
    },
    awp: {
      type: SchemaTypes.Map,
      of: Number,
    },
  },
  tStats: playerHalfStatsSchema,
  ctStats: playerHalfStatsSchema,
});

export const mapSchema = new Schema({
  hltvId: {
    type: Number,
    unique: true,
  },
  matchId: {
    type: Number,
  },
  mapType: String,
  score: scoreSchema,
  // If not a tie, teamOne is the winner, teamTwo is the loser
  teamOneStats: [playerStatsSchema],
  teamTwoStats: [playerStatsSchema],
});

const Map = model("Map", mapSchema);

export default Map;
