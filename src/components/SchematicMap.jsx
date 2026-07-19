import { useEffect, useMemo, useRef, useState } from "react";
import { select } from "d3-selection";
import { line as d3Line } from "d3-shape";
import { zoom as d3Zoom, zoomIdentity } from "d3-zoom";

import schematicStations from "../data/schematic-stations.json";
import viewBox from "../data/schematic-viewbox.json";
import lineSequences from "../data/line-sequences.json";
import lineColors from "../data/line-colors.json";
import { lookupStationPoint, resolveSchematicPoint } from "../lib/coords";
import { getTrains } from "../lib/trainStore";
import TrainTooltip from "./TrainTooltip.jsx";

// viewBox height is derived (not guessed) from the network's true aspect ratio --
// see bin/build_schematic_layout.py -- so the diagram fills the canvas on both axes.
const { width: VIEW_W, height: VIEW_H } = viewBox;
const SVG_NS = "http://www.w3.org/2000/svg";
const HOVER_RADIUS_PX = 14; // screen pixels, converted to local units by the zoom scale

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

export default function SchematicMap({ visibleLines }) {
  const containerRef = useRef(null);
  const svgRef = useRef(null);
  const zoomGroupRef = useRef(null);
  const trainsGroupRef = useRef(null);
  const [tooltip, setTooltip] = useState(null);

  // The animation-loop effect below mounts once ([] deps); it reads visibility through
  // this ref, kept in sync separately, rather than restarting the loop on every toggle.
  const visibleLinesRef = useRef(visibleLines);
  useEffect(() => {
    visibleLinesRef.current = visibleLines;
  }, [visibleLines]);

  const allLinePaths = useMemo(buildLinePaths, []);
  const linePaths = allLinePaths.filter(({ lineId }) => visibleLines.has(lineId));
  const stationPoints = useMemo(
    () =>
      Object.entries(schematicStations).map(([name, keys]) => [
        name,
        keys["*"] ?? Object.values(keys)[0],
      ]),
    [],
  );

  // Pan/zoom: d3-zoom drives a transform on the inner <g>, React never re-renders for it.
  const zoomScaleRef = useRef(1);
  useEffect(() => {
    const svg = select(svgRef.current);
    const zoomGroup = select(zoomGroupRef.current);
    const behavior = d3Zoom()
      .scaleExtent([0.6, 8])
      .on("zoom", (event) => {
        zoomGroup.attr("transform", event.transform);
        zoomScaleRef.current = event.transform.k;
      });
    svg.call(behavior).call(behavior.transform, zoomIdentity);
    return () => svg.on(".zoom", null);
  }, []);

  // Train animation loop: imperative SVG DOM writes at 60fps, same perf reasoning as
  // GeoMap's per-frame deck.gl layer rebuild -- must not go through React state.
  const latestPositionedRef = useRef([]);
  const lockedIdRef = useRef(null);
  const hoveredIdRef = useRef(null);

  useEffect(() => {
    let rafId;
    const tick = () => {
      const now = Date.now();
      const group = trainsGroupRef.current;
      const positioned = [];
      for (const train of getTrains()) {
        if (!visibleLinesRef.current.has(train.lineId)) continue;
        const point = resolveSchematicPoint(schematicStations, train, now);
        if (point) positioned.push({ train, point });
      }
      latestPositionedRef.current = positioned;

      if (group) {
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

      const activeId = lockedIdRef.current ?? hoveredIdRef.current;
      const active = activeId != null ? positioned.find((d) => d.train.id === activeId) : null;
      if (active && svgRef.current && zoomGroupRef.current && containerRef.current) {
        const pt = svgRef.current.createSVGPoint();
        pt.x = active.point[0];
        pt.y = active.point[1];
        const screenPt = pt.matrixTransform(zoomGroupRef.current.getScreenCTM());
        const rect = containerRef.current.getBoundingClientRect();
        setTooltip({
          train: active.train,
          x: screenPt.x - rect.left,
          y: screenPt.y - rect.top,
          locked: lockedIdRef.current != null,
          containerWidth: rect.width,
        });
      } else {
        setTooltip((prev) => (prev ? null : prev));
      }

      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(rafId);
  }, []);

  function nearestTrainId(clientX, clientY) {
    if (!svgRef.current || !zoomGroupRef.current) return null;
    const pt = svgRef.current.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const local = pt.matrixTransform(zoomGroupRef.current.getScreenCTM().inverse());
    const radius = HOVER_RADIUS_PX / zoomScaleRef.current;

    let bestId = null;
    let bestDistSq = radius * radius;
    for (const { train, point } of latestPositionedRef.current) {
      const dx = point[0] - local.x;
      const dy = point[1] - local.y;
      const distSq = dx * dx + dy * dy;
      if (distSq < bestDistSq) {
        bestDistSq = distSq;
        bestId = train.id;
      }
    }
    return bestId;
  }

  return (
    <div ref={containerRef} style={{ position: "absolute", inset: 0 }}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        style={{ width: "100%", height: "100%", background: "#0A0D16", display: "block" }}
        onMouseMove={(e) => {
          hoveredIdRef.current = nearestTrainId(e.clientX, e.clientY);
        }}
        onMouseLeave={() => {
          hoveredIdRef.current = null;
        }}
        onClick={(e) => {
          const id = nearestTrainId(e.clientX, e.clientY);
          lockedIdRef.current = lockedIdRef.current === id ? null : id;
        }}
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
      <TrainTooltip info={tooltip} />
    </div>
  );
}
