#!/usr/bin/env python3
"""Build src/data/schematic-stations.json from bin/stations-schematic.json.

bin/stations-schematic.json holds hand-curated idealised (Beck-diagram-style) station
positions in an ad-hoc "fake lat/lng" space, originally chosen to align with the old
schematic/map.png image overlay -- but it only covers the classic Underground/DLR/Tram
network. It has zero Elizabeth line coverage and almost none of the 6 Overground lines
(101 stations, confirmed by diffing against src/data/line-sequences.json).

For those 101 stations, this script fits a small affine transform (real lat/lng ->
schematic's fake lat/lng) calibrated on the ~300 stations present in *both* datasets,
then applies it to their real coordinates (bin/stations.json) as a fallback position --
not a hand-bent schematic bend, but plausible and correctly relative to the rest of the
layout, because the fit is calibrated against real neighbouring stations rather than
normalised independently. The combined result (idealised + transformed-fallback) is then reprojected as one
bounding-box normalisation onto a canvas VIEW_W wide; the height is derived from the
content's true aspect ratio (written to schematic-viewbox.json) rather than a second
fixed guess, so the network isn't padded with dead space on whichever axis it happens
to be more elongated on.

Usage:
    python bin/build_schematic_layout.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent

sys.path.insert(0, str(SCRIPT_DIR))
from fetch import LINE_ABBREVIATIONS, load_station_locations  # noqa: E402

OUTPUT_PATH = REPO_ROOT / "src" / "data" / "schematic-stations.json"
VIEWBOX_PATH = REPO_ROOT / "src" / "data" / "schematic-viewbox.json"
LINE_SEQUENCES_PATH = REPO_ROOT / "src" / "data" / "line-sequences.json"

VIEW_W = 1000.0
PAD = 40.0

Coord = tuple[float, float]


def _drop_abbreviations(stations: dict[str, dict[str, Coord]]) -> dict[str, dict[str, Coord]]:
    """load_station_locations adds full-line-name keys alongside the source file's
    single-letter ones (e.g. both "H" and "hammersmith-city"); keep only the former."""
    abbreviations = set(LINE_ABBREVIATIONS)
    return {
        name: {k: v for k, v in keys.items() if k not in abbreviations}
        for name, keys in stations.items()
    }


def _solve_3x3(matrix: list[list[float]], vector: list[float]) -> list[float]:
    """Solve a 3x3 linear system via Cramer's rule (fixed small size, no numpy needed)."""
    def det3(m: list[list[float]]) -> float:
        return (
            m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
        )

    d = det3(matrix)
    solution = []
    for col in range(3):
        replaced = [row[:] for row in matrix]
        for row in range(3):
            replaced[row][col] = vector[row]
        solution.append(det3(replaced) / d)
    return solution


def _fit_affine(pairs: list[tuple[Coord, Coord]]) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Least-squares fit of schematic_lat/lng = a*real_lat + b*real_lng + c, solved
    independently for each output via the normal equations (X^T X) beta = X^T y."""
    xtx = [[0.0] * 3 for _ in range(3)]
    xty_lat = [0.0, 0.0, 0.0]
    xty_lng = [0.0, 0.0, 0.0]

    for (real_lat, real_lng), (schem_lat, schem_lng) in pairs:
        row = [real_lat, real_lng, 1.0]
        for i in range(3):
            for j in range(3):
                xtx[i][j] += row[i] * row[j]
            xty_lat[i] += row[i] * schem_lat
            xty_lng[i] += row[i] * schem_lng

    return _solve_3x3(xtx, xty_lat), _solve_3x3(xtx, xty_lng)


def _apply_affine(coeffs: tuple[tuple[float, float, float], tuple[float, float, float]], point: Coord) -> Coord:
    (a, b, c), (d, e, f) = coeffs
    lat, lng = point
    return (a * lat + b * lng + c, d * lat + e * lng + f)


def _load_raw() -> dict[str, dict[str, Coord]]:
    schematic = _drop_abbreviations(load_station_locations(SCRIPT_DIR / "stations-schematic.json"))
    real = _drop_abbreviations(load_station_locations(SCRIPT_DIR / "stations.json"))

    # Calibrate the real -> schematic transform on stations present in both, using
    # each station's "*" entry (or any single entry it has) as the representative point.
    def representative(keys: dict[str, Coord]) -> Coord:
        return keys.get("*") or next(iter(keys.values()))

    pairs = [
        (representative(real[name]), representative(schematic[name]))
        for name in schematic
        if name in real
    ]
    coeffs = _fit_affine(pairs)
    print(f"Calibrated real->schematic transform on {len(pairs)} shared stations", file=sys.stderr)

    merged = dict(schematic)

    if LINE_SEQUENCES_PATH.is_file():
        sequences = json.loads(LINE_SEQUENCES_PATH.read_text(encoding="utf-8"))
        wanted = {
            name
            for line in sequences.values()
            for branch in line["branches"]
            for name in branch
        }
        missing = sorted(wanted - set(merged))
        for name in missing:
            if name not in real:
                print(f"  no coordinates at all for {name!r}, skipping", file=sys.stderr)
                continue
            merged[name] = {"*": _apply_affine(coeffs, representative(real[name]))}
        print(f"Added {len(missing)} fallback stations via the calibrated transform", file=sys.stderr)

    return merged


def _project(stations: dict[str, dict[str, Coord]]) -> tuple[dict[str, dict[str, list[float]]], float]:
    """Project onto a canvas VIEW_W wide, with height *derived* from the content's true
    aspect ratio (not a second fixed guess) -- otherwise, whichever axis TfL's network
    happens to be more elongated on gets padded with dead space instead of filling the
    canvas. Returns (projected_stations, view_height)."""
    lats = [lat for keys in stations.values() for lat, _lng in keys.values()]
    lngs = [lng for keys in stations.values() for _lat, lng in keys.values()]
    min_lat, max_lat = min(lats), max(lats)
    min_lng, max_lng = min(lngs), max(lngs)
    span_lat = (max_lat - min_lat) or 1.0
    span_lng = (max_lng - min_lng) or 1.0

    scale = (VIEW_W - 2 * PAD) / span_lng
    view_h = round(span_lat * scale + 2 * PAD, 2)

    def to_xy(lat: float, lng: float) -> list[float]:
        x = PAD + (lng - min_lng) * scale
        y = PAD + (max_lat - lat) * scale  # invert: higher latitude (north) is up
        return [round(x, 2), round(y, 2)]

    projected = {
        name: {key: to_xy(lat, lng) for key, (lat, lng) in keys.items()}
        for name, keys in stations.items()
    }
    return projected, view_h


def main() -> int:
    stations = _load_raw()
    projected, view_h = _project(stations)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(projected, indent=2, sort_keys=True), encoding="utf-8")
    VIEWBOX_PATH.write_text(
        json.dumps({"width": VIEW_W, "height": view_h}, indent=2), encoding="utf-8"
    )
    print(f"Wrote {len(projected)} stations to {OUTPUT_PATH} (viewBox 0 0 {VIEW_W} {view_h})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
