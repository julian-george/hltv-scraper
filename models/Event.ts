import { Schema, model } from "mongoose";

export const eventSchema = new Schema({
  hltvId: {
    type: Number,
    unique: true,
  },
  title: String,
  startDate: Date,
  endDate: Date,
  prizePool: Number,
  teamNum: Number,
  teamRankings: [Number],
  location: String,
  online: Boolean,
  format: String,
});

const Event = model("Event", eventSchema);

export default Event;
