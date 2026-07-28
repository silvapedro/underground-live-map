import { useEffect, useSyncExternalStore } from "react";
import {
  getDiagnostics,
  getFeedStatus,
  getTrains,
  recordPoll,
  reconcileTrains,
  setFeedStatus,
  subscribe,
} from "../lib/trainStore";

export const POLL_INTERVAL_MS = 15_000;

/** Polls /api/trains and keeps trainStore in sync; returns the latest snapshot. */
export function useTrainPositions() {
  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const response = await fetch("/api/trains");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const { trains, stale, error, updatedAt } = await response.json();
        if (cancelled) return;
        if (error) {
          setFeedStatus("error");
          recordPoll({ error, serverUpdatedAt: updatedAt });
          return;
        }
        reconcileTrains(trains);
        setFeedStatus(stale ? "stale" : "live");
        recordPoll({ serverUpdatedAt: updatedAt, trainCount: trains.length });
      } catch (err) {
        if (!cancelled) {
          setFeedStatus("error");
          recordPoll({ error: String(err?.message ?? err) });
        }
      }
    }

    poll();
    const id = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const trains = useSyncExternalStore(subscribe, getTrains);
  const feedStatus = useSyncExternalStore(subscribe, getFeedStatus);
  const diagnostics = useSyncExternalStore(subscribe, getDiagnostics);
  return { trains, feedStatus, diagnostics };
}
