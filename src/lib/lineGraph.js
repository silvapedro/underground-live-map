// Line topology derived from line-sequences.json, used to synthesize a plausible
// origin station for trains that report no between-station location.
//
// TfL gives ~78% of trains only a *destination* station + ETA and no origin (all of
// DLR/Overground/Elizabeth/Tram, plus every "Approaching X" tube train). Rendered
// literally those are static dots that only jump on each poll. Given the line's
// ordered station list we can pick the station immediately before the target and
// glide that final leg instead -- so the whole network moves.

import lineSequences from "../data/line-sequences.json";

/** Loose key for matching names that differ across TfL feeds ("Harlesden Rail Station"
 * vs "Harlesden") or a free-text destination ("Kennington via CX") against a canonical
 * station name -- strip suffixes, line qualifiers, punctuation. */
export function normStation(name) {
  return norm(name);
}
function norm(name) {
  return name
    .toLowerCase()
    .replace(/&amp;/g, "and")
    .replace(/&/g, "and")
    .replace(/\bvia\b.*$/, "")
    .replace(/\(.*?\)/g, "")
    .replace(/\b(underground|rail|dlr)?\s*station\b/g, "")
    .replace(/\btram stop\b/g, "")
    .replace(/[^a-z0-9]/g, "");
}

// lineId -> [{ branch: string[], normed: string[] }]
const graph = {};
for (const [lineId, { branches }] of Object.entries(lineSequences)) {
  graph[lineId] = branches.map((branch) => ({ branch, normed: branch.map(norm) }));
}

/**
 * A plausible predecessor of `toStation` on `lineId`, biased toward the one the train
 * is travelling *from* given its `destination`. Returns null if the station isn't on
 * any known branch (so the caller keeps it pinned).
 */
export function neighborToward(lineId, toStation, destination) {
  const branches = graph[lineId];
  if (!branches) return null;
  // Match on the normalized key: the Arrivals feed and the Route/Sequence feed
  // canonicalize some rail/Overground names differently ("Harlesden Rail Station"
  // vs "Harlesden"), and the returned neighbour is a branch name, which is
  // guaranteed present in both coordinate tables.
  const toN = norm(toStation);
  const destN = destination ? norm(destination) : null;
  let fallback = null;

  for (const { branch, normed } of branches) {
    const i = normed.indexOf(toN);
    if (i === -1) continue;
    const prev = i > 0 ? branch[i - 1] : null;
    const next = i < branch.length - 1 ? branch[i + 1] : null;
    if (fallback == null) fallback = prev ?? next;

    // If the destination is further along this branch, the train came from the
    // other side -- pick the neighbour on the opposite end from the destination.
    if (destN) {
      const j = normed.indexOf(destN);
      if (j !== -1 && j !== i) return j > i ? (prev ?? next) : (next ?? prev);
    }
  }
  return fallback;
}
