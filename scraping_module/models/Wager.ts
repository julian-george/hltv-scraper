import { Schema, model } from "mongoose";

export const wagerSchema = new Schema({
  wagerId: {
    type: Number,
    unique: true,
  },
  matchId: Number,
  amountBetted: Number,
  odds: Number,
  result: {
    type: String,
    enum: ["UNFINISHED", "WON", "LOST", "CANCELLED"],
    default: "UNFINISHED",
  },
});

const Wager = model("Wager", wagerSchema);

export default Wager;
