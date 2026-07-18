import { useEffect, useRef } from "react";
import maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { ScatterplotLayer } from "@deck.gl/layers";

import geoStations from "../data/geo-stations.json";
import lineColors from "../data/line-colors.json";
import lineNames from "../data/line-names.json";
import { resolveGeoPoint } from "../lib/coords";
import { getTrains } from "../lib/trainStore";

// No API token/signup required: https://tiles.openfreemap.org
const STYLE_URL = "https://tiles.openfreemap.org/styles/dark";
const INITIAL_CENTER = [-0.1276, 51.5074]; // central London
const INITIAL_ZOOM = 10.2;

function hexToRgb(hex) {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

const LINE_RGB = Object.fromEntries(
  Object.entries(lineColors).map(([lineId, hex]) => [lineId, hexToRgb(hex)]),
);
const FALLBACK_RGB = [200, 200, 200];

export default function GeoMap() {
  const containerRef = useRef(null);

  useEffect(() => {
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: STYLE_URL,
      center: INITIAL_CENTER,
      zoom: INITIAL_ZOOM,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    const overlay = new MapboxOverlay({
      interleaved: true,
      layers: [],
      getTooltip: ({ object }) =>
        object && {
          html: `<b>${lineNames[object.train.lineId] ?? object.train.lineId}</b><br/>toward ${object.train.destination}`,
        },
    });
    map.addControl(overlay);

    let rafId;
    const tick = () => {
      const now = Date.now();

      // Resolved once per frame (not per accessor call): each train's real-world
      // [lng, lat] extrapolated from its last fromStation/toStation/fraction poll.
      // geo-stations.json stores [lat, lng]; deck.gl positions are [lng, lat].
      const positioned = [];
      for (const train of getTrains()) {
        const point = resolveGeoPoint(geoStations, train, now);
        if (point) positioned.push({ train, lngLat: [point[1], point[0]] });
      }

      const layer = new ScatterplotLayer({
        id: "trains",
        data: positioned,
        pickable: true,
        radiusUnits: "pixels",
        getRadius: 5,
        getFillColor: (d) => LINE_RGB[d.train.lineId] ?? FALLBACK_RGB,
        getPosition: (d) => d.lngLat,
        // Forces deck.gl to re-read positions every frame -- they change continuously
        // via client-side extrapolation, not just when a new poll lands.
        updateTriggers: { getPosition: now },
      });

      overlay.setProps({ layers: [layer] });
      rafId = requestAnimationFrame(tick);
    };
    rafId = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafId);
      map.remove();
    };
  }, []);

  return <div ref={containerRef} style={{ position: "absolute", inset: 0 }} />;
}
