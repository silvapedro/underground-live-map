import { useState } from "react";
import GeoMap from "./components/GeoMap.jsx";
import SchematicMap from "./components/SchematicMap.jsx";
import ModeSwitcher from "./components/ModeSwitcher.jsx";
import LineLegend from "./components/LineLegend.jsx";
import { useTrainPositions } from "./hooks/useTrainPositions.js";

// Both renderers stay mounted always and crossfade via opacity, rather than being
// conditionally rendered: switching modes can't geometrically morph across a
// WebGL-canvas/SVG boundary (see src/lib/coords.js), so instead both keep animating
// live underneath and the mode switch just fades between them.
function fadeStyle(active) {
  return {
    position: "absolute",
    inset: 0,
    opacity: active ? 1 : 0,
    pointerEvents: active ? "auto" : "none",
    transition: "opacity 400ms ease",
  };
}

const STATUS_LABEL = {
  connecting: "connecting…",
  live: "live",
  stale: "stale · reconnecting",
  error: "offline · reconnecting",
};

const STATUS_COLOR = {
  connecting: "#6b7688",
  live: "#4CAF50",
  stale: "#FFC107",
  error: "#E32017",
};

export default function App() {
  const [mode, setMode] = useState("geo");
  const { trains, feedStatus } = useTrainPositions();

  return (
    <div
      style={{
        height: "100%",
        width: "100%",
        display: "flex",
        flexDirection: "column",
        background: "#0A0D16",
        color: "#e8ecf2",
      }}
    >
      <header
        style={{
          display: "flex",
          alignItems: "center",
          gap: 14,
          padding: "14px 18px",
          borderBottom: "1px solid #161f33",
          flexWrap: "wrap",
        }}
      >
        <svg width="26" height="26" viewBox="0 0 100 100" aria-hidden="true">
          <circle cx="50" cy="50" r="34" fill="none" stroke="#E32017" strokeWidth="13" />
          <rect x="6" y="42" width="88" height="16" fill="#10069F" />
        </svg>
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.1 }}>
          <span
            style={{
              fontSize: 14,
              fontWeight: 700,
              letterSpacing: "0.14em",
              textTransform: "uppercase",
            }}
          >
            Underground Live
          </span>
          <span style={{ fontSize: 11, color: STATUS_COLOR[feedStatus] }}>
            ● {STATUS_LABEL[feedStatus]} · {trains.length} trains
          </span>
        </div>
        <div style={{ marginLeft: "auto" }}>
          <ModeSwitcher mode={mode} onChange={setMode} />
        </div>
      </header>

      <div style={{ position: "relative", flex: 1, minHeight: 0 }}>
        <div style={fadeStyle(mode === "geo")}>
          <GeoMap />
        </div>
        <div style={fadeStyle(mode === "schematic")}>
          <SchematicMap />
        </div>
      </div>

      <footer style={{ borderTop: "1px solid #161f33" }}>
        <LineLegend />
      </footer>
    </div>
  );
}
