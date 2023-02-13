import Event, { eventSchema } from "../models/Event";

export const getEventByHltvId = async (id: number) => {
  const event = await Event.findOne({ hltvId: id });
  if (!event) return null;
  else return event;
};

export const createEvent = async (event) => {
  return await Event.create(event);
};
