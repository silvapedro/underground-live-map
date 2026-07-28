import lineNames from "../data/line-names.json";

function formatEta(etaSeconds) {
  if (etaSeconds < 1) return "due";
  if (etaSeconds < 60) return `${Math.ceil(etaSeconds)}s`;
  const m = Math.floor(etaSeconds / 60);
  const s = Math.round(etaSeconds % 60);
  return `${m}m ${String(s).padStart(2, "0")}s`;
}

/** Station names carry per-mode suffixes ("X Station", "X Tram Stop") that just eat
 * tooltip width; strip them for display only. */
function shortName(name) {
  return name
    .replace(/&amp;/g, "&")
    .replace(/ (Underground |Rail |DLR )?Station$/, "")
    .replace(/ Tram Stop$/, "");
}

/**
 * Shared hover/click tooltip for both rendering modes. `info` is either null or
 * {train, x, y, locked, etaNow} where x/y are CSS pixels relative to the map
 * container and etaNow is the live (per-frame) countdown to the next station.
 */
export default function TrainTooltip({ info }) {
  if (!info) return null;
  const { train, x, y, locked } = info;
  const lineName = lineNames[train.lineId] ?? train.lineId;
  const flip = x > (info.containerWidth ?? 1e9) * 0.6;
  const eta = formatEta(info.etaNow ?? train.etaSeconds);

  const journey = train.atPlatform
    ? `at ${shortName(train.toStation)}`
    : train.fromStation === train.toStation
      ? `approaching ${shortName(train.toStation)} · ${eta}`
      : `${shortName(train.fromStation)} → ${shortName(train.toStation)} · ${eta}`;

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        top: 0,
        transform: flip
          ? `translate(${x - 14}px, ${y - 14}px) translateX(-100%)`
          : `translate(${x + 14}px, ${y - 14}px)`,
        pointerEvents: "none",
        background: "rgba(11,15,26,0.94)",
        border: "1px solid #263353",
        borderRadius: 10,
        padding: "8px 12px",
        fontSize: 12,
        minWidth: 170,
        color: "#e8ecf2",
        boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
        zIndex: 10,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 2 }}>
        <span style={{ fontWeight: 700 }}>{lineName} line</span>
        {locked && <span style={{ marginLeft: "auto", fontSize: 10 }}>📌</span>}
      </div>
      <div style={{ color: "#6b7688", fontSize: 10, marginBottom: 4 }}>
        Train {train.vehicleId}
      </div>
      <div style={{ color: "#aab4c5" }}>toward {shortName(train.destination)}</div>
      <div style={{ color: "#9fd0ff", fontSize: 11, marginTop: 2, fontVariantNumeric: "tabular-nums" }}>
        {journey}
      </div>
    </div>
  );
}
