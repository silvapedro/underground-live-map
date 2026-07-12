# Codebase Overview — Full Repository Map

**Branch:** `feature/week2_reppit`
**Date:** 2026-07-11
**Scope:** The entire repository as it exists today. This document maps every component; for the Python fetch/server backend it summarises and cross-references the deeper companion document `research/fetch-server-modernisation.md` rather than duplicating it.

---

## Summary

`underground-live-map` is a live transit-map web application (originally a 2010 Science Hackday project by Matthew Somerville) that plots approximate real-time positions of London Underground trains on a Leaflet map. The current state of the repo is mid-migration from a PHP deployment to a Python/FastAPI backend: `pyapp/app.py` is a FastAPI server that runs `bin/fetch.py` as a background subprocess every 60 seconds to regenerate JSON data files, serves those files as static assets, and re-implements three former PHP endpoints (`/text`, `/data/bus`, `/accessible`) as Python routes. The frontend is a single shared vanilla-JS file (`js/trains.js`) driven by a per-page `TrainTimes` config object, reused across five HTML front-ends: the geographic tube map (`index.html`), a schematic version (`schematic/`), a "Skyfall" styled version (`skyfall/`), a London bus map (`london-buses/`), and a "guess the route" game (`london-buses/guess-the-route/`, which uses its own `buses.js`). A separate, older Python 2/3-mixed subsystem under `tfwm/` fetches West Midlands bus data from a GTFS-realtime protobuf feed. The repo also carries meta-documentation for a "RePPIT" spec-driven workflow (`.agents/skills/`, `proposals/`, `plans/`, `research/`). Live data files (`data/*.json`), caches, and secrets are gitignored.

---

## Repository Layout

```
underground-live-map/
├── index.html                     Geographic tube map (front-end)
├── css.css                        Shared stylesheet for all front-ends
├── README                         Project readme + install/runtime notes (MIT/LGPL)
├── requirements.txt               Python deps (FastAPI stack)
├── .env.example                   Template for TFL_APP_KEY
├── .gitignore                     Excludes data/*.json, caches, .env, config.py
│
├── pyapp/                         FastAPI backend (current)
│   ├── __init__.py                Docstring only: "Python web app replacing legacy PHP endpoints."
│   ├── app.py                     FastAPI app: routes, static mounts, 60s refresh loop
│   ├── services/
│   │   ├── accessible.py          TrackerNet XML → step-free predictions
│   │   ├── bus.py                 URA NDJSON → London bus positions
│   │   └── textual.py             Reads london-text.json → grouped rows
│   └── templates/
│       ├── accessible.html        Jinja2 table of accessible predictions
│       └── text.html              Jinja2 textual network description
│
├── bin/                           Data-generation scripts + source data
│   ├── fetch.py                   Main TfL tube fetch → data/london.json
│   ├── stations.json              658 station name → "lng,lat" coordinates
│   ├── london-lines.js            Polyline geometry fragment (spliced into london.json)
│   ├── lines_for_stations.json    Station name → list of serving lines
│   ├── stations-schematic.json    Schematic-map station coordinates
│   ├── stations.kml               KML source for station coords
│   ├── 1.kml-to-json              (py2) KML → JSON converter utility
│   ├── new-stations-from-api.py   (py2 urllib) Regenerate stations.json from TfL API
│   ├── bus-fetch-lines            (py3) Emit <option> list of bus routes
│   └── .htaccess                  "Deny from all" (Apache legacy)
│
├── schematic/                     Schematic tube front-end (index.html + map.png)
├── skyfall/                       "Skyfall" styled front-end (index.html, css.css, black.png, dot.png)
├── london-buses/                  London bus map front-end
│   ├── index.html
│   └── guess-the-route/           Route-guessing game (index.html + buses.js)
│
├── js/trains.js                   Shared front-end map/animation engine
├── lib/                           Vendored Leaflet + arc.js + reqwest
├── i/                             Icons (pins, station, train, loading, pacman, trophy)
│
├── tfwm/                          West Midlands bus subsystem (separate, older)
│   ├── index.html                 TfWM bus map front-end
│   └── bin/
│       ├── fetch.py               GTFS-realtime protobuf → data/<route> JSON
│       ├── fetch-check.py         (py2) Debug dump of feed entities
│       ├── gtfs-realtime.proto    Protobuf schema
│       ├── gtfs_realtime_pb2.py   Generated protobuf bindings
│       └── Stops.csv              Stop code → coordinates/name
│
├── tests/                         Pytest unit tests (accessible, bus, textual)
│
├── .agents/skills/                RePPIT workflow skill definitions (reppit-*)
├── .claude/agents/                reppit-orchestrator agent definition
├── proposals/                     modern-python-app-options.md
├── plans/                         proposal-1-python-first-php-removal.md, mini-followup.md
└── research/                      This dir: baseline + modernisation research docs
```

Total tracked files: 74 (`git ls-files`).

---

## 1. Python Backend (fetch + server)

Documented in depth in `research/fetch-server-modernisation.md`. Key facts, for orientation:

- **`bin/fetch.py`** — Standalone procedural script (all logic at module scope). Fetches live arrivals for **21 TfL lines** from `https://api.tfl.gov.uk/Line/<line>/Arrivals`, caches raw responses per line under `bin/cache/<line>` (100 s TTL), interpolates train positions from textual `currentLocation` strings, and atomically writes `data/london.json` (via `os.replace`) plus `data/london-text.json`. Imports `simplejson as json` (line 10) — a dependency **absent from `requirements.txt`** and the venv. Loads `.env` with `override=True`. Reads `bin/stations.json` and splices `bin/london-lines.js` verbatim into the output JSON string (`bin/fetch.py:410-411`).
- **`pyapp/app.py`** — FastAPI app. A `lifespan` context launches `_refresh_loop()` as an `asyncio.Task` that calls `_fetch_data()` immediately then every `DATA_REFRESH_INTERVAL = 60` s (`pyapp/app.py:41-86`). `_fetch_data()` runs `bin/fetch.py` via `asyncio.create_subprocess_exec`, passing `--app-key` from `os.environ["TFL_APP_KEY"]`. Serves an allowlist of static dirs/files, each mounted at both `/<x>` and `/map/tube/<x>`, and defines the three migrated endpoints. `import subprocess` (line 6) is unused.
- **`pyapp/services/`** — Three narrow modules: `accessible.py` (TrackerNet XML over HTTP, `_STOP_CODE_RE` guard, 55 hardcoded `STOPS`), `bus.py` (URA NDJSON over HTTP, see §4 detail below), `textual.py` (reads `data/london-text.json`, groups contiguous rows by line).
- **`tests/`** — `test_accessible.py` (2), `test_bus.py` (3), `test_textual.py` (1); all use `monkeypatch.setattr`; no tests for `fetch.py`.

### Route inventory (`pyapp/app.py`)

| Path(s) | Handler | Returns |
|---|---|---|
| `/text`, `/text.php`, `/map/tube/text`, `/map/tube/text.php` | `text_view` | Jinja2 `text.html` |
| `/data/bus[.php]`, `/map/tube/data/bus[.php]` | `bus_view` | `JSONResponse` |
| `/accessible[/index.php]`, `/map/tube/accessible[/index.php]` | `accessible_view` | Jinja2 `accessible.html` |
| `/map/tube/schematic/data/{name:path}` | `schematic_data_redirect` | 301 → `/map/tube/data/{name}` |
| `/`, `/index.html`, `/map/tube[/][index.html]` | `serve_index` | `FileResponse(index.html)` |
| `PUBLIC_STATIC_DIRS` × 2 mounts | `StaticFiles` | static files |
| `PUBLIC_STATIC_FILES` × 2 routes | `_make_handler` | `FileResponse` |

The bus module has a detail worth recording precisely (confirmed in `pyapp/services/bus.py`):

- `BUS_COLS_TEXT` (17 columns) is used both as the URA `ReturnList` request parameter and as the parse schema (`bus.py:10-14`).
- Route selection: if `len(route) == 7 and "," not in route` the query uses `RegistrationNumber`, else `LineName` (`bus.py:37-40`).
- Only rows with `ReturnType == 1` are kept; `StopPointState` 2 or 3 are dropped (`bus.py:61-64`).
- `route_prior` (`bus.py:88-97`) records, per stop, which stop preceded it in each vehicle's `EstimatedTime`-sorted route; used to back-position a bus behind its first upcoming stop (`bus.py:132-147`).
- `EstimatedTime` is a millisecond Unix timestamp (`/1000 - now`, `bus.py:114`).
- Two hardcoded zero-coordinate patches: "Summit Close" → `[51.606065, -0.276948]` and "Whitgift Centre (WJ)…" → `[51.3769688, -0.0987477]` (`bus.py:77-80, 120-121`).
- Output shape matches `london.json`'s top-level contract (`{lastupdate, station, trains, polylines, stations}`), so `trains.js` consumes it unchanged; `empty_bus_payload()` returns the same shape empty (`bus.py:168-175`).

---

## 2. Front-End Engine — `js/trains.js`

The single shared client engine for the tube/bus/schematic/skyfall maps. Pure vanilla JS + Leaflet; no build step. Configured entirely by a global `TrainTimes` object each HTML page defines before loading it.

### `TrainTimes` config surface (read across pages)

Observed keys and their consumers in `js/trains.js`:

| Key | Effect |
|---|---|
| `url` | Base path; `data/<name>` is appended for the XHR (`trains.js:409`), and controls popup wording (`trains.js:189`) |
| `refresh` | Minutes between data re-fetches; `setTimeout(... 1000*60*(TrainTimes.refresh||2))` (`trains.js:377`) |
| `centre`, `zoom`, `minZoom` | Initial map view (`trains.js:52-54`) |
| `keep_trains` | Reuse existing train markers on refresh vs. clear (`trains.js:368, 386`) |
| `station_icon` | Pin marker (`Station` = `L.Marker`) vs. `L.CircleMarker` (`trains.js:75-111`) |
| `station_hide` | Suppress station markers (`trains.js:381`) |
| `train_colour`, `line_colour` | Marker/polyline colours (`trains.js:116, 342`) |
| `train_marker` | Override marker class (used by skyfall, `trains.js:113`) |
| `permanent_train_label` | Bind persistent label vs. click popup (`trains.js:131, 137`) |
| `schematic` | Use image-overlay map (`schematic/map.png`) instead of tile layer (`trains.js:41-50`) |
| `map: 'black'` | Use `skyfall/black.png` tiles instead of OpenStreetMap (`trains.js:61-66`) |
| `fit_bounds` | `map.fitBounds(stations.getBounds())` after load (`trains.js:400`) |
| `update` | ms between animation ticks (`trains.js:403, 432`, default 200) |

### Data flow in the client

1. `load()` (`trains.js:38`) reads a route from the URL query/hash (`read_hash`, `trains.js:9`), builds the Leaflet map, adds tile/overlay + `trains` + `stations` layer groups, calls `Update.mapStart()`.
2. `Update.map(refresh)` (`trains.js:268`) XHR-GETs `TrainTimes.url + 'data/' + name` (default `london.json`; from `#line` dropdown when present). On the first (`refresh`) load it draws `data.polylines` (optionally arc-interpolated via `lib/arc.js`), then plots `data.stations` and `data.trains` markers; subsequent loads only update trains.
3. `process_data` schedules the next fetch and starts `Update.trains()` (`trains.js:403`), a `setTimeout` loop that recomputes every train's position each `update` ms.
4. `Train.calculateLocation(secs)` (`trains.js:159`) walks the train's `next[]` route, linearly (or great-circle) interpolating between consecutive stops based on `secs` vs. cumulative `mins*60`, sets the marker LatLng and a bearing angle; `getPathString` (`trains.js:219`) draws a custom SVG wedge (and a Pac-Man shape when `?pacman` is in the URL, `trains.js:237`).
5. A "speedy" checkbox multiplies animation `Speed` to 10× (`Update.speed`, `trains.js:434`).

Data contract the client expects: `{lastupdate, station, stations:[{point:[lat,lng], name}], trains:[{id, title, point:[lat,lng], left, next:[{point, name, mins, dexp}], string?, link?}], polylines:[[colour, opacity, [lat,lng]…]…], center?, span?}`.

---

## 3. Front-End HTML Pages

All five map pages load `js/trains.js` (except guess-the-route, see below), Leaflet from `lib/`, and `css.css`. Each differs only in its `TrainTimes` config and chrome.

| Page | File | `url` | Notable config |
|---|---|---|---|
| Geographic tube | `index.html` | `/map/tube/` | `station_icon: true`, `train_colour:'#ff0'`, `refresh:1` (`index.html:15-23`) |
| Schematic tube | `schematic/index.html` | `/map/tube/schematic/` | `schematic: true`, `station_icon:false` (`schematic/index.html:15-24`); map is `schematic/map.png` image overlay |
| Skyfall | `skyfall/index.html` | `/map/tube/` | `map:'black'`, `station_hide:true`, `permanent_train_label:true`, `line_colour:'#c00'`, custom `train_marker` using `skyfall/dot.png` (`skyfall/index.html:15-35`) |
| London buses | `london-buses/index.html` | `/map/london-buses/` | `refresh:0.5`, large `<select id="line">` of ~600 bus routes (`london-buses/index.html:48-675`); `ALL` option = `all-buses.json` |
| Guess the route | `london-buses/guess-the-route/index.html` | `/map/london-buses/guess-the-route/` | Loads `buses.js` (not `trains.js`) + `reqwest.min.js` (`.../index.html:13-25`) |

Shared UI patterns across pages: a `#map` div, a `#header` with title + "Data collected" timestamp span (`#update`), a `<noscript>` fallback linking to the textual view, and an `Info` show/hide panel. `index.html` links between the Geographic / Schematic / Skyfall variants and to `?pacman`.

### Guess-the-route game — `london-buses/guess-the-route/buses.js`

A fork of `trains.js` (same `Train`/`Station`/`Update`/`Message`/`Info` structure) with game logic bolted on and networking via `reqwest` instead of `XMLHttpRequest`:

- `pick_a_random_route()` selects a random `<option>` from `#line`; the route is hidden until guessed (`buses.js:14-20`).
- Map tiles start as `skyfall/black.png` (blacked out); the real OpenStreetMap tiles (`mapTiles`) are only added once the user guesses correctly (`buses.js:34, 52-57`).
- `make_guess()` compares the selection to the hidden `query` and shows higher/lower hints (`buses.js:28-42`).
- `createTitle` renders `"??? to ???"` until `solved` (`buses.js:110-112`).
- Fetches `/map/london-buses/data/<query>` — i.e. it consumes the same London-bus JSON payload as the main bus map.

---

## 4. TfWM Subsystem (`tfwm/`)

A separate, older West Midlands bus map, independent of the FastAPI app. Not wired into `pyapp/app.py`'s refresh loop; the README notes it is optional and run manually (`python tfwm/bin/fetch.py`).

- **`tfwm/bin/fetch.py`** — Python 3. Reads stop coordinates from `tfwm/bin/Stops.csv` (keyed by `ATCOCode`, `tfwm/bin/fetch.py:18-24`). Fetches a **GTFS-realtime protobuf** trip-updates feed from `http://api.tfwm.org.uk/gtfs/trip_updates` (cached 100 s) and a routes list from `.../Line/Route` (cached 3600 s), using `APP_ID`/`APP_KEY` imported from `tfwm/bin/config.py` (gitignored). Parses the protobuf via `gtfs_realtime_pb2.FeedMessage` (`tfwm/bin/fetch.py:59-60`). Emits one JSON file per route (plus an `all` aggregate) into `tfwm/data/`, matching the same `{station, lastupdate, trains, stations}` client contract, written with `os.rename` (`tfwm/bin/fetch.py:104-113`).
- **`tfwm/bin/fetch-check.py`** — Python **2** debug script (`print entity` without parens, `tfwm/bin/fetch-check.py:13`); dumps feed entities. Shebang points at a hardcoded `/srv/.virtualenvs/tfwm/bin/python`.
- **`tfwm/bin/gtfs_realtime_pb2.py`** — Generated protobuf bindings; **`tfwm/bin/gtfs-realtime.proto`** the schema.
- **`tfwm/index.html`** — Front-end. `url:'/map/tfwm/'`, `train_colour:'#f00'`, `station_icon:false`, `fit_bounds:true`; `<select>` of West Midlands routes (`tfwm/index.html:14-22, 40-208`). Loads the shared `/map/tube/js/trains.js`.

Gitignored TfWM artifacts: `/tfwm/data`, `/tfwm/bin/cache`, `/tfwm/bin/config.py` (`.gitignore:8-10`).

---

## 5. `bin/` Data & Utility Scripts

Besides `fetch.py` (see §1):

- **`bin/stations.json`** — Master coordinate table: 658 entries mapping station display name → `"lng,lat"` string (e.g. `"Acton Town Station": "-0.280462,51.503057"`). Some entries are per-line dicts; normalisation happens in `fetch.py`. (`bin/stations.json:1-…`)
- **`bin/london-lines.js`** — A JSON fragment beginning `"polylines": [ [ "#9364cc", 0.9, [lat,lng]… ] … ]`. Not valid standalone JSON; string-concatenated into `london.json` by `fetch.py` (`bin/london-lines.js:1-…`).
- **`bin/lines_for_stations.json`** — Station name → array of serving line names, e.g. `"Farringdon": ["Metropolitan","Circle","Hammersmith & City"]`.
- **`bin/stations-schematic.json`** — Alternate coordinate set for the schematic map.
- **`bin/stations.kml`** — KML source of station placemarks.
- **`bin/1.kml-to-json`** — Python **2** one-liner (`print json.dumps(...)`, `import simplejson`) that regexes `<name>`/`<coordinates>` out of `stations.kml` (`bin/1.kml-to-json:1-5`).
- **`bin/new-stations-from-api.py`** — Python **2** (`urllib.urlopen`) utility that rebuilds `stations.json` from the TfL `Route/Sequence/all` endpoint for a fixed list of line types, appending DLR/Overground/Tram suffixes, writing `stationsN.json` (`bin/new-stations-from-api.py:1-20`).
- **`bin/bus-fetch-lines`** — Python 3 utility that queries the URA `instant_V1?ReturnList=LineName` feed and prints a sorted `<option>` list (used to regenerate the bus `<select>` in the HTML pages) (`bin/bus-fetch-lines:1-27`).
- **`bin/.htaccess`** — `Deny from all` (Apache-era protection of the `bin/` dir).

Note the mix of Python versions: `fetch.py`, `bus-fetch-lines`, and `tfwm/bin/fetch.py` are Python 3; `1.kml-to-json`, `new-stations-from-api.py`, and `tfwm/bin/fetch-check.py` are Python 2 and would not run under the project's CPython 3.11 venv.

---

## 6. Static Assets

- **`lib/`** — Vendored, minified third-party JS/CSS: Leaflet core (`leaflet.js`, `leaflet.css`, `leaflet.ie.css`), the label plugin (`leaflet.label.js/.css`), a combined `leaflet.core-and-label.js/.css`, `arc.js` (great-circle interpolation, used by `trains.js` when present), and `reqwest.min.js` (AJAX, used only by guess-the-route). README notes: "PDMarker is LGPL", rest MIT.
- **`i/`** — Icons: `pin_{green,red,yellow,shadow}.png`, `station.png`, `train.{png,gif}`, `loading.gif`, `pacmanS.png`, `trophy.png`.
- **`css.css`** — Shared stylesheet (referenced with cache-busting query strings like `?2017-11-05c`).
- **`schematic/map.png`**, **`skyfall/{black.png,dot.png,css.css}`**, **`lu-screenshot.png`** — Page-specific imagery.

---

## 7. Configuration & Environment

- **`requirements.txt`** — `fastapi`, `uvicorn[standard]`, `jinja2`, `requests`, `python-dotenv`, `pytest` (all pinned with `>=…,<major+1`). No `simplejson` (imported by `fetch.py`), no `httpx`, `pydantic`, or protobuf lib (needed by `tfwm/`).
- **`.env.example`** — Documents the single secret `TFL_APP_KEY` (register at api-portal.tfl.gov.uk). Copied to `.env` (gitignored).
- **`.gitignore`** — Excludes `*.pyc`, `.env`, generated data (`data/all-buses.json`, `data/london.json`, `data/london-text.json`), `schematic/data`, `bin/cache`, `/tfwm/data`, `/tfwm/bin/cache`, `/tfwm/bin/config.py`, `.vite`, `node_modules`.
- **`README`** — Install/run instructions using `uv` (create `.venv`, install requirements, copy `.env`, seed data with `bin/fetch.py`, run `uvicorn pyapp.app:app --reload`, open `http://127.0.0.1:8000/index.html`). States PHP is no longer required and lists the Python replacement routes. Contains an "Issues"/"Possible TODOs" section describing known data-quality quirks (missing H&C stations, munged duplicate train IDs, constant-journey-time assumption). Copyright 2010 Matthew Somerville, MIT licence text.

`TFL_APP_KEY` is consumed in two places with differing `.env` override semantics: `fetch.py` (`override=True`) and `app.py` (module-import `load_dotenv` without override, then read from `os.environ` at each fetch and passed as `--app-key`). See `research/fetch-server-modernisation.md` for the full analysis.

---

## 8. Meta-Documentation & Tooling (non-runtime)

These directories describe a "RePPIT" (Research, Propose, Plan, Implement, Test) spec-driven workflow and hold prior planning artifacts; they are not part of the running application:

- **`.agents/skills/reppit-*/SKILL.md`** — Six skill definitions: `reppit-explore`, `reppit-research`, `reppit-propose`, `reppit-plan`, `reppit-implement`, `reppit-test`. `reppit-plan` carries `assets/design_doc_template.md`.
- **`.claude/agents/reppit-orchestrator.md`** — Orchestrator agent tying the RePPIT phases together.
- **`proposals/modern-python-app-options.md`** — Options analysis for the Python modernisation.
- **`plans/proposal-1-python-first-php-removal.md`**, **`plans/mini-followup.md`** — Implementation plans for the PHP→Python migration.
- **`research/php-to-python-modernization-baseline.md`** — Baseline research on the pre-migration PHP state.
- **`research/fetch-server-modernisation.md`** — Deep-dive on `fetch.py` + `pyapp/` (companion to this document).

---

## Cross-Component Data Flows

### Tube map (primary path)

```
[startup] pyapp/app.py lifespan → _refresh_loop (every 60s)
   → subprocess: bin/fetch.py --app-key <key>
        reads bin/stations.json, bin/london-lines.js, bin/cache/<line>
        GET api.tfl.gov.uk/Line/<line>/Arrivals   (21 lines)
        writes data/london.json (atomic), data/london-text.json
   → StaticFiles mount serves /map/tube/data/london.json
        ← js/trains.js (index / schematic / skyfall) polls & animates
   → /map/tube/text  → services/textual.py reads data/london-text.json → text.html
```

### On-demand endpoints (no background job)

```
/map/tube/data/bus?line=<route> → services/bus.py → GET countdown.api.tfl.gov.uk (URA NDJSON)
     ← london-buses/index.html (js/trains.js) and guess-the-route (buses.js) consume same shape
/map/tube/accessible?stop=<code> → services/accessible.py → GET cloud.tfl.gov.uk/TrackerNet → accessible.html
```

### TfWM map (independent, manual)

```
tfwm/bin/fetch.py (manual) → GET api.tfwm.org.uk GTFS-realtime protobuf + routes
     reads tfwm/bin/Stops.csv, tfwm/bin/config.py
     writes tfwm/data/<route>
   ← tfwm/index.html (js/trains.js) polls /map/tfwm/data/<route>
```

### Shared client contract

All server outputs (`london.json`, the bus payload, and TfWM per-route files) converge on the same top-level JSON shape — `{station, lastupdate, trains, stations, polylines}` with `trains[].next[]` route lists — so the single `js/trains.js` engine (and its `buses.js` fork) can render every map. `data/london.json` is the only file that carries `polylines` (spliced in from `bin/london-lines.js`); the bus and TfWM payloads send `polylines: []`.

---

## Notable Present-State Facts (no evaluation)

- `fetch.py` imports `simplejson as json` but `simplejson` is not in `requirements.txt` or the venv (`bin/fetch.py:10`).
- `pyapp/app.py:6` imports `subprocess` but the actual child process is spawned via `asyncio.create_subprocess_exec`.
- The `bin/` directory mixes Python 2 and Python 3 scripts; three utilities (`1.kml-to-json`, `new-stations-from-api.py`, `tfwm/bin/fetch-check.py`) are Python 2 syntax.
- `js/trains.js` and `london-buses/guess-the-route/buses.js` are near-duplicate engines; guess-the-route additionally depends on `lib/reqwest.min.js`.
- Static assets are referenced with absolute `/map/tube/...` paths in the HTML, matching the dual `/` and `/map/tube/` static mounts in `pyapp/app.py`.
- `TFL_APP_KEY` is the only application secret; `tfwm/bin/config.py` (`APP_ID`, `APP_KEY`) is a second, gitignored credential source for the West Midlands feed.
- Live/generated data (`data/*.json`) is gitignored and absent from a fresh checkout; the README's install steps seed it via `bin/fetch.py`.
```
