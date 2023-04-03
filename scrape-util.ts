import { Query } from "mongoose";
import dotenv from "dotenv";
import { queryQueue } from "./queues.js";

dotenv.config();

const MAX_QUERY_TIME = 10000;
const MAX_QUERY_WAIT = 1500;
const MIN_QUERY_WAIT = 200;
const MIN_EXTENDED_QUERY_WAIT = 20000;
const MAX_EXTENDED_QUERY_WAIT = 40000;
const RETRY_NUM = 5;

queryQueue.on("add", () => {
  const queueSize = queryQueue.size;
  if ((queueSize + 1) % 100 == 0)
    console.error("queryQueue size:", queueSize - 1);
  const numPending = queryQueue.pending;
  if ((numPending + 1) % 25 == 0)
    console.error("num queries pending:", numPending - 1);
});

export const delay = (delayOffset: number, maxDelay: number = 1500) =>
  new Promise((resolve) => {
    setTimeout(() => {
      resolve(true);
    }, Math.random() * maxDelay + delayOffset);
  });

export const queryWrapper = async (query: () => Query<any, any, any, any>) => {
  for (let i = 0; i < RETRY_NUM; i++) {
    try {
      const queryResult = await queryQueue.add(() =>
        query().maxTimeMS(MAX_QUERY_TIME)
      );
      return queryResult || null;
    } catch (err) {
      err = err.toString().toLowerCase();
      if (
        // If the query timed out on the server side
        err.includes("timed out") ||
        // or if it went over the maxTimeMS set above
        err.includes("mongoservererror: operation exceeded time limit")
      ) {
        console.error(`Query timeout on try ${i}:`, err);
        // Short variable delay to prevent clumping of queries at static intervals
        if (i < RETRY_NUM - 1)
          await delay(MIN_QUERY_WAIT, MAX_QUERY_WAIT - MIN_QUERY_WAIT);
        else
          await delay(
            MIN_EXTENDED_QUERY_WAIT,
            MAX_EXTENDED_QUERY_WAIT - MIN_EXTENDED_QUERY_WAIT
          );
      } else {
        console.error(`Query error:`, err);
        throw err;
      }
      if (i == RETRY_NUM - 1) throw err;
    }
  }
};

export const insertWrapper = async (insert: () => Promise<any>) => {
  for (let i = 0; i < RETRY_NUM; i++) {
    try {
      const insertResult = await queryQueue.add(insert);
      return insertResult || null;
    } catch (err) {
      err = err.toString().toLowerCase();
      if (err.includes("e11000")) {
        if (i == 0) {
          console.log("Duplicate insert:", err);
          return null;
        }
        return true;
      } else if (err.includes("timed out")) {
        console.error(`Insert timeout on try ${i}:`, err);
        if (i < RETRY_NUM - 1)
          await delay(MIN_QUERY_WAIT, MAX_QUERY_WAIT - MIN_QUERY_WAIT);
        else
          await delay(
            MIN_EXTENDED_QUERY_WAIT,
            MAX_EXTENDED_QUERY_WAIT - MIN_EXTENDED_QUERY_WAIT
          );
      } else {
        console.error(`Insert error:`, err);
        throw err;
      }
    }
  }
};

["exit"].forEach((eventType) => {
  process.on(eventType, () => {
    console.error("queryQueue info: ");
    console.error(`num pending: ${queryQueue.pending}`);
    console.error(`size: ${queryQueue.size}`);
    console.error(`isPaused: ${queryQueue.isPaused}`);
  });
});
