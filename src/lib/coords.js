// Coordinate resolution for the geographic (MapLibre/deck.gl) rendering mode.
//
// /api/trains gives each train a mode-agnostic position: {fromStation, toStation,
// fraction, etaSeconds}. This module turns that into a real [lat, lng] by looking
// the two station names up in geo-stations.json and lerping between them -- the
// schematic renderer (Phase 3) does the same thing against its own coordinate table.

/** Look up a station's coordinate, preferring a line-specific entry over the wildcard. */
export function lookupStationPoint(geoStations, stationName, lineId) {
  const entry = geoStations[stationName];
  if (!entry) return null;
  return entry[lineId] ?? entry["*"] ?? null;
}

export function lerp(a, b, t) {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

/**
 * Extrapolate a train's progress (0..1) between fromStation and toStation at `nowMs`,
 * given the fraction/etaSeconds/receivedAtMs snapshot from its last poll.
 *
 * There's no segmentSeconds field from the backend -- the implied per-second rate is
 * derived as (1 - fraction) / etaSeconds. Once a train reaches its next station
 * (extrapolated fraction hits 1), it holds there until the next poll supplies a new
 * segment; Phase 2 has no line-topology data yet to guess what comes after toStation.
 */
export function extrapolateFraction(train, nowMs) {
  if (train.fraction >= 1 || train.etaSeconds <= 0) return 1;
  const elapsedSeconds = (nowMs - train.receivedAtMs) / 1000;
  const rate = (1 - train.fraction) / train.etaSeconds; // fraction progress per second
  return Math.min(1, train.fraction + rate * elapsedSeconds);
}

/** Resolve a train's position in an arbitrary 2D coordinate table (geo or schematic),
 * or null if either station is unknown there. Both tables share the same shape:
 * {"Station Name": {lineId: [a, b], "*": [a, b]}}. */
function resolvePoint(stationTable, train, nowMs) {
  const from = lookupStationPoint(stationTable, train.fromStation, train.lineId);
  const to = lookupStationPoint(stationTable, train.toStation, train.lineId);
  if (!from || !to) return null;
  const fraction = extrapolateFraction(train, nowMs);
  return lerp(from, to, fraction);
}

/** Resolve a train's current real-world [lat, lng], or null if either station is unknown. */
export function resolveGeoPoint(geoStations, train, nowMs) {
  return resolvePoint(geoStations, train, nowMs);
}

/** Resolve a train's current schematic [x, y] (SVG viewBox units), or null if unknown. */
export function resolveSchematicPoint(schematicStations, train, nowMs) {
  return resolvePoint(schematicStations, train, nowMs);
}
