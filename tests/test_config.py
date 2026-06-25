"""Unit tests for config loading/validation. Run: python -m pytest tests/"""

import json
from pathlib import Path

import pytest

from src.config import ConfigError, load_config

REPO_CONFIG = "config.json"


def test_loads_repo_config() -> None:
    cfg = load_config(REPO_CONFIG)
    assert [s.id for s in cfg.stations] == ["8591041", "8591285"]
    # Per-station min_time preserved.
    assert {s.id: s.min_time for s in cfg.stations} == {"8591041": 2, "8591285": 5}
    # Labels resolved from destination_labels.
    s2 = next(s for s in cfg.stations if s.id == "8591285")
    labels = {c.number: c.label for c in s2.connections}
    assert labels == {"32": "Strassenverkehrsamt", "61": "Wallisellen", "62": "Schwamendingerplatz"}


def test_display_defaults_and_overrides() -> None:
    cfg = load_config(REPO_CONFIG)
    assert cfg.display.poll_interval_sec == 60
    assert cfg.display.gpio_slowdown == 2
    assert cfg.display.font == "6x10"


def test_missing_label_falls_back_to_stripped_city(tmp_path: Path) -> None:
    p = tmp_path / "c.json"
    p.write_text(json.dumps({
        "stations": [{"id": "1", "display_name": "Somewhere", "min_time": 0,
                      "connections": [{"number": "9", "destination": "Zürich, Nowhere"}]}],
        "destination_labels": {},
    }), encoding="utf-8")
    cfg = load_config(p)
    assert cfg.stations[0].connections[0].label == "Nowhere"


def test_rejects_empty_stations(tmp_path: Path) -> None:
    p = tmp_path / "c.json"
    p.write_text(json.dumps({"stations": [], "destination_labels": {}}), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)


def test_rejects_negative_min_time(tmp_path: Path) -> None:
    p = tmp_path / "c.json"
    p.write_text(json.dumps({
        "stations": [{"id": "1", "min_time": -1,
                      "connections": [{"number": "9", "destination": "X"}]}],
        "destination_labels": {},
    }), encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)
