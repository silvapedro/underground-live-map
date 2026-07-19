// Coordinate resolution shared by both rendering modes.
//
// /api/trains gives each train a mode-agnostic position: {fromStation, toStation,
// fraction, etaSeconds}. This module turns that into an [a, b] point by looking the
// two station names up in a coordinate table (geo or schematic) and lerping between
// them. For the ~78% of trains TfL reports with no origin (fromStation == toStation),
// effectiveSegment() synthesizes an origin from line topology so they glide too.

import { neighborToward, normStation } from "./lineGraph";

// Assumed time to traverse one inter-station gap, for trains where we only know the
// ETA to the next stop and had to synthesize the origin. ~110s ≈ a typical tube hop.
const NOMINAL_SEGMENT_S = 110;

// Normalized-name -> exact-key index per coordinate table, built once and cached.
// The Arrivals feed and the Route/Sequence feed spell some rail/Overground stations
// differently; this lets a lookup fall back to a loose match instead of returning null.
const _normIndexCache = new WeakMap();
function normIndex(table) {
  let idx = _normIndexCache.get(table);
  if (!idx) {
    idx = new Map();
    for (const key of Object.keys(table)) idx.set(normStation(key), key);
    _normIndexCache.set(table, idx);
  }
  return idx;
}

/** Look up a station's coordinate, preferring a line-specific entry over the wildcard,
 * and falling back to a normalized-name match when the exact key is absent. */
export function lookupStationPoint(table, stationName, lineId) {
  let entry = table[stationName];
  if (!entry) {
    const key = normIndex(table).get(normStation(stationName));
    if (key) entry = table[key];
  }
  if (!entry) return null;
  return entry[lineId] ?? entry["*"] ?? null;
}

export function lerp(a, b, t) {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

/** True once per session unless the OS setting changes; cheap enough to call per frame,
 * but memoized anyway since matchMedia() allocates. */
let _reducedMotion = null;
export function prefersReducedMotion() {
  if (_reducedMotion === null) {
    _reducedMotion = typeof window !== "undefined"
      && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
  }
  return _reducedMotion;
}

/**
 * Extrapolate a train's progress (0..1) between fromStation and toStation at `nowMs`,
 * given the fraction/etaSeconds/receivedAtMs snapshot from its last poll.
 *
 * There's no segmentSeconds field from the backend -- the implied per-second rate is
 * derived as (1 - fraction) / etaSeconds. Once a train reaches its next station
 * (extrapolated fraction hits 1), it holds there until the next poll supplies a new
 * segment; Phase 2 has no line-topology data yet to guess what comes after toStation.
 *
 * Under prefers-reduced-motion, skip the continuous per-frame extrapolation entirely --
 * trains only move when a new poll actually lands, rather than gliding every frame.
 */
export function extrapolateFraction(train, nowMs) {
  if (train.fraction >= 1 || train.etaSeconds <= 0 || prefersReducedMotion()) {
    return train.fraction;
  }
  const elapsedSeconds = (nowMs - train.receivedAtMs) / 1000;
  const rate = (1 - train.fraction) / train.etaSeconds; // fraction progress per second
  return Math.min(1, train.fraction + rate * elapsedSeconds);
}

/**
 * The train's remaining seconds to toStation right now, counting down between polls.
 * etaSeconds is a snapshot taken at receivedAtMs; subtract the elapsed time since.
 */
export function liveEtaSeconds(train, nowMs) {
  const elapsed = (nowMs - train.receivedAtMs) / 1000;
  return Math.max(0, train.etaSeconds - elapsed);
}

/**
 * The segment a train should actually be drawn on right now: {from, to, progress}.
 *
 * - Real segment (TfL gave distinct from/to): use it, progress from extrapolation.
 * - At a platform: pinned at the station (it's genuinely stopped there).
 * - Otherwise (from == to, only a destination + ETA known): synthesize the origin
 *   from line topology and drive progress off the live countdown, so it glides in.
 */
export function effectiveSegment(train, nowMs) {
  if (train.fromStation !== train.toStation) {
    return {
      from: train.fromStation,
      to: train.toStation,
      progress: extrapolateFraction(train, nowMs),
    };
  }
  if (train.atPlatform) {
    return { from: train.toStation, to: train.toStation, progress: 1 };
  }
  const prev = neighborToward(train.lineId, train.toStation, train.destination);
  if (!prev) return { from: train.toStation, to: train.toStation, progress: 1 };

  // Static under reduced motion (uses the poll snapshot, not the ticking countdown).
  const eta = prefersReducedMotion() ? train.etaSeconds : liveEtaSeconds(train, nowMs);
  const denom = Math.max(NOMINAL_SEGMENT_S, train.etaSeconds);
  const progress = Math.min(1, Math.max(0.02, 1 - eta / denom));
  return { from: prev, to: train.toStation, progress };
}

/** Resolve a train's position in an arbitrary 2D coordinate table (geo or schematic),
 * or null if either station is unknown there. Both tables share the same shape:
 * {"Station Name": {lineId: [a, b], "*": [a, b]}}. */
function resolvePoint(stationTable, train, nowMs) {
  const seg = effectiveSegment(train, nowMs);
  const from = lookupStationPoint(stationTable, seg.from, train.lineId);
  const to = lookupStationPoint(stationTable, seg.to, train.lineId);
  if (!from || !to) return null;
  return lerp(from, to, seg.progress);
}

/** Resolve a train's current real-world [lat, lng], or null if either station is unknown. */
export function resolveGeoPoint(geoStations, train, nowMs) {
  return resolvePoint(geoStations, train, nowMs);
}

/** Resolve a train's current schematic [x, y] (SVG viewBox units), or null if unknown. */
export function resolveSchematicPoint(schematicStations, train, nowMs) {
  return resolvePoint(schematicStations, train, nowMs);
}
