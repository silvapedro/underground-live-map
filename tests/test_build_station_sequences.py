import io
import json
import urllib.request

from build_station_sequences import _canon_name, _dedupe_branches, fetch_line_sequence


def test_canon_name_strips_underground_station_suffix():
    assert _canon_name("Green Park Underground Station", "victoria") == "Green Park Station"


def test_canon_name_strips_tram_stop_suffix_for_tram():
    assert _canon_name("Addiscombe Tram Stop", "tram") == "Addiscombe Tram Stop"


def test_canon_name_no_suffix_for_overground():
    assert _canon_name("Emerson Park Rail Station", "liberty") == "Emerson Park Rail Station"


def test_dedupe_branches_collapses_exact_reverse():
    branches = [["A", "B", "C"], ["C", "B", "A"]]
    assert len(_dedupe_branches(branches)) == 1


def test_dedupe_branches_keeps_distinct_via_variants():
    branches = [["A", "B", "C"], ["A", "D", "C"]]
    assert len(_dedupe_branches(branches)) == 2


def test_dedupe_branches_drops_empty():
    assert _dedupe_branches([[]]) == []


def _payload(*sequences):
    return {
        "stopPointSequences": [
            {"stopPoint": [{"id": str(i), "name": n} for i, n in enumerate(seq)]}
            for seq in sequences
        ]
    }


def test_fetch_line_sequence_builds_branches_from_stop_point_sequences(monkeypatch):
    payload = _payload(["Green Park Underground Station", "Oxford Circus Underground Station"])
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda url, timeout=None: io.BytesIO(json.dumps(payload).encode()),
    )
    branches = fetch_line_sequence("victoria", "http://x/%s")
    assert branches == [["Green Park Station", "Oxford Circus Station"]]


def test_fetch_line_sequence_collapses_consecutive_duplicate_stops(monkeypatch):
    payload = _payload(["A Underground Station", "A Underground Station", "B Underground Station"])
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda url, timeout=None: io.BytesIO(json.dumps(payload).encode()),
    )
    branches = fetch_line_sequence("victoria", "http://x/%s")
    assert branches == [["A Station", "B Station"]]


def test_fetch_line_sequence_skips_too_short_branches(monkeypatch):
    payload = _payload(["Green Park Underground Station"])  # only 1 stop
    monkeypatch.setattr(
        urllib.request, "urlopen",
        lambda url, timeout=None: io.BytesIO(json.dumps(payload).encode()),
    )
    assert fetch_line_sequence("victoria", "http://x/%s") == []
