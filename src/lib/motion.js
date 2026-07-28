// Per-train display-position smoothing, shared by both renderers.
//
// The API poll can move a train's resolved position abruptly: lines that report no
// currentLocation (DLR, Overground, Elizabeth, Tram) snap from station to station,
// and any train's segment jumps when a fresh poll lands. Instead of teleporting the
// marker, each frame eases the *displayed* position toward the resolved target with
// an exponential decay (the same trick the original tube-live-map.jsx prototype used
// for its mode-morph), so jumps become short glides while genuinely moving trains
// track their extrapolated position almost exactly.
//
// The per-frame display delta is also what gives us heading: the direction the dot
// actually moved on screen is the direction arrow we draw, with no need to guess
// bearing from route topology.

export function createMotionSmoother({ angleEpsilon }) {
  const state = new Map(); // train id -> {x, y, angleDeg|null}

  return {
    /**
     * Ease this train's displayed position toward (tx, ty) and return
     * {x, y, angleDeg}. angleDeg is atan2(dy, dx) of the display movement in
     * degrees — interpret it in the caller's own coordinate convention (y-up for
     * geo lat, y-down for SVG). null until the train has visibly moved.
     */
    step(id, tx, ty, dtSeconds) {
      let s = state.get(id);
      if (!s) {
        s = { x: tx, y: ty, angleDeg: null };
        state.set(id, s);
      }
      const prevX = s.x;
      const prevY = s.y;
      // ~93% convergence per second: a station-to-station snap reads as a ~1.5s glide.
      const k = 1 - Math.pow(0.0025, dtSeconds);
      s.x += (tx - s.x) * k;
      s.y += (ty - s.y) * k;
      const dx = s.x - prevX;
      const dy = s.y - prevY;
      if (Math.abs(dx) > angleEpsilon || Math.abs(dy) > angleEpsilon) {
        s.angleDeg = (Math.atan2(dy, dx) * 180) / Math.PI;
      }
      return s;
    },

    /** Drop state for trains no longer present, so the map doesn't grow forever. */
    prune(seenIds) {
      for (const id of state.keys()) {
        if (!seenIds.has(id)) state.delete(id);
      }
    },
  };
}
