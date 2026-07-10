import { useRef, useEffect, useState, useCallback } from "react";

/*
  London Underground — live map test slice
  --------------------------------------------------------------
  Two renderings of the SAME train feed, switchable with a morph:
    • Geographic — real lat/long projected to canvas
    • Schematic  — Beck-style idealised grid
  Data here is SIMULATED. To go live, replace stepTrain()'s motion
  with positions interpolated from TfL Unified API predictions
  (GET /Line/{ids}/Arrivals -> vehicleId, timeToStation, direction).
  See wireUpLiveFeed() note at the bottom of this file.
*/

// ---- Network slice: real coords (geo) + grid coords (schematic) ----
const STATIONS = {
  victoria:  { name: "Victoria",           lat: 51.4965, lon: -0.1447, sx: 4, sy: 6, side: "r" },
  greenpark: { name: "Green Park",         lat: 51.5067, lon: -0.1428, sx: 4, sy: 5, side: "r" },
  oxford:    { name: "Oxford Circus",      lat: 51.5152, lon: -0.1418, sx: 4, sy: 4, side: "l", interchange: true },
  warren:    { name: "Warren Street",      lat: 51.5247, lon: -0.1385, sx: 4, sy: 3, side: "r" },
  euston:    { name: "Euston",             lat: 51.5282, lon: -0.1337, sx: 5, sy: 2, side: "r" },
  kings:     { name: "King's Cross St P.", lat: 51.5308, lon: -0.1238, sx: 6, sy: 1, side: "r" },
  bond:      { name: "Bond Street",        lat: 51.5142, lon: -0.1494, sx: 3, sy: 4, side: "b" },
  tcr:       { name: "Tottenham Court Rd", lat: 51.5165, lon: -0.1308, sx: 5, sy: 4, side: "b" },
  holborn:   { name: "Holborn",            lat: 51.5174, lon: -0.1200, sx: 6, sy: 4, side: "b" },
  chancery:  { name: "Chancery Lane",      lat: 51.5185, lon: -0.1122, sx: 7, sy: 4, side: "b" },
};

const LINES = [
  { id: "victoria", name: "Victoria", color: "#0098D4",
    stations: ["victoria", "greenpark", "oxford", "warren", "euston", "kings"] },
  { id: "central", name: "Central", color: "#E32017",
    stations: ["bond", "oxford", "tcr", "holborn", "chancery"] },
];
const LINEMAP = Object.fromEntries(LINES.map((l) => [l.id, l]));

const SEG = 120.0;  // real seconds between stations at 1× (≈ 2 min on tube)
const DWELL = 30.0; // real seconds at platform at 1× speed

// ---- helpers ----
function hexA(hex, a) {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
}

function computeLayout(mode, w, h) {
  const ids = Object.keys(STATIONS);
  const pad = 78;
  const raw = {};
  const lat0 = (51.514 * Math.PI) / 180;
  for (const id of ids) {
    const s = STATIONS[id];
    raw[id] = mode === "geo"
      ? { x: s.lon * Math.cos(lat0), y: s.lat }   // y up = north
      : { x: s.sx, y: -s.sy };                    // y up = north (sy grows south)
  }
  const xs = ids.map((i) => raw[i].x);
  const ys = ids.map((i) => raw[i].y);
  const minX = Math.min(...xs), maxX = Math.max(...xs);
  const minY = Math.min(...ys), maxY = Math.max(...ys);
  const spanX = maxX - minX || 1, spanY = maxY - minY || 1;
  const scale = Math.min((w - 2 * pad) / spanX, (h - 2 * pad) / spanY);
  const offX = (w - spanX * scale) / 2;
  const offY = (h - spanY * scale) / 2;
  const out = {};
  for (const id of ids) {
    out[id] = { x: offX + (raw[id].x - minX) * scale, y: offY + (maxY - raw[id].y) * scale };
  }
  return out;
}

function pointG(line, layout, g) {
  const n = line.stations.length;
  const gc = Math.max(0, Math.min(n - 1, g));
  const lo = Math.min(n - 2, Math.floor(gc));
  const fr = gc - lo;
  const a = layout[line.stations[lo]];
  const b = layout[line.stations[lo + 1]];
  return { x: a.x + (b.x - a.x) * fr, y: a.y + (b.y - a.y) * fr };
}

function initTrains() {
  const trains = [];
  let id = 0;
  for (const line of LINES) {
    const n = line.stations.length;
    const count = n - 1;
    for (let k = 0; k < count; k++) {
      trains.push({
        id: id++, line: line.id, color: line.color,
        g: (k / count) * (n - 1) + (k % 2) * 0.35,
        dir: k % 2 === 0 ? 1 : -1, mode: "move", dwellT: 0,
      });
    }
  }
  return trains;
}

function stepTrain(tr, dt) {
  const line = LINEMAP[tr.line];
  const n = line.stations.length;
  if (tr.mode === "dwell") {
    tr.dwellT -= dt;
    if (tr.dwellT <= 0) tr.mode = "move";
    return;
  }
  const prev = tr.g;
  let g = tr.g + tr.dir * (dt / SEG);
  const nextInt = tr.dir > 0 ? Math.floor(prev + 1e-9) + 1 : Math.ceil(prev - 1e-9) - 1;
  if ((tr.dir > 0 && g >= nextInt) || (tr.dir < 0 && g <= nextInt)) {
    // Clamp to boundary and dwell — live data will correct direction on next poll.
    g = Math.max(0, Math.min(n - 1, nextInt));
    tr.mode = "dwell";
    tr.dwellT = DWELL;
    // No reversal: trains beyond our slice get corrected by the next API update.
  }
  tr.g = Math.max(0, Math.min(n - 1, g));
}

// ---------------------------------------------------------------------------
// Live feed — reconcile API response into sim.current.trains
// ---------------------------------------------------------------------------

/**
 * Merge incoming [{vehicleId, lineId, g, dir}] from the backend into the
 * existing train array, keeping dead-reckoning trains alive for up to 3
 * consecutive missed polls before removing them.
 */
function reconcileTrains(s, incoming) {
  const byVehicle = new Map(s.trains.map((tr) => [tr.vehicleId ?? String(tr.id), tr]));

  const next = incoming.map((d) => {
    const existing = byVehicle.get(d.vehicleId);
    if (existing) {
      // Snap to real TfL position; stepTrain() dead-reckons from here until next poll.
      existing.g = d.g;
      existing.dir = d.dir;
      existing.mode = "move";
      existing.missCount = 0;
      return existing;
    }
    const line = LINEMAP[d.lineId];
    if (!line) return null; // unknown line — skip
    return {
      id: d.vehicleId,
      vehicleId: d.vehicleId,
      line: d.lineId,
      color: line.color,
      g: d.g,
      dir: d.dir,
      mode: "move",
      dwellT: 0,
      missCount: 0,
    };
  }).filter(Boolean);

  // Preserve recently-seen trains for up to 2 more polls (smooth disappearance).
  const incomingIds = new Set(incoming.map((d) => d.vehicleId));
  for (const tr of s.trains) {
    const vid = tr.vehicleId ?? String(tr.id);
    if (!incomingIds.has(vid)) {
      tr.missCount = (tr.missCount ?? 0) + 1;
      if (tr.missCount < 3) next.push(tr);
    }
  }

  s.trains = next;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function TubeLiveMap() {
  const [mode, setMode] = useState("geo");
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [selId, setSelId] = useState(null);
  const [feedStatus, setFeedStatus] = useState("connecting"); // "connecting"|"live"|"stale"|"error"

  const wrapRef = useRef(null);
  const canvasRef = useRef(null);
  const tipRef = useRef(null);
  const tipDotRef = useRef(null);
  const tipLineRef = useRef(null);
  const tipIdRef = useRef(null);
  const tipDestRef = useRef(null);
  const tipEtaRef = useRef(null);
  const tipLockRef = useRef(null);
  const hoverRef = useRef(null); // train id under cursor (not locked)

  const sim = useRef({
    display: null, target: null,
    trains: [],          // populated by the live feed (was initTrains())
    screens: [], last: 0, size: { w: 0, h: 0, dpr: 1 },
    reduce: false,
  });
  const modeRef = useRef(mode);
  const playRef = useRef(playing);
  const speedRef = useRef(speed);
  const selRef = useRef(selId);
  useEffect(() => { modeRef.current = mode; }, [mode]);
  useEffect(() => { playRef.current = playing; }, [playing]);
  useEffect(() => { speedRef.current = speed; }, [speed]);
  useEffect(() => { selRef.current = selId; }, [selId]);

  // ---- live feed: poll /api/tube/trains every 15 s ----
  useEffect(() => {
    let mounted = true;

    const poll = async () => {
      try {
        const resp = await fetch("/api/tube/trains");
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const { trains, stale } = await resp.json();
        if (!mounted) return;
        reconcileTrains(sim.current, trains);
        setFeedStatus(stale ? "stale" : "live");
      } catch {
        if (!mounted) return;
        // Leave trains in place — stepTrain() continues dead-reckoning.
        setFeedStatus("error");
      }
    };

    poll();
    const id = setInterval(poll, 15_000);
    return () => { mounted = false; clearInterval(id); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // retarget layout on mode change (eases via morph)
  useEffect(() => {
    const s = sim.current;
    if (!s.size.w) return;
    s.target = computeLayout(mode, s.size.w, s.size.h);
    if (s.reduce || !s.display) s.display = JSON.parse(JSON.stringify(s.target));
  }, [mode]);

  const resize = useCallback(() => {
    const wrap = wrapRef.current, cv = canvasRef.current;
    if (!wrap || !cv) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const w = wrap.clientWidth, h = wrap.clientHeight;
    cv.width = w * dpr; cv.height = h * dpr;
    cv.style.width = w + "px"; cv.style.height = h + "px";
    const s = sim.current;
    s.size = { w, h, dpr };
    s.target = computeLayout(modeRef.current, w, h);
    s.display = JSON.parse(JSON.stringify(s.target)); // snap on resize
  }, []);

  useEffect(() => {
    sim.current.reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || false;
    resize();
    const ro = new ResizeObserver(resize);
    if (wrapRef.current) ro.observe(wrapRef.current);
    return () => ro.disconnect();
  }, [resize]);

  // main loop
  useEffect(() => {
    let raf;
    const cv = canvasRef.current;
    const ctx = cv.getContext("2d");

    const frame = (now) => {
      const s = sim.current;
      const dpr = s.size.dpr;
      if (!s.last) s.last = now;
      const dt = Math.min(0.05, (now - s.last) / 1000);
      s.last = now;

      // morph display -> target (real time, not sim time)
      if (s.display && s.target) {
        const k = s.reduce ? 1 : 1 - Math.pow(0.0025, dt);
        for (const id in s.target) {
          s.display[id].x += (s.target[id].x - s.display[id].x) * k;
          s.display[id].y += (s.target[id].y - s.display[id].y) * k;
        }
      }
      // advance trains (sim time)
      if (playRef.current) {
        const sdt = dt * speedRef.current;
        for (const tr of s.trains) stepTrain(tr, sdt);
      }

      const { w, h } = s.size;
      const layout = s.display;
      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, w, h);

      // background: tunnel dark with soft vignette
      ctx.fillStyle = "#0A0D16";
      ctx.fillRect(0, 0, w, h);
      const vg = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.2, w / 2, h / 2, Math.max(w, h) * 0.75);
      vg.addColorStop(0, "rgba(30,40,66,0.35)");
      vg.addColorStop(1, "rgba(5,7,12,0.85)");
      ctx.fillStyle = vg;
      ctx.fillRect(0, 0, w, h);

      if (layout) {
        // lines: soft glow underlay + solid
        for (const line of LINES) {
          const pts = line.stations.map((id) => layout[id]);
          ctx.lineJoin = "round"; ctx.lineCap = "round";
          ctx.strokeStyle = hexA(line.color, 0.18);
          ctx.lineWidth = 16;
          ctx.beginPath();
          pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
          ctx.stroke();
          ctx.strokeStyle = line.color;
          ctx.lineWidth = 5.5;
          ctx.beginPath();
          pts.forEach((p, i) => (i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)));
          ctx.stroke();
        }

        // stations
        for (const id in STATIONS) {
          const st = STATIONS[id], p = layout[id];
          if (st.interchange) {
            ctx.fillStyle = "#fff";
            ctx.beginPath(); ctx.arc(p.x, p.y, 7, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = "#0A0D16";
            ctx.beginPath(); ctx.arc(p.x, p.y, 3.4, 0, Math.PI * 2); ctx.fill();
          } else {
            ctx.fillStyle = "#0A0D16";
            ctx.beginPath(); ctx.arc(p.x, p.y, 4.6, 0, Math.PI * 2); ctx.fill();
            ctx.fillStyle = "#cfd8e6";
            ctx.beginPath(); ctx.arc(p.x, p.y, 3, 0, Math.PI * 2); ctx.fill();
          }
        }

        // labels
        ctx.font = "600 11px ui-sans-serif, system-ui, -apple-system, sans-serif";
        ctx.textBaseline = "middle";
        for (const id in STATIONS) {
          const st = STATIONS[id], p = layout[id];
          let dx = 10, dy = 0, align = "left";
          if (st.side === "l") { dx = -10; align = "right"; }
          if (st.side === "b") { dx = 0; dy = 15; align = "center"; }
          ctx.textAlign = align;
          ctx.lineWidth = 3.5; ctx.strokeStyle = "rgba(6,8,14,0.92)";
          ctx.strokeText(st.name, p.x + dx, p.y + dy);
          ctx.fillStyle = "#9aa6ba";
          ctx.fillText(st.name, p.x + dx, p.y + dy);
        }

        // trains
        const screens = [];
        const pulse = s.reduce ? 1 : 0.75 + 0.25 * Math.sin(now / 240);
        for (const tr of s.trains) {
          const line = LINEMAP[tr.line];
          const p = pointG(line, layout, tr.g);
          screens.push({ id: tr.id, x: p.x, y: p.y, tr });

          // trail behind (opposite of travel dir)
          const TN = 6, dstp = 0.09;
          for (let k = TN; k >= 1; k--) {
            const p0 = pointG(line, layout, tr.g - tr.dir * dstp * k);
            const p1 = pointG(line, layout, tr.g - tr.dir * dstp * (k - 1));
            ctx.strokeStyle = hexA(tr.color, (1 - k / TN) * 0.45);
            ctx.lineWidth = 2 + (1 - k / TN) * 3.5;
            ctx.beginPath(); ctx.moveTo(p0.x, p0.y); ctx.lineTo(p1.x, p1.y); ctx.stroke();
          }
          // glow dot
          ctx.shadowBlur = 14 * pulse; ctx.shadowColor = tr.color;
          ctx.fillStyle = tr.color;
          ctx.beginPath(); ctx.arc(p.x, p.y, 5, 0, Math.PI * 2); ctx.fill();
          ctx.shadowBlur = 0;
          ctx.fillStyle = "rgba(255,255,255,0.9)";
          ctx.beginPath(); ctx.arc(p.x, p.y, 1.8, 0, Math.PI * 2); ctx.fill();

          const isLocked = tr.id === selRef.current;
          const isHovered = tr.id === hoverRef.current;
          if (isLocked) {
            ctx.strokeStyle = "#fff"; ctx.lineWidth = 2;
            ctx.beginPath(); ctx.arc(p.x, p.y, 10, 0, Math.PI * 2); ctx.stroke();
          } else if (isHovered) {
            ctx.strokeStyle = "rgba(255,255,255,0.5)"; ctx.lineWidth = 1.5;
            ctx.setLineDash([3, 3]);
            ctx.beginPath(); ctx.arc(p.x, p.y, 10, 0, Math.PI * 2); ctx.stroke();
            ctx.setLineDash([]);
          }
        }
        s.screens = screens;

        // tooltip: hover to peek, click to lock
        const lockedSc = screens.find((x) => x.id === selRef.current);
        const hovSc = screens.find((x) => x.id === hoverRef.current);
        const sel = lockedSc ?? hovSc;
        const isLocked = !!lockedSc;
        const tip = tipRef.current;
        if (sel && tip) {
          const tr = sel.tr, line = LINEMAP[tr.line];
          const n = line.stations.length;
          const nextIdx = tr.mode === "dwell"
            ? Math.round(tr.g)
            : (tr.dir > 0 ? Math.floor(tr.g) + 1 : Math.ceil(tr.g) - 1);
          const term = tr.dir > 0 ? line.stations[n - 1] : line.stations[0];
          const remG = tr.mode === "dwell" ? 0 : Math.abs(nextIdx - tr.g);
          const etaSec = Math.max(0, Math.round((remG * SEG) / Math.max(0.1, speedRef.current)));
          const etaFmt = etaSec >= 60 ? Math.round(etaSec / 60) + "m" : etaSec + "s";
          // Position tooltip: flip left if train is in right 40% of canvas
          const { w } = s.size;
          const flipX = sel.x > w * 0.6;
          tip.style.display = "block";
          tip.style.transform = flipX
            ? `translate(${sel.x - 16}px, ${sel.y - 14}px) translateX(-100%)`
            : `translate(${sel.x + 16}px, ${sel.y - 14}px)`;
          if (tipDotRef.current) tipDotRef.current.style.background = tr.color;
          if (tipLineRef.current) tipLineRef.current.textContent = line.name + " line";
          if (tipIdRef.current)
            tipIdRef.current.textContent = "Train " + (tr.vehicleId ?? String(tr.id));
          if (tipLockRef.current)
            tipLockRef.current.style.opacity = isLocked ? "1" : "0";
          if (tipDestRef.current)
            tipDestRef.current.textContent = "toward " + STATIONS[term].name;
          if (tipEtaRef.current)
            tipEtaRef.current.textContent = tr.mode === "dwell"
              ? "at " + STATIONS[Math.max(0, Math.min(n - 1, Math.round(tr.g)))].name
              : "next: " + STATIONS[line.stations[Math.max(0, Math.min(n - 1, nextIdx))]].name + " · " + etaFmt;
        } else if (tip) {
          tip.style.display = "none";
        }
      }

      ctx.restore();
      raf = requestAnimationFrame(frame);
    };
    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, []);

  const _nearestTrain = (e) => {
    const rect = canvasRef.current.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    let best = null, bd = 20 * 20;
    for (const sc of sim.current.screens) {
      const d = (sc.x - mx) ** 2 + (sc.y - my) ** 2;
      if (d < bd) { bd = d; best = sc.id; }
    }
    return best;
  };

  const onCanvasMouseMove = (e) => {
    hoverRef.current = _nearestTrain(e);
  };

  const onCanvasMouseLeave = () => {
    hoverRef.current = null;
  };

  const onCanvasClick = (e) => {
    const hit = _nearestTrain(e);
    // Toggle: click same locked train to release; click another to lock it.
    setSelId((prev) => (prev === hit ? null : hit));
  };

  // ---- UI ----
  const btn = (active) => ({
    padding: "6px 14px", fontSize: 12, fontWeight: 600, letterSpacing: "0.04em",
    borderRadius: 8, cursor: "pointer", border: "1px solid",
    borderColor: active ? "#3b4a68" : "transparent",
    background: active ? "#1b2540" : "transparent",
    color: active ? "#eaf0fb" : "#8a94a6", transition: "all .15s",
  });

  return (
    <div style={{
      height: "min(90vh, 760px)", width: "100%", display: "flex", flexDirection: "column",
      background: "#0A0D16", color: "#e8ecf2", borderRadius: 14, overflow: "hidden",
      fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, sans-serif",
      border: "1px solid #1a2338",
    }}>
      {/* header */}
      <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "14px 18px", borderBottom: "1px solid #161f33", flexWrap: "wrap" }}>
        <svg width="26" height="26" viewBox="0 0 100 100" aria-hidden>
          <circle cx="50" cy="50" r="34" fill="none" stroke="#E32017" strokeWidth="13" />
          <rect x="6" y="42" width="88" height="16" fill="#10069F" />
        </svg>
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1.1 }}>
          <span style={{ fontSize: 14, fontWeight: 700, letterSpacing: "0.14em", textTransform: "uppercase" }}>Underground</span>
          <span style={{ fontSize: 11, letterSpacing: "0.02em", color:
            feedStatus === "live"       ? "#4CAF50" :
            feedStatus === "stale"      ? "#FFC107" :
            feedStatus === "error"      ? "#E32017" :
                                          "#6b7688"
          }}>
            {feedStatus === "live"  ? "● live · Victoria & Central" :
             feedStatus === "stale" ? "● stale · reconnecting" :
             feedStatus === "error" ? "● offline · reconnecting" :
                                      "● connecting…"}
          </span>
        </div>

        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
          <div style={{ display: "flex", gap: 4, background: "#0f1524", padding: 4, borderRadius: 10, border: "1px solid #1a2338" }}>
            <button style={btn(mode === "geo")} onClick={() => setMode("geo")}>Geographic</button>
            <button style={btn(mode === "schematic")} onClick={() => setMode("schematic")}>Schematic</button>
          </div>
          <button style={btn(true)} onClick={() => setPlaying((p) => !p)}>{playing ? "Pause" : "Play"}</button>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ fontSize: 11, color: "#6b7688" }}>Speed</span>
            <input type="range" min="0.5" max="3" step="0.5" value={speed}
              onChange={(e) => setSpeed(parseFloat(e.target.value))}
              style={{ width: 90, accentColor: "#0098D4" }} />
            <span style={{ fontSize: 11, color: "#8a94a6", width: 26 }}>{speed}x</span>
          </div>
        </div>
      </div>

      {/* canvas */}
      <div ref={wrapRef} style={{ position: "relative", flex: 1, minHeight: 0 }}>
        <canvas
          ref={canvasRef}
          onClick={onCanvasClick}
          onMouseMove={onCanvasMouseMove}
          onMouseLeave={onCanvasMouseLeave}
          style={{ display: "block", cursor: "pointer" }}
        />
        <div ref={tipRef} style={{
          position: "absolute", top: 0, left: 0, display: "none", pointerEvents: "none",
          background: "rgba(11,15,26,0.94)", border: "1px solid #263353", borderRadius: 10,
          padding: "8px 12px", fontSize: 12, minWidth: 170, backdropFilter: "blur(4px)",
          boxShadow: "0 8px 24px rgba(0,0,0,0.5)",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 2 }}>
            <span ref={tipDotRef} style={{ width: 9, height: 9, borderRadius: 9, background: "#fff", flexShrink: 0 }} />
            <span ref={tipLineRef} style={{ fontWeight: 700 }}>Line</span>
            <span ref={tipLockRef} style={{ marginLeft: "auto", fontSize: 10, opacity: 0, transition: "opacity .15s" }}>📌</span>
          </div>
          <div ref={tipIdRef} style={{ color: "#4f5a70", fontSize: 10, marginBottom: 4 }}>Train —</div>
          <div ref={tipDestRef} style={{ color: "#aab4c5" }}>toward —</div>
          <div ref={tipEtaRef} style={{ color: "#6b7688", fontSize: 11, marginTop: 2 }}>—</div>
        </div>
        <div style={{ position: "absolute", left: 16, bottom: 12, fontSize: 11, color: "#4f5a70", pointerEvents: "none" }}>
          Hover to inspect · click to pin
        </div>
      </div>

      {/* footer legend */}
      <div style={{ display: "flex", alignItems: "center", gap: 18, padding: "11px 18px", borderTop: "1px solid #161f33", fontSize: 12, color: "#8a94a6", flexWrap: "wrap" }}>
        {LINES.map((l) => (
          <span key={l.id} style={{ display: "flex", alignItems: "center", gap: 7 }}>
            <span style={{ width: 22, height: 5, borderRadius: 3, background: l.color }} />
            {l.name}
          </span>
        ))}
        <span style={{ marginLeft: "auto", color: "#4f5a70" }}>
          TfL Open Data · {feedStatus === "connecting" ? "…" : sim.current.trains.length} trains
        </span>
      </div>
    </div>
  );
}

/*
  wireUpLiveFeed():
  1. Backend proxy polls  https://api.tfl.gov.uk/Line/victoria,central/Arrivals?app_key=KEY
     every ~10s, caches, fans out to all clients (keeps key server-side).
  2. Each prediction => { vehicleId, naptanId (station), timeToStation, direction }.
     Group by vehicleId, sort its predictions by timeToStation to find the two
     nearest stations => derive segment + fractional progress (t = 1 - timeToStation/segTravel).
  3. Map that onto this component's train model (line, g, dir) and drop stepTrain().
     The renderer/morph/tooltip all stay exactly as-is.
*/
