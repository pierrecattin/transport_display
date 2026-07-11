"""transport.opendata.ch client, parsing and per-station filtering.

We fetch a station board, keep only the (line number, direction) pairs the
config asks for, and store the best-known departure timestamp for each — the
realtime estimate (``prognosis.departure`` / ``delay``) when the API provides
one, the planned time otherwise. The minutes-until-departure countdown and the
``min_time`` cut-off are recomputed at render time from those timestamps (see
:func:`visible_departures`), so the board stays live between the once-a-minute
polls.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import requests

from .config import Connection, Station

log = logging.getLogger(__name__)

API_URL = "https://transport.opendata.ch/v1/stationboard"
REQUEST_TIMEOUT = 10  # seconds

# Shared session: connection reuse across the once-a-minute polls.
_session = requests.Session()


@dataclass(frozen=True)
class Departure:
    """One matched upcoming departure for a station."""

    number: str  # bus line, e.g. "32"
    destination: str  # API "to" terminal (identifies the direction)
    label: str  # short on-screen destination label
    departure_ts: int  # best-known departure (realtime if available), unix seconds


def fetch_station(station_id: str, limit: int) -> list[dict[str, Any]] | None:
    """Fetch the raw stationboard list for ``station_id``.

    Returns the list of entries, or ``None`` on any network/HTTP/parse error
    (callers keep their last good data rather than crashing).
    """
    params: dict[str, str | int] = {"id": station_id, "limit": limit}
    try:
        resp = _session.get(API_URL, params=params, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("Fetch failed for station %s: %s", station_id, exc)
        return None

    board = data.get("stationboard")
    if not isinstance(board, list):
        log.warning("Unexpected response for station %s (no stationboard)", station_id)
        return None
    return board


def _effective_departure_ts(stop: dict[str, Any]) -> int | None:
    """Best-known departure time for a stationboard ``stop`` object.

    Prefers the realtime estimate — ``prognosis.departure`` (ISO 8601), then
    the ``delay`` in whole minutes on top of the planned time — and falls back
    to the planned ``departureTimestamp``. ``None`` if no usable time at all.
    """
    planned = stop.get("departureTimestamp")
    if isinstance(planned, bool) or not isinstance(planned, (int, float)):
        return None

    prognosis = stop.get("prognosis")
    estimate = prognosis.get("departure") if isinstance(prognosis, dict) else None
    if isinstance(estimate, str):
        try:
            return int(datetime.fromisoformat(estimate).timestamp())
        except ValueError:
            log.debug("Unparseable prognosis.departure %r", estimate)

    delay = stop.get("delay")
    if isinstance(delay, int) and not isinstance(delay, bool):
        return int(planned) + delay * 60

    return int(planned)


def parse_departures(
    board: list[dict[str, Any]], connections: list[Connection]
) -> list[Departure]:
    """Filter a raw stationboard to the configured (number, destination) pairs.

    Matching is on ``number`` + ``to`` (the line's terminal in the desired
    direction). Results are sorted ascending by best-known departure time.
    """
    # Map (number, destination) -> label for O(1) matching.
    wanted: dict[tuple[str, str], str] = {
        (c.number, c.destination): c.label for c in connections
    }

    out: list[Departure] = []
    for entry in board:
        if not isinstance(entry, dict):
            continue
        number = entry.get("number")
        to = entry.get("to")
        if not isinstance(number, str) or not isinstance(to, str):
            continue
        label = wanted.get((number, to))
        if label is None:
            continue

        stop = entry.get("stop")
        ts = _effective_departure_ts(stop) if isinstance(stop, dict) else None
        if ts is None:
            continue

        out.append(
            Departure(number=number, destination=to, label=label, departure_ts=ts)
        )

    out.sort(key=lambda d: d.departure_ts)
    return out


def fetch_and_parse(station: Station, limit: int) -> list[Departure] | None:
    """Fetch + parse one station. ``None`` on fetch failure."""
    board = fetch_station(station.id, limit)
    if board is None:
        return None
    return parse_departures(board, station.connections)


def minutes_until(departure_ts: int, now: float) -> int:
    """Whole minutes from ``now`` (unix seconds) until planned departure.

    Floors so a bus shows "0" only inside its final minute; never negative.
    """
    return max(0, math.floor((departure_ts - now) / 60))


def visible_departures(
    departures: list[Departure], min_time: int, now: float
) -> list[tuple[Departure, int]]:
    """Departures still worth showing, paired with their live minute count.

    Drops anything departing in fewer than ``min_time`` minutes, then keeps only
    the *soonest* catchable departure per ``(number, destination)`` connection —
    so a busy line doesn't fill the panel with its own repeats and crowd out the
    other lines/stations. Input is assumed already sorted by timestamp, so output
    stays sorted and the first survivor of each key is the next one you can catch.
    """
    result: list[tuple[Departure, int]] = []
    seen: set[tuple[str, str]] = set()
    for dep in departures:
        mins = minutes_until(dep.departure_ts, now)
        if mins < min_time:
            continue
        key = (dep.number, dep.destination)
        if key in seen:
            continue
        seen.add(key)
        result.append((dep, mins))
    return result
