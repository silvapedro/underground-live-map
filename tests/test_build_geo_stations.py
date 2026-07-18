import json

from build_geo_stations import build_geo_stations


def _write(tmp_path, stations):
    path = tmp_path / "stations.json"
    path.write_text(json.dumps(stations), encoding="utf-8")
    return path


def test_simple_station_gets_wildcard_key(tmp_path):
    path = _write(tmp_path, {"A Station": "-0.1,51.5"})
    data = build_geo_stations(path)
    assert data == {"A Station": {"*": [51.5, -0.1]}}


def test_single_letter_abbreviation_keys_are_dropped(tmp_path):
    # load_station_locations expands "B" into an additional "bakerloo" key; the
    # single-letter key itself must not survive into the frontend-facing output.
    path = _write(tmp_path, {"Edgware Road Station": {"B": [51.52, -0.17]}})
    data = build_geo_stations(path)
    assert "B" not in data["Edgware Road Station"]
    assert data["Edgware Road Station"]["bakerloo"] == [51.52, -0.17]


def test_hammersmith_city_abbreviation_also_yields_circle_key(tmp_path):
    path = _write(tmp_path, {"Baker Street Station": {"H": [51.52, -0.16]}})
    data = build_geo_stations(path)
    assert data["Baker Street Station"] == {
        "hammersmith-city": [51.52, -0.16],
        "circle": [51.52, -0.16],
    }


def test_real_stations_json_produces_only_json_serialisable_lists(tmp_path):
    """Coordinates from load_station_locations are tuples; the build script must
    convert them to lists so json.dumps doesn't need a custom encoder."""
    path = _write(tmp_path, {"A Station": "-0.1,51.5"})
    data = build_geo_stations(path)
    assert isinstance(data["A Station"]["*"], list)
    # Round-trips through json without error.
    json.dumps(data)
