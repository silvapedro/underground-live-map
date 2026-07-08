# Research: PHP-to-Python Modernization Baseline

## Summary
This repository is a static Leaflet frontend plus backend data files served from `data/`, with language usage split between JavaScript for rendering, Python for feed generation, and a small set of PHP endpoints/pages. The committed PHP surface is limited to three files: `text.php`, `data/bus.php`, and `accessible/index.php` (`text.php:1-3`, `data/bus.php:1-5`, `accessible/index.php:1-4`; also inventory from `**/*.php`). The main map frontend fetches JSON via `TrainTimes.url + 'data/' + encodeURIComponent(name)` and does not directly call PHP APIs (`js/trains.js:408-409`). Python scripts generate the core tube and TfWM data files (`bin/fetch.py:49`, `bin/fetch.py:386-391`, `tfwm/bin/fetch.py:31`, `tfwm/bin/fetch.py:104-114`). Generated runtime data outputs are intentionally not committed (`.gitignore:2-4`).

## Detailed Findings

### 1. Frontend Runtime Contract (Static HTML/JS + JSON data files)
- The primary tube page sets `TrainTimes.url` to `/map/tube/` and includes `js/trains.js` (`index.html:18`, `index.html:25`).
- The schematic variant points to `/map/tube/schematic/` (`schematic/index.html:18`), the London buses page points to `/map/london-buses/` (`london-buses/index.html:17`), and TfWM points to `/map/tfwm/` (`tfwm/index.html:17`).
- The frontend data fetch path is assembled as `TrainTimes.url + 'data/' + encodeURIComponent(name)` (`js/trains.js:409`) using `XMLHttpRequest` (`js/trains.js:408`).
- Default file selection for tube mode is `london.json` when no dropdown exists (`js/trains.js:287`), while London buses exposes an `all-buses.json` option (`london-buses/index.html:674`).

### 2. PHP Footprint in the Repository
- PHP files in tree: `text.php`, `data/bus.php`, `accessible/index.php` (file inventory from `**/*.php`).
- `text.php` includes external site helpers and renders a textual view from `data/london-text.json` (`text.php:3`, `text.php:10`).
- `data/bus.php` is a JSON-producing endpoint that calls the legacy TfL Countdown API and emits JSON with `Content-Type: application/json` (`data/bus.php:17`, `data/bus.php:145-147`).
- `accessible/index.php` is an HTML page with PHP templates/includes and fetches TrackerNet XML for a specific stop (`accessible/index.php:3-4`, `accessible/index.php:24`, `accessible/index.php:116`).
- The main tube and schematic pages link users to the textual PHP page in `<noscript>` content (`index.html:50`, `schematic/index.html:51`).

### 3. Python Data Generation (Tube)
- The main tube generator is `bin/fetch.py` (`bin/fetch.py:1-2`) and reads TfL arrivals from `https://api.tfl.gov.uk/Line/%s/Arrivals` (`bin/fetch.py:49`).
- It canonicalizes station names, computes train positions/timings, and builds two outputs: map JSON (`london.json`) and textual data (`london-text.json`) (`bin/fetch.py:386-391`).
- The README install instructions describe running `bin/fetch.py` to produce map data (`README:26`).
- Station source files used by this path are committed in `bin/` (`bin/stations.json`, `bin/stations-schematic.json`, `bin/london-lines.js`).

### 4. Python Data Generation (TfWM)
- `tfwm/bin/fetch.py` reads API credentials from `config.py` (`tfwm/bin/fetch.py:16`), and `.gitignore` excludes this credentials file (`.gitignore:9`).
- It fetches GTFS realtime updates and route metadata (`tfwm/bin/fetch.py:31`, `tfwm/bin/fetch.py:44`) and parses protobuf via `gtfs_realtime_pb2` (`tfwm/bin/fetch.py:13`, `tfwm/bin/fetch.py:59`).
- It writes per-route JSON outputs into `tfwm/data/` (`tfwm/bin/fetch.py:104-114`), which are then consumed by the same frontend contract through `TrainTimes.url` (`tfwm/index.html:17`, `js/trains.js:409`).

### 5. Data and Ignore Rules
- Generated outputs are excluded from version control: `data/all-buses.json`, `data/london.json`, and `data/london-text.json` (`.gitignore:2-4`).
- Python cache and compiled artifacts are ignored (`.gitignore:1`, `.gitignore:6-8`), indicating expected local execution for feed scripts.

## Cross-Component Connections
- Tube rendering path: `index.html` bootstraps `TrainTimes.url=/map/tube/` (`index.html:18`) -> `js/trains.js` requests `/map/tube/data/<name>` (`js/trains.js:409`) -> expected file `london.json` (`js/trains.js:287`) produced by `bin/fetch.py` (`bin/fetch.py:386-389`).
- Textual accessibility path: `index.html` and `schematic/index.html` link to `text.php` (`index.html:50`, `schematic/index.html:51`) -> `text.php` reads `data/london-text.json` (`text.php:10`) produced by `bin/fetch.py` (`bin/fetch.py:391`).
- London bus route path: `london-buses/index.html` uses `/map/london-buses/` (`london-buses/index.html:17`) and route names including `all-buses.json` (`london-buses/index.html:674`) -> generic frontend fetch in `js/trains.js` (`js/trains.js:409`) -> legacy dynamic bus endpoint still exists in PHP (`data/bus.php:17`, `data/bus.php:145-147`).
- TfWM path: `tfwm/index.html` sets `/map/tfwm/` (`tfwm/index.html:17`) -> `js/trains.js` same fetch contract (`js/trains.js:409`) -> files written by `tfwm/bin/fetch.py` (`tfwm/bin/fetch.py:104-114`).
