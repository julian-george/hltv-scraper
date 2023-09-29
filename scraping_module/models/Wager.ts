import { Schema, model } from "mongoose";

export const wagerSchema = new Schema({
  wagerId: {
    type: Number,
    unique: true,
  },
  matchId: Number,
  marketName: String,
  amountBetted: Number,
  odds: Number,
  creationDate: Date,
  result: {
    type: String,
    enum: ["UNFINISHED", "WON", "LOST", "CANCELLED"],
    default: "UNFINISHED",
  },
});

const Wager = model("Wager", wagerSchema);

export default Wager;
