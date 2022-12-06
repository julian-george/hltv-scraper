import { Schema, model } from "mongoose";

export const matchSchema = new Schema({
  hltvId: {
    type: Number,
    unique: true,
  },
  date: Date,
  format: String,
  online: Boolean,
  // i.e. grand final, quarterfinal, swiss stage, etc
  matchType: String,
});

const Match = model("Match", matchSchema);

export default Match;
