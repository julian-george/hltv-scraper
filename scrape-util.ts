import { Query } from "mongoose";

const RETRY_NUM = 5;

export const delay = (ms: number, maxDelay: number = 1500) =>
  new Promise((resolve) => {
    setTimeout(() => {
      resolve(true);
    }, Math.random() * maxDelay + ms);
  });

export const queryWrapper = async (query: Query<any, any, any, any>) => {
  for (let i = 0; i < RETRY_NUM; i++) {
    try {
      return await query;
    } catch (err) {
      if (
        err.toString().includes("MongooseServerSelectionError") &&
        err.toString().toLowerCase().includes("timed out")
      ) {
        console.error(`Timeout on try ${i}:`, err);
      } else {
        return null;
      }
      if (i == RETRY_NUM - 1) return null;
    }
  }
};
