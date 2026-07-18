import { useEffect, useSyncExternalStore } from "react";
import {
  getFeedStatus,
  getTrains,
  reconcileTrains,
  setFeedStatus,
  subscribe,
} from "../lib/trainStore";

const POLL_INTERVAL_MS = 15_000;

/** Polls /api/trains and keeps trainStore in sync; returns the latest snapshot. */
export function useTrainPositions() {
  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const response = await fetch("/api/trains");
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const { trains, stale, error } = await response.json();
        if (cancelled) return;
        if (error) {
          setFeedStatus("error");
          return;
        }
        reconcileTrains(trains);
        setFeedStatus(stale ? "stale" : "live");
      } catch {
        if (!cancelled) setFeedStatus("error");
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
  return { trains, feedStatus };
}
