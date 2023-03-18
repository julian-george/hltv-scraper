import Event, { eventSchema } from "../models/Event";
import { queryWrapper, insertWrapper } from "../scrape-util";

export const getEventByHltvId = async (id: number) => {
  const event = await queryWrapper(Event.findOne({ hltvId: id }));
  if (!event) return null;
  else return event;
};

export const createEvent = async (event) => {
  return await insertWrapper(Event.create(event));
};
