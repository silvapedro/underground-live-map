import { useEffect, useMemo, useRef } from "react";
import { select } from "d3-selection";
import { line as d3Line } from "d3-shape";
import { zoom as d3Zoom, zoomIdentity } from "d3-zoom";

import schematicStations from "../data/schematic-stations.json";
import viewBox from "../data/schematic-viewbox.json";
import lineSequences from "../data/line-sequences.json";
import lineColors from "../data/line-colors.json";
import { lookupStationPoint, resolveSchematicPoint } from "../lib/coords";
import { getTrains } from "../lib/trainStore";

// viewBox height is derived (not guessed) from the network's true aspect ratio --
// see bin/build_schematic_layout.py -- so the diagram fills the canvas on both axes.
const { width: VIEW_W, height: VIEW_H } = viewBox;
const SVG_NS = "http://www.w3.org/2000/svg";

const lineGenerator = d3Line();

/** Each line's branches, resolved to schematic points once -- station order and
 * coordinates don't change at runtime, so this never needs to be recomputed. */
function buildLinePaths() {
  const paths = [];
  for (const [lineId, { branches }] of Object.entries(lineSequences)) {
    for (const branch of branches) {
      const points = branch
        .map((name) => lookupStationPoint(schematicStations, name, lineId))
        .filter(Boolean);
      if (points.length >= 2) paths.push({ lineId, points });
    }
  }
  return paths;
}

export default function SchematicMap() {
  const svgRef = useRef(null);
  const zoomGroupRef = useRef(null);
  const trainsGroupRef = useRef(null);

  const linePaths = useMemo(buildLinePaths, []);
  const stationPoints = useMemo(
    () =>
      Object.entries(schematicStations).map(([name, keys]) => [
        name,
        keys["*"] ?? Object.values(keys)[0],
      ]),
    [],
  );

  // Pan/zoom: d3-zoom drives a transform on the inner <g>, React never re-renders for it.
  useEffect(() => {
    const svg = select(svgRef.current);
    const zoomGroup = select(zoomGroupRef.current);
    const behavior = d3Zoom()
      .scaleExtent([0.6, 8])
      .on("zoom", (event) => zoomGroup.attr("transform", event.transform));
    svg.call(behavior).call(behavior.transform, zoomIdentity);
    return () => svg.on(".zoom", null);
  }, []);

  // Train animation loop: imperative SVG DOM writes at 60fps, same perf reasoning as
  // GeoMap's per-frame deck.gl layer rebuild -- must not go through React state.
  useEffect(() => {
    let rafId;
    const tick = () => {
      const now = Date.now();
      const group = trainsGroupRef.current;
      if (group) {
        const positioned = [];
        for (const train of getTrains()) {
          const point = resolveSchematicPoint(schematicStations, train, now);
          if (point) positioned.push({ train, point });
        }

        while (group.children.length < positioned.length) {
          group.appendChild(document.createElementNS(SVG_NS, "circle"));
        }
        while (group.children.length > positioned.length) {
          group.removeChild(group.lastChild);
        }

        positioned.forEach(({ train, point }, i) => {
          const circle = group.children[i];
          circle.setAttribute("cx", point[0]);
          circle.setAttribute("cy", point[1]);
          circle.setAttribute("r", "4");
          circle.setAttribute("fill", lineColors[train.lineId] ?? "#cfd8e6");
        });
      }
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, []);

  return (
    <svg
      ref={svgRef}
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      style={{ width: "100%", height: "100%", background: "#0A0D16", display: "block" }}
    >
      <g ref={zoomGroupRef}>
        {linePaths.map(({ lineId, points }, i) => (
          <path
            key={`${lineId}-${i}`}
            d={lineGenerator(points)}
            fill="none"
            stroke={lineColors[lineId] ?? "#888"}
            strokeWidth={3}
            strokeLinejoin="round"
            strokeLinecap="round"
            opacity={0.85}
          />
        ))}
        {stationPoints.map(([name, [x, y]]) => (
          <circle key={name} cx={x} cy={y} r={2.5} fill="#cfd8e6" />
        ))}
        <g ref={trainsGroupRef} />
      </g>
    </svg>
  );
}
