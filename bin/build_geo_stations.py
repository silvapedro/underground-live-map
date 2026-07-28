#!/usr/bin/env python3
"""Build src/data/geo-stations.json from bin/stations.json.

Reuses fetch.py's load_station_locations() -- the same station-name/coordinate source
of truth the live fetch pipeline uses -- so this can never drift from what /api/trains'
fromStation/toStation values actually resolve against. The one difference: fetch.py's
loader adds full-line-name keys (e.g. "bakerloo") *alongside* the single-letter keys
already in stations.json (e.g. "B") so old callers keyed by abbreviation still work;
this script drops those single-letter keys from the output, since the frontend only
ever has a full lineId (from /api/trains) to look up with.

Usage:
    python bin/build_geo_stations.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

sys.path.insert(0, str(SCRIPT_DIR))
from fetch import LINE_ABBREVIATIONS, load_station_locations  # noqa: E402

OUTPUT_PATH = REPO_ROOT / "src" / "data" / "geo-stations.json"


def build_geo_stations(stations_path: Path) -> dict[str, dict[str, list[float]]]:
    """Return {"Station Name": {"central": [lat, lng], "*": [lat, lng], ...}}."""
    stations = load_station_locations(stations_path)
    abbreviations = set(LINE_ABBREVIATIONS)

    return {
        name: {key: [lat, lng] for key, (lat, lng) in keys.items() if key not in abbreviations}
        for name, keys in stations.items()
    }


def main() -> int:
    data = build_geo_stations(SCRIPT_DIR / "stations.json")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Wrote {len(data)} stations to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
