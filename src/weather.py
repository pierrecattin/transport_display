"""Ecowitt GW3000 local-API client and parsing.

The gateway's ``/get_livedata_info`` endpoint returns all live sensor readings
as JSON; we only extract the two temperatures the board shows: outdoor from the
``common_list`` entry with ``id == "0x02"`` and indoor from ``wh25[0].intemp``
(both string-encoded Celsius values). Like :mod:`transport`, fetch errors
return ``None`` so callers keep their last good data. No rendering here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger(__name__)

REQUEST_TIMEOUT = 5  # seconds; the gateway is on the LAN

OUTDOOR_TEMP_ID = "0x02"

# Shared session: connection reuse across the once-a-minute polls.
_session = requests.Session()


@dataclass(frozen=True)
class Temps:
    """The latest indoor/outdoor temperature readings, in Celsius.

    Either field may be ``None`` when the gateway response lacks that sensor
    (unpaired, battery dead, ...).
    """

    indoor: float | None
    outdoor: float | None


def _parse_float(value: object) -> float | None:
    """The gateway encodes numbers as strings like ``"26.1"``."""
    if not isinstance(value, str):
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_livedata(data: object) -> Temps:
    """Extract the two temperatures from a ``get_livedata_info`` document."""
    indoor: float | None = None
    outdoor: float | None = None
    if isinstance(data, dict):
        common = data.get("common_list")
        if isinstance(common, list):
            for entry in common:
                if isinstance(entry, dict) and entry.get("id") == OUTDOOR_TEMP_ID:
                    outdoor = _parse_float(entry.get("val"))
                    break
        wh25 = data.get("wh25")
        if isinstance(wh25, list) and wh25 and isinstance(wh25[0], dict):
            indoor = _parse_float(wh25[0].get("intemp"))
    return Temps(indoor=indoor, outdoor=outdoor)


def fetch_weather(url: str) -> Temps | None:
    """Fetch and parse the gateway's live data.

    Returns ``None`` on any network/HTTP/parse error (callers keep last good
    data rather than crashing).
    """
    try:
        resp = _session.get(url, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("Weather fetch failed (%s): %s", url, exc)
        return None
    return parse_livedata(data)
