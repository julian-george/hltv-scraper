export const delay = (ms: number, maxDelay: number = 1500) =>
  new Promise((resolve) => {
    setTimeout(() => {
      resolve(true);
    }, Math.random() * maxDelay + ms);
  });
