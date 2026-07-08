from __future__ import annotations

from pathlib import Path

import logging

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pyapp.services.accessible import STOPS, fetch_accessible_predictions
from pyapp.services.bus import empty_bus_payload, fetch_bus_payload
from pyapp.services.textual import group_rows_by_line, load_textual_rows

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
DATA_DIR = REPO_ROOT / "data"

# Directories at the repo root that are safe to expose as static assets.
PUBLIC_STATIC_DIRS = ("lib", "js", "i", "data", "schematic", "skyfall", "london-buses", "tfwm")
# Individual files at the repo root that are safe to expose.
PUBLIC_STATIC_FILES = ("css.css", "lu-screenshot.png", "README")

app = FastAPI(title="underground-live-map Python runtime")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
logger = logging.getLogger(__name__)


@app.get("/text")
@app.get("/text.php")
def text_view(request: Request):
    rows = load_textual_rows(DATA_DIR / "london-text.json")
    groups = group_rows_by_line(rows)
    return templates.TemplateResponse(
        request,
        "text.html",
        {
            "groups": groups,
        },
    )


@app.get("/data/bus")
@app.get("/data/bus.php")
def bus_view(line: str = Query(default="")):
    if not line.strip():
        raise HTTPException(status_code=400, detail="line query parameter is required")

    try:
        payload = fetch_bus_payload(line)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Bus upstream request failed; returning empty payload", exc_info=exc)
        payload = empty_bus_payload()

    response = JSONResponse(content=payload)
    response.headers["Cache-Control"] = "max-age=30"
    if not payload["trains"] and not payload["stations"]:
        response.headers["X-Upstream-Status"] = "fallback-empty"
    return response


@app.get("/accessible")
@app.get("/accessible/index.php")
def accessible_view(request: Request, stop: str | None = None):
    station_name = ""
    platforms = []

    if stop:
        try:
            result = fetch_accessible_predictions(stop)
            station_name = result["station_name"]
            platforms = result["platforms"]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid stop code")
        except Exception as exc:  # noqa: BLE001
            logger.warning("Accessible upstream request failed", exc_info=exc)
            raise HTTPException(status_code=502, detail="Failed to fetch predictions")

    return templates.TemplateResponse(
        request,
        "accessible.html",
        {
            "station_name": station_name,
            "platforms": platforms,
            "stops": STOPS,
        },
    )


# Serve repository static files so current HTML/CSS/JS assets remain usable.
# Restricted to an explicit allowlist so private/dev files (.venv, .git, plans/,
# proposals/, research/, pyapp/, bin/, ...) are not exposed.
INDEX_FILE = REPO_ROOT / "index.html"


@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
@app.get("/map/tube", include_in_schema=False)
@app.get("/map/tube/", include_in_schema=False)
@app.get("/map/tube/index.html", include_in_schema=False)
def serve_index():
    return FileResponse(INDEX_FILE)


for _filename in PUBLIC_STATIC_FILES:
    _path = REPO_ROOT / _filename
    if not _path.is_file():
        continue

    def _make_handler(target: Path):
        def _handler():
            return FileResponse(target)

        return _handler

    _handler = _make_handler(_path)
    app.add_api_route(f"/{_filename}", _handler, include_in_schema=False)
    app.add_api_route(f"/map/tube/{_filename}", _handler, include_in_schema=False)

for _dirname in PUBLIC_STATIC_DIRS:
    _dir = REPO_ROOT / _dirname
    if not _dir.is_dir():
        continue
    app.mount(
        f"/map/tube/{_dirname}",
        StaticFiles(directory=str(_dir), html=True),
        name=f"tube-static-{_dirname}",
    )
    app.mount(
        f"/{_dirname}",
        StaticFiles(directory=str(_dir), html=True),
        name=f"static-{_dirname}",
    )
