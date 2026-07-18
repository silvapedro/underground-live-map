import io
import json
import os
import shutil
import time
import urllib.error
import urllib.request
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


@pytest.mark.parametrize(
    "line", ["dlr", "elizabeth", "liberty", "lioness", "mildmay",
             "suffragette", "weaver", "windrush"]
)
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


# --------------------------------------------------------------------------
# resolve_segment — the five currentLocation cases, expressed as station names
# + a progress fraction rather than coordinates (coordinate resolution now
# happens client-side, per rendering mode).
# --------------------------------------------------------------------------

def test_resolve_segment_at_platform_snaps_to_current_station():
    seg = fetch.resolve_segment("At Platform", "B Station", 0, "victoria")
    assert seg == fetch.Segment("B Station", "B Station", 1.0)


def test_resolve_segment_empty_location_snaps_for_no_location_lines():
    seg = fetch.resolve_segment("", "B Station", 45, "dlr")
    assert seg == fetch.Segment("B Station", "B Station", 1.0)


def test_resolve_segment_empty_location_unresolved_for_other_lines():
    # Only dlr/london-overground/tram/elizabeth report no location text at all.
    assert fetch.resolve_segment("", "B Station", 45, "victoria") is None


def test_resolve_segment_leaving_computes_fraction_toward_destination():
    # canon_station_name appends " Station" to the regex-extracted departure name.
    seg = fetch.resolve_segment("Leaving A", "B Station", 30, "victoria")
    assert seg.from_station == "A Station"
    assert seg.to_station == "B Station"
    assert seg.fraction == pytest.approx(30 / 60)


def test_resolve_segment_between_uses_180s_floor_when_time_below_150():
    seg = fetch.resolve_segment("Between A and B", "B Station", 90, "victoria")
    assert seg.from_station == "A Station"
    assert seg.to_station == "B Station"
    assert seg.fraction == pytest.approx((180 - 90) / 180)


def test_resolve_segment_between_uses_time_plus_30_when_time_above_150():
    seg = fetch.resolve_segment("Between A and B", "B Station", 200, "victoria")
    assert seg.fraction == pytest.approx((230 - 200) / 230)


def test_resolve_segment_between_skips_h_line_mismatch():
    """Regression: on the H&C line, a 'Between' report whose second station doesn't
    match the arrival station_name is discarded rather than plotted wrong."""
    assert fetch.resolve_segment("Between A and Other", "B Station", 90, "H") is None


def test_resolve_segment_approaching_snaps_to_the_approached_station():
    seg = fetch.resolve_segment("Approaching B", "B Station", 30, "victoria")
    assert seg == fetch.Segment("B Station", "B Station", 1.0)


def test_resolve_segment_unrecognised_text_returns_none():
    assert fetch.resolve_segment("Some new TfL wording", "B Station", 30, "victoria") is None


@pytest.mark.parametrize(
    "line", ["liberty", "lioness", "mildmay", "suffragette", "weaver", "windrush"]
)
def test_resolve_segment_empty_location_snaps_for_every_overground_line(line):
    """Regression: TfL reports no currentLocation text at all for these 6 lines (same
    as dlr/elizabeth), but they were missing from the empty-location check, so every
    Overground train was silently dropped from train-positions.json."""
    assert fetch.resolve_segment("", "B Station", 45, line) == fetch.Segment(
        "B Station", "B Station", 1.0
    )


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


def test_corrupt_cache_entry_is_discarded_and_refetched(tmp_path, monkeypatch):
    """Regression: a cache file truncated by a killed process, or holding an HTML error
    page, must be re-fetched. Raising JSONDecodeError here aborted the whole run -- and
    since the bad file stays on disk, it poisoned every subsequent run too."""
    cache = tmp_path / "cache"
    cache.mkdir()
    corrupt = cache / "victoria"
    corrupt.write_bytes(b"<html>502 Bad Gateway</html>")  # fresh mtime, so within TTL

    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **kw: io.BytesIO(b'[{"ok": true}]'))

    assert fetch.fetch_line("victoria", "http://x/%s", cache) == [{"ok": True}]
    # The corrupt entry is replaced, so the next run is healthy too.
    assert json.loads(corrupt.read_bytes()) == [{"ok": True}]


def test_malformed_response_body_skips_the_line_and_is_not_cached(tmp_path, monkeypatch):
    """Regression: a 200 carrying a maintenance page (not JSON) must skip just this line.
    It must also never reach the cache, or it would break every later run."""
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **kw: io.BytesIO(b"<html>maintenance</html>"))

    assert fetch.fetch_line("victoria", "http://x/%s", cache) is None
    assert not (cache / "victoria").exists()


def test_rate_limit_retries_are_capped(tmp_path, monkeypatch):
    """Regression: the retry loop was unbounded. app.py awaits this subprocess, so a
    persistent 429 froze the 60s refresh loop forever with no error and no new data."""
    cache = tmp_path / "cache"
    cache.mkdir()
    calls, slept = [], []

    def always_429(*a, **kw):
        calls.append(1)
        raise _http_error(429, b"Try again in 1 second")

    monkeypatch.setattr(urllib.request, "urlopen", always_429)
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))

    assert fetch.fetch_line("victoria", "http://x/%s", cache) is None
    assert len(calls) == fetch.MAX_FETCH_ATTEMPTS  # gives up rather than looping forever
    assert len(slept) == fetch.MAX_FETCH_ATTEMPTS


def test_rate_limit_delay_is_clamped(tmp_path, monkeypatch):
    """A hostile or buggy Retry-After must not stall the run for hours."""
    cache = tmp_path / "cache"
    cache.mkdir()
    slept = []
    responses = [_http_error(429, b"Try again in 86400 second"), io.BytesIO(b"[]")]

    def fake_urlopen(*a, **kw):
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))

    assert fetch.fetch_line("victoria", "http://x/%s", cache) == []
    assert slept == [fetch.MAX_RATE_LIMIT_DELAY]  # clamped from 86400


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

    assert (out_dir / "london-text.json").is_file()
    assert (out_dir / "train-positions.json").is_file()
    # The atomic-write temp file must not be left behind.
    assert not (out_dir / "train-positions.jsonN").exists()


def test_train_positions_json_has_the_shared_position_contract(frozen_cache, tmp_path, monkeypatch):
    """The frontend (either rendering mode) depends on this shape."""
    out_dir = tmp_path / "data"
    _run(frozen_cache, out_dir, monkeypatch)

    data = json.loads((out_dir / "train-positions.json").read_text(encoding="utf-8"))
    assert set(data) == {"updatedAt", "trains"}
    assert data["trains"], "expected at least one train from the fixture cache"

    train = data["trains"][0]
    assert set(train) == {
        "id", "lineId", "vehicleId", "destination",
        "fromStation", "toStation", "fraction", "etaSeconds", "atPlatform",
    }
    assert 0.0 <= train["fraction"] <= 1.0
    assert isinstance(train["atPlatform"], bool)


def test_train_positions_omits_siding_trains_like_the_map_does(frozen_cache, tmp_path, monkeypatch):
    out_dir = tmp_path / "data"
    _run(frozen_cache, out_dir, monkeypatch)

    positions = json.loads((out_dir / "train-positions.json").read_text(encoding="utf-8"))
    assert not any(t["id"].startswith("victoria-105") for t in positions["trains"])


def test_london_text_json_matches_golden(frozen_cache, tmp_path, monkeypatch):
    """The load-bearing regression test for the text pipeline: given identical inputs,
    fetch -> parse -> dedupe -> serialise must produce byte-identical output."""
    out_dir = tmp_path / "data"
    _run(frozen_cache, out_dir, monkeypatch)

    produced = json.loads((out_dir / "london-text.json").read_text(encoding="utf-8"))
    golden = json.loads((FIXTURES / "golden-london-text.json").read_text(encoding="utf-8"))
    assert produced == golden


def test_siding_train_still_appears_in_the_textual_listing(frozen_cache, tmp_path, monkeypatch):
    """Train 105 is in a Siding: excluded from train-positions.json (see
    test_train_positions_omits_siding_trains_like_the_map_does) but still listed as
    text, since /text describes every train regardless of plottability."""
    out_dir = tmp_path / "data"
    _run(frozen_cache, out_dir, monkeypatch)

    text = json.loads((out_dir / "london-text.json").read_text(encoding="utf-8"))
    assert any(r["id"].startswith("105") for r in text)
