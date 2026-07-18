import io
import json
import urllib.request

from build_station_sequences import _canon_name, _dedupe_routes, fetch_line_sequence


def test_canon_name_strips_underground_station_suffix():
    assert _canon_name("Green Park Underground Station", "victoria") == "Green Park Station"


def test_canon_name_strips_tram_stop_suffix_for_tram():
    assert _canon_name("Addiscombe Tram Stop", "tram") == "Addiscombe Tram Stop"


def test_canon_name_no_suffix_for_overground():
    assert _canon_name("Emerson Park Rail Station", "liberty") == "Emerson Park Rail Station"


def test_dedupe_routes_collapses_exact_reverse():
    routes = [
        {"name": "A <-> B", "naptanIds": ["1", "2", "3"]},
        {"name": "B <-> A", "naptanIds": ["3", "2", "1"]},
    ]
    assert len(_dedupe_routes(routes)) == 1


def test_dedupe_routes_keeps_distinct_via_variants():
    routes = [
        {"name": "A <-> B via X", "naptanIds": ["1", "2", "3"]},
        {"name": "A <-> B via Y", "naptanIds": ["1", "4", "3"]},
    ]
    assert len(_dedupe_routes(routes)) == 2


def test_dedupe_routes_drops_empty_naptan_lists():
    routes = [{"name": "empty", "naptanIds": []}]
    assert _dedupe_routes(routes) == []


def test_fetch_line_sequence_builds_canonicalised_branches(monkeypatch):
    payload = {
        "stations": [
            {"id": "1", "name": "Green Park Underground Station"},
            {"id": "2", "name": "Oxford Circus Underground Station"},
        ],
        "orderedLineRoutes": [
            {"name": "A <-> B", "naptanIds": ["1", "2"]},
            {"name": "B <-> A", "naptanIds": ["2", "1"]},
        ],
    }
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda url, timeout=None: io.BytesIO(json.dumps(payload).encode()),
    )
    branches = fetch_line_sequence("victoria", "http://x/%s")
    assert branches == [["Green Park Station", "Oxford Circus Station"]]


def test_fetch_line_sequence_skips_naptan_ids_missing_from_stations(monkeypatch):
    payload = {
        "stations": [{"id": "1", "name": "Green Park Underground Station"}],
        "orderedLineRoutes": [{"name": "A <-> B", "naptanIds": ["1", "unknown"]}],
    }
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda url, timeout=None: io.BytesIO(json.dumps(payload).encode()),
    )
    branches = fetch_line_sequence("victoria", "http://x/%s")
    # Only 1 resolvable stop -- too short to be a usable branch.
    assert branches == []
