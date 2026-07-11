"""Unit tests for the GW3000 live-data client. Run: python -m pytest tests/"""

from typing import Any

import pytest
import requests

from src import weather
from src.weather import Temps, fetch_weather, parse_livedata

# Trimmed capture of a real GW3000 /get_livedata_info response: outdoor temp is
# the common_list entry id 0x02, indoor lives in wh25[0].intemp; everything
# else (dew point 0x03, wind, rain, ...) must be ignored.
LIVEDATA: dict[str, Any] = {
    "common_list": [
        {"id": "0x02", "val": "34.7", "unit": "C"},
        {"id": "0x07", "val": "26%"},
        {"id": "3", "val": "34.7", "unit": "C"},
        {"id": "0x03", "val": "12.4", "unit": "C"},
        {"id": "0x0B", "val": "0.0 m/s"},
    ],
    "piezoRain": [{"id": "0x0D", "val": "0.0 mm"}],
    "wh25": [
        {"intemp": "26.1", "unit": "C", "inhumi": "51%", "abs": "960.5 hPa"}
    ],
    "debug": [{"heap": "82516"}],
}


def test_parse_livedata_extracts_both_temps() -> None:
    assert parse_livedata(LIVEDATA) == Temps(indoor=26.1, outdoor=34.7)


def test_parse_livedata_missing_sensors() -> None:
    # No wh25 block (indoor sensor unpaired) -> indoor None, outdoor kept.
    no_indoor = {"common_list": LIVEDATA["common_list"]}
    assert parse_livedata(no_indoor) == Temps(indoor=None, outdoor=34.7)
    # No 0x02 entry (outdoor sensor dead) -> outdoor None, indoor kept.
    no_outdoor = {"common_list": [{"id": "0x03", "val": "12.4"}], "wh25": LIVEDATA["wh25"]}
    assert parse_livedata(no_outdoor) == Temps(indoor=26.1, outdoor=None)


def test_parse_livedata_tolerates_garbage() -> None:
    assert parse_livedata("nope") == Temps(indoor=None, outdoor=None)
    assert parse_livedata({}) == Temps(indoor=None, outdoor=None)
    bad_values = {
        "common_list": [{"id": "0x02", "val": "--"}],
        "wh25": [{"intemp": None}],
    }
    assert parse_livedata(bad_values) == Temps(indoor=None, outdoor=None)


class _Response:
    def __init__(self, payload: Any):
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def test_fetch_weather_parses_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        weather._session, "get", lambda url, timeout: _Response(LIVEDATA)
    )
    assert fetch_weather("http://gw/get_livedata_info") == Temps(26.1, 34.7)


def test_fetch_weather_returns_none_on_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(url: str, timeout: int) -> Any:
        raise requests.ConnectionError("gateway offline")

    monkeypatch.setattr(weather._session, "get", _raise)
    assert fetch_weather("http://gw/get_livedata_info") is None

    # HTML/garbage body -> resp.json() raises ValueError -> None.
    monkeypatch.setattr(
        weather._session, "get", lambda url, timeout: _Response(ValueError("not json"))
    )
    assert fetch_weather("http://gw/get_livedata_info") is None
