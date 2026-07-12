from __future__ import annotations

from pyapp.services import accessible


def test_stop_code_regex_accepts_valid_codes_and_rejects_invalid_codes():
    assert accessible._STOP_CODE_RE.fullmatch("WMP")
    assert accessible._STOP_CODE_RE.fullmatch("PADc")
    assert not accessible._STOP_CODE_RE.fullmatch("../../etc/passwd")
    assert not accessible._STOP_CODE_RE.fullmatch("W-M-P")


def test_fetch_accessible_predictions_parses_xml(monkeypatch):
    class FakeResponse:
        text = (
            "<R>"
            "<S N='Wimbledon'>"
            "<P N='Platform 1'>"
            "<T LCID='2001' TimeTo='0:30' Destination='East Putney' Location='At platform'/>"
            "<T LCID='1002' TimeTo='-' Destination=\"Earl's Court\" Location='Approaching'/>"
            "</P>"
            "</S>"
            "</R>"
        )

        def raise_for_status(self):
            return None

    monkeypatch.setattr(accessible.requests, "get", lambda *args, **kwargs: FakeResponse())

    payload = accessible.fetch_accessible_predictions("WMP")

    assert payload["station_name"] == "Wimbledon"
    assert payload["platforms"][0]["name"] == "Platform 1"
    assert payload["platforms"][0]["rows"][0]["due"] == "1/2 min"
    assert payload["platforms"][0]["rows"][0]["is_non"] is False
    assert payload["platforms"][0]["rows"][1]["due"] == "Now"
    assert payload["platforms"][0]["rows"][1]["is_non"] is True