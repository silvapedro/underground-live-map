import io
import json
import os
import shutil
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from pathlib import Path

import pytest

import fetch

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# --------------------------------------------------------------------------
# parse_time
# --------------------------------------------------------------------------

@pytest.mark.parametrize("value", ["-", "due"])
def test_parse_time_due_and_dash_return_zero(value):
    assert fetch.parse_time(value) == 0


def test_parse_time_accepts_int_passthrough():
    assert fetch.parse_time(150) == 150


def test_parse_time_parses_mm_ss():
    assert fetch.parse_time("02:30") == 150


def test_parse_time_parses_hh_mm_ss():
    assert fetch.parse_time("01:02:30") == 3750


def test_parse_time_raises_on_garbage():
    with pytest.raises(ValueError):
        fetch.parse_time("banana")


# --------------------------------------------------------------------------
# canon_station_name
# --------------------------------------------------------------------------

def test_canon_station_name_appends_station_suffix():
    assert fetch.canon_station_name("Acton Town", "central") == "Acton Town Station"


def test_canon_station_name_appends_tram_stop_for_tram():
    assert fetch.canon_station_name("Addiscombe", "tram") == "Addiscombe Tram Stop"


@pytest.mark.parametrize("line", ["dlr", "elizabeth", "london-overground"])
def test_canon_station_name_no_suffix_for_dlr_overground_elizabeth(line):
    assert fetch.canon_station_name("Abbey Road", line) == "Abbey Road"


def test_canon_station_name_strips_platform_suffix():
    assert fetch.canon_station_name("Baker Street Platform 3", "jubilee") == "Baker Street Station"


def test_canon_station_name_encodes_ampersand():
    assert fetch.canon_station_name("Elephant & Castle", "bakerloo") == "Elephant &amp; Castle Station"


def test_canon_station_name_disambiguates_edgware_road():
    # 'B' is the Bakerloo abbreviation; every other line means the Circle-side station.
    assert fetch.canon_station_name("Edgware Road", "B") == "Edgware Road Bakerloo Station"
    assert fetch.canon_station_name("Edgware Road", "district") == "Edgware Road Circle Station"


def test_canon_station_name_normalises_curly_apostrophe():
    # The TfL feed uses U+2019; stations.json keys use an ASCII apostrophe.
    assert fetch.canon_station_name("Queen’s Park", "bakerloo") == "Queen's Park Station"


# --------------------------------------------------------------------------
# load_station_locations / lookup
# --------------------------------------------------------------------------

def test_load_station_locations_reads_utf8_not_cp1252():
    """Regression: stations.json is UTF-8. Reading it with the Windows locale default
    (cp1252) mangles 'Earl’s Court Station' into mojibake."""
    stations = fetch.load_station_locations(FIXTURES.parent.parent / "bin" / "stations.json")
    assert "Earl’s Court Station" in stations


def test_load_station_locations_expands_line_abbreviations():
    stations = fetch.load_station_locations(FIXTURES.parent.parent / "bin" / "stations.json")
    # Every 'lng,lat' string entry becomes a wildcard coordinate.
    assert stations["Acton Town Station"]["*"] == (51.503057, -0.280462)


def test_lookup_returns_zero_zero_for_unknown_station():
    assert fetch.lookup({}, "victoria", "Nowhere Station") == (0, 0)


def test_lookup_prefers_line_specific_over_wildcard():
    stations = {"X": {"*": (1.0, 1.0), "victoria": (2.0, 2.0)}}
    assert fetch.lookup(stations, "victoria", "X") == (2.0, 2.0)
    assert fetch.lookup(stations, "central", "X") == (1.0, 1.0)


# --------------------------------------------------------------------------
# assign_locations — the five interpolation branches
# --------------------------------------------------------------------------

STATIONS = {
    "A Station": {"*": (0.0, 0.0)},
    "B Station": {"*": (10.0, 10.0)},
}


def _out(current_location, time_to_station, station_name="B Station"):
    out = OrderedDict()
    out["victoria"] = OrderedDict()
    out["victoria"]["t1"] = {
        "station_name": station_name,
        "current_location": current_location,
        "time_to_station": time_to_station,
        "destination": "B",
        "platform_name": "P1",
    }
    return out


def test_interpolate_at_platform_uses_station_coords():
    out = _out("At Platform", 0)
    fetch.assign_locations(out, STATIONS)
    assert out["victoria"]["t1"]["location"] == (10.0, 10.0)


def test_interpolate_approaching_snaps_to_station():
    out = _out("Approaching B", 30)
    fetch.assign_locations(out, STATIONS)
    assert out["victoria"]["t1"]["location"] == (10.0, 10.0)


def test_interpolate_leaving_is_midpoint_at_zero_seconds():
    # fraction = 30 / (0 + 30) = 1.0 -> all the way at the destination.
    out = _out("Leaving A", 0)
    fetch.assign_locations(out, STATIONS)
    assert out["victoria"]["t1"]["location"] == (10.0, 10.0)


def test_interpolate_leaving_moves_toward_destination_as_time_shrinks():
    near = _out("Leaving A", 30)
    far = _out("Leaving A", 570)
    fetch.assign_locations(near, STATIONS)
    fetch.assign_locations(far, STATIONS)
    # fraction = 30/60 = 0.5 vs 30/600 = 0.05
    assert near["victoria"]["t1"]["location"] == (5.0, 5.0)
    assert far["victoria"]["t1"]["location"] == pytest.approx((0.5, 0.5))


def test_interpolate_between_uses_180s_floor_when_time_below_150():
    # span = 180 (not time+30), fraction = (180-90)/180 = 0.5
    out = _out("Between A and B", 90)
    fetch.assign_locations(out, STATIONS)
    assert out["victoria"]["t1"]["location"] == pytest.approx((5.0, 5.0))


def test_interpolate_between_uses_time_plus_30_when_time_above_150():
    # span = 200+30 = 230, fraction = (230-200)/230
    out = _out("Between A and B", 200)
    fetch.assign_locations(out, STATIONS)
    expected = 10.0 * (30 / 230)
    assert out["victoria"]["t1"]["location"] == pytest.approx((expected, expected))


@pytest.mark.parametrize("location", [
    "At Ruislip Siding", "In Depot", "On Network Rail Track",
    "North Acton Junction", "Lord's Disused", "At Road 21",
])
def test_unplottable_locations_get_no_position(location):
    out = _out(location, 60)
    fetch.assign_locations(out, STATIONS)
    assert "location" not in out["victoria"]["t1"]


# --------------------------------------------------------------------------
# fetch_line — caching and error handling
# --------------------------------------------------------------------------

def _http_error(code, body=b""):
    return urllib.error.HTTPError("http://x", code, "err", {}, io.BytesIO(body))


def test_cache_is_used_when_fresh(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "victoria").write_bytes(json.dumps([{"hello": "world"}]).encode())

    def boom(*a, **kw):
        raise AssertionError("network must not be touched when the cache is fresh")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert fetch.fetch_line("victoria", "http://x/%s", cache) == [{"hello": "world"}]


def test_cache_refetches_when_stale(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    stale = cache / "victoria"
    stale.write_bytes(b'[{"old": true}]')
    old = time.time() - (fetch.CACHE_TTL + 60)
    os.utime(stale, (old, old))

    calls = []

    def fake_urlopen(url, timeout=None):
        calls.append(url)
        return io.BytesIO(b'[{"fresh": true}]')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert fetch.fetch_line("victoria", "http://x/%s", cache) == [{"fresh": True}]
    assert len(calls) == 1
    # The refreshed response is written back to the cache.
    assert json.loads(stale.read_bytes()) == [{"fresh": True}]


def test_http_error_is_caught_before_url_error(tmp_path, monkeypatch):
    """Regression: HTTPError subclasses URLError. When URLError was caught first the
    429 retry below was unreachable and the line was silently skipped instead."""
    cache = tmp_path / "cache"
    cache.mkdir()

    responses = [
        _http_error(429, b"Try again in 3 seconds"),
        io.BytesIO(b'[{"ok": true}]'),
    ]
    slept = []

    def fake_urlopen(url, timeout=None):
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))

    assert fetch.fetch_line("victoria", "http://x/%s", cache) == [{"ok": True}]
    assert slept == [3]  # backoff parsed from the 429 body, not the 10s fallback
    assert responses == []


def test_non_429_http_error_skips_the_line(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **kw: (_ for _ in ()).throw(_http_error(500)))
    assert fetch.fetch_line("victoria", "http://x/%s", cache) is None


def test_network_error_skips_the_line(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **kw: (_ for _ in ()).throw(urllib.error.URLError("down")))
    assert fetch.fetch_line("victoria", "http://x/%s", cache) is None


# --------------------------------------------------------------------------
# End-to-end: golden output from the frozen cache fixtures
# --------------------------------------------------------------------------

@pytest.fixture
def frozen_cache(tmp_path):
    """Copy the committed cache fixtures somewhere writable with fresh mtimes, so
    fetch_line reads them instead of going to the network."""
    cache = tmp_path / "cache"
    shutil.copytree(FIXTURES / "cache", cache)
    now = time.time()
    for f in cache.iterdir():
        os.utime(f, (now, now))
    return cache


def _run(cache, out_dir, monkeypatch):
    def boom(*a, **kw):
        raise AssertionError("fetch.py must not hit the network when the cache is fresh")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    rc = fetch.main(["--cache-dir", str(cache), "--output", str(out_dir)])
    assert rc == 0


def test_fetch_writes_both_output_files(frozen_cache, tmp_path, monkeypatch):
    out_dir = tmp_path / "data"
    _run(frozen_cache, out_dir, monkeypatch)

    assert (out_dir / "london.json").is_file()
    assert (out_dir / "london-text.json").is_file()
    # The atomic-write temp file must not be left behind.
    assert not (out_dir / "london.jsonN").exists()


def test_london_json_matches_golden(frozen_cache, tmp_path, monkeypatch):
    """The load-bearing regression test: given identical inputs, the whole
    fetch -> parse -> dedupe -> interpolate -> serialise pipeline must produce
    byte-identical output (modulo the lastupdate timestamp)."""
    out_dir = tmp_path / "data"
    _run(frozen_cache, out_dir, monkeypatch)

    produced = json.loads((out_dir / "london.json").read_text(encoding="utf-8"))
    golden = json.loads((FIXTURES / "golden-london.json").read_text(encoding="utf-8"))

    produced["lastupdate"] = golden["lastupdate"] = "<normalised>"
    assert produced == golden


def test_london_text_json_matches_golden(frozen_cache, tmp_path, monkeypatch):
    out_dir = tmp_path / "data"
    _run(frozen_cache, out_dir, monkeypatch)

    produced = json.loads((out_dir / "london-text.json").read_text(encoding="utf-8"))
    golden = json.loads((FIXTURES / "golden-london-text.json").read_text(encoding="utf-8"))
    assert produced == golden


def test_london_json_has_frontend_contract(frozen_cache, tmp_path, monkeypatch):
    """js/trains.js depends on this shape; changing it silently breaks every map."""
    out_dir = tmp_path / "data"
    _run(frozen_cache, out_dir, monkeypatch)

    data = json.loads((out_dir / "london.json").read_text(encoding="utf-8"))
    assert set(data) == {"station", "lastupdate", "trains", "stations", "polylines"}

    train = data["trains"][0]
    assert set(train) == {"point", "next", "left", "id", "title"}
    assert len(train["point"]) == 2

    stop = train["next"][0]
    assert set(stop) == {"point", "name", "mins", "dexp"}

    station = data["stations"][0]
    assert set(station) == {"point", "name"}


def test_siding_trains_are_excluded_from_the_map(frozen_cache, tmp_path, monkeypatch):
    """Train 105 is in a Siding: it must not be plotted, but must still appear in the
    textual listing."""
    out_dir = tmp_path / "data"
    _run(frozen_cache, out_dir, monkeypatch)

    data = json.loads((out_dir / "london.json").read_text(encoding="utf-8"))
    text = json.loads((out_dir / "london-text.json").read_text(encoding="utf-8"))

    assert not any(t["id"].startswith("victoria-105") for t in data["trains"])
    assert any(r["id"].startswith("105") for r in text)
