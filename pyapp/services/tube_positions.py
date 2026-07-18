"""
Live train positions for the frontend, read from data/train-positions.json.

bin/fetch.py (run as a subprocess by pyapp/app.py's refresh loop) writes this file
every refresh cycle with the shared, mode-agnostic position model: each train carries
{fromStation, toStation, fraction, etaSeconds, ...} rather than a baked coordinate, so
either rendering mode (geographic or schematic) can resolve its own pixels. This module
just reads that file back, with an mtime guard so repeat requests within a refresh
cycle don't re-parse JSON from disk.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_EMPTY: dict[str, Any] = {"trains": [], "updated_at": 0.0, "error": None}

_cache: dict[str, Any] = {"mtime": None, "data": _EMPTY}


def get_live_trains(data_dir: Path) -> dict[str, Any]:
    """Return {"trains": [...], "updated_at": float, "error": str | None}."""
    path = data_dir / "train-positions.json"

    try:
        mtime = path.stat().st_mtime
    except OSError as exc:
        return {"trains": [], "updated_at": 0.0, "error": str(exc)}

    if _cache["mtime"] == mtime:
        return _cache["data"]

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        data = {"trains": payload["trains"], "updated_at": payload["updatedAt"], "error": None}
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("Failed to read train-positions.json: %s", exc)
        data = {"trains": [], "updated_at": 0.0, "error": str(exc)}

    _cache["mtime"] = mtime
    _cache["data"] = data
    return data
