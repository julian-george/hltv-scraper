import Event from "../models/Event";

export const getEventByHltvId = async (id: number) => {
  const events = await Event.find({ hltvId: id });
  if (events.length != 1) return null;
  else return events[0];
};
