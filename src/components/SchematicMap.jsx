import { useEffect, useMemo, useRef, useState } from "react";
import { select } from "d3-selection";
import { line as d3Line } from "d3-shape";
import { zoom as d3Zoom, zoomIdentity } from "d3-zoom";

import schematicStations from "../data/schematic-stations.json";
import viewBox from "../data/schematic-viewbox.json";
import lineSequences from "../data/line-sequences.json";
import lineColors from "../data/line-colors.json";
import {
  liveEtaSeconds,
  lookupStationPoint,
  prefersReducedMotion,
  resolveSchematicPoint,
} from "../lib/coords";
import { createMotionSmoother } from "../lib/motion";
import { getTrains } from "../lib/trainStore";
import TrainTooltip from "./TrainTooltip.jsx";
import StationBoard from "./StationBoard.jsx";

// viewBox height is derived (not guessed) from the network's true aspect ratio --
// see bin/build_schematic_layout.py -- so the diagram fills the canvas on both axes.
const { width: VIEW_W, height: VIEW_H } = viewBox;
const SVG_NS = "http://www.w3.org/2000/svg";
const HOVER_RADIUS_PX = 14; // screen pixels, converted to local units by the zoom scale

// Fare-zone band fills, Zone 1 (centre, lightest) → Zone 6 (edge, darkest).
const ZONE_FILL = ["#39456a", "#313c5c", "#2a334e", "#232b41", "#1d2436", "#171d2c"];


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
  const highlightRef = useRef(null);
  const [tooltip, setTooltip] = useState(null);
  const [stationInfo, setStationInfo] = useState(null);

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

  // Approximate fare-zone rings: concentric circles centred on the network centroid,
  // for spatial context on an otherwise empty dark backdrop. Not the real (irregular)
  // zone boundaries -- a legibility aid, hence "~Zone N".
  const zones = useMemo(() => {
    const pts = stationPoints.map(([, p]) => p);
    const cx = pts.reduce((s, p) => s + p[0], 0) / pts.length;
    const cy = pts.reduce((s, p) => s + p[1], 0) / pts.length;
    const dists = pts.map((p) => Math.hypot(p[0] - cx, p[1] - cy)).sort((a, b) => a - b);
    const maxR = dists[Math.floor(dists.length * 0.96)]; // clip a few far outliers
    const N = 6;
    return {
      cx,
      cy,
      rings: Array.from({ length: N }, (_, i) => ({ r: (maxR * (i + 1)) / N, zone: i + 1 })),
    };
  }, [stationPoints]);

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
    let lastFrameMs = 0;
    const reduceMotion = prefersReducedMotion();
    // viewBox units: sub-0.02 movement per frame is stillness, not a heading change.
    const smoother = createMotionSmoother({ angleEpsilon: 0.02 });

    // Each train renders as a <g>: soft glow halo, coloured core dot, and a white
    // heading triangle rotated to the direction of actual displayed movement.
    function makeTrainNode() {
      const g = document.createElementNS(SVG_NS, "g");
      const glow = document.createElementNS(SVG_NS, "circle");
      glow.setAttribute("r", "8");
      const core = document.createElementNS(SVG_NS, "circle");
      core.setAttribute("r", "4");
      core.setAttribute("stroke", "#ffffff");
      core.setAttribute("stroke-width", "1");
      const arrow = document.createElementNS(SVG_NS, "polygon");
      arrow.setAttribute("points", "4.2,0 -2.6,2.8 -2.6,-2.8"); // points right at 0deg
      arrow.setAttribute("fill", "#ffffff");
      g.append(glow, core, arrow);
      return g;
    }

    const tick = () => {
      const now = Date.now();
      const dtS = lastFrameMs ? Math.min(0.1, (now - lastFrameMs) / 1000) : 0.016;
      lastFrameMs = now;
      const pulse = reduceMotion ? 1 : 0.8 + 0.2 * Math.sin(now / 240);

      // Train nodes live inside the zoomed <g>, so counter-scale them by 1/k to keep
      // markers a constant screen size -- the same job vector-effect does for strokes,
      // which SVG has no equivalent of for a circle radius or polygon.
      const invScale = 1 / (zoomScaleRef.current || 1);

      const group = trainsGroupRef.current;
      const positioned = [];
      const seenIds = new Set();
      for (const train of getTrains()) {
        if (!visibleLinesRef.current.has(train.lineId)) continue;
        const target = resolveSchematicPoint(schematicStations, train, now);
        if (!target) continue;
        const eased = smoother.step(train.id, target[0], target[1], dtS);
        // eased.angleDeg is atan2(dy, dx) with SVG's y-down axis, which is exactly
        // what SVG rotate() (clockwise-positive) expects -- no conversion needed.
        positioned.push({ train, point: [eased.x, eased.y], angleDeg: eased.angleDeg });
        seenIds.add(train.id);
      }
      smoother.prune(seenIds);
      latestPositionedRef.current = positioned;

      if (group) {
        while (group.children.length < positioned.length) {
          group.appendChild(makeTrainNode());
        }
        while (group.children.length > positioned.length) {
          group.removeChild(group.lastChild);
        }
        positioned.forEach(({ train, point, angleDeg }, i) => {
          const g = group.children[i];
          const [glow, core, arrow] = g.children;
          const color = lineColors[train.lineId] ?? "#cfd8e6";
          g.setAttribute("transform", `translate(${point[0]} ${point[1]}) scale(${invScale})`);
          glow.setAttribute("fill", color);
          glow.setAttribute("opacity", (0.28 * pulse).toFixed(3));
          core.setAttribute("fill", color);
          if (angleDeg == null) {
            arrow.setAttribute("display", "none");
          } else {
            arrow.removeAttribute("display");
            arrow.setAttribute("transform", `rotate(${angleDeg.toFixed(1)})`);
          }
        });
      }

      const activeId = lockedIdRef.current ?? hoveredIdRef.current;
      const active = activeId != null ? positioned.find((d) => d.train.id === activeId) : null;

      // Highlight ring rides along with the hovered/pinned train (counter-scaled to
      // stay a constant screen size, like the train nodes).
      const ring = highlightRef.current;
      if (ring) {
        if (active) {
          const pinned = lockedIdRef.current != null;
          ring.setAttribute(
            "transform",
            `translate(${active.point[0]} ${active.point[1]}) scale(${invScale})`,
          );
          ring.setAttribute("stroke", pinned ? "#ffffff" : "rgba(255,255,255,0.6)");
          ring.setAttribute("stroke-width", pinned ? "2" : "1.3");
          ring.removeAttribute("display");
        } else {
          ring.setAttribute("display", "none");
        }
      }

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
          etaNow: liveEtaSeconds(active.train, now),
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

  function nearestStationName(clientX, clientY) {
    if (!svgRef.current || !zoomGroupRef.current) return null;
    const pt = svgRef.current.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const local = pt.matrixTransform(zoomGroupRef.current.getScreenCTM().inverse());
    const radius = HOVER_RADIUS_PX / zoomScaleRef.current;

    let bestName = null;
    let bestDistSq = radius * radius;
    for (const [name, [x, y]] of stationPoints) {
      const dx = x - local.x;
      const dy = y - local.y;
      const distSq = dx * dx + dy * dy;
      if (distSq < bestDistSq) {
        bestDistSq = distSq;
        bestName = name;
      }
    }
    return bestName;
  }

  // Train hover wins; if no train is near, fall back to the station board.
  function onMove(e) {
    const trainId = nearestTrainId(e.clientX, e.clientY);
    hoveredIdRef.current = trainId;
    if (trainId) {
      if (stationInfo) setStationInfo(null);
      return;
    }
    const name = nearestStationName(e.clientX, e.clientY);
    if (!name) {
      if (stationInfo) setStationInfo(null);
    } else {
      const rect = containerRef.current.getBoundingClientRect();
      setStationInfo({
        name,
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
        containerWidth: rect.width,
      });
    }
  }

  return (
    <div ref={containerRef} style={{ position: "absolute", inset: 0 }}>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
        style={{ width: "100%", height: "100%", display: "block" }}
        onMouseMove={onMove}
        onMouseLeave={() => {
          hoveredIdRef.current = null;
          setStationInfo(null);
        }}
        onClick={(e) => {
          const id = nearestTrainId(e.clientX, e.clientY);
          lockedIdRef.current = lockedIdRef.current === id ? null : id;
        }}
      >
        {/* Darkest base fills the whole viewport (beyond the outermost zone). */}
        <rect x="0" y="0" width={VIEW_W} height={VIEW_H} fill="#12172a" />
        <g ref={zoomGroupRef}>
          {/* Filled concentric fare-zone bands -- lightest at the centre (Zone 1),
              darkening outward, for a readable "zone map" backdrop. Approximate
              (real zone boundaries are irregular); drawn largest-first so inner,
              lighter bands paint on top. */}
          {[...zones.rings].reverse().map(({ r, zone }) => (
            <circle
              key={`band-${zone}`}
              cx={zones.cx}
              cy={zones.cy}
              r={r}
              fill={ZONE_FILL[zone - 1]}
              stroke="#3f496a"
              strokeWidth={1}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {zones.rings.map(({ r, zone }) => (
            <text
              key={`zlabel-${zone}`}
              x={zones.cx}
              y={zones.cy - r + 9}
              fill="#8792a8"
              fontSize={8}
              textAnchor="middle"
              opacity={0.6}
            >
              {`Zone ${zone}`}
            </text>
          ))}
          {/* vector-effect: non-scaling-stroke keeps every width in SCREEN pixels, so
              zooming in doesn't balloon lines and glow into giant blobs. */}
          {/* Wide low-opacity underlay first: the soft glow beneath every line. */}
          {linePaths.map(({ lineId, points }, i) => (
            <path
              key={`glow-${lineId}-${i}`}
              d={lineGenerator(points)}
              fill="none"
              stroke={lineColors[lineId] ?? "#888"}
              strokeWidth={9}
              strokeLinejoin="round"
              strokeLinecap="round"
              opacity={0.18}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {linePaths.map(({ lineId, points }, i) => (
            <path
              key={`${lineId}-${i}`}
              d={lineGenerator(points)}
              fill="none"
              stroke={lineColors[lineId] ?? "#888"}
              strokeWidth={3.5}
              strokeLinejoin="round"
              strokeLinecap="round"
              opacity={0.85}
              vectorEffect="non-scaling-stroke"
            />
          ))}
          {/* A zero-length round-capped stroke renders as a screen-constant dot --
              circles have no non-scaling equivalent for their radius. */}
          {stationPoints.map(([name, [x, y]]) => (
            <path
              key={name}
              d={`M ${x} ${y} h 0.001`}
              stroke="#cfd8e6"
              strokeWidth={5}
              strokeLinecap="round"
              vectorEffect="non-scaling-stroke"
            />
          ))}
          <g ref={trainsGroupRef} />
          <circle ref={highlightRef} r={9} fill="none" display="none" pointerEvents="none" />
        </g>
      </svg>
      <TrainTooltip info={tooltip} />
      {!tooltip && <StationBoard info={stationInfo} />}
    </div>
  );
}
