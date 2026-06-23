"""Load and validate the JSON configuration file.

The schema is the one supplied by the project owner (stations + per-station
connections + destination_labels) plus an optional, non-breaking ``display``
section for hardware / rendering tunables. Everything in ``display`` has a
sane default so an old config without it keeps working.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

# Defaults for the optional "display" section.
DISPLAY_DEFAULTS = {
    "brightness": 60,
    "poll_interval_sec": 60,
    "api_limit": 30,
    "scroll_px_per_sec": 20.0,
    "font": "6x10",
    "header_font": "5x7",
    "gpio_slowdown": 2,
    "pwm_bits": 11,
    "pwm_lsb_nanoseconds": 130,
}


@dataclass(frozen=True)
class Connection:
    """A bus line + direction we want to watch at a station.

    ``destination`` matches the transport API ``to`` field (the line's
    terminal in the desired direction). ``label`` is what we draw on screen.
    """

    number: str
    destination: str
    label: str


@dataclass
class Station:
    id: str
    min_time: int
    connections: list[Connection]
    name: str | None = None  # optional header override; else API station name


@dataclass
class Display:
    brightness: int = DISPLAY_DEFAULTS["brightness"]
    poll_interval_sec: int = DISPLAY_DEFAULTS["poll_interval_sec"]
    api_limit: int = DISPLAY_DEFAULTS["api_limit"]
    scroll_px_per_sec: float = DISPLAY_DEFAULTS["scroll_px_per_sec"]
    font: str = DISPLAY_DEFAULTS["font"]
    header_font: str = DISPLAY_DEFAULTS["header_font"]
    gpio_slowdown: int = DISPLAY_DEFAULTS["gpio_slowdown"]
    pwm_bits: int = DISPLAY_DEFAULTS["pwm_bits"]
    pwm_lsb_nanoseconds: int = DISPLAY_DEFAULTS["pwm_lsb_nanoseconds"]


@dataclass
class Config:
    stations: list[Station]
    destination_labels: dict[str, str]
    display: Display = field(default_factory=Display)


class ConfigError(ValueError):
    """Raised when the config file is structurally invalid."""


def _strip_city(destination: str) -> str:
    """Fallback label: drop a leading ``City, `` prefix, e.g.
    ``"Zürich, Bucheggplatz"`` -> ``"Bucheggplatz"``."""
    if ", " in destination:
        return destination.split(", ", 1)[1]
    return destination


def load_config(path: str | Path) -> Config:
    """Parse, validate and return the configuration.

    Raises ``ConfigError`` on structural problems. Missing destination labels
    are only warned about (we fall back to a stripped destination).
    """
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config file is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("Top-level config must be a JSON object")

    labels = raw.get("destination_labels", {})
    if not isinstance(labels, dict):
        raise ConfigError("'destination_labels' must be an object")

    raw_stations = raw.get("stations")
    if not isinstance(raw_stations, list) or not raw_stations:
        raise ConfigError("'stations' must be a non-empty list")

    stations: list[Station] = []
    for i, s in enumerate(raw_stations):
        where = f"stations[{i}]"
        if not isinstance(s, dict):
            raise ConfigError(f"{where} must be an object")

        sid = s.get("id")
        if not isinstance(sid, str) or not sid:
            raise ConfigError(f"{where}.id must be a non-empty string")

        min_time = s.get("min_time", 0)
        if not isinstance(min_time, int) or isinstance(min_time, bool) or min_time < 0:
            raise ConfigError(f"{where}.min_time must be a non-negative integer")

        name = s.get("name")
        if name is not None and not isinstance(name, str):
            raise ConfigError(f"{where}.name must be a string if present")

        raw_conns = s.get("connections")
        if not isinstance(raw_conns, list) or not raw_conns:
            raise ConfigError(f"{where}.connections must be a non-empty list")

        conns: list[Connection] = []
        for j, c in enumerate(raw_conns):
            cwhere = f"{where}.connections[{j}]"
            if not isinstance(c, dict):
                raise ConfigError(f"{cwhere} must be an object")
            number = c.get("number")
            destination = c.get("destination")
            if not isinstance(number, str) or not number:
                raise ConfigError(f"{cwhere}.number must be a non-empty string")
            if not isinstance(destination, str) or not destination:
                raise ConfigError(f"{cwhere}.destination must be a non-empty string")

            if destination in labels:
                label = labels[destination]
            else:
                label = _strip_city(destination)
                log.warning(
                    "No destination_labels entry for %r; using fallback label %r",
                    destination,
                    label,
                )
            conns.append(Connection(number=number, destination=destination, label=label))

        stations.append(Station(id=sid, min_time=min_time, connections=conns, name=name))

    display = _parse_display(raw.get("display", {}))
    return Config(stations=stations, destination_labels=labels, display=display)


def _parse_display(raw: object) -> Display:
    if not isinstance(raw, dict):
        raise ConfigError("'display' must be an object if present")
    merged = {**DISPLAY_DEFAULTS, **raw}
    # Ignore unknown keys but keep known ones.
    return Display(
        brightness=int(merged["brightness"]),
        poll_interval_sec=int(merged["poll_interval_sec"]),
        api_limit=int(merged["api_limit"]),
        scroll_px_per_sec=float(merged["scroll_px_per_sec"]),
        font=str(merged["font"]),
        header_font=str(merged["header_font"]),
        gpio_slowdown=int(merged["gpio_slowdown"]),
        pwm_bits=int(merged["pwm_bits"]),
        pwm_lsb_nanoseconds=int(merged["pwm_lsb_nanoseconds"]),
    )
