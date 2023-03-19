import { Query } from "mongoose";
import PQueue from "p-queue";
import dotenv from "dotenv";

dotenv.config();

const MAX_QUERY_TIME = 10000;
const MAX_QUERY_WAIT = 1500;
const MIN_QUERY_WAIT = 200;
const RETRY_NUM = 5;
const BROWSER_LIMIT = Number(process.env.BROWSER_LIMIT) || 1;
const MAX_CONCURRENT_QUERIES = BROWSER_LIMIT;

const queryQueue = new PQueue({
  concurrency: MAX_CONCURRENT_QUERIES,
});

queryQueue.on("add", () => {
  const queueSize = queryQueue.size;
  if ((queueSize + 1) % 100 == 0)
    console.error("queryQueue size:", queueSize - 1);
  const numPending = queryQueue.pending;
  if ((numPending + 1) % 25 == 0)
    console.error("num queries pending:", numPending - 1);
});

export const delay = (ms: number, maxDelay: number = 1500) =>
  new Promise((resolve) => {
    setTimeout(() => {
      resolve(true);
    }, Math.random() * maxDelay + ms);
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
        console.error(`Timeout on try ${i}:`, err);
        // query = query.clone();
        // Short variable delay to prevent clumping of queries at static intervals
        await delay(MIN_QUERY_WAIT, MAX_QUERY_WAIT - MIN_QUERY_WAIT);
      } else {
        console.error(`Query error:`, err);
        throw err;
      }
      if (i == RETRY_NUM - 1) throw err;
    }
  }
};

const errorPromise = () => new Promise((resolve, reject) => reject("Fuck"));

export const insertWrapper = async (insert: () => Promise<any>) => {
  try {
    const insertResult = await queryQueue.add(insert);
    return insertResult || null;
  } catch (err) {
    err = err.toString().toLowerCase();
    if (err.includes("e11000")) {
      // console.log("Duplicate insert: ", err);
      return null;
    } else {
      console.error(`Insert error:`, err);
      throw err;
    }
  }
};

["exit"].forEach((eventType) => {
  process.on(eventType, () => {
    console.error("queryQueue info: ");
    console.error(`num pending: ${queryQueue.pending}`);
    console.error(`size: ${queryQueue.size}`);
    console.error(`isPaused: ${queryQueue.isPaused}`);
    process.kill(process.pid);
  });
});
