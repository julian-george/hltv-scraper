const null_substrings = ["disqual", "forfeit", "standin"];

const matchTypeProcessor = (matchTypeString?: string) => {
  if (
    !matchTypeString ||
    null_substrings.some((v) => matchTypeString.includes(v))
  ) {
    return null;
  }
  matchTypeString = matchTypeString.split(".")[0];
  let matchTypeCategory = null;
  if (matchTypeString.includes("showmatch")) {
    matchTypeCategory = 0;
  } else if (matchTypeString.includes("upper")) {
    matchTypeCategory = 1;
  } else if (
    matchTypeString.includes("lower") ||
    matchTypeString.includes("last chance") ||
    matchTypeString.includes("loser") ||
    matchTypeString.includes("winner") ||
    matchTypeString.includes("play-in")
  ) {
    matchTypeCategory = 2;
  } else if (
    matchTypeString.includes("group") ||
    matchTypeString.includes("stage")
  ) {
    if (
      matchTypeString.includes("elim") ||
      matchTypeString.includes("decider") ||
      matchTypeString.includes("final") ||
      matchTypeString.includes("playoff")
    ) {
      matchTypeCategory = 2;
    } else {
      matchTypeCategory = 1;
    }
  } else if (matchTypeString.includes("round")) {
    if (matchTypeString.includes("-2")) {
      matchTypeCategory = 2;
    } else {
      matchTypeCategory = 1;
    }
  } else if (matchTypeString.includes("grand")) {
    matchTypeCategory = 6;
  } else if (
    matchTypeString.includes("1/2") ||
    matchTypeString.includes("semi")
  ) {
    matchTypeCategory = 5;
  } else if (
    matchTypeString.includes("1/4") ||
    matchTypeString.includes("quarter") ||
    matchTypeString.includes("quater")
  ) {
    matchTypeCategory = 4;
  } else if (
    matchTypeString.includes("round of") ||
    matchTypeString.includes("decider") ||
    matchTypeString.includes("3rd") ||
    matchTypeString.includes("playoff") ||
    matchTypeString.includes("consolidation")
  ) {
    matchTypeCategory = 3;
  } else if (matchTypeString.includes("final")) {
    matchTypeCategory = 5;
  }
  return matchTypeCategory;
};

export default matchTypeProcessor;
