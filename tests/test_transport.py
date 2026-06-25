"""Unit tests for parsing/filtering/countdown. Run: python -m pytest tests/"""

import json
from pathlib import Path
from typing import Any

from src.config import Connection
from src.transport import (
    minutes_until,
    parse_departures,
    station_name,
    visible_departures,
)

FIXTURE = Path(__file__).parent / "fixtures" / "stationboard_8591285.json"
BASE = 1782198000  # reference "now"; fixture timestamps are offsets from this

# Connections configured for station 8591285 (see config.json).
CONNS = [
    Connection("32", "Zürich, Strassenverkehrsamt", "Strassenverkehrsamt"),
    Connection("61", "Zürich, Strassenverkehrsamt", "Strassenverkehrsamt"),
    Connection("62", "Wallisellen, Glatt (Bus)", "Wallisellen"),
]


def _board() -> list[dict[str, Any]]:
    board: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))[
        "stationboard"
    ]
    return board


def test_minutes_until_floors_and_clamps() -> None:
    assert minutes_until(BASE + 180, BASE) == 3
    assert minutes_until(BASE + 59, BASE) == 0  # within final minute -> 0
    assert minutes_until(BASE - 30, BASE) == 0  # never negative


def test_station_name() -> None:
    board = _board()
    assert station_name(board) == "Zürich, Neuaffoltern"


def test_parse_matches_number_and_direction_only() -> None:
    deps = parse_departures(_board(), CONNS)
    # Excludes 32->Holzerhurd (wrong direction) and the tram (number 11).
    matched = [(d.number, d.label, d.departure_ts) for d in deps]
    assert matched == [
        ("62", "Wallisellen", BASE + 60),
        ("32", "Strassenverkehrsamt", BASE + 180),
        ("61", "Strassenverkehrsamt", BASE + 600),
        ("62", "Wallisellen", BASE + 900),
    ]  # sorted ascending by departure


def test_visible_departures_applies_min_time() -> None:
    deps = parse_departures(_board(), CONNS)
    visible = visible_departures(deps, min_time=5, now=BASE)
    # 62@1min and 32@3min are dropped; 61@10min and 62@15min remain.
    assert [(d.number, m) for d, m in visible] == [("61", 10), ("62", 15)]


def test_visible_departures_dedupes_to_next_per_connection() -> None:
    deps = parse_departures(_board(), CONNS)
    visible = visible_departures(deps, min_time=0, now=BASE)
    # 62 appears twice (1min, 15min) -> only the soonest catchable one is kept.
    assert [(d.number, m) for d, m in visible] == [("62", 1), ("32", 3), ("61", 10)]


def test_visible_departures_min_time_drops_then_dedupes() -> None:
    deps = parse_departures(_board(), CONNS)
    visible = visible_departures(deps, min_time=5, now=BASE)
    # 62@1min dropped by min_time, so 62@15min becomes the next catchable 62.
    assert [(d.number, m) for d, m in visible] == [("61", 10), ("62", 15)]


def test_parse_skips_malformed_entries() -> None:
    board: list[Any] = _board()
    board += [{"number": "32"}, "garbage", {"number": "32", "to": "Zürich, Strassenverkehrsamt"}]
    deps = parse_departures(board, CONNS)
    # The extra entries lack a usable departureTimestamp -> ignored, count unchanged.
    assert len(deps) == 4
