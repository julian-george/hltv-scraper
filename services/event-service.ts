import Event, { eventSchema } from "../models/Event.js";
import { queryWrapper, insertWrapper } from "../scrape-util.js";

export const getEventByHltvId = async (id: number) => {
  const event = await queryWrapper(() => Event.findOne({ hltvId: id }));
  if (!event) return null;
  else return event;
};

export const createEvent = async (event) => {
  return await insertWrapper(() => new Event(event).save());
};
