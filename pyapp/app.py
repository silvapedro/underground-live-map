from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import subprocess
import sys
import time

import logging
import os
import re

from dotenv import load_dotenv

# Load .env from the repo root (silently ignored if absent).
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pyapp.services.accessible import STOPS, fetch_accessible_predictions
from pyapp.services.bus import empty_bus_payload, fetch_bus_payload
from pyapp.services.textual import group_rows_by_line, load_textual_rows
from pyapp.services.tube_live import get_cached_positions, refresh_tube_live

BASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = BASE_DIR.parent
DATA_DIR = REPO_ROOT / "data"
FETCH_SCRIPT = REPO_ROOT / "bin" / "fetch.py"

# How often (seconds) to refresh london.json.
DATA_REFRESH_INTERVAL = 60

# How often (seconds) to refresh the canvas live-feed cache.
TUBE_LIVE_REFRESH_INTERVAL = 30

# Directories at the repo root that are safe to expose as static assets.
PUBLIC_STATIC_DIRS = ("lib", "js", "i", "data", "schematic", "skyfall", "london-buses", "tfwm")
# Individual files at the repo root that are safe to expose.
PUBLIC_STATIC_FILES = ("css.css", "lu-screenshot.png", "README")


async def _fetch_data() -> None:
    """Run bin/fetch.py in a subprocess and log the result."""
    logger.info("Refreshing tube data from TfL API…")
    env = os.environ.copy()
    app_key = env.get("TFL_APP_KEY", "")
    cmd = [sys.executable, str(FETCH_SCRIPT)]
    if app_key:
        cmd += ["--app-key", app_key]
    else:
        logger.warning("TFL_APP_KEY not set — tube data fetch will likely return 403")
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(REPO_ROOT),
            env=env,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.warning("fetch.py exited %d: %s", proc.returncode, stderr.decode().strip())
        else:
            logger.info("Tube data refreshed successfully.")
    except Exception:
        logger.exception("Failed to run fetch.py")


async def _refresh_loop() -> None:
    """Background task: fetch on startup then every DATA_REFRESH_INTERVAL seconds."""
    await _fetch_data()
    while True:
        await asyncio.sleep(DATA_REFRESH_INTERVAL)
        await _fetch_data()


async def _tube_live_loop() -> None:
    """Background task: keep the canvas live-feed cache warm every 30 s."""
    app_key = os.environ.get("TFL_APP_KEY", "")
    await refresh_tube_live(app_key)
    while True:
        await asyncio.sleep(TUBE_LIVE_REFRESH_INTERVAL)
        app_key = os.environ.get("TFL_APP_KEY", "")
        await refresh_tube_live(app_key)


@asynccontextmanager
async def lifespan(application: FastAPI):
    task = asyncio.create_task(_refresh_loop())
    tube_task = asyncio.create_task(_tube_live_loop())
    try:
        yield
    finally:
        for t in (task, tube_task):
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass


app = FastAPI(title="underground-live-map Python runtime", lifespan=lifespan)
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
logger = logging.getLogger(__name__)
_LINE_RE = re.compile(r"^[A-Za-z0-9,]{1,10}$")


@app.get("/text")
@app.get("/text.php")
@app.get("/map/tube/text")
@app.get("/map/tube/text.php")
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
@app.get("/map/tube/data/bus")
@app.get("/map/tube/data/bus.php")
def bus_view(line: str = Query(default="")):
    route = line.strip()
    if not route:
        raise HTTPException(status_code=400, detail="line query parameter is required")
    if not _LINE_RE.fullmatch(route):
        raise HTTPException(status_code=400, detail="line query parameter is invalid")

    try:
        payload = fetch_bus_payload(route)
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
@app.get("/map/tube/accessible")
@app.get("/map/tube/accessible/index.php")
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


@app.get("/api/tube/trains", tags=["live-feed"])
def tube_trains_api():
    """
    Return cached train positions for the TubeLiveMap canvas component.

    Each train has: vehicleId, lineId, g (fractional station-index position),
    dir (+1 forward / -1 reverse). The cache is refreshed every 30 s by a
    background task; stale=true if the last refresh was more than 90 s ago.
    """
    data = get_cached_positions()
    age = time.time() - data["updated_at"] if data["updated_at"] else float("inf")
    response = JSONResponse(
        {
            "trains": data["trains"],
            "updatedAt": data["updated_at"],
            "stale": age > 90,
            "error": data["error"],
        }
    )
    response.headers["Cache-Control"] = "no-store"
    return response


# Serve the Vite production build when present.
_DIST_DIR = REPO_ROOT / "dist"
if _DIST_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=str(_DIST_DIR), html=True), name="vite-dist")


# Serve repository static files so current HTML/CSS/JS assets remain usable.
# Restricted to an explicit allowlist so private/dev files (.venv, .git, plans/,
# proposals/, research/, pyapp/, bin/, ...) are not exposed.
INDEX_FILE = REPO_ROOT / "index.html"

# The schematic view sets TrainTimes.url='/map/tube/schematic/', so trains.js
# fetches data from '/map/tube/schematic/data/<name>'. Redirect those requests
# to the canonical data location so both views share the same JSON source.
@app.get("/map/tube/schematic/data/{name:path}", include_in_schema=False)
def schematic_data_redirect(name: str):
    return RedirectResponse(url=f"/map/tube/data/{name}", status_code=301)


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
