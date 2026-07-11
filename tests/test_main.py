"""Tests for the hardware-free glue in src.__main__ (no rgbmatrix needed)."""

import threading
from pathlib import Path

import pytest

import src.__main__ as main_mod
from src.__main__ import Poller, StationState, WeatherState, _build_groups, _build_temps
from src.config import Weather, load_config
from src.weather import Temps

FIXTURE_CONFIG = Path(__file__).parent / "fixtures" / "config.json"


def test_build_groups_marks_stale_stations() -> None:
    cfg = load_config(FIXTURE_CONFIG)  # poll_interval 60 -> stale after 180s
    now = 1_000_000.0
    state = {s.id: StationState() for s in cfg.stations}
    state[cfg.stations[0].id].last_ok = now - 10_000  # polls failing for hours
    state[cfg.stations[1].id].last_ok = now - 30  # freshly polled
    groups = _build_groups(cfg, state, threading.Lock(), now)
    assert [g.stale for g in groups] == [True, False]


def test_build_groups_not_stale_before_first_poll() -> None:
    # last_ok is None until the first successful fetch; don't dim a board
    # that is merely still starting up.
    cfg = load_config(FIXTURE_CONFIG)
    state = {s.id: StationState() for s in cfg.stations}
    groups = _build_groups(cfg, state, threading.Lock(), now=1_000_000.0)
    assert not any(g.stale for g in groups)


def test_build_temps_none_before_first_fetch_then_live_then_stale() -> None:
    cfg = load_config(FIXTURE_CONFIG)  # poll_interval 60 -> stale after 180s
    now = 1_000_000.0
    lock = threading.Lock()

    weather = WeatherState()
    assert _build_temps(cfg, weather, lock, now) is None  # never fetched

    weather = WeatherState(temps=Temps(21.5, 34.7), last_ok=now - 30)
    fresh = _build_temps(cfg, weather, lock, now)
    assert fresh is not None
    assert (fresh.indoor, fresh.outdoor, fresh.stale) == (21.5, 34.7, False)

    weather = WeatherState(temps=Temps(21.5, 34.7), last_ok=now - 10_000)
    old = _build_temps(cfg, weather, lock, now)
    assert old is not None and old.stale is True


def test_poll_once_updates_weather_and_keeps_last_good(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = load_config(FIXTURE_CONFIG)
    cfg.weather = Weather(url="http://gw/get_livedata_info")
    state = {s.id: StationState() for s in cfg.stations}
    weather = WeatherState()
    poller = Poller(cfg, state, weather, threading.Lock())

    # Station fetches fail (None -> keep last data); weather succeeds.
    monkeypatch.setattr(main_mod, "fetch_station", lambda sid, limit: None)
    monkeypatch.setattr(
        main_mod, "fetch_weather", lambda url: Temps(indoor=21.5, outdoor=34.7)
    )
    poller._poll_once()
    assert weather.temps == Temps(21.5, 34.7)
    assert weather.last_ok is not None

    # A failed weather fetch keeps the previous reading and its timestamp.
    last_ok = weather.last_ok
    monkeypatch.setattr(main_mod, "fetch_weather", lambda url: None)
    poller._poll_once()
    assert weather.temps == Temps(21.5, 34.7)
    assert weather.last_ok == last_ok


def test_poll_once_skips_weather_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = load_config(FIXTURE_CONFIG)  # fixture predates the weather section
    assert cfg.weather.url == ""
    weather = WeatherState()
    poller = Poller(
        cfg, {s.id: StationState() for s in cfg.stations}, weather, threading.Lock()
    )
    monkeypatch.setattr(main_mod, "fetch_station", lambda sid, limit: None)

    def _boom(url: str) -> Temps:
        raise AssertionError("weather must not be fetched when no URL is set")

    monkeypatch.setattr(main_mod, "fetch_weather", _boom)
    poller._poll_once()
    assert weather.temps is None
