import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { PathLayer, ScatterplotLayer, TextLayer } from "@deck.gl/layers";
import { TripsLayer } from "@deck.gl/geo-layers";

import geoStations from "../data/geo-stations.json";
import lineSequences from "../data/line-sequences.json";
import lineColors from "../data/line-colors.json";
import {
  liveEtaSeconds,
  lookupStationPoint,
  prefersReducedMotion,
  resolveGeoPoint,
} from "../lib/coords";
import { createMotionSmoother } from "../lib/motion";
import { getTrains } from "../lib/trainStore";
import TrainTooltip from "./TrainTooltip.jsx";

// No API token/signup required: https://tiles.openfreemap.org
// "liberty" (not "dark") -- the fully-black basemap made the (officially black)
// Northern line invisible, and liberty ships a ready-to-use 3D buildings layer
// (fill-extrusion, auto-enabled above zoom 14 -- tilt the map to see it).
const STYLE_URL = "https://tiles.openfreemap.org/styles/liberty";
const INITIAL_CENTER = [-0.1276, 51.5074]; // central London
const INITIAL_ZOOM = 10.2;

// Comet trail: how far back each train's fading tail reaches, and how often a new
// trail sample is recorded (recording every frame would be 60/s/train for no visual
// benefit -- TripsLayer interpolates smoothly between whatever samples it's given).
// Real subway speed only covers a handful of pixels in 2-3s at any sensible zoom, so
// this is a stylistic exaggeration -- a "wow" comet effect, not a literal speed trace.
const TRAIL_SECONDS = 25;
const TRAIL_SAMPLE_MS = 200;

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

const LINE_RGB = Object.fromEntries(
  Object.entries(lineColors).map(([lineId, hex]) => [lineId, hexToRgb(hex)]),
);
const FALLBACK_RGB = [200, 200, 200];

/** Each line's branches as real-world [lng, lat] paths, resolved once -- station
 * order and coordinates don't change at runtime. Mirrors SchematicMap's line-path
 * construction, against geo-stations.json instead of schematic-stations.json. */
function buildGeoLinePaths() {
  const paths = [];
  for (const [lineId, { branches }] of Object.entries(lineSequences)) {
    for (const branch of branches) {
      const path = branch
        .map((name) => lookupStationPoint(geoStations, name, lineId))
        .filter(Boolean)
        .map(([lat, lng]) => [lng, lat]); // deck.gl wants [lng, lat]
      if (path.length >= 2) paths.push({ lineId, path });
    }
  }
  return paths;
}

export default function GeoMap({ visibleLines }) {
  const containerRef = useRef(null);
  const [tooltip, setTooltip] = useState(null);

  // The map-setup effect below mounts once ([] deps); it reads visibility through this
  // ref, kept in sync by a separate effect, rather than depending on the prop directly
  // and re-running the whole MapLibre/deck.gl setup on every toggle.
  const visibleLinesRef = useRef(visibleLines);
  useEffect(() => {
    visibleLinesRef.current = visibleLines;
  }, [visibleLines]);

  useEffect(() => {
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE_URL,
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const resizeObserver = new ResizeObserver(() => map.resize());
    resizeObserver.observe(containerRef.current);

    // TripsLayer timestamps go into a Float32Array on the GPU; raw Unix-epoch seconds
    // (~1.8e9) are far beyond float32's ~7-significant-digit precision, so every
    // timestamp collapses to the same value and the trail never animates. Use an
    // epoch relative to mount time instead, keeping values small (0, 1, 2, ...).
    const timeOriginMs = Date.now();

    const lockedIdRef = { current: null };
    const hoveredIdRef = { current: null };
    // trainId -> [[lng, lat, tSeconds], ...], trimmed to the last TRAIL_SECONDS.
    const trails = new Map();
    let lastSampleMs = 0;
    let lastFrameMs = 0;
    const geoLinePaths = buildGeoLinePaths();
    const reduceMotion = prefersReducedMotion();
    // Degrees of lng/lat: even a slowly extrapolating train moves ~1e-6/frame, so this
    // threshold only suppresses the heading update when the train is truly stationary.
    const smoother = createMotionSmoother({ angleEpsilon: 1e-7 });

    const overlay = new MapboxOverlay({
      interleaved: true,
      layers: [],
      onHover: (info) => {
        hoveredIdRef.current = info.object?.train.id ?? null;
      },
      onClick: (info) => {
        const id = info.object?.train.id ?? null;
        lockedIdRef.current = lockedIdRef.current === id ? null : id;
      },
    });
    map.addControl(overlay);

    let rafId;
    const tick = () => {
      const now = Date.now();
      const nowS = (now - timeOriginMs) / 1000; // small relative value, see timeOriginMs above
      const dtS = lastFrameMs ? Math.min(0.1, (now - lastFrameMs) / 1000) : 0.016;
      lastFrameMs = now;
      // Soft breathing pulse on the glow halo, matching the old prototype's cadence.
      const pulse = reduceMotion ? 1 : 0.8 + 0.2 * Math.sin(now / 240);

      const sampleTrail = now - lastSampleMs >= TRAIL_SAMPLE_MS;
      if (sampleTrail) lastSampleMs = now;

      // Resolved once per frame (not per accessor call): each train's real-world
      // [lng, lat] extrapolated from its last fromStation/toStation/fraction poll,
      // then eased through the motion smoother so poll-time jumps glide instead of
      // teleporting. geo-stations.json stores [lat, lng]; deck.gl wants [lng, lat].
      const positioned = [];
      const seenIds = new Set();
      for (const train of getTrains()) {
        if (!visibleLinesRef.current.has(train.lineId)) continue;
        const point = resolveGeoPoint(geoStations, train, now);
        if (!point) continue;
        const eased = smoother.step(train.id, point[1], point[0], dtS, reduceMotion);
        const lngLat = [eased.x, eased.y];
        // eased.angleDeg is atan2(dLat, dLng): degrees CCW from east, y-up like the map.
        positioned.push({ train, lngLat, angleDeg: eased.angleDeg });
        seenIds.add(train.id);

        if (sampleTrail) {
          // lineId travels with the trail itself so its colour survives frames where
          // the owning train briefly drops out of `positioned` (e.g. a visibility
          // toggle mid-fade) -- looking lineId up from the current frame's trains
          // only made a just-hidden trail's tail flash the grey fallback colour.
          const entry = trails.get(train.id) ?? { lineId: train.lineId, path: [] };
          entry.path.push([lngLat[0], lngLat[1], nowS]);
          const cutoff = nowS - TRAIL_SECONDS;
          while (entry.path.length > 1 && entry.path[0][2] < cutoff) entry.path.shift();
          trails.set(train.id, entry);
        }
      }
      for (const id of trails.keys()) {
        if (!seenIds.has(id)) trails.delete(id);
      }
      smoother.prune(seenIds);

      const trailData = [];
      for (const { lineId, path } of trails.values()) {
        if (path.length >= 2) trailData.push({ lineId, path });
      }

      const tripsLayer = new TripsLayer({
        id: "trails",
        data: trailData,
        getPath: (d) => d.path,
        getTimestamps: (d) => d.path.map((p) => p[2]),
        getColor: (d) => LINE_RGB[d.lineId] ?? FALLBACK_RGB,
        currentTime: nowS,
        trailLength: TRAIL_SECONDS,
        fadeTrail: true,
        widthUnits: "pixels",
        widthMinPixels: 2.5,
        capRounded: true,
        jointRounded: true,
        opacity: 0.6,
      });

      // Soft pulsing halo underneath each train, in its line colour.
      const glowLayer = new ScatterplotLayer({
        id: "train-glow",
        data: positioned,
        pickable: false,
        radiusUnits: "pixels",
        getRadius: 11 * pulse,
        getFillColor: (d) => [...(LINE_RGB[d.train.lineId] ?? FALLBACK_RGB), 60],
        getPosition: (d) => d.lngLat,
        updateTriggers: { getPosition: now, getRadius: pulse },
      });

      const scatterLayer = new ScatterplotLayer({
        id: "trains",
        data: positioned,
        pickable: true,
        radiusUnits: "pixels",
        getRadius: 5.5,
        getFillColor: (d) => LINE_RGB[d.train.lineId] ?? FALLBACK_RGB,
        getPosition: (d) => d.lngLat,
        // A white outline keeps dark line colours (Northern's official black, DLR-ish
        // dark teal) visible against any basemap, light or dark.
        stroked: true,
        getLineColor: [255, 255, 255],
        lineWidthUnits: "pixels",
        getLineWidth: 1,
        // Forces deck.gl to re-read positions every frame -- they change continuously
        // via client-side extrapolation, not just when a new poll lands.
        updateTriggers: { getPosition: now },
      });

      // Heading arrow inside each dot, rotated to the direction of actual movement.
      // '▲' points north at angle 0 and TextLayer angles are CCW degrees, so a train
      // heading east (angleDeg 0, measured CCW from east) needs a -90 rotation.
      const arrowLayer = new TextLayer({
        id: "train-headings",
        data: positioned.filter((d) => d.angleDeg != null),
        pickable: false,
        characterSet: ["▲"],
        getText: () => "▲",
        getPosition: (d) => d.lngLat,
        getAngle: (d) => d.angleDeg - 90,
        getColor: [255, 255, 255, 235],
        getSize: 8,
        updateTriggers: { getPosition: now, getAngle: now },
      });

      const linesGlowLayer = new PathLayer({
        id: "tube-lines-glow",
        data: geoLinePaths.filter((p) => visibleLinesRef.current.has(p.lineId)),
        getPath: (d) => d.path,
        getColor: (d) => [...(LINE_RGB[d.lineId] ?? FALLBACK_RGB), 45],
        getWidth: 9,
        widthUnits: "pixels",
        widthMinPixels: 6,
        capRounded: true,
        jointRounded: true,
      });

      const linesLayer = new PathLayer({
        id: "tube-lines",
        data: geoLinePaths.filter((p) => visibleLinesRef.current.has(p.lineId)),
        getPath: (d) => d.path,
        getColor: (d) => [...(LINE_RGB[d.lineId] ?? FALLBACK_RGB), 170],
        getWidth: 2.5,
        widthUnits: "pixels",
        widthMinPixels: 2,
        capRounded: true,
        jointRounded: true,
      });

      // Draw order: track glow, tracks, fading trails, halo, dots, heading arrows.
      overlay.setProps({
        layers: [linesGlowLayer, linesLayer, tripsLayer, glowLayer, scatterLayer, arrowLayer],
      });

      const activeId = lockedIdRef.current ?? hoveredIdRef.current;
      const active = activeId != null ? positioned.find((d) => d.train.id === activeId) : null;
      if (active) {
        const screen = map.project(active.lngLat);
        setTooltip({
          train: active.train,
          x: screen.x,
          y: screen.y,
          locked: lockedIdRef.current != null,
          containerWidth: containerRef.current?.clientWidth,
          etaNow: liveEtaSeconds(active.train, now),
        });
      } else {
        setTooltip((prev) => (prev ? null : prev));
      }

      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafId);
      resizeObserver.disconnect();
      map.remove();
    };
  }, []);

  return (
    <div ref={containerRef} style={{ position: "absolute", inset: 0 }}>
      <TrainTooltip info={tooltip} />
    </div>
  );
}
