import json
import os
import time

from pyapp.services.tube_positions import _cache, get_live_trains


def _write(path, trains, updated_at=1000.0):
    path.write_text(json.dumps({"updatedAt": updated_at, "trains": trains}), encoding="utf-8")


def setup_function(_fn):
    # get_live_trains caches by mtime across calls/tests; reset it so tests don't
    # see a stale in-memory result from a previous test's tmp_path.
    _cache["mtime"] = None
    _cache["data"] = {"trains": [], "updated_at": 0.0, "error": None}


def test_missing_file_returns_empty_with_error(tmp_path):
    data = get_live_trains(tmp_path)
    assert data["trains"] == []
    assert data["error"] is not None


def test_reads_trains_and_updated_at(tmp_path):
    _write(tmp_path / "train-positions.json", [{"id": "central-1"}], updated_at=1234.5)
    data = get_live_trains(tmp_path)
    assert data["trains"] == [{"id": "central-1"}]
    assert data["updated_at"] == 1234.5
    assert data["error"] is None


def test_unchanged_mtime_is_served_from_cache(tmp_path, monkeypatch):
    path = tmp_path / "train-positions.json"
    _write(path, [{"id": "central-1"}])
    first = get_live_trains(tmp_path)

    # If the file were re-read, this would blow up -- proves the mtime cache is used.
    def boom(*a, **kw):
        raise AssertionError("must not re-read the file when mtime is unchanged")

    monkeypatch.setattr("pathlib.Path.read_text", boom)
    second = get_live_trains(tmp_path)
    assert second == first


def test_touched_file_is_re_read(tmp_path):
    path = tmp_path / "train-positions.json"
    _write(path, [{"id": "central-1"}], updated_at=1000.0)
    get_live_trains(tmp_path)

    # Advance the mtime so the cache is invalidated, and change the content.
    _write(path, [{"id": "central-2"}], updated_at=2000.0)
    os.utime(path, (time.time() + 5, time.time() + 5))

    data = get_live_trains(tmp_path)
    assert data["trains"] == [{"id": "central-2"}]
    assert data["updated_at"] == 2000.0


def test_malformed_json_returns_empty_with_error(tmp_path):
    (tmp_path / "train-positions.json").write_text("not json", encoding="utf-8")
    data = get_live_trains(tmp_path)
    assert data["trains"] == []
    assert data["error"] is not None
