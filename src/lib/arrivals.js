import { normStation } from "./lineGraph";
import { liveEtaSeconds } from "./coords";

/**
 * The next trains due at a station: every train whose toStation matches, sorted by
 * live ETA. Matched on the normalized name so the Arrivals feed's naming variants
 * ("Harlesden Rail Station" vs "Harlesden") all resolve. Like a platform board.
 */
export function stationArrivals(trains, stationName, nowMs, limit = 6) {
  const key = normStation(stationName);
  const out = [];
  for (const t of trains) {
    if (normStation(t.toStation) !== key) continue;
    out.push({
      id: t.id,
      lineId: t.lineId,
      destination: t.destination,
      eta: liveEtaSeconds(t, nowMs),
      atPlatform: t.atPlatform,
    });
  }
  out.sort((a, b) => a.eta - b.eta);
  return out.slice(0, limit);
}
