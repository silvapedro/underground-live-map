## Solution Proposals

Context:
- Request: Propose options for a more modern app that removes PHP and standardizes mainly on Python.
- Research Source: research/php-to-python-modernization-baseline.md (Summary, PHP Footprint, Frontend Runtime Contract, Cross-Component Connections).

Proposal 1 - Python-first, static-site-compatible migration (minimal disruption)
- Overview: Keep the existing static Leaflet frontend and JSON contract, but replace all PHP files with Python utilities/pages while preserving current URLs and data file semantics. This aligns with the current architecture where the frontend already consumes JSON files and does not require PHP to render maps. It modernizes runtime by removing PHP without forcing a frontend rewrite.
- Key Changes:
  - Replace text.php with a Python-generated static HTML page (or lightweight Python-rendered endpoint) sourced from data/london-text.json: text.php:10, bin/fetch.py:391.
  - Retire data/bus.php by moving bus data generation to Python and writing compatible data files into data/: data/bus.php:17, data/bus.php:145-147, js/trains.js:409, london-buses/index.html:674.
  - Replace accessible/index.php with Python-rendered equivalent page and templates: accessible/index.php:3-4, accessible/index.php:24, accessible/index.php:116.
  - Update noscript links in index pages away from PHP paths: index.html:50, schematic/index.html:51.
- Trade-offs:
  - Benefits: Lowest migration risk; preserves frontend behavior and deployment shape; easy rollback by file-level parity.
  - Costs: Keeps legacy frontend stack and URL assumptions; modernization is primarily backend/runtime and tooling, not UX architecture.
- Validation:
  - Compare JSON schema/fields before vs after for london.json, london-text.json, and bus data payloads: js/trains.js:287, js/trains.js:409.
  - Browser smoke tests for geographic/schematic/tfwm/bus pages loading and map refresh behavior: index.html:18, schematic/index.html:18, tfwm/index.html:17, london-buses/index.html:17.
  - Accessibility page parity tests against existing stop query behavior: accessible/index.php:24.
- Open Questions:
  - Should compatibility require keeping identical route paths under /map/... or is URL change acceptable?
  - Is static generation sufficient for accessible page behavior, or does it need live request-time fetches?

Proposal 2 - Python service layer (FastAPI) with scheduled data jobs (balanced modernization)
- Overview: Introduce a single Python web service that owns all current PHP responsibilities plus data endpoints, while retaining existing frontend pages initially. Move from file-based-only serving to API endpoints with optional persisted snapshots for cache/offline resilience.
- Key Changes:
  - Create FastAPI app with endpoints for text view data, bus data, and accessible stop lookups replacing text.php, data/bus.php, accessible/index.php: text.php:1-3, data/bus.php:1-5, accessible/index.php:1-4.
  - Wrap existing generators (bin/fetch.py and tfwm/bin/fetch.py) into reusable modules invoked by scheduled jobs; expose latest data via API and optional static files: bin/fetch.py:1-2, bin/fetch.py:386-391, tfwm/bin/fetch.py:104-114.
  - Migrate frontend fetch target from /data/<name> files to versioned API routes with backward-compatible aliases: js/trains.js:409.
- Trade-offs:
  - Benefits: Clear Python application boundary, easier testing/observability, straightforward future expansion.
  - Costs: Moderate migration complexity; introduces server runtime dependency instead of pure static+files for core paths.
- Validation:
  - Contract tests for API responses matching fields expected by trains.js markers and timing logic: js/trains.js:294-407.
  - End-to-end tests for route selection and periodic refresh semantics: js/trains.js:373-407, london-buses/index.html:674.
  - Scheduled job checks for data freshness and failure handling around upstream APIs: bin/fetch.py:49, tfwm/bin/fetch.py:31.
- Open Questions:
  - Should the service continue writing snapshot JSON files for compatibility and fallback?
  - What deployment target is preferred (single VM/container, platform service, or static+API split)?

Proposal 3 - Full modern app split: Python API + modern frontend rewrite (highest modernization)
- Overview: Replace the legacy static HTML pages with a modern frontend app (for example React/Vite) backed by a Python API service. Keep existing map logic behavior, but modularize data/state/rendering and add typed contracts.
- Key Changes:
  - Build Python backend as system of record for transit data and textual/accessible views; remove all PHP and file-coupled endpoint assumptions: text.php:1-3, data/bus.php:1-5, accessible/index.php:1-4.
  - Rewrite frontend pages currently using inline TrainTimes config and shared trains.js into componentized routes/views: index.html:15-25, schematic/index.html:15-23, tfwm/index.html:14-22, london-buses/index.html:14-23.
  - Replace XMLHttpRequest polling with modern fetch/state management while preserving refresh semantics: js/trains.js:408-420, js/trains.js:423-449.
- Trade-offs:
  - Benefits: Largest long-term maintainability gain, modern developer experience, clean separation of concerns.
  - Costs: Highest scope and regression risk; requires broader test coverage and staged rollout.
- Validation:
  - Golden-path visual parity tests for map rendering, markers, and train movement calculations against current behavior: js/trains.js:98-275, js/trains.js:423-449.
  - API contract + frontend integration tests per view (tube, schematic, buses, tfwm): index.html:18, schematic/index.html:18, london-buses/index.html:17, tfwm/index.html:17.
  - Performance checks for refresh intervals and rendering smoothness under full route datasets.
- Open Questions:
  - Is modernization expected to preserve current page look-and-feel or allow UX redesign?
  - Should this happen as one cutover or incremental route-by-route migration?
