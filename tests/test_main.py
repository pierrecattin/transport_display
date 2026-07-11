"""Tests for the hardware-free glue in src.__main__ (no rgbmatrix needed)."""

import threading
from pathlib import Path

from src.__main__ import StationState, _build_groups
from src.config import load_config

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
