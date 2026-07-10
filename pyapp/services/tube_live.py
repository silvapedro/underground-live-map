"""
Live train positions for the TubeLiveMap canvas component.

Polls TfL GET /Line/victoria,central/Arrivals every ~30 s, derives a
fractional `g` (position along each line's station sequence) for every
vehicle, and caches the result in memory so the HTTP endpoint stays fast.

The station sequences and IDs here must match LINES / STATIONS in
src/tube-live-map.jsx exactly.
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Station / NaPTAN configuration (matches src/tube-live-map.jsx)
# ---------------------------------------------------------------------------

_LINES_CONFIG: dict[str, dict[str, Any]] = {
    "victoria": {
        "tfl_id": "victoria",
        # Ordered south → north (index 0 = Victoria, 5 = King's Cross)
        "stations": ["victoria", "greenpark", "oxford", "warren", "euston", "kings"],
        "naptan": {
            "victoria":  "940GZZLUVIC",
            "greenpark": "940GZZLUGPK",
            "oxford":    "940GZZLUOXC",
            "warren":    "940GZZLUWRR",
            "euston":    "940GZZLUEUS",
            "kings":     "940GZZLUKSX",
        },
    },
    "central": {
        "tfl_id": "central",
        # Ordered west → east (index 0 = Bond St, 4 = Chancery Lane)
        "stations": ["bond", "oxford", "tcr", "holborn", "chancery"],
        "naptan": {
            "bond":     "940GZZLUBND",
            "oxford":   "940GZZLUOXC",
            "tcr":      "940GZZLUTCR",
            "holborn":  "940GZZLUHBN",
            "chancery": "940GZZLUCHL",
        },
    },
}

# Inverted lookup: NaPTAN → list of {line_id, station_id, station_idx}
# A NaPTAN can appear on multiple lines (Oxford Circus is on both).
_NAPTAN_MAP: dict[str, list[dict[str, Any]]] = defaultdict(list)
for _line_id, _cfg in _LINES_CONFIG.items():
    for _idx, _sid in enumerate(_cfg["stations"]):
        _NAPTAN_MAP[_cfg["naptan"][_sid]].append(
            {"line_id": _line_id, "station_id": _sid, "station_idx": _idx}
        )

_TFL_LINE_IDS = ",".join(cfg["tfl_id"] for cfg in _LINES_CONFIG.values())

# ---------------------------------------------------------------------------
# In-memory cache (written by background task, read by HTTP handler)
# ---------------------------------------------------------------------------

_cache: dict[str, Any] = {"trains": [], "updated_at": 0.0, "error": None}


# ---------------------------------------------------------------------------
# TfL API fetch (blocking — run in executor)
# ---------------------------------------------------------------------------

def _fetch_arrivals(app_key: str) -> list[dict]:
    """Fetch raw arrival predictions from TfL Unified API.

    Uses `requests` so that certifi's CA bundle is used on all platforms
    (avoids SSL verification failures on Windows with urllib).
    """
    params = {"app_key": app_key} if app_key else {}
    resp = requests.get(
        f"https://api.tfl.gov.uk/Line/{_TFL_LINE_IDS}/Arrivals",
        params=params,
        headers={"User-Agent": "underground-live-map/1.0"},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# g-value computation
# ---------------------------------------------------------------------------

def _compute_positions(raw: list[dict]) -> list[dict]:
    """
    Derive {vehicleId, lineId, g, dir} from raw TfL arrival predictions.

    Algorithm per vehicle:
      Sort the vehicle's predictions by timeToStation (ascending).
        preds[0] → next station (t0 seconds away, index next_idx)
        preds[1] → station after that (t1 seconds away)

      seg_duration = max(30, t1 - t0)   # estimated time for one segment
      g = next_idx - t0 / seg_duration   # fraction through current segment

      At-platform heuristic: if t0 < 15 s, snap g = float(next_idx).
      Direction: preds[1].station_idx > preds[0].station_idx → dir = +1 (forward).
    """
    by_vehicle: dict[tuple, list] = defaultdict(list)

    for pred in raw:
        naptan = pred.get("naptanId", "")
        if naptan not in _NAPTAN_MAP:
            continue
        vehicle_id = pred.get("vehicleId", "")
        if not vehicle_id:
            continue
        line_id = pred.get("lineId", "")
        tts = int(pred.get("timeToStation", 0))

        for entry in _NAPTAN_MAP[naptan]:
            if entry["line_id"] == line_id:
                by_vehicle[(vehicle_id, line_id)].append(
                    {"station_idx": entry["station_idx"], "timeToStation": tts}
                )

    results: list[dict] = []
    for (vehicle_id, line_id), preds in by_vehicle.items():
        if not preds:
            continue

        preds.sort(key=lambda p: p["timeToStation"])
        n = len(_LINES_CONFIG[line_id]["stations"])
        t0 = preds[0]["timeToStation"]
        next_idx = preds[0]["station_idx"]

        if t0 < 15:
            # Train is effectively at the platform — snap to the station.
            g = float(next_idx)
            dir_ = 1  # will be corrected on the next poll when t0 grows
        else:
            if len(preds) >= 2:
                seg = max(30.0, float(preds[1]["timeToStation"] - t0))
                dir_ = 1 if preds[1]["station_idx"] > next_idx else -1
            else:
                seg = 90.0  # ~1.5 min default segment travel time
                dir_ = 1
            g = next_idx - t0 / seg

        g = max(0.0, min(float(n - 1), g))

        results.append(
            {
                "vehicleId": vehicle_id,
                "lineId": line_id,
                "g": round(g, 4),
                "dir": dir_,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Public API used by app.py
# ---------------------------------------------------------------------------

async def refresh_tube_live(app_key: str) -> None:
    """Fetch TfL arrivals and update the shared cache. Called by background loop."""
    try:
        loop = asyncio.get_running_loop()
        raw = await loop.run_in_executor(None, _fetch_arrivals, app_key)
        trains = _compute_positions(raw)
        _cache["trains"] = trains
        _cache["updated_at"] = time.time()
        _cache["error"] = None
        logger.info("Tube live: %d train positions cached", len(trains))
    except Exception as exc:
        _cache["error"] = str(exc)
        logger.warning("Tube live refresh failed: %s", exc)


def get_cached_positions() -> dict[str, Any]:
    """Return a snapshot of the current cache. Safe to call from any coroutine."""
    return dict(_cache)
