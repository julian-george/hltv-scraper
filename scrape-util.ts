export const delay = (ms: number, maxDelay: number = 6000) =>
  new Promise((resolve) => {
    setTimeout(() => {
      resolve(true);
    }, Math.random() * maxDelay + ms);
  });
