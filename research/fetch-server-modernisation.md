# Fetch & Server Modernisation — Baseline Research

**Branch:** `feature/week2_reppit`  
**Date:** 2026-07-11  
**Scope:** `bin/fetch.py`, `pyapp/app.py`, and all supporting modules, as they exist today.

---

## Summary

`bin/fetch.py` is a standalone procedural script that fetches live arrival data from the TfL REST API for 21 lines, writes raw responses to a per-line on-disk cache, interpolates train positions from textual location strings, and atomically writes two JSON files (`data/london.json`, `data/london-text.json`) consumed by the JavaScript frontend. `pyapp/app.py` is a FastAPI application that drives fetch.py as a child subprocess on a 60-second timer, serves the resulting JSON as static files, and exposes three rendered HTML endpoints (text view, bus view, accessible predictions). The three service modules (`accessible.py`, `bus.py`, `textual.py`) each have a single, narrow responsibility: one parses TrackerNet XML for step-free predictions, one parses URA NDJSON for bus positions, and one reads and re-groups the text-format train list written by fetch.py. The dependency set is minimal (FastAPI, Jinja2, requests, python-dotenv, pytest); notably `simplejson`, which fetch.py imports, is absent from `requirements.txt` and is not installed in the project venv. The test suite covers the three service modules with unit tests only; fetch.py has no tests at all.

---

## 1. fetch.py — Structure and Responsibilities

**File:** `bin/fetch.py`

### Entry point and execution model

The script is executable (`#!/usr/bin/python3`, line 1) and runs from top to bottom when invoked directly. It is not a Python module with importable functions; all logic including the HTTP fetch loop, deduplication, and output write executes at module scope. `app.py` invokes it exclusively as a subprocess.

### CLI argument parsing

Uses the deprecated `optparse` module (line 27). Four options are defined:

| Flag | Default | Description |
|---|---|---|
| `-d` / `--debug` | `False` | Enables verbose output to stdout |
| `-s` / `--stations` | `stations.json` | Station coordinate file, relative to script dir |
| `-o` / `--output` | `../data` | Output directory, relative to script dir |
| `-k` / `--app-key` | `$TFL_APP_KEY` env var | TfL Unified API key |

Source: lines 27–33.

### .env / TFL_APP_KEY loading

`python-dotenv` is imported inside a bare `try/except` at lines 20–24. `load_dotenv` is called with the path `<script_dir>/../.env` and `override=True`, so `.env` values win over any pre-existing shell environment. The `TFL_APP_KEY` value is then picked up via `os.environ.get('TFL_APP_KEY', '')` as the default for the `--app-key` CLI option (line 31). If `python-dotenv` is absent the import fails silently and the env var still works. The API key is appended as a query-string parameter: `_app_key_qs = ('?app_key=' + options.app_key) if options.app_key else ''` (line 58), making `api = 'https://api.tfl.gov.uk/Line/%s/Arrivals' + _app_key_qs` (line 59).

### `lines` dict

Defined at lines 86–109. Maps 21 TfL line identifiers (strings used as URL path segments) to display names:

- 6 London Overground lines (split in 2024): `liberty`, `lioness`, `mildmay`, `suffragette`, `weaver`, `windrush`
- `tram`, `dlr`, `bakerloo`, `central`, `circle`, `district`, `elizabeth`, `hammersmith-city`, `jubilee`, `metropolitan`, `northern`, `piccadilly`, `victoria`, `waterloo-city`

`tfl-rail` is present but commented out (line 95).

### `station_locations` loading and normalisation

Loaded from `bin/stations.json` (or the path in `--stations`) via `json.load(open(dir + options.stations))` at line 62. The file stores entries either as a `"lng,lat"` string (most entries, as seen in lines 2–30 of stations.json) or as a dict keyed by line abbreviation. The normalisation loop at lines 63–84:

1. String values: split on `,`, parse float, store as `{ '*': (lat, lng) }` (lat/lng order is swapped from the file's lng,lat order).
2. Single-letter line keys are expanded to full line names via a `switch` dict: `'B'→'bakerloo'`, `'C'→'central'`, `'D'→'district'`, `'E'→'elizabeth'`, `'H'→'hammersmith-city'`, `'J'→'jubilee'`, `'M'→'metropolitan'`, `'N'→'northern'`, `'P'→'piccadilly'`, `'V'→'victoria'`, `'W'→'waterloo-city'`. The `'H'` key also copies the entry under `'circle'` (line 83–84).

### Cache mechanism

- **Directory:** `bin/cache/` — created at startup if absent (line 48).
- **File naming:** `bin/cache/<line_key>`, e.g. `bin/cache/jubilee`. One file per line key.
- **TTL:** 100 seconds. The check at line 256: `time.time() - os.path.getmtime('cache/%s' % key) > 100`. If the file is newer than 100 s it is read from disk; otherwise a fresh HTTP fetch is triggered.
- **Format:** raw bytes from the TfL API (JSON array), written with `open(... 'wb')` at line 282.

### HTTP fetch loop

Source: lines 252–290. For each line key:

1. Try to use the cached file (lines 256–259).
2. On failure (file absent, too old, or any exception from the try block), enter an inner `while True` loop.
3. `urllib.request.urlopen(api % key, timeout=10)` (line 264). A custom opener is installed once at module scope at lines 248–250 with a `User-Agent` header.
4. **URLError** (network failure): print warning to stderr, set `_skip=True`, break (lines 265–268).
5. **HTTPError 429** (rate-limited): attempt to parse "Try again in N second" from the response body with a regex at line 273; `time.sleep(N)` or fallback `time.sleep(10)`, then retry (lines 269–277).
6. **Other HTTPError**: print warning to stderr, set `_skip=True`, break (lines 278–281).
7. On success: write raw bytes to cache file (lines 282–284), parse JSON, break.
8. If `_skip` is True after the inner loop: `continue` to the next line, skipping `parse_json` (lines 287–288).

### `parse_time(s)` — line 194

Signature: `parse_time(s: str | int) -> int`

- If `s` is already an int, return it unchanged.
- `'-'` or `'due'` → returns `0`.
- `MM:SS` → seconds.
- `HH:MM:SS` → seconds.
- Any other format raises `Exception('Did not match time %s' % s)`.

### `canon_station_name(s, line)` — line 111

Signature: `canon_station_name(s: str, line: str) -> str`

Applies a long chain of `re.sub`, `str.replace`, and special-case `if` blocks to normalise the station name strings returned by the TfL API to match the keys in `station_locations`. Notable rules:

- Strips trailing `Platform N` (regex at line 123).
- Appends ` Tram Stop` for `line == 'tram'`; no suffix for `dlr`, `london-overground`, `elizabeth`; ` Station` for everything else (lines 124–129).
- Encodes `&` as `&amp;` (line 130).
- Contains ~40 specific string corrections for known TfL API typos and aliases (lines 135–187).
- Two post-chain `if` blocks disambiguate Edgware Road for the Bakerloo vs other lines (lines 188–191).

### `parse_entry(...)` — line 212

Signature: `parse_entry(time_to_station, set_id, dest_code, destination, current_location, station_name, key, platform_name)`

Uses and modifies the module-level globals `out`, `outNext`, `sub_id`, `sub_ids`.

- Calls `parse_time` on `time_to_station`.
- Builds `train_key = set_id + '-' + dest_code`.
- For trains with `set_id` in `('000', '477')` or ambiguous destinations (`'Unknown'`, `'Special'`, `'Network Rail TOC'`) or `dest_code == '0'`, a `sub_ids` counter disambiguates multiple trains sharing the same `set_id` by their `current_location` (lines 218–226).
- Builds an `entry` dict with `station_name`, `platform_name`, `current_location`, `time_to_station`, `destination` (lines 227–233).
- **`out`**: stores one entry per `(line_key, train_key)`, keeping the one with the lowest `time_to_station` (lines 234–235).
- **`outNext`**: appends every entry, building a list of all station arrival predictions per train (line 236).

### `parse_json(live)` — line 239

Iterates the raw TfL API prediction list. For each prediction, strips `' Underground Station'` from `stationName`, reads `currentLocation`, `destinationNaptanId`, and calls `parse_entry`. The module-level variable `key` (the current line being processed) is used as a free variable captured from the enclosing for-loop scope (line 245).

### Module-level globals and mutable state

| Name | Defined at | Role |
|---|---|---|
| `out` | line 209 | `OrderedDict` — best (lowest time) arrival entry per `(line_key, train_key)` |
| `outNext` | line 210 | `dict` — all arrival entries per `(line_key, train_key)`, used to build the `next` stop list |
| `sub_id` | set per line at line 253 | Integer counter for disambiguation within a line |
| `sub_ids` | set per line at line 254 | `dict` mapping `current_location` strings to sub-IDs for that line |

### Train-deduplication pass — lines 295–304

Nested O(n²) loop over all `(line, train_key)` pairs. If the same `train_key` appears in two different lines, the entry with the higher `time_to_station` is deleted from its respective line's dict. The comparison uses `arr['time_to_station']` from `out`, which already holds the minimum per-line arrival.

### Position interpolation — lines 321–358

The inner `lookup(line, name)` function at line 308 looks up station coordinates from `station_locations`: tries line-specific key first, then `'*'` wildcard, returns `(0, 0)` if the station is not found at all (changed from the old `stations-schematic.json`-gated check in this branch).

Certain `current_location` values are skipped before interpolation: `'Siding'`, `'Depot'`, `'Network Rail Track'`, `'North Acton Junction'`, `"Lord's Disused"`, `'Road 21'` (lines 324–329).

**Interpolation cases (in order of evaluation):**

1. **`'At Platform'`** (line 332): `arr['location'] = lookup(line, station_name)` — train is at the destination station.
2. **Empty location string on DLR/Overground/Tram/Elizabeth** (lines 335–336): same as above, use `station_name` coordinates.
3. **`'Leaving ...'` / `'South of ...'` / `'Left ...'`** (lines 338–343): regex `(?:South of|Leaving|Left) (.*?)`. Linear interpolation between the named station (departure) and `station_name` (destination). Fraction = `30 / (time_to_station + 30)`, so a train 0 s away is placed 50% between the two stations and fraction increases towards 1 as time grows.
4. **`'Between X and Y'`** (lines 345–353): regex `Between (.*?) and (.*)`. Linear interpolation between X and Y. For line `'H'` (hammersmith-city), skips if `station_name != canon_station_name(m.group(2), line)`. `max = time_to_station + 30` if time > 150, else `180`. Fraction = `(max - time_to_station) / max`.
5. **`'Approaching X'`** (lines 355–358): sets `arr['location']` to X's coordinates directly; no interpolation (a comment at line 357 notes the limitation).

### Output files — lines 360–418

**`data/london.json`:**
- Built as a dict with keys `station`, `lastupdate` (ISO 8601 datetime), `trains` (list), `stations` (list) at lines 362–368.
- `trains` entries (line 393–399): `point`, `next` (list of upcoming stops with `point`, `name`, `mins`, `dexp`), `left` (always empty string `''`), `id` (`<line>-<train_key>`), `title`.
- `stations` entries (line 401–407): one per `station_locations` entry. Uses `popitem()` to get the last coordinate value — this mutates `station_locations` in place.
- `london-lines.js` content (the polylines array from `bin/london-lines.js`) is read and concatenated verbatim into the JSON string at lines 410–411: `grr = grr[:-2] + ',\n' + polylines + '}'`. This is string manipulation, not JSON serialisation.
- Written atomically: temp file `data/london.jsonN`, then `os.replace(... london.jsonN, ... london.json)` at lines 413–416. `os.replace` was substituted for `os.rename` in this branch to fix Windows cross-device rename failures.

**`data/london-text.json`:**
- Written directly (no atomic rename) at line 418 with `json.dump(outT, open(...))`.
- `outT` is a flat list of `{'id', 'time', 'line', 'current'}` dicts for all trains regardless of whether they have a location.

### Python 2 compatibility shims

- `from __future__ import division` at line 5. All `/` division in the file (fraction calculations at lines 342, 352) now does true float division in Python 3 without this import, so the shim is inert but harmless.
- `if isinstance(s, str): s = s.replace(...)` / `else: s = s.replace(u'’', ...)` at lines 131–134 in `canon_station_name`. In Python 3, `str` is always Unicode, so the else branch is dead code.

---

## 2. FastAPI app — Structure and Responsibilities

**File:** `pyapp/app.py`

### Module-level constants — lines 27–38

| Name | Value |
|---|---|
| `BASE_DIR` | `pyapp/` directory |
| `REPO_ROOT` | repository root |
| `DATA_DIR` | `REPO_ROOT / "data"` |
| `FETCH_SCRIPT` | `REPO_ROOT / "bin" / "fetch.py"` |
| `DATA_REFRESH_INTERVAL` | `60` (seconds) |
| `PUBLIC_STATIC_DIRS` | `("lib", "js", "i", "data", "schematic", "skyfall", "london-buses", "tfwm")` |
| `PUBLIC_STATIC_FILES` | `("css.css", "lu-screenshot.png", "README")` |

### .env loading — line 16

`load_dotenv(Path(__file__).resolve().parent.parent / ".env")` is called at module import time, before FastAPI is initialised. No `override=True`; shell environment takes precedence over `.env` values. Contrast with fetch.py which uses `override=True`.

### Logging setup — line 91

`logger = logging.getLogger(__name__)`. No `logging.basicConfig()` call. The logging configuration is entirely delegated to uvicorn's startup.

### `_fetch_data()` — lines 41–65

`async def _fetch_data() -> None`

Reads `TFL_APP_KEY` from `os.environ` at call time (not at startup), copies the full environment, and runs:

```
[sys.executable, str(FETCH_SCRIPT)] + (["--app-key", app_key] if app_key else [])
```

via `asyncio.create_subprocess_exec` with `cwd=REPO_ROOT` and both stdout and stderr captured as pipes (lines 52–58). After `proc.communicate()`, logs a warning if the exit code is non-zero (line 61). On any exception, calls `logger.exception(...)` (line 65). Note: `import subprocess` at line 6 is present but unused; the actual subprocess is created via `asyncio.create_subprocess_exec`.

### `_refresh_loop()` — lines 68–73

`async def _refresh_loop() -> None`

Calls `_fetch_data()` immediately on startup, then loops with `asyncio.sleep(DATA_REFRESH_INTERVAL)` between calls.

### Lifespan context — lines 76–86

`@asynccontextmanager async def lifespan(application: FastAPI)`

Creates `_refresh_loop` as an `asyncio.Task` on startup. On shutdown, cancels the task and awaits it, swallowing `CancelledError`.

### Route inventory

| Path(s) | Handler | Return type |
|---|---|---|
| `GET /text`, `/text.php`, `/map/tube/text`, `/map/tube/text.php` | `text_view` | Jinja2 HTML (`text.html`) |
| `GET /data/bus`, `/data/bus.php`, `/map/tube/data/bus`, `/map/tube/data/bus.php` | `bus_view` | JSON (`JSONResponse`) |
| `GET /accessible`, `/accessible/index.php`, `/map/tube/accessible`, `/map/tube/accessible/index.php` | `accessible_view` | Jinja2 HTML (`accessible.html`) |
| `GET /map/tube/schematic/data/{name:path}` | `schematic_data_redirect` | 301 redirect to `/map/tube/data/{name}` |
| `GET /`, `/index.html`, `/map/tube`, `/map/tube/`, `/map/tube/index.html` | `serve_index` | `FileResponse(index.html)` |
| Static: per file in `PUBLIC_STATIC_FILES` | `_make_handler` closure | `FileResponse` |
| Static mounts: per dir in `PUBLIC_STATIC_DIRS` | `StaticFiles` | Static file serving |

Sources: lines 95–215.

### `bus_view` validation — lines 111–132

`_LINE_RE = re.compile(r"^[A-Za-z0-9,]{1,10}$")` at line 92 validates the `line` query parameter before calling `fetch_bus_payload`. Returns HTTP 400 for empty or non-matching values. On upstream exception, falls back to `empty_bus_payload()` and sets `X-Upstream-Status: fallback-empty` header. Sets `Cache-Control: max-age=30` on all bus responses.

### `accessible_view` error handling — lines 135–162

`ValueError` from `fetch_accessible_predictions` (raised when stop code fails regex) → HTTP 400. Any other exception → HTTP 502.

### Static file mounting strategy — lines 165–215

All static directories and individual files are restricted to an explicit allowlist. Each item in `PUBLIC_STATIC_DIRS` is mounted twice: at `/<dir>` and `/map/tube/<dir>`. Each file in `PUBLIC_STATIC_FILES` is registered at `/<file>` and `/map/tube/<file>` via `app.add_api_route`. The schematic redirect (line 173) is registered before the static mounts so it takes priority over the `data/` static mount for schematic requests.

### Templates

`Jinja2Templates` points to `pyapp/templates/` (line 90). Two templates exist: `accessible.html` and `text.html`.

---

## 3. Service Modules

### `pyapp/services/accessible.py`

**External call:** `GET http://cloud.tfl.gov.uk/TrackerNet/PredictionDetailed/D/{stop}` (line 85). Uses `requests.get` with `timeout=20`. Note: HTTP, not HTTPS.

**Input validation:** `_STOP_CODE_RE = re.compile(r"^[A-Za-z0-9]{1,8}$")` at line 10. Raises `ValueError("invalid stop code")` before making the HTTP call (lines 82–83).

**Response parsing:** XML via `xml.etree.ElementTree`. Root element `<R>`, child `<S N="...">` for station, `<P N="...">` for platform, `<T LCID="..." TimeTo="..." Destination="..." Location="..."/>` for each train (lines 89–112).

**`pretty_time(value)` — line 73:** String formatting only. `":00"→" min"`, `"0:30"→"1/2 min"`, `":30"→"1/2 min"`, `"-"→"Now"`.

**`is_non` flag — line 109:** `True` when `LCID` does not start with `"2"`. Encodes whether the train is a non-LUL (non-London Underground Limited) train.

**Return shape:**
```python
{
    "station_name": str,
    "platforms": [
        {
            "name": str,
            "rows": [
                {"due": str, "destination": str, "id": str, "location": str, "is_non": bool}
            ]
        }
    ]
}
```

**`STOPS` constant — lines 12–70:** A list of 55 `(stop_code, station_name)` tuples, hardcoded. These are District/Circle/H&C line stations.

---

### `pyapp/services/bus.py`

**External call:** `GET http://countdown.api.tfl.gov.uk/interfaces/ura/instant_V1?ReturnList=<cols>&LineName=<route>` (or `RegistrationNumber=<route>` if `len(route) == 7` and no comma, lines 37–44). Uses `requests.get` with `timeout=20`. Note: HTTP, not HTTPS.

**`BUS_COLS_TEXT` — line 10:** Comma-separated column list used in the `ReturnList` parameter and as the column schema for parsing. 17 columns total.

**Response format:** NDJSON-style — one JSON array per line. Parsed at lines 49–55. The first element of each array is `ReturnType`. Only rows with `ReturnType == 1` are processed (line 61). Rows with `StopPointState` 2 or 3 are filtered out (lines 62–63).

**`route_prior` dict — lines 88–97:** Built by iterating all predictions per vehicle sorted by `EstimatedTime`. Records which stop preceded each stop in each vehicle's route. Used to determine a bus's approximate position between stops (lines 132–147).

**`EstimatedTime` handling — line 114:** The column value is a Unix timestamp in milliseconds (divided by 1000 to get seconds, then subtracted from `now`).

**Hard-coded coordinate overrides — lines 77–80, 120–121:** Two stops with zero-coordinate data have coordinates patched inline: "Summit Close" at `[51.606065, -0.276948]` and "Whitgift Centre" at `[51.3769688, -0.0987477]`.

**Return shape:**
```python
{
    "lastupdate": str,  # formatted local time with timezone
    "station": "",      # always empty string
    "trains": [         # actually buses
        {"id": str, "title": str, "next": [...], "left": "", "point": [lat, lng]}
    ],
    "polylines": [],    # always empty list
    "stations": [{"point": [lat, lng], "name": str}]
}
```

`empty_bus_payload()` at line 168 returns the same shape with empty `trains` and `stations` lists.

---

### `pyapp/services/textual.py`

**No external calls.** Reads `data/london-text.json` from disk.

**`load_textual_rows(data_file: Path)` — line 8:** Returns an empty list if the file does not exist or is not a JSON array. Filters out non-dict rows.

**`group_rows_by_line(rows)` — line 18:** Linear scan grouping contiguous rows with the same `line` value into segments. Rows with an empty or missing `line` key are grouped under `"Unknown"`. `time` (seconds integer/float) is converted to `minutes` by dividing by 60. Missing `time` → `minutes=None`.

**Return shape:**
```python
[{"line": str, "items": [{"current": str, "minutes": float | None}]}]
```

---

## 4. Tests

**Files:**
- `tests/test_accessible.py` — 2 tests
- `tests/test_bus.py` — 3 tests
- `tests/test_textual.py` — 1 test
- No test file for `fetch.py`.

### test_accessible.py

**`test_stop_code_regex_accepts_valid_codes_and_rejects_invalid_codes`** (line 6): Directly tests `accessible._STOP_CODE_RE` against known-good codes (`"WMP"`, `"PADc"`) and known-bad inputs (`"../../etc/passwd"`, `"W-M-P"`).

**`test_fetch_accessible_predictions_parses_xml`** (line 13): Patches `accessible.requests.get` via `monkeypatch.setattr` to return a `FakeResponse` object whose `.text` is a handcrafted XML string. Asserts on `station_name`, `platforms[0]["name"]`, `rows[0]["due"]`, `rows[0]["is_non"]`, `rows[1]["due"]`, `rows[1]["is_non"]`.

### test_bus.py

**`test_plural_minutes_formats_half_minutes_and_whole_minutes`** (line 12): Tests `bus._plural_minutes` with `1.3 → "in 1.5 minutes"` and `1.0 → "in 1.0 minute"`.

**`test_bus_view_rejects_invalid_line_before_fetch`** (line 17): Patches `app_module.fetch_bus_payload` to raise `AssertionError` if called. Calls `app_module.bus_view(line="bad value")` directly and asserts that `HTTPException` is raised with `status_code=400` before the patched function is reached.

**`test_fetch_bus_payload_parses_rows`** (line 29): Patches `bus.dt.datetime` to return a fixed UTC timestamp and `bus.requests.get` to return two pre-built NDJSON rows for a single vehicle with two stops. Asserts on `payload["stations"][0]["name"]`, `payload["trains"][0]["id"]`, `payload["trains"][0]["title"]`, and the `dexp` strings for both next-stop predictions.

### test_textual.py

**`test_group_rows_by_line_groups_contiguous_rows`** (line 4): Calls `group_rows_by_line` with four rows (two Central, one District, one with empty line) and asserts the full expected output structure including `"Unknown"` grouping and `minutes` conversion.

### Mocking strategy

All three test files use pytest's `monkeypatch.setattr`. No `unittest.mock` or `patch` decorators are used. No async tests. No tests exercise HTTP networking, file I/O, or the FastAPI lifespan.

### Test runner

`pytest >= 8.0.0, < 9.0.0` (requirements.txt line 6).

---

## 5. Dependencies and Toolchain

### requirements.txt (complete)

```
fastapi>=0.116.1,<1.0.0
uvicorn[standard]>=0.35.0,<1.0.0
jinja2>=3.1.6,<4.0.0
requests>=2.32.5,<3.0.0
python-dotenv>=1.0.0,<2.0.0
pytest>=8.0.0,<9.0.0
```

Source: `requirements.txt` lines 1–6.

### Python version

CPython 3.11.15, managed by uv 0.11.3. Source: `.venv/pyvenv.cfg`.

### `simplejson` discrepancy

`fetch.py` imports `simplejson` as `json` at line 10: `import simplejson as json`. `simplejson` is **not** listed in `requirements.txt` and is **not** installed in the project venv (`pip show simplejson` returns nothing). The standard library `json` module is a drop-in replacement for all usages in this file; `simplejson` was historically preferred for its C extension speed.

### Notable absent dependencies

- No `httpx` — all HTTP is synchronous `requests` (service modules) or `urllib.request` (fetch.py).
- No `pydantic` models — data shapes are plain `dict[str, Any]`.
- No `celery`, `redis`, or queue machinery — the refresh loop is a bare `asyncio.Task`.
- No `aiohttp` — the background subprocess model means fetch.py's synchronous urllib is never in the async event loop.
- No `pytest-asyncio` — no async tests.
- `subprocess` is imported in `app.py` (line 6) but is not used anywhere; `asyncio.create_subprocess_exec` is used instead.

---

## 6. Data Flow End-to-End (Server Side)

```
FastAPI startup
  │
  └─► asyncio.create_task(_refresh_loop())          [app.py:78]
        │
        ├─► _fetch_data()  [app.py:41]  (immediate, then every 60 s)
        │     │
        │     └─► asyncio.create_subprocess_exec(
        │           sys.executable, bin/fetch.py, --app-key, <key>
        │           cwd=REPO_ROOT
        │         )                                  [app.py:52–58]
        │
        └── bin/fetch.py runs synchronously as child process
              │
              ├─ loads .env (override=True)          [fetch.py:20–24]
              ├─ loads bin/stations.json             [fetch.py:62]
              ├─ for each of 21 lines:
              │    ├─ if bin/cache/<line> < 100s old:
              │    │    read cache file              [fetch.py:256–259]
              │    └─ else:
              │         GET https://api.tfl.gov.uk/Line/<line>/Arrivals
              │             ?app_key=<key>           [fetch.py:264]
              │         write bytes → bin/cache/<line>  [fetch.py:282–284]
              │
              ├─ parse_json() for each line         [fetch.py:290]
              │    builds out (OrderedDict) and outNext (dict)
              │
              ├─ deduplication pass                  [fetch.py:295–304]
              │
              ├─ position interpolation pass         [fetch.py:321–358]
              │    assigns arr['location'] per train
              │
              ├─ read bin/london-lines.js            [fetch.py:410]
              │
              ├─ write data/london.jsonN             [fetch.py:413–415]
              │    (JSON blob + raw london-lines.js polylines string)
              │
              ├─ os.replace(london.jsonN → london.json)  [fetch.py:416]
              │
              └─ write data/london-text.json         [fetch.py:418]
                  (flat list of {id, time, line, current})

Static file serving
  │
  ├─ GET /map/tube/data/london.json
  │    └── served by StaticFiles mount on data/     [app.py:206–210]
  │        JS frontend polls this for train positions
  │
  └─ GET /map/tube/data/london-text.json
       └── also served by same StaticFiles mount

Rendered endpoints (not data flow but same server)
  ├─ GET /map/tube/text
  │    ├─ load_textual_rows(data/london-text.json)  [textual.py:8]
  │    └─ group_rows_by_line(rows) → Jinja2 render  [textual.py:18]
  │
  ├─ GET /map/tube/data/bus?line=<route>
  │    └─ fetch_bus_payload(route)
  │         GET http://countdown.api.tfl.gov.uk/...  [bus.py:43]
  │         returns JSON matching london.json shape
  │
  └─ GET /map/tube/accessible?stop=<code>
       └─ fetch_accessible_predictions(stop)
            GET http://cloud.tfl.gov.uk/TrackerNet/... [accessible.py:85]
            parse XML → Jinja2 render
```

---

## Cross-Component Connections

### Call graph

```
app.py
  ├─ subprocess → bin/fetch.py
  │     reads  bin/stations.json
  │     reads  bin/london-lines.js
  │     reads  bin/cache/<line>   (conditional)
  │     writes bin/cache/<line>
  │     writes data/london.json   (atomic)
  │     writes data/london-text.json
  │
  ├─ pyapp.services.textual
  │     reads  data/london-text.json
  │     returns list[dict] to app.py:text_view
  │
  ├─ pyapp.services.bus
  │     HTTP GET countdown.api.tfl.gov.uk
  │     returns dict to app.py:bus_view
  │
  └─ pyapp.services.accessible
        HTTP GET cloud.tfl.gov.uk
        returns dict to app.py:accessible_view
```

### Shared data contracts

- `data/london.json`: Written by fetch.py, served as static JSON by the `data/` StaticFiles mount. The JS frontend reads it directly. Not consumed by any Python service module.
- `data/london-text.json`: Written by fetch.py, read by `textual.load_textual_rows`. Schema: `[{"id": str, "time": int, "line": str, "current": str}]` (fetch.py lines 371–375).
- Bus and accessible responses match the same top-level shape as `london.json` (`{station, lastupdate, trains, stations, polylines}`) so the same JS client code (`trains.js`) can consume all three.

### Environment variable flow

`TFL_APP_KEY` is read in two places:
1. `fetch.py` line 31 — as the default for `--app-key` CLI option, loaded after `.env` with `override=True`.
2. `app.py` line 45 — read from `os.environ` at each `_fetch_data()` call, then passed as `--app-key` to the subprocess. `.env` was loaded at import time without `override=True`.

The two `.env` loads use different `override` settings. In practice the app.py flow dominates because app.py passes `--app-key` explicitly to the subprocess, bypassing fetch.py's own env/dotenv lookup for this value.

### git log (recent 20 commits)

```
9b1299e fix: improve logging for TFL_APP_KEY in data fetch process
70ebe81 fix: handle unknown stations and Windows os.rename in fetch.py
dd955e6 Add .env support for TFL_APP_KEY and auto-refresh tube data every 60s
9d61847 Fix schematic data path: redirect /map/tube/schematic/data/* to /map/tube/data/*
50edf40 Modernize tube app follow-up
d8cd6b3 Refactor: Migrate PHP endpoints to Python with FastAPI
f1d446e Add design document template for RePPIT framework implementation
2436e25 Add RePPIT framework skills for research, proposal, planning, implementation, and testing
621756d Some data updates.
cb7fee4 [Tube] Slight robustness increase.
29e19e9 [Tube] Add Elizabeth Line.
6647e6d [TfWM] Catch errors.
2536be3 [Tube] Remove old unused code.
502799a Updates for python3 and bugfixes.
cdc8579 Guess the Route. Made years ago?
cd6a128 Skip missing stations in schematic.
5415019 (Old) Bugfix for lines lookup.
629d8cc (Old) Data update, new line.
2f844e7 (Old) Deal with rate limiting.
11df2f7 Yet more tube station names
```

### Changes on this branch vs master (summarised from `git diff master..HEAD`)

**`bin/fetch.py`:**
- Added `python-dotenv` import block with `.env` loading and `override=True` (lines 20–24).
- Added `--app-key` CLI option (line 31) and `_app_key_qs` appended to the API URL (lines 58–59).
- Replaced `'london-overground': 'Overground'` with 6 named Overground lines (lines 87–93).
- Added custom `User-Agent` opener (lines 248–250).
- Changed `sys.exit(1)` on network/HTTP errors to warn-and-skip (`_skip` flag), allowing partial output instead of full abort (lines 261–288).
- Changed `os.rename` to `os.replace` for the atomic output write (line 416), fixing Windows cross-device errors.
- Changed `lookup()` to return `(0, 0)` for any unknown station unconditionally, instead of only when using the schematic stations file (lines 308–309).

**`pyapp/app.py`:**
- Entirely new file on this branch (introduced in commit `d8cd6b3`).
