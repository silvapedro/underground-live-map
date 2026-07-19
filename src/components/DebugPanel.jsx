import { useEffect, useRef, useState } from "react";
import { POLL_INTERVAL_MS } from "../hooks/useTrainPositions.js";
import { neighborToward } from "../lib/lineGraph.js";

// Classify a train the way effectiveSegment does, for the moving/pinned breakdown.
function classify(train) {
  if (train.fromStation !== train.toStation) return "moving";
  if (train.atPlatform) return "platform";
  return neighborToward(train.lineId, train.toStation, train.destination) ? "moving" : "pinned";
}

function useFps() {
  const [fps, setFps] = useState(0);
  useEffect(() => {
    let raf, frames = 0, last = performance.now();
    const loop = (now) => {
      frames++;
      if (now - last >= 1000) {
        setFps(Math.round((frames * 1000) / (now - last)));
        frames = 0;
        last = now;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);
  return fps;
}

// Re-render once a second so the "Xs ago" clocks tick.
function useNow(active) {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [active]);
  return Date.now();
}

const STATUS_COLOR = { connecting: "#6b7688", live: "#4CAF50", stale: "#FFC107", error: "#E32017" };

function Row({ label, value, color }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", gap: 12, padding: "2px 0" }}>
      <span style={{ color: "#8a94a6" }}>{label}</span>
      <span style={{ color: color ?? "#e8ecf2", fontVariantNumeric: "tabular-nums" }}>{value}</span>
    </div>
  );
}

export default function DebugPanel({ trains, visibleLines, feedStatus, diagnostics }) {
  const [open, setOpen] = useState(false);
  const fps = useFps();
  const now = useNow(open);
  const pollRef = useRef();

  const visible = trains.filter((t) => visibleLines.has(t.lineId));
  const counts = { moving: 0, platform: 0, pinned: 0 };
  for (const t of visible) counts[classify(t)]++;

  const secsAgo = diagnostics.lastPollAtMs ? Math.round((now - diagnostics.lastPollAtMs) / 1000) : null;
  const dataAge = diagnostics.serverUpdatedAt ? Math.round(now / 1000 - diagnostics.serverUpdatedAt) : null;
  const nextPollIn = diagnostics.lastPollAtMs
    ? Math.max(0, Math.round((diagnostics.lastPollAtMs + POLL_INTERVAL_MS - now) / 1000))
    : null;

  return (
    <div style={{ position: "absolute", top: 12, right: 12, zIndex: 20, fontSize: 12 }}>
      <button
        onClick={() => setOpen((o) => !o)}
        title="Diagnostics"
        style={{
          display: "flex", alignItems: "center", gap: 6, marginLeft: "auto",
          padding: "6px 10px", borderRadius: 8, cursor: "pointer",
          background: "rgba(11,15,26,0.9)", border: "1px solid #263353", color: "#aab4c5",
        }}
      >
        <span style={{ color: STATUS_COLOR[feedStatus] }}>●</span> Debug {open ? "▸" : "◂"}
      </button>

      {open && (
        <div
          ref={pollRef}
          style={{
            marginTop: 8, width: 250, padding: "12px 14px", borderRadius: 10,
            background: "rgba(11,15,26,0.95)", border: "1px solid #263353",
            boxShadow: "0 8px 24px rgba(0,0,0,0.5)", backdropFilter: "blur(4px)",
          }}
        >
          <div style={{ fontWeight: 700, marginBottom: 8, letterSpacing: "0.06em", color: "#cfd8e6" }}>
            LIVE FEED
          </div>
          <Row label="Status" value={feedStatus} color={STATUS_COLOR[feedStatus]} />
          <Row label="Endpoint" value="/api/trains" />
          <Row label="Polls" value={diagnostics.pollCount} />
          <Row label="Last poll" value={secsAgo == null ? "—" : `${secsAgo}s ago`} />
          <Row label="Next poll" value={nextPollIn == null ? "—" : `in ${nextPollIn}s`} />
          <Row label="Data age" value={dataAge == null ? "—" : `${dataAge}s`} />
          {diagnostics.lastError && <Row label="Error" value={diagnostics.lastError} color="#E32017" />}

          <div style={{ height: 1, background: "#1a2338", margin: "10px 0" }} />
          <div style={{ fontWeight: 700, marginBottom: 8, letterSpacing: "0.06em", color: "#cfd8e6" }}>
            TRAINS
          </div>
          <Row label="Total (feed)" value={diagnostics.lastTrainCount} />
          <Row label="Visible" value={visible.length} />
          <Row label="Gliding" value={counts.moving} color="#9fd0ff" />
          <Row label="At platform" value={counts.platform} />
          <Row label="Pinned (no route)" value={counts.pinned} color={counts.pinned ? "#FFC107" : undefined} />

          <div style={{ height: 1, background: "#1a2338", margin: "10px 0" }} />
          <div style={{ fontWeight: 700, marginBottom: 8, letterSpacing: "0.06em", color: "#cfd8e6" }}>
            RENDER
          </div>
          <Row label="FPS" value={fps} color={fps >= 50 ? "#4CAF50" : fps >= 30 ? "#FFC107" : "#E32017"} />
          <Row label="Reduced motion" value={window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "on" : "off"} />
        </div>
      )}
    </div>
  );
}
