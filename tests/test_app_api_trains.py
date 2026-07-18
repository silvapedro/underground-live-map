"""
Tests for pyapp.app's /api/trains handler.

Calls the route function directly rather than going through FastAPI's TestClient,
which needs httpx -- not otherwise a dependency of this project, and unnecessary
for asserting this handler's envelope/staleness logic.
"""
from __future__ import annotations

import json
import time

import pyapp.app as app_module


def _patch_live_trains(monkeypatch, trains, updated_at, error=None):
    monkeypatch.setattr(
        app_module,
        "get_live_trains",
        lambda data_dir: {"trains": trains, "updated_at": updated_at, "error": error},
    )


def _body(response):
    return json.loads(response.body)


def test_trains_api_returns_the_cached_trains(monkeypatch):
    _patch_live_trains(monkeypatch, [{"id": "central-1"}], time.time())
    body = _body(app_module.trains_api())
    assert body["trains"] == [{"id": "central-1"}]
    assert body["error"] is None


def test_trains_api_is_not_stale_when_recently_updated(monkeypatch):
    _patch_live_trains(monkeypatch, [], time.time())
    assert _body(app_module.trains_api())["stale"] is False


def test_trains_api_is_stale_after_90_seconds(monkeypatch):
    _patch_live_trains(monkeypatch, [], time.time() - 91)
    assert _body(app_module.trains_api())["stale"] is True


def test_trains_api_is_stale_when_never_updated(monkeypatch):
    _patch_live_trains(monkeypatch, [], 0.0)
    assert _body(app_module.trains_api())["stale"] is True


def test_trains_api_surfaces_the_error_field(monkeypatch):
    _patch_live_trains(monkeypatch, [], 0.0, error="train-positions.json missing")
    assert _body(app_module.trains_api())["error"] == "train-positions.json missing"


def test_trains_api_sets_no_store_cache_header(monkeypatch):
    _patch_live_trains(monkeypatch, [], time.time())
    response = app_module.trains_api()
    assert response.headers["cache-control"] == "no-store"
