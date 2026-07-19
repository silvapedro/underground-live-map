import lineColors from "../data/line-colors.json";
import lineNames from "../data/line-names.json";

// Display order roughly matches the physical map's north-to-south / west-to-east
// familiarity rather than alphabetical, but any stable order is fine here.
const LINE_ORDER = Object.keys(lineNames);

/** Doubles as the line-visibility control: click a line to toggle it on/off. */
export default function LineLegend({ visibleLines, onToggle }) {
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
      {LINE_ORDER.map((lineId) => {
        const visible = visibleLines.has(lineId);
        return (
          <button
            key={lineId}
            onClick={() => onToggle(lineId)}
            title={visible ? "Click to hide" : "Click to show"}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              background: "none",
              border: "none",
              padding: 0,
              cursor: "pointer",
              font: "inherit",
              color: visible ? "#8a94a6" : "#4f5a70",
              opacity: visible ? 1 : 0.55,
            }}
          >
            <span
              style={{
                width: 18,
                height: 4,
                borderRadius: 2,
                background: visible ? lineColors[lineId] : "#4f5a70",
                display: "inline-block",
              }}
            />
            {lineNames[lineId]}
          </button>
        );
      })}
    </div>
  );
}
