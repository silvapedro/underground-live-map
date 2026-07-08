# Mini Follow-Up Plan

## Current Context
- The PHP-to-Python migration is already in place and the main runtime paths are working.
- The remaining follow-up work is small and focused: make the production-style `/map/tube` path match the root routes, harden input validation for the bus endpoint, add a small test suite for the new service layer, and align the README install instructions with the validated `uv` workflow.
- The current implementation already has route handlers in `pyapp/app.py`, service logic in `pyapp/services/bus.py` and `pyapp/services/accessible.py`, and installation guidance in `README`.

## Requirements

### Functional Requirements
- Requests under `/map/tube/*` should behave consistently with the root URLs used by the app.
- The bus endpoint should reject clearly invalid `line` inputs before they reach the upstream request builder.
- The new service layer should have a minimal test set covering the text grouping, bus formatting, and accessible stop-code validation paths.
- The README should describe the Python installation flow that was actually validated in this repo.

### Non-Functional Requirements
- Keep the change set small and local to the follow-up work.
- Preserve the existing compatibility shims for legacy `.php` routes.
- Keep the runtime behavior stable for existing valid requests.
- Avoid reintroducing exposure of private repo files while adding route aliases.

## Design Decisions

### 1. Route Alias Coverage
Add explicit `/map/tube/...` aliases for the Python routes that users can reach from the production-style mount because the current UI and links assume that path prefix.
- Rationale: keeps the published URL shape consistent with the static asset mount.
- Rationale: avoids forcing the front end to know about the server layout.
- Trade-offs considered: duplicate route definitions versus changing all links to absolute root paths.

### 2. Input Validation at the Boundary
Validate `line` in `pyapp/app.py` before it reaches `fetch_bus_payload`.
- Rationale: the route boundary is the narrowest and clearest enforcement point.
- Rationale: mirrors the stop-code validation already added for the accessible route.
- Trade-offs considered: strict validation versus permissive pass-through; strict validation is preferred because the endpoint accepts a small, structured parameter.

### 3. Minimal Test Coverage
Add a focused pytest suite for the new Python services rather than broad end-to-end mocking.
- Rationale: the service functions are the main behavior-shaping layer.
- Rationale: tests can validate the transformation logic without depending on live upstream services.
- Trade-offs considered: live integration coverage would be more realistic, but it would be slower and flaky for this repo.

## Technical Design

### 1. Core Components
- `pyapp/app.py` will gain route aliases for `/map/tube/text`, `/map/tube/accessible`, and `/map/tube/data/bus`, plus a `line` validation guard before bus requests are dispatched.
- `pyapp/services/bus.py` will keep the transformation logic unchanged, but the route contract will assume validated input from the app layer.
- `pyapp/services/accessible.py` will remain the stop-code validator and XML parser; no behavior change is planned here beyond tests.
- `README` will be updated to match the validated virtual-environment and `uv` workflow.

### 2. Data Models
- No new runtime data models are required.
- The tests will exercise the existing dictionary-shaped payloads returned by `group_rows_by_line`, `fetch_bus_payload`, and `fetch_accessible_predictions`.

### 3. Integration Points
- The browser-side URLs should work under both `/` and `/map/tube/` after the aliases are added.
- The `line` parameter will be checked before `fetch_bus_payload` constructs the upstream request URL.
- The test suite will patch upstream calls where necessary and assert only the local transformation/validation behavior.

### 4. Files Changed
- `pyapp/app.py` (relevant snippet lines 30-119) - add `/map/tube/text`, `/map/tube/accessible`, and `/map/tube/data/bus` aliases; validate `line` before calling the bus service.
- `pyapp/services/bus.py` (relevant snippet lines 31-46, 25-28) - keep current parsing and formatting behavior in place; support the boundary validation contract and cover it with tests.
- `pyapp/services/accessible.py` (relevant snippet lines 81-89, 10-11) - keep the stop validation and XML parsing behavior as-is; add test coverage for accepted/rejected stop codes.
- `README` (relevant snippet lines 22-29) - update install instructions to the `uv venv` / `uv pip install` flow and keep the runtime note accurate.
- `tests/test_textual.py` (new file, planned lines 1-120) - cover `group_rows_by_line` and the existing textual grouping output shape.
- `tests/test_bus.py` (new file, planned lines 1-180) - cover `_plural_minutes` and the bus payload transformation path with a mocked upstream response.
- `tests/test_accessible.py` (new file, planned lines 1-120) - cover `_STOP_CODE_RE` acceptance/rejection and the accessible parser's local output mapping.

## Implementation Plan

1. Add route aliases and boundary validation.
   - Register the `/map/tube/...` aliases in `pyapp/app.py`.
   - Add a `line` validation guard before `fetch_bus_payload` is called.
   - Keep the existing `.php` compatibility routes intact.

2. Add targeted tests.
   - Create tests for the text grouping service.
   - Create tests for the bus formatting helpers and route-level validation behavior.
   - Create tests for the accessible stop-code validation and parser output shape.

3. Update the README.
   - Replace the generic `pip install -r requirements.txt` wording with the validated `uv` workflow.
   - Keep the runtime notes in sync with the route aliases and Python endpoints.

## Testing Strategy

### Unit Tests
- Verify `group_rows_by_line` produces the expected grouped structure for a small sample input.
- Verify `_plural_minutes` formats whole and half-minute values consistently.
- Verify the bus route rejects invalid `line` values before the service call.
- Verify `_STOP_CODE_RE` accepts valid District stop codes and rejects traversal-like or malformed inputs.
- Verify `fetch_accessible_predictions` produces the expected output mapping for a mocked XML payload.

### Integration Tests
- Smoke-test `/text`, `/accessible`, `/data/bus`, and the new `/map/tube/...` aliases against the local FastAPI app.
- Confirm the README wording change does not affect runtime behavior.

## Observability

### Logging
- No new logging is required for this follow-up.
- Preserve the existing warning logs for upstream failures in the bus and accessible routes.

### Metrics
- No new metrics are required.

## Future Considerations

### Potential Enhancements
- Convert the static repo asset mounting into a dedicated public directory in a later cleanup pass.
- Consider replacing the remaining legacy `.php` compatibility routes after callers migrate.

### Known Limitations
- The bus and accessible endpoints still depend on upstream TfL services, so local validation only confirms the request path and payload shaping.

## Dependencies

### Development Dependencies
- `pytest` for the new unit tests.
- Existing runtime dependencies already present in `requirements.txt`.

## Security Considerations
- The route aliasing must not re-expose private repo content.
- The added `line` validation should reject malformed inputs before they can influence upstream URL construction.
- The existing accessible stop validation remains the primary input boundary for that endpoint.

## Rollout Strategy
1. Develop and verify locally.
2. Run the focused test suite.
3. Smoke-test the route aliases and validation behavior against the local server.
4. Update the README.
5. Review and merge.

## References
- [pyapp/app.py](../pyapp/app.py)
- [pyapp/services/bus.py](../pyapp/services/bus.py)
- [pyapp/services/accessible.py](../pyapp/services/accessible.py)
- [README](../README)
