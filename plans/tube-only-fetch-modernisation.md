# [Tube-Only + fetch.py Modernisation] Design Document

**Status:** Plan — not yet implemented
**Branch:** `feature/week2_reppit`
**Research source:** `research/codebase-overview.md`, `research/fetch-server-modernisation.md`
**Approach:** Proposal 1 (in-place modernisation, subprocess boundary retained)

---

## Current Context

- **The app is broken right now.** `bin/fetch.py:10` does `import simplejson as json`; `simplejson` is in neither `requirements.txt` nor the venv. Running the script raises `ModuleNotFoundError` immediately, so `data/` is never created and no tube data exists. The 60s refresh loop swallows this — `pyapp/app.py:61` only logs a warning on non-zero exit — so it fails silently and permanently.
- **Backend:** `pyapp/app.py` (FastAPI) spawns `bin/fetch.py` as a subprocess every 60s (`DATA_REFRESH_INTERVAL`, `pyapp/app.py:33`), serves an allowlist of static dirs, and hosts three migrated endpoints: `/text`, `/data/bus`, `/accessible`.
- **fetch.py:** A 421-line procedural script with all logic at module scope — no `main()`, no importable functions. Uses deprecated `optparse` (`bin/fetch.py:16`), carries Python-2 shims (`from __future__ import division` at `:5`; a dead `else` branch at `:131-134`), and mutates module-level globals (`out`, `outNext`, `sub_id`, `sub_ids`). Zero test coverage.
- **Bus/TfWM surface is dead or unwanted:**
  - **TfWM cannot run at all** — `tfwm/bin/config.py` (credentials) is gitignored and absent; `protobuf` is not installed nor in `requirements.txt`; `tfwm/data/` does not exist; and `tfwm/index.html:17` fetches `/map/tfwm/`, a route `app.py` never defines (it mounts `/tfwm` and `/map/tube/tfwm`). Every data fetch 404s. It is 2019 dead code.
  - **London buses** (`london-buses/`, `pyapp/services/bus.py`, `/data/bus`) works but is out of scope — the project is tube-only going forward.
- **Tests:** 6 tests across 3 files; 3 of them (`tests/test_bus.py`) cover bus code that is being deleted. `fetch.py` has none.

### Pain points being addressed

1. Fatal `simplejson` import — app produces no data.
2. Dead 429 retry logic and a cache that never hits (see Design Decision 3).
3. `fetch.py` is untestable (module-scope execution) and unmodernised (`optparse`, py2 shims).
4. ~Half the repo is bus/TfWM code that is unused, unwanted, or unrunnable.

---

## Requirements

### Functional Requirements

- `bin/fetch.py` runs to completion under the project venv and writes `data/london.json` + `data/london-text.json`.
- **The JSON output contract is unchanged.** `js/trains.js` must keep working without modification: `{station, lastupdate, trains[], stations[], polylines}` with `trains[].next[]` route lists. This includes the `london-lines.js` polyline splice (`bin/fetch.py:409-411`).
- All 21 tube/DLR/Overground/Elizabeth/Tram lines continue to be fetched (`bin/fetch.py:86-109`).
- Station canonicalisation, deduplication, and position-interpolation behaviour are preserved exactly.
- `/text` and `/accessible` endpoints remain functional. `/data/bus` is removed.
- All bus and TfWM code, assets, front-ends, and config are removed from the repo.
- `fetch.py`'s pure functions become importable for testing.

### Non-Functional Requirements

- **Performance:** Fixing the cache bug (Design Decision 3) reduces TfL API calls from 21/minute to ~21 per 100s window, materially cutting rate-limit exposure.
- **Observability:** `fetch.py` failures must be visible. Today a crash is invisible; after this change, warnings/errors go through `logging` and the subprocess exit code is meaningful.
- **Security:** No change to the secret model. `TFL_APP_KEY` remains the only application secret (`.env`, gitignored). The `tfwm/bin/config.py` credential path disappears with TfWM.
- **Scalability:** Not a concern — single-instance, single-user-scale app. Explicitly out of scope.

---

## Design Decisions

### 1. Keep the subprocess boundary; modernise in place

Will keep `fetch.py` as a standalone script invoked via `asyncio.create_subprocess_exec` (`pyapp/app.py:52-58`) rather than absorbing it into the app as an in-process async service, because:

- Process isolation means a crash or hang in the interpolation math cannot take down the web server. Given the script has *never run successfully on this branch*, preserving that blast-radius containment matters.
- The serial fetch loop implicitly avoids TfL's rate limit. Going concurrent (`asyncio.gather` + `httpx`) risks 429s whose real ceiling we have not measured.
- Smallest diff to a working app.
- **Trade-off:** Retains module-level mutable globals and the O(n²) dedup pass (`bin/fetch.py:295-304`). Modernised, not redesigned. The in-process rewrite remains available as a clean follow-up — and extracting `main()` + pure functions here is exactly its prerequisite.

### 2. Delete bus + TfWM outright rather than feature-flagging

Will remove the files entirely because:

- TfWM is provably unrunnable (four independent blockers, see Current Context) — there is nothing to preserve.
- Buses are explicitly out of the project's scope.
- Git history retains everything; recovery is `git revert`.
- **Trade-off:** `london-buses/` is working code being deleted. Accepted as an explicit product decision.

### 3. Fix the two latent bugs found while reading fetch.py

These are **behaviour changes**, called out deliberately rather than smuggled into a "pure refactor":

- **429 retry is dead code** (`bin/fetch.py:265-269`). `urllib.error.URLError` is caught *before* `urllib.error.HTTPError` — but `HTTPError` is a **subclass** of `URLError`, so it can never reach the `HTTPError` branch. Every HTTP error, including 429, is treated as a network error and the line is skipped. Fix: order `HTTPError` first. Effect: rate-limit backoff starts working.
- **Cache never hits** (`bin/fetch.py:256`). The freshness check calls `os.path.getmtime('cache/%s')` — **cwd-relative** — while the read and write use `dir + 'cache/%s'` — **script-relative**. `app.py` runs the subprocess with `cwd=REPO_ROOT`, so `getmtime` looks for `<repo>/cache/jubilee` (never exists), raises, and forces a fresh HTTP fetch every single run. Fix: use `dir` consistently. Effect: the 100s TTL cache starts working as designed.
- Also fix the 429 branch's use of an unbound/stale `live` variable (`bin/fetch.py:273`) — read the retry-after body from the exception (`e.read()`) instead.
- **Trade-off:** Output for a given set of cached inputs is unchanged; only the *fetch layer* behaviour changes. The golden-file test (Testing Strategy) pins the transformation pipeline, so these fixes are provably isolated to fetching.

### 4. Keep `/text` and `/accessible`

Both are tube features, so both stay. `/text` (and therefore `data/london-text.json`) is the `<noscript>` fallback linked from `index.html:50`. `/accessible` serves District line step-free predictions. Consequently `requests` stays in `requirements.txt` (still used by `pyapp/services/accessible.py`).

---

## Technical Design

### 1. Core Components

`bin/fetch.py` restructured so logic is importable. Module-scope execution is replaced by an explicit entry point; the pure transformation functions are lifted out of global state.

```python
# bin/fetch.py — target shape

def canon_station_name(s: str, line: str) -> str:
    """Normalise a TfL station name to match keys in stations.json. Unchanged logic."""

def parse_time(s: str | int) -> int:
    """'-'/'due' -> 0; 'MM:SS' and 'HH:MM:SS' -> seconds. Unchanged logic."""

def load_station_locations(path: Path) -> dict[str, dict[str, tuple[float, float]]]:
    """Parse stations.json; normalise 'lng,lat' strings and expand single-letter line keys."""

def fetch_line(key: str, api: str, cache_dir: Path, ttl: int = 100) -> list[dict] | None:
    """Return raw predictions for one line: cache-first, then HTTP.
    Returns None if the line should be skipped (network/HTTP error).
    HTTPError is caught BEFORE URLError (see Design Decision 3)."""

def interpolate_location(arr: dict, line: str, lookup) -> tuple[float, float] | None:
    """The five position cases: At Platform / empty-on-DLR / Leaving / Between / Approaching."""

def build_payload(out, outNext, station_locations, lines) -> tuple[dict, list]:
    """Return (london.json dict, london-text.json list). No globals."""

def main(argv: list[str] | None = None) -> int:
    """argparse; orchestrates fetch -> parse -> dedupe -> interpolate -> write."""

if __name__ == "__main__":
    sys.exit(main())
```

### 2. Data Models

No new models. Plain `dict` shapes are preserved exactly as the frontend contract requires (no pydantic — out of scope):

```python
# Per-train entry accumulated during parsing (unchanged)
Entry = TypedDict("Entry", {
    "station_name": str, "platform_name": str, "current_location": str,
    "time_to_station": int, "destination": str,
})

# data/london.json (unchanged — consumed by js/trains.js)
# {"station": str, "lastupdate": str, "trains": [...], "stations": [...], "polylines": [...]}

# data/london-text.json (unchanged — consumed by pyapp/services/textual.py)
# [{"id": str, "time": int, "line": str, "current": str}]
```

### 3. Integration Points

- **`pyapp/app.py` → `bin/fetch.py`:** unchanged contract — invoked as `[sys.executable, FETCH_SCRIPT, "--app-key", <key>]` with `cwd=REPO_ROOT`. The `--app-key` / `--stations` / `--output` / `--debug` CLI surface is preserved under `argparse`.
- **`bin/fetch.py` → `data/*.json` → `js/trains.js`:** JSON contract unchanged; frontend needs no edits beyond removing the bus-only `all-buses.json` branch.
- **Removed:** `/data/bus` route and the `pyapp/services/bus.py` → `countdown.api.tfl.gov.uk` integration. `tfwm/` → `api.tfwm.org.uk` GTFS-realtime integration.

### 4. Files Changed

**Modify:**
- `bin/fetch.py` (whole file, lines 1-421) — full restructure. Key sites: imports `1-16`, CLI `27-33`, station load `62-84`, fetch loop `252-290` (bug fixes at `256`, `265-281`), dedupe `295-304`, interpolation `321-358`, output `360-418`.
- `pyapp/app.py` — remove bus import (line `24`), `bus_view` route (lines `111-132`), `_LINE_RE` (line `92`, only used by `bus_view`), `"london-buses"` and `"tfwm"` from `PUBLIC_STATIC_DIRS` (line `36`), unused `import subprocess` (line `6`). After removal, `Query` (line `18`) and `JSONResponse` (line `19`) become unused imports — drop them.
- `js/trains.js` (lines `278-282`) — remove the `all-buses.json` refresh-interval special case.
- `index.html` (line `70`) — remove the "London buses" link.
- `schematic/index.html` (line `71`) — remove the "London buses" link.
- `skyfall/index.html` (line `78`) — remove the "London buses" link.
- `.gitignore` (lines `3`, `8-10`) — drop `data/all-buses.json`, `/tfwm/data`, `/tfwm/bin/cache`, `/tfwm/bin/config.py`.
- `README` (line `28`, lines `34-40`) — remove the TfWM generation step and the `/data/bus` route from Runtime notes.
- `requirements.txt` — no change (`requests` still needed by `accessible.py`); `simplejson` is *not* added — it is removed from use.

**Delete:**
- `tfwm/` (entire directory: `index.html`, `bin/fetch.py`, `bin/fetch-check.py`, `bin/gtfs-realtime.proto`, `bin/gtfs_realtime_pb2.py`, `bin/Stops.csv`)
- `london-buses/` (entire directory, incl. `guess-the-route/index.html` and `guess-the-route/buses.js`)
- `pyapp/services/bus.py` (lines 1-175)
- `tests/test_bus.py` (lines 1-60)
- `bin/bus-fetch-lines` (lines 1-27)

**Create:**
- `tests/test_fetch.py` — new unit tests (see Testing Strategy).

---

## Implementation Plan

1. **Phase 1 — Unbreak (smallest possible diff, verifiable on its own)**
   - Replace `import simplejson as json` with stdlib `import json` (`bin/fetch.py:10`).
   - Run `bin/fetch.py` and confirm `data/london.json` + `data/london-text.json` are produced.
   - **Capture golden fixtures:** freeze the resulting `bin/cache/*` files and the generated `london.json` as the baseline for Phase 3's regression test.

2. **Phase 2 — Delete bus + TfWM**
   - `git rm -r tfwm london-buses pyapp/services/bus.py tests/test_bus.py bin/bus-fetch-lines`.
   - Strip bus references from `pyapp/app.py`, `js/trains.js`, the three HTML link sites, `.gitignore`, `README`.
   - Confirm the app still boots and `/`, `/text`, `/accessible` all respond.

3. **Phase 3 — Modernise fetch.py**
   - `optparse` → `argparse`; preserve the exact CLI flags.
   - Drop py2 shims: `from __future__ import division` (`:5`), dead `else` branch (`:131-134`).
   - Extract pure functions; wrap orchestration in `main()` + `if __name__ == "__main__"`.
   - Replace `print`-to-stderr with `logging`; wire `--debug` to log level.
   - **Apply the two bug fixes** (Design Decision 3): `HTTPError` before `URLError`; consistent `dir`-relative cache path; read retry-after from `e.read()`.
   - Assert the golden fixture from Phase 1 still reproduces byte-identically from the frozen cache.

4. **Phase 4 — Tests**
   - Add `tests/test_fetch.py` (cases enumerated below).
   - Full suite green; manual browser verification.

---

## Testing Strategy

### Unit Tests (`tests/test_fetch.py`, new)

Mocking limited to the HTTP boundary via `monkeypatch.setattr`, matching the existing convention in `tests/test_accessible.py` and `tests/test_textual.py`. No mocking of internal functions.

- `test_parse_time_due_and_dash_return_zero` — `'-'` → `0`, `'due'` → `0`.
- `test_parse_time_accepts_int_passthrough` — `int` in → same `int` out.
- `test_parse_time_parses_mm_ss` — `'02:30'` → `150`.
- `test_parse_time_parses_hh_mm_ss` — `'01:02:30'` → `3750`.
- `test_parse_time_raises_on_garbage` — `'banana'` → raises.
- `test_canon_station_name_appends_station_suffix` — `'Acton Town'` + `central` → `'Acton Town Station'`.
- `test_canon_station_name_appends_tram_stop_for_tram` — tram line → `' Tram Stop'`.
- `test_canon_station_name_no_suffix_for_dlr_and_elizabeth` — no suffix appended.
- `test_canon_station_name_strips_platform_suffix` — `'Baker Street Platform 3'` → `'Baker Street Station'`.
- `test_canon_station_name_disambiguates_edgware_road` — Bakerloo → `'Edgware Road Bakerloo Station'`; other → `'Edgware Road Circle Station'`.
- `test_canon_station_name_encodes_ampersand` — `' & '` → `' &amp; '`.
- `test_lookup_returns_zero_zero_for_unknown_station` — unknown name → `(0, 0)`.
- `test_lookup_prefers_line_specific_over_wildcard` — line key wins over `'*'`.
- `test_interpolate_at_platform_uses_station_coords` — `'At Platform'` → destination coords exactly.
- `test_interpolate_leaving_midpoint_at_zero_seconds` — `'Leaving X'` with `time_to_station=0` → fraction `30/30` = midpoint behaviour per `bin/fetch.py:342`.
- `test_interpolate_between_uses_180s_floor` — `'Between X and Y'` with `time < 150` → `max=180` (`bin/fetch.py:351`).
- `test_interpolate_approaching_snaps_to_station` — `'Approaching X'` → X's coords.
- `test_skipped_locations_get_no_position` — `Siding`, `Depot`, `Network Rail Track`, `North Acton Junction`, `Lord's Disused`, `Road 21` → no `location` key set.
- **`test_http_error_caught_before_url_error`** — regression test for Bug 1: raising `HTTPError(429)` must hit the retry path, **not** the skip path.
- **`test_cache_is_used_when_fresh`** — regression test for Bug 2: a cache file newer than the TTL must prevent any HTTP call (assert the mocked `urlopen` is never invoked).
- `test_cache_refetches_when_stale` — cache file older than TTL → HTTP call is made.

### Integration Tests

- **`test_golden_output_from_frozen_cache`** — the load-bearing test. Given the Phase-1 frozen `bin/cache/*` fixtures, running the pipeline produces a `london.json` byte-identical to the frozen baseline. This is what proves the refactor and the bug fixes did not alter the transformation.
- `test_fetch_writes_both_output_files` — run `main()` against fixtures in a `tmp_path` output dir; assert both files exist and parse as valid JSON.
- `test_london_json_has_frontend_contract` — assert top-level keys `station`, `lastupdate`, `trains`, `stations`, `polylines` are present and `trains[0]` has `point`, `next`, `left`, `id`, `title` (the contract `js/trains.js` depends on).
- Existing `tests/test_accessible.py` and `tests/test_textual.py` must remain green (regression guard for the `app.py` edits).

---

## Observability

### Logging

Replaces the current `print_debug` / `print(..., file=sys.stderr)` mix in `bin/fetch.py`.

- `INFO` — run start/finish; per-line cache-hit vs. fetched; count of trains written.
- `WARNING` — line skipped due to network or HTTP error (currently `bin/fetch.py:266`, `:279`); station lookup failure (currently `:319`).
- `ERROR` — unrecoverable failure that aborts the run.
- `--debug` sets level to `DEBUG`; default is `INFO`. Output goes to stderr, which `app.py` already captures via `proc.communicate()` (`pyapp/app.py:52-58`).

### Metrics

Not applicable — single-instance hobby app, no metrics backend. Deliberately out of scope.

The one gap worth closing is that `pyapp/app.py:61` currently logs a non-zero subprocess exit at `WARNING` and continues. With `fetch.py` now logging to stderr, that warning becomes actionable rather than silent.

---

## Future Considerations

### Potential Enhancements

- **Proposal 2 (deferred):** absorb `fetch.py` into `pyapp/services/tube.py`, called in-process with `httpx.AsyncClient` and `asyncio.gather` for concurrent line fetching. This plan's `main()` + pure-function extraction is its prerequisite. Blocked on measuring TfL's actual rate limit.
- Parse `bin/london-lines.js` as real data instead of the string-splice at `bin/fetch.py:409-411`.
- Consolidate `stations.json` / `stations-schematic.json` / `lines_for_stations.json` / `stations.kml` into one authoritative source (the README's own top TODO).

### Known Limitations (accepted, not addressed here)

- Module-level mutable globals (`out`, `outNext`, `sub_ids`) survive as function-local state but the overall design stays procedural.
- O(n²) cross-line dedup pass (`bin/fetch.py:295-304`) is left as-is — n is small (~600 trains).
- `data/london-text.json` is still written non-atomically (`bin/fetch.py:418`), unlike `london.json`.
- `'Approaching X'` interpolation snaps to the station with no departure-side interpolation (`bin/fetch.py:355-358`) — needs position history to fix, out of scope.
- The remaining py2 utilities `bin/1.kml-to-json` and `bin/new-stations-from-api.py` are untouched; they are manual, occasional-use tools.

---

## Dependencies

### Development Dependencies

No new runtime or dev dependencies.

- **Removed from use:** `simplejson` (was imported but never installed — the root cause of the outage).
- **Removed with TfWM:** the `protobuf` requirement, which was never actually declared.
- **Retained:** `requests` — still used by `pyapp/services/accessible.py`.
- **Test framework:** existing `pytest>=8.0.0,<9.0.0` (`requirements.txt:6`). No `pytest-asyncio` needed — the subprocess boundary means no async tests.

---

## Security Considerations

- **Secrets:** No change. `TFL_APP_KEY` remains the only application secret, loaded from gitignored `.env`. Deleting TfWM removes a second credential path (`tfwm/bin/config.py`, `APP_ID`/`APP_KEY`).
- **Attack surface reduction:** Removing `/data/bus` deletes a user-input-reachable endpoint (the `line` query param and its `_LINE_RE` validator at `pyapp/app.py:92`) and an outbound HTTP integration to `countdown.api.tfl.gov.uk`. Removing the `london-buses` and `tfwm` static mounts (`pyapp/app.py:36`) shrinks the exposed static allowlist.
- **Note (pre-existing, unchanged):** `pyapp/services/accessible.py:85` calls TfL TrackerNet over plain **HTTP**, not HTTPS. Out of scope for this change; flagged for a follow-up.
- The `--app-key` is passed as a subprocess argv element and appended to the TfL URL as a query string (`bin/fetch.py:58-59`) — visible in process listings. Pre-existing; unchanged by this plan.

---

## Rollout Strategy

Single PR on `feature/week2_reppit`, with the four phases as separate reviewable commits. This is a local/hobby app with no staging or production tiers, so the ceremony is deliberately light.

1. **Development:** Phases 1-4 as above, each commit independently green.
2. **Testing:** Full `pytest` suite passes; golden-file regression test confirms unchanged output.
3. **Manual verification:** Boot `uvicorn pyapp.app:app --reload`; confirm:
   - `/index.html` renders trains that move, `#update` timestamp advances after 60s.
   - `/schematic/` and `/skyfall/` still render (they share `js/trains.js` and `london.json`).
   - `/text` and `/accessible` still respond.
   - `/data/bus`, `/london-buses/`, `/tfwm/` now return 404.
   - No `ModuleNotFoundError` in the uvicorn log; `bin/cache/` populates and is reused on the second refresh cycle.
4. **Rollback:** `git revert` the merge. Bus/TfWM code is recoverable from history.

---

## References

- `research/codebase-overview.md` — full repository map; §1 Python Backend, §4 TfWM, §5 `bin/` utilities, Cross-Component Data Flows.
- `research/fetch-server-modernisation.md` — `fetch.py` structure, globals, interpolation cases, dependency discrepancy.
- `plans/proposal-1-python-first-php-removal.md` — the prior PHP→Python migration this builds on.
- TfL Unified API — `https://api.tfl.gov.uk/Line/<line>/Arrivals`; key registration at `https://api-portal.tfl.gov.uk/`.
