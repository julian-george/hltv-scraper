import PQueue from "p-queue";
import config from "config";
import { delay } from "./scrape-util.js";

const BROWSER_LIMIT = config.get("browsers.limit");

export const getQueue = new PQueue({
  concurrency: BROWSER_LIMIT,
});

export const queryQueue = new PQueue({
  concurrency: BROWSER_LIMIT,
});

const onIdlePromises = [getQueue.onIdle(), queryQueue.onIdle()];
Promise.all(onIdlePromises).then(() => onIdle());

// Called whenever there are no promises in both queues
const onIdle = async () => {
  // If there are still no promises in both queues after this delay, the process is probably done
  await delay(10000);
  if (
    getQueue.pending == 0 &&
    getQueue.size == 0 &&
    queryQueue.pending == 0 &&
    queryQueue.size == 0
  ) {
    console.log("No pages left, exiting now.");
    process.exit(0);
  } else {
    // If not, wait for them both to idle
    const onIdlePromises = [getQueue.onIdle(), queryQueue.onIdle()];
    Promise.all(onIdlePromises).then(() => onIdle());
  }
};
