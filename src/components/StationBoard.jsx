import { useEffect, useState } from "react";
import lineColors from "../data/line-colors.json";
import lineNames from "../data/line-names.json";
import { stationArrivals } from "../lib/arrivals";
import { getTrains } from "../lib/trainStore";

function shortName(name) {
  return name
    .replace(/&amp;/g, "&")
    .replace(/ (Underground |Rail |DLR )?Station$/, "")
    .replace(/ Tram Stop$/, "");
}

function formatEta(s) {
  if (s < 30) return "due";
  if (s < 60) return `${Math.ceil(s)}s`;
  return `${Math.round(s / 60)} min`;
}

/**
 * Platform-style arrivals board shown when hovering a station. `info` is null or
 * {name, x, y, containerWidth}. Recomputes ETAs every second so the board ticks.
 */
export default function StationBoard({ info }) {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!info) return;
    const id = setInterval(() => setTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [info]);

  if (!info) return null;
  // Read live trains directly: the host map components are imperative and don't
  // re-render on store changes, but this board re-renders on its own 1s tick.
  const arrivals = stationArrivals(getTrains(), info.name, Date.now(), 6);
  const flip = info.x > (info.containerWidth ?? 1e9) * 0.6;

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        transform: flip
          ? `translate(${info.x - 16}px, ${info.y - 14}px) translateX(-100%)`
          : `translate(${info.x + 16}px, ${info.y - 14}px)`,
        pointerEvents: "none",
        background: "rgba(11,15,26,0.96)",
        border: "1px solid #263353",
        borderRadius: 10,
        padding: "9px 12px",
        fontSize: 12,
        minWidth: 210,
        color: "#e8ecf2",
        boxShadow: "0 8px 24px rgba(0,0,0,0.55)",
        zIndex: 12,
      }}
    >
      <div style={{ fontWeight: 700, marginBottom: 6 }}>{shortName(info.name)}</div>
      {arrivals.length === 0 ? (
        <div style={{ color: "#6b7688" }}>No trains due</div>
      ) : (
        arrivals.map((a) => (
          <div
            key={a.id}
            style={{ display: "flex", alignItems: "center", gap: 8, padding: "2px 0" }}
          >
            <span
              style={{
                width: 9, height: 9, borderRadius: 9, flexShrink: 0,
                background: lineColors[a.lineId] ?? "#888",
                boxShadow: "0 0 0 1px rgba(255,255,255,0.25)",
              }}
              title={lineNames[a.lineId] ?? a.lineId}
            />
            <span style={{ flex: 1, color: "#cbd4e2", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {shortName(a.destination)}
            </span>
            <span style={{ color: "#9fd0ff", fontVariantNumeric: "tabular-nums", flexShrink: 0 }}>
              {a.atPlatform ? "here" : formatEta(a.eta)}
            </span>
          </div>
        ))
      )}
    </div>
  );
}
