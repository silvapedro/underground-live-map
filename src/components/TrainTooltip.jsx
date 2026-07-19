import lineNames from "../data/line-names.json";

function formatEta(etaSeconds) {
  if (etaSeconds <= 0) return "due";
  if (etaSeconds >= 60) return `${Math.round(etaSeconds / 60)} min`;
  return `${Math.round(etaSeconds)}s`;
}

/**
 * Shared hover/click tooltip for both rendering modes. `info` is either null or
 * {train, x, y, locked} where x/y are CSS pixels relative to the map container.
 */
export default function TrainTooltip({ info }) {
  if (!info) return null;
  const { train, x, y, locked } = info;
  const lineName = lineNames[train.lineId] ?? train.lineId;
  const flip = x > (info.containerWidth ?? 1e9) * 0.6;

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
      <div style={{ color: "#aab4c5" }}>toward {train.destination}</div>
      <div style={{ color: "#6b7688", fontSize: 11, marginTop: 2 }}>
        {train.atPlatform ? "at " : "next: "}
        {train.toStation} · {formatEta(train.etaSeconds)}
      </div>
    </div>
  );
}
