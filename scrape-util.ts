import { Query } from "mongoose";

const RETRY_NUM = 5;

export const delay = (ms: number, maxDelay: number = 1500) =>
  new Promise((resolve) => {
    setTimeout(() => {
      resolve(true);
    }, Math.random() * maxDelay + ms);
  });

// TODO: is this causing redundant event/player scrapes?
export const queryWrapper = async (query: Query<any, any, any, any>) => {
  for (let i = 0; i < RETRY_NUM; i++) {
    try {
      const queryResult = await query;
      return queryResult || null;
    } catch (err) {
      if (
        err.toString().includes("MongooseServerSelectionError") &&
        err.toString().toLowerCase().includes("timed out")
      ) {
        console.error(`Timeout on try ${i}:`, err);
      } else {
        console.error(`Query error:`, err);
        throw err;
      }
      if (i == RETRY_NUM - 1) throw err;
    }
  }
};
