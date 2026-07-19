import { useEffect, useRef, useState } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { PathLayer, ScatterplotLayer } from "@deck.gl/layers";
import { TripsLayer } from "@deck.gl/geo-layers";

import geoStations from "../data/geo-stations.json";
import lineSequences from "../data/line-sequences.json";
import lineColors from "../data/line-colors.json";
import { lookupStationPoint, resolveGeoPoint } from "../lib/coords";
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
    const geoLinePaths = buildGeoLinePaths();

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
      const sampleTrail = now - lastSampleMs >= TRAIL_SAMPLE_MS;
      if (sampleTrail) lastSampleMs = now;

      // Resolved once per frame (not per accessor call): each train's real-world
      // [lng, lat] extrapolated from its last fromStation/toStation/fraction poll.
      // geo-stations.json stores [lat, lng]; deck.gl positions are [lng, lat].
      const positioned = [];
      const seenIds = new Set();
      for (const train of getTrains()) {
        if (!visibleLinesRef.current.has(train.lineId)) continue;
        const point = resolveGeoPoint(geoStations, train, now);
        if (!point) continue;
        const lngLat = [point[1], point[0]];
        positioned.push({ train, lngLat });
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

      const scatterLayer = new ScatterplotLayer({
        id: "trains",
        data: positioned,
        pickable: true,
        radiusUnits: "pixels",
        getRadius: 5,
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

      // Draw order: tracks underneath, then fading trails, then the train dots on top.
      overlay.setProps({ layers: [linesLayer, tripsLayer, scatterLayer] });

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
