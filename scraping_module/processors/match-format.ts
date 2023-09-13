const formatProcessor = (formatString?: string) => {
  if (!formatString) return null;
  formatString = formatString.toLowerCase();
  let formatCategory: number | null = null;
  if (formatString.includes("best of 7")) {
    formatCategory = 7;
  } else if (formatString.includes("best of 5")) {
    formatCategory = 5;
  } else if (
    formatString.includes("best of 3") ||
    formatString.includes("bo3") ||
    formatString.includes("all 3")
  ) {
    formatCategory = 3;
  } else if (formatString.includes("best of 2")) {
    formatCategory = 2;
  } else if (
    formatString.includes("final") ||
    formatString.includes("decider")
  ) {
    formatCategory = 3;
  } else if (formatString.includes("showmatch")) {
    formatCategory = 3;
  } else {
    formatCategory = 1;
  }
  return formatCategory;
};

export default formatProcessor;
