// Plain external store (React 18 useSyncExternalStore-compatible) holding the latest
// reconciled train list from /api/trains, plus the feed's connection status.
//
// Per-frame position extrapolation is NOT done here -- it's a pure function of
// (train, now) computed at render time by src/lib/coords.js, so this store only
// changes (and only re-renders React) when a poll actually lands, not 60 times a
// second.

const MAX_MISSED_POLLS = 3;

let trains = [];
let feedStatus = "connecting"; // "connecting" | "live" | "stale" | "error"
// Diagnostics for the debug panel, updated on every poll.
let diagnostics = {
  lastPollAtMs: 0, // when the client last completed a poll
  serverUpdatedAt: 0, // updatedAt from the payload (epoch seconds)
  pollCount: 0,
  lastError: null,
  lastTrainCount: 0,
};
const listeners = new Set();

function notify() {
  for (const listener of listeners) listener();
}

export function subscribe(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getTrains() {
  return trains;
}

export function getFeedStatus() {
  return feedStatus;
}

export function getDiagnostics() {
  return diagnostics;
}

/** Record poll metadata for the debug panel. Replaces the object (new identity) so
 * useSyncExternalStore sees a change. */
export function recordPoll({ serverUpdatedAt, error, trainCount }) {
  diagnostics = {
    lastPollAtMs: Date.now(),
    serverUpdatedAt: serverUpdatedAt ?? diagnostics.serverUpdatedAt,
    pollCount: diagnostics.pollCount + 1,
    lastError: error ?? null,
    lastTrainCount: trainCount ?? diagnostics.lastTrainCount,
  };
  notify();
}

/**
 * Merge an incoming /api/trains payload into the store.
 *
 * Trains missing from `incoming` are kept for up to MAX_MISSED_POLLS more polls
 * (smooth disappearance rather than a hard cut when a single poll drops a train),
 * mirroring the reconciliation approach in the original src/tube-live-map.jsx spike.
 */
export function reconcileTrains(incoming) {
  const receivedAtMs = Date.now();

  const next = incoming.map((t) => ({ ...t, receivedAtMs, missCount: 0 }));
  const incomingIds = new Set(incoming.map((t) => t.id));

  for (const train of trains) {
    if (incomingIds.has(train.id)) continue;
    const missCount = (train.missCount ?? 0) + 1;
    if (missCount < MAX_MISSED_POLLS) next.push({ ...train, missCount });
  }

  trains = next;
  notify();
}

export function setFeedStatus(status) {
  if (status === feedStatus) return;
  feedStatus = status;
  notify();
}
