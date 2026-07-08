from __future__ import annotations

import datetime as real_dt
import json

import pytest

from pyapp import app as app_module
from pyapp.services import bus


def test_plural_minutes_formats_half_minutes_and_whole_minutes():
    assert bus._plural_minutes(1.3) == "in 1.5 minutes"
    assert bus._plural_minutes(1.0) == "in 1.0 minute"


def test_bus_view_rejects_invalid_line_before_fetch(monkeypatch):
    def fail_if_called(_line: str):
        raise AssertionError("fetch_bus_payload should not be called for invalid input")

    monkeypatch.setattr(app_module, "fetch_bus_payload", fail_if_called)

    with pytest.raises(app_module.HTTPException) as excinfo:
        app_module.bus_view(line="bad value")

    assert excinfo.value.status_code == 400


def test_fetch_bus_payload_parses_rows(monkeypatch):
    class FixedDatetime(real_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return real_dt.datetime(2024, 1, 1, tzinfo=tz)

    class FakeResponse:
        def __init__(self, text: str):
            self.text = text

        def raise_for_status(self):
            return None

    monkeypatch.setattr(bus.dt, "datetime", FixedDatetime)

    cols = ["ReturnType"] + bus.BUS_COLS_TEXT.split(",")
    col = {name: idx for idx, name in enumerate(cols)}

    def make_row(**values):
        row = [None] * len(cols)
        for key, value in values.items():
            row[col[key]] = value
        return row

    first_time = int(real_dt.datetime(2024, 1, 1, tzinfo=real_dt.timezone.utc).timestamp() * 1000)
    rows = [
        make_row(
            ReturnType=1,
            StopPointName="Start",
            StopID="S1",
            Towards="",
            StopPointIndicator="",
            StopPointState=0,
            Latitude=51.5,
            Longitude=-0.1,
            VisitNumber=1,
            LineID="73",
            LineName="73",
            DirectionID=0,
            DestinationName="End",
            VehicleID="veh1",
            TripID="trip1",
            RegistrationNumber="AB12CDE",
            EstimatedTime=first_time + 120000,
            ExpireTime=first_time + 180000,
        ),
        make_row(
            ReturnType=1,
            StopPointName="End",
            StopID="S2",
            Towards="",
            StopPointIndicator="",
            StopPointState=0,
            Latitude=51.6,
            Longitude=-0.2,
            VisitNumber=2,
            LineID="73",
            LineName="73",
            DirectionID=0,
            DestinationName="End",
            VehicleID="veh1",
            TripID="trip1",
            RegistrationNumber="AB12CDE",
            EstimatedTime=first_time + 240000,
            ExpireTime=first_time + 300000,
        ),
    ]
    payload_text = "\n".join(json.dumps(row) for row in rows)

    monkeypatch.setattr(bus.requests, "get", lambda *args, **kwargs: FakeResponse(payload_text))

    payload = bus.fetch_bus_payload("73")

    assert payload["stations"][0]["name"] == "Start"
    assert payload["trains"][0]["id"] == "AB12CDE"
    assert payload["trains"][0]["title"] == "73 to End (AB12CDE, id veh1)"
    assert payload["trains"][0]["next"][0]["dexp"] == "in 2.0 minutes"
    assert payload["trains"][0]["next"][1]["dexp"] == "in 4.0 minutes"