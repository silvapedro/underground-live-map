#!/usr/bin/env python3
"""Build src/data/line-sequences.json from the TfL Route/Sequence API.

One-off/occasionally-rerun script (station order only changes on line closures or
extensions) -- not part of the 30s live refresh loop. For each line in fetch.py's
LINES dict, fetches ordered branch routes and writes them as canonicalised station
name lists, used by the frontend to draw each line's schematic track as a path
through its stations in the correct order.

Usage:
    python bin/build_station_sequences.py [--app-key KEY]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

sys.path.insert(0, str(SCRIPT_DIR))
from fetch import LINES, build_opener, canon_station_name  # noqa: E402

try:
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(REPO_ROOT / ".env", override=True)
except ImportError:
    pass

API_TEMPLATE = "https://api.tfl.gov.uk/Line/%s/Route/Sequence/all"
OUTPUT_PATH = REPO_ROOT / "src" / "data" / "line-sequences.json"


def _canon_name(raw_name: str, line_id: str) -> str:
    """TfL's Sequence API already appends a line-appropriate suffix ('Green Park
    Underground Station', 'Addiscombe Tram Stop'); canon_station_name expects the
    bare name and adds its own, so strip whichever suffix this line's names carry
    first or it gets doubled ('Addiscombe Tram Stop Tram Stop')."""
    suffix = " Tram Stop" if line_id == "tram" else " Underground Station"
    if raw_name.endswith(suffix):
        raw_name = raw_name[: -len(suffix)]
    return canon_station_name(raw_name, line_id)


def _dedupe_branches(branches: list[list[str]]) -> list[list[str]]:
    """Drop reverse-direction duplicates: same set of stops, opposite order."""
    seen: set[tuple[str, ...]] = set()
    unique = []
    for names in branches:
        key = tuple(sorted(names))
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(names)
    return unique


def fetch_line_sequence(line_id: str, api: str) -> list[list[str]]:
    """Return each branch as an ordered list of canonicalised station names.

    Uses stopPointSequences[].stopPoint[], which carries the full ordered stop list
    with names inline. The orderedLineRoutes + top-level `stations` lookup we used
    before is incomplete for several Overground/Elizabeth lines -- `stations` there
    holds only a subset (interchanges), so stops missing from it were silently
    dropped, producing short jumbled branches.
    """
    for attempt in range(1, 4):
        try:
            raw = urllib.request.urlopen(api % line_id, timeout=15).read()
            break
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < 3:
                time.sleep(5)
                continue
            print(f"  {line_id}: HTTP {exc.code}, skipping", file=sys.stderr)
            return []
        except OSError as exc:
            print(f"  {line_id}: network error ({exc}), skipping", file=sys.stderr)
            return []

    data = json.loads(raw)

    branches = []
    for seq in data.get("stopPointSequences", []):
        names = [_canon_name(sp["name"], line_id) for sp in seq.get("stopPoint", []) if sp.get("name")]
        # Collapse consecutive dupes (loops can repeat a stop) but keep order.
        deduped = [n for k, n in enumerate(names) if k == 0 or n != names[k - 1]]
        if len(deduped) >= 2:
            branches.append(deduped)
    return _dedupe_branches(branches)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("-k", "--app-key", default=os.environ.get("TFL_APP_KEY", ""))
    options = parser.parse_args()

    urllib.request.install_opener(build_opener())
    api = API_TEMPLATE + (("?app_key=" + options.app_key) if options.app_key else "")

    result: dict[str, dict[str, list[list[str]]]] = {}
    for line_id in LINES:
        print(f"Fetching {line_id}...", file=sys.stderr)
        branches = fetch_line_sequence(line_id, api)
        result[line_id] = {"branches": branches}

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    total_branches = sum(len(v["branches"]) for v in result.values())
    print(f"Wrote {len(result)} lines ({total_branches} branches) to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
