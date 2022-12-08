import cloudscraper from "cloudscraper";

const DEFAULT_URL = "https://hltv.org";

export const clientGet = async (url: string) => {
  return new Promise<string>((resolve, reject) =>
    setTimeout(() => {
      cloudscraper
        // @ts-ignore
        .get(DEFAULT_URL + url)
        .then((data) => resolve(data))
        .catch((err) => reject(err));
    }, Math.random() * 500 + 1000)
  );
};
