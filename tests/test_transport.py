"""Unit tests for parsing/filtering/countdown. Run: python -m pytest tests/"""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from src.config import Connection
from src.transport import (
    _effective_departure_ts,
    minutes_until,
    parse_departures,
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


def test_parse_matches_number_and_direction_only() -> None:
    deps = parse_departures(_board(), CONNS)
    # Excludes 32->Holzerhurd (wrong direction) and the tram (number 11).
    matched = [(d.number, d.label, d.departure_ts) for d in deps]
    assert matched == [
        ("62", "Wallisellen", BASE + 120),  # prognosis.departure beats planned +60s
        ("32", "Strassenverkehrsamt", BASE + 240),  # planned +180s with delay: 1
        ("61", "Strassenverkehrsamt", BASE + 600),
        ("62", "Wallisellen", BASE + 900),
    ]  # sorted ascending by best-known departure


def test_visible_departures_applies_min_time() -> None:
    deps = parse_departures(_board(), CONNS)
    visible = visible_departures(deps, min_time=5, now=BASE)
    # 62@2min and 32@4min are dropped; 61@10min and 62@15min remain.
    assert [(d.number, m) for d, m in visible] == [("61", 10), ("62", 15)]


def test_visible_departures_dedupes_to_next_per_connection() -> None:
    deps = parse_departures(_board(), CONNS)
    visible = visible_departures(deps, min_time=0, now=BASE)
    # 62 appears twice (2min, 15min) -> only the soonest catchable one is kept.
    assert [(d.number, m) for d, m in visible] == [("62", 2), ("32", 4), ("61", 10)]


def test_visible_departures_min_time_drops_then_dedupes() -> None:
    deps = parse_departures(_board(), CONNS)
    visible = visible_departures(deps, min_time=5, now=BASE)
    # 62@2min dropped by min_time, so 62@15min becomes the next catchable 62.
    assert [(d.number, m) for d, m in visible] == [("61", 10), ("62", 15)]


def test_effective_ts_prefers_prognosis_then_delay() -> None:
    # Prognosis (realtime ISO estimate) wins over both delay and planned.
    iso = datetime.fromtimestamp(BASE + 300, timezone(timedelta(hours=2))).isoformat()
    stop: dict[str, Any] = {
        "departureTimestamp": BASE,
        "delay": 1,
        "prognosis": {"departure": iso},
    }
    assert _effective_departure_ts(stop) == BASE + 300
    # No prognosis -> planned + delay (delays can be negative: early bus).
    assert _effective_departure_ts({"departureTimestamp": BASE, "delay": 2}) == BASE + 120
    assert _effective_departure_ts({"departureTimestamp": BASE, "delay": -1}) == BASE - 60
    # Unparseable prognosis falls back to delay/planned; no planned -> None.
    bad = {"departureTimestamp": BASE, "prognosis": {"departure": "garbage"}}
    assert _effective_departure_ts(bad) == BASE
    assert _effective_departure_ts({"delay": 2}) is None


def test_parse_skips_malformed_entries() -> None:
    board: list[Any] = _board()
    board += [{"number": "32"}, "garbage", {"number": "32", "to": "Zürich, Strassenverkehrsamt"}]
    deps = parse_departures(board, CONNS)
    # The extra entries lack a usable departureTimestamp -> ignored, count unchanged.
    assert len(deps) == 4
