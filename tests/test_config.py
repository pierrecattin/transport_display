"""Unit tests for config loading/validation. Run: python -m pytest tests/"""

import json
from pathlib import Path
from typing import Any

import pytest

from src.config import ConfigError, load_config

# A frozen copy of a realistic config. The repo-root config.json is the *live*
# config (rewritten at runtime by the web UI), so tests must not assert its
# exact contents -- only that it still loads (see test_live_repo_config_is_valid).
FIXTURE_CONFIG = Path(__file__).parent / "fixtures" / "config.json"


def _write(tmp_path: Path, data: dict[str, Any]) -> Path:
    p = tmp_path / "c.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def test_live_repo_config_is_valid() -> None:
    load_config("config.json")


def test_loads_fixture_config() -> None:
    cfg = load_config(FIXTURE_CONFIG)
    assert [s.id for s in cfg.stations] == ["8591041", "8591285"]
    # Per-station min_time preserved.
    assert {s.id: s.min_time for s in cfg.stations} == {"8591041": 2, "8591285": 5}
    # Labels resolved from destination_labels.
    s2 = next(s for s in cfg.stations if s.id == "8591285")
    labels = {c.number: c.label for c in s2.connections}
    assert labels == {"32": "Strassenverkehrsamt", "61": "Wallisellen", "62": "Schwamendingerplatz"}


def test_display_overrides_from_fixture() -> None:
    cfg = load_config(FIXTURE_CONFIG)
    assert cfg.display.poll_interval_sec == 60
    assert cfg.display.gpio_slowdown == 4  # fixture overrides the default (2)
    assert cfg.display.font == "6x10"


def test_display_defaults_when_absent(tmp_path: Path) -> None:
    p = _write(tmp_path, {
        "stations": [{"id": "1", "display_name": "S", "min_time": 0,
                      "connections": [{"number": "9", "destination": "X"}]}],
        "destination_labels": {},
    })
    cfg = load_config(p)
    assert cfg.display.poll_interval_sec == 60
    assert cfg.display.gpio_slowdown == 2
    assert cfg.display.font == "6x10"


def test_rejects_non_numeric_display_value(tmp_path: Path) -> None:
    for bad in ("high", None, True, [60]):
        p = _write(tmp_path, {
            "stations": [{"id": "1", "display_name": "S", "min_time": 0,
                          "connections": [{"number": "9", "destination": "X"}]}],
            "destination_labels": {},
            "display": {"brightness": bad},
        })
        with pytest.raises(ConfigError):
            load_config(p)


def test_rejects_out_of_range_display_value(tmp_path: Path) -> None:
    for key, bad in (("brightness", 0), ("brightness", 101), ("pwm_bits", 12)):
        p = _write(tmp_path, {
            "stations": [{"id": "1", "display_name": "S", "min_time": 0,
                          "connections": [{"number": "9", "destination": "X"}]}],
            "destination_labels": {},
            "display": {key: bad},
        })
        with pytest.raises(ConfigError):
            load_config(p)


def test_rejects_unknown_font(tmp_path: Path) -> None:
    p = _write(tmp_path, {
        "stations": [{"id": "1", "display_name": "S", "min_time": 0,
                      "connections": [{"number": "9", "destination": "X"}]}],
        "destination_labels": {},
        "display": {"font": "9x18"},
    })
    with pytest.raises(ConfigError):
        load_config(p)


def test_accepts_integer_scroll_speed(tmp_path: Path) -> None:
    p = _write(tmp_path, {
        "stations": [{"id": "1", "display_name": "S", "min_time": 0,
                      "connections": [{"number": "9", "destination": "X"}]}],
        "destination_labels": {},
        "display": {"scroll_px_per_sec": 15},
    })
    assert load_config(p).display.scroll_px_per_sec == 15.0


def test_colors_parsed_from_fixture() -> None:
    cfg = load_config(FIXTURE_CONFIG)
    assert cfg.colors.clock == (255, 255, 255)
    assert cfg.colors.header == (0, 19, 97)  # #001361


def test_color_defaults_when_absent(tmp_path: Path) -> None:
    p = _write(tmp_path, {
        "stations": [{"id": "1", "display_name": "S", "min_time": 0,
                      "connections": [{"number": "9", "destination": "X"}]}],
        "destination_labels": {},
    })
    cfg = load_config(p)
    # Defaults mirror the values layout.py used to hardcode.
    assert cfg.colors.clock == (255, 176, 0)  # #FFB000


def test_color_overrides_hex_and_rgb(tmp_path: Path) -> None:
    p = _write(tmp_path, {
        "stations": [{"id": "1", "display_name": "S", "min_time": 0,
                      "connections": [{"number": "9", "destination": "X"}]}],
        "destination_labels": {},
        "colors": {"clock": "#FF0000", "header": [0, 128, 255]},
    })
    cfg = load_config(p)
    assert cfg.colors.clock == (255, 0, 0)
    assert cfg.colors.header == (0, 128, 255)
    # Unspecified roles keep their defaults.
    assert cfg.colors.number == (255, 220, 0)


def test_rejects_bad_hex_color(tmp_path: Path) -> None:
    # "#+1+2+3" and " FF0000" would survive a naive int(x, 16) parse.
    for bad in ("#ZZZZZZ", "#+1+2+3", " FF0000", "#FF00", ""):
        p = _write(tmp_path, {
            "stations": [{"id": "1", "display_name": "S", "min_time": 0,
                          "connections": [{"number": "9", "destination": "X"}]}],
            "destination_labels": {},
            "colors": {"clock": bad},
        })
        with pytest.raises(ConfigError):
            load_config(p)


def test_missing_label_falls_back_to_stripped_city(tmp_path: Path) -> None:
    p = _write(tmp_path, {
        "stations": [{"id": "1", "display_name": "Somewhere", "min_time": 0,
                      "connections": [{"number": "9", "destination": "Zürich, Nowhere"}]}],
        "destination_labels": {},
    })
    cfg = load_config(p)
    assert cfg.stations[0].connections[0].label == "Nowhere"


def test_rejects_empty_stations(tmp_path: Path) -> None:
    p = _write(tmp_path, {"stations": [], "destination_labels": {}})
    with pytest.raises(ConfigError):
        load_config(p)


def test_rejects_negative_min_time(tmp_path: Path) -> None:
    p = _write(tmp_path, {
        "stations": [{"id": "1", "min_time": -1,
                      "connections": [{"number": "9", "destination": "X"}]}],
        "destination_labels": {},
    })
    with pytest.raises(ConfigError):
        load_config(p)
