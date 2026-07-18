import lineColors from "../data/line-colors.json";
import lineNames from "../data/line-names.json";

// Display order roughly matches the physical map's north-to-south / west-to-east
// familiarity rather than alphabetical, but any stable order is fine here.
const LINE_ORDER = Object.keys(lineNames);

export default function LineLegend() {
  return (
    <div
      style={{
        display: "flex",
        flexWrap: "wrap",
        gap: "6px 14px",
        padding: "10px 18px",
        fontSize: 11,
        color: "#8a94a6",
      }}
    >
      {LINE_ORDER.map((lineId) => (
        <span key={lineId} style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span
            style={{
              width: 18,
              height: 4,
              borderRadius: 2,
              background: lineColors[lineId],
              display: "inline-block",
            }}
          />
          {lineNames[lineId]}
        </span>
      ))}
    </div>
  );
}
