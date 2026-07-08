# [PHP Removal + Python-First Modernization] Design Document

## Current Context
- The map UI is static HTML + JavaScript and reads transit payloads from `/data/<name>` via `XMLHttpRequest` in shared client logic (`js/trains.js:408-409`).
- Tube and TfWM data generation is already Python-based (`bin/fetch.py:1-2`, `bin/fetch.py:386-391`, `tfwm/bin/fetch.py:104-114`).
- PHP is limited to three paths:
  - Textual fallback page: `text.php:1-27`
  - London buses JSON endpoint: `data/bus.php:1-147`
  - Accessible District page: `accessible/index.php:1-119`
- Two pages still reference `text.php` in noscript blocks (`index.html:46-51`, `schematic/index.html:47-52`).

## Requirements

### Functional Requirements
- Remove PHP from the repository and replace all current PHP behavior with Python equivalents.
- Preserve current user-visible behavior for:
  - Textual underground description page (currently from `data/london-text.json`).
  - London buses JSON response shape consumed by map markers.
  - Accessible District stop lookup page behavior (`?stop=` query model).
- Keep existing frontend map behavior and data refresh logic unchanged for tube/tfwm routes.
- Ensure noscript textual links point to the new Python-backed route/page.

### Non-Functional Requirements
- Keep migration low-risk by minimizing frontend changes and preserving response schemas.
- Maintain compatibility with simple local/dev hosting workflows.
- Keep generated data files excluded from git as currently configured (`.gitignore:2-4`).

## Design Decisions

### 1. Use a Python HTTP app for former PHP responsibilities
Will implement a lightweight Python web app (FastAPI or Flask) for the three former PHP behaviors because:
- It removes runtime PHP while preserving dynamic capabilities currently present in `data/bus.php` and `accessible/index.php`.
- It avoids forcing a frontend rewrite; existing static map pages can continue to consume JSON and links with minimal edits.
- Trade-off: introduces a Python service process for runtime routes that were previously PHP scripts.

### 2. Keep frontend JSON/map contract stable
Will keep `js/trains.js` data expectations unchanged because:
- Current marker/render logic is tightly coupled to specific JSON fields (`js/trains.js:294-407`).
- Stable payloads reduce regression risk and allow incremental modernization.
- Trade-off: some legacy response shape quirks are retained during this phase.

### 3. Replace links and remove PHP files in same milestone
Will update HTML references and delete PHP files in one controlled migration because:
- Prevents dead links after deployment.
- Keeps repository language footprint aligned with the objective (mainly Python).
- Trade-off: requires a clear rollout sequence to avoid temporary broken routes.

## Technical Design

### 1. Core Components
```python
# New Python web entrypoint
app = FastAPI()  # or Flask if chosen during implementation

@app.get("/text")
def text_view():
    ...  # render london-text.json as HTML

@app.get("/data/bus")
def bus_data(line: str):
    ...  # return JSON schema compatible with existing frontend

@app.get("/accessible")
def accessible(stop: str | None = None):
    ...  # render stop list and optional live table
```

### 2. Data Models
```python
# Transport payload shape expected by frontend
class VehicleStop(BaseModel):
    dexp: str
    mins: float
    name: str
    point: list[float]

class MapVehicle(BaseModel):
    id: str
    title: str
    next: list[VehicleStop]
    left: str
    point: list[float]

class MapPayload(BaseModel):
    lastupdate: str
    station: str
    trains: list[MapVehicle]
    polylines: list
    stations: list
```

### 3. Integration Points
- Static pages keep loading `js/trains.js` and existing `/data/<name>` patterns for tube/tfwm (`js/trains.js:409`).
- Noscript links in tube pages switch from PHP to Python route/page.
- New Python bus endpoint must keep JSON fields used by the map (`id`, `title`, `next`, `point`, `stations`, `lastupdate`).
- New Python accessible endpoint preserves `?stop=<code>` behavior and station list navigation.

### 4. Files Changed
- index.html (noscript text link snippet line 46-51)
- schematic/index.html (noscript text link snippet line 47-52)
- text.php (entire file line 1-27, remove)
- data/bus.php (entire file line 1-147, remove)
- accessible/index.php (entire file line 1-119, remove)
- README (install/runtime instructions currently around line 17-27; update to Python service + generators)
- requirements.txt (new file, line 1-40; runtime + HTTP client deps)
- pyapp/app.py (new file, line 1-260; Python routes replacing PHP behavior)
- pyapp/templates/text.html (new file, line 1-160; textual route template)
- pyapp/templates/accessible.html (new file, line 1-260; accessible route template)
- pyapp/services/bus.py (new file, line 1-260; bus data transformation logic)
- pyapp/services/accessible.py (new file, line 1-220; TrackerNet fetch + parsing)
- pyapp/services/textual.py (new file, line 1-140; london-text.json rendering model)
- pyapp/__init__.py (new file, line 1-20)

## Implementation Plan

1. Phase 1: Python runtime skeleton
   - Add Python app structure (`pyapp/`) with route stubs and typed payload contracts.
   - Add dependency manifest (`requirements.txt`) and local run instructions in `README`.
   - Add route-level smoke checks for `/text`, `/data/bus`, `/accessible` (manual + scripted).

2. Phase 2: Feature parity migration
   - Implement `/text` route using `data/london-text.json` parity with former `text.php` behavior.
   - Implement `/data/bus?line=...` with JSON schema parity to former `data/bus.php`.
   - Implement `/accessible?stop=...` with parity to former `accessible/index.php` table output behavior.

3. Phase 3: Frontend link updates and PHP removal
   - Update `index.html` and `schematic/index.html` noscript links to Python route.
   - Remove PHP files after confirming replacement routes are working.
   - Verify no PHP references remain in repository text search.

4. Phase 4: Validation and rollout hardening
   - Validate all map modes still load and refresh (tube/schematic/london-buses/tfwm).
   - Validate fallback/no-script journey for textual page.
   - Document deployment notes for serving static assets plus Python app.

## Testing Strategy

### Unit Tests
- Bus transformation:
  - given sample upstream records, outputs required schema keys and point fields.
  - preserves pluralization/time formatting behavior compatible with current UI.
- Text rendering:
  - groups entries by line and formats minute text like current page.
- Accessible parsing:
  - parses representative TrackerNet XML and marks non-2xxxx trains with CSS class equivalent.

### Integration Tests
- `GET /text` returns HTML containing grouped line sections from `data/london-text.json`.
- `GET /data/bus?line=73` returns JSON with `trains`, `stations`, `lastupdate`.
- `GET /accessible` returns station list; `GET /accessible?stop=ACT` returns prediction table.
- Browser smoke tests:
  - tube page still loads map data.
  - schematic page still loads map data.
  - london-buses page still refreshes and updates permalink/dropdown behavior.
  - tfwm page remains unaffected.

## Observability

### Logging
- Add request-level logging for new Python routes.
- Add upstream API failure logging for bus and accessible providers.
- Include timing/duration logs for upstream fetch calls.

### Metrics
- Route latency (`/text`, `/data/bus`, `/accessible`).
- Upstream failure rate (TfL/TrackerNet requests).
- Payload generation success/failure counters.

## Future Considerations

### Potential Enhancements
- Replace `XMLHttpRequest` in `js/trains.js` with modern fetch abstraction.
- Consolidate legacy Python scripts into shared service modules.
- Add caching layer for bus/accessibility upstream calls.

### Known Limitations
- Legacy frontend architecture remains in place in this proposal.
- Some upstream endpoints used by legacy logic may be unstable or subject to deprecation.

## Dependencies

### Development Dependencies
- fastapi or flask
- uvicorn or waitress/gunicorn for local/prod run
- requests (or stdlib urllib) for upstream HTTP calls
- lxml or xml.etree for XML parsing

## Security Considerations
- Validate and sanitize `line` and `stop` query params.
- Enforce outbound request timeouts and handle upstream failures safely.
- Avoid exposing credentialed endpoints in client-side code.

## Rollout Strategy
1. Land Python app + tests without deleting PHP.
2. Run parity verification in local/staging environment.
3. Switch links to Python routes.
4. Remove PHP files.
5. Monitor logs/metrics for 24-48h and adjust.

## References
- research/php-to-python-modernization-baseline.md
- proposals/modern-python-app-options.md
- js/trains.js:287
- js/trains.js:408-409
- bin/fetch.py:386-391
