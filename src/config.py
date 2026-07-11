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
from typing import TypedDict

log = logging.getLogger(__name__)

# Bundled BDF bitmap fonts; display.font/header_font must name one of these.
# (Lives here rather than layout.py so validation doesn't need PIL.)
FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"


class DisplayDefaults(TypedDict):
    brightness: int
    poll_interval_sec: int
    api_limit: int
    scroll_px_per_sec: float
    font: str
    header_font: str
    gpio_slowdown: int
    pwm_bits: int
    pwm_lsb_nanoseconds: int


# Defaults for the optional "display" section.
DISPLAY_DEFAULTS: DisplayDefaults = {
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

# Valid (min, max) per numeric "display" key. The single source for both
# validation here and the web UI's number-input hints (via /api/meta), so the
# two can't drift apart.
DISPLAY_BOUNDS: dict[str, tuple[int, int]] = {
    "brightness": (1, 100),
    "poll_interval_sec": (10, 600),
    "api_limit": (1, 100),
    "scroll_px_per_sec": (0, 100),
    "gpio_slowdown": (0, 5),
    "pwm_bits": (1, 11),
    "pwm_lsb_nanoseconds": (50, 3000),
}


# The render roles drawn on the panel and their default colours, as #RRGGBB.
# These mirror what layout.py used to hardcode; the optional "colors" section
# overrides any subset. ``COLOR_ROLES`` fixes the field order (used by the web
# UI and by ``_parse_colors``).
COLOR_ROLES = ("clock", "header", "number", "dest", "minutes")

COLOR_DEFAULTS: dict[str, str] = {
    "clock": "#FFB000",  # amber
    "header": "#00C8FF",  # cyan
    "number": "#FFDC00",  # yellow
    "dest": "#EBEBEB",  # near-white
    "minutes": "#00E650",  # green
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
    display_name: str
    min_time: int
    connections: list[Connection]


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


RGB = tuple[int, int, int]


def _hex_to_rgb(value: str) -> RGB:
    """Parse ``#RRGGBB`` (the leading ``#`` is optional) into an (r, g, b)."""
    h = value.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"expected #RRGGBB, got {value!r}")
    try:
        r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    except ValueError as exc:
        raise ValueError(f"invalid hex colour {value!r}") from exc
    return (r, g, b)


@dataclass(frozen=True)
class Colors:
    """The five render colours, as (r, g, b) tuples. Defaults match the values
    layout.py used to hardcode."""

    clock: RGB = _hex_to_rgb(COLOR_DEFAULTS["clock"])
    header: RGB = _hex_to_rgb(COLOR_DEFAULTS["header"])
    number: RGB = _hex_to_rgb(COLOR_DEFAULTS["number"])
    dest: RGB = _hex_to_rgb(COLOR_DEFAULTS["dest"])
    minutes: RGB = _hex_to_rgb(COLOR_DEFAULTS["minutes"])


@dataclass
class Config:
    stations: list[Station]
    display: Display = field(default_factory=Display)
    colors: Colors = field(default_factory=Colors)


class ConfigError(ValueError):
    """Raised when the config file is structurally invalid."""


def _strip_city(destination: str) -> str:
    """Fallback label: drop a leading ``City, `` prefix, e.g.
    ``"Zürich, Bucheggplatz"`` -> ``"Bucheggplatz"``."""
    if ", " in destination:
        return destination.split(", ", 1)[1]
    return destination


def load_config(path: str | Path) -> Config:
    """Read ``path``, validate and return the configuration.

    Raises ``ConfigError`` on a missing/unreadable file or structural problems.
    """
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config file is not valid JSON: {exc}") from exc
    return parse_config(raw)


def parse_config(raw: object) -> Config:
    """Validate an already-parsed JSON document and return the configuration.

    Raises ``ConfigError`` on structural problems. Missing destination labels
    are only warned about (we fall back to a stripped destination).
    """
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

        display_name = s.get("display_name")
        if not isinstance(display_name, str):
            raise ConfigError(f"{where}.display_name must be a string")

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

        stations.append(Station(id=sid, display_name=display_name, min_time=min_time, connections=conns))

    display = _parse_display(raw.get("display", {}))
    colors = _parse_colors(raw.get("colors", {}))
    return Config(stations=stations, display=display, colors=colors)


def _parse_display(raw: object) -> Display:
    if not isinstance(raw, dict):
        raise ConfigError("'display' must be an object if present")
    # Read each known key from the config, falling back to its default and
    # validating type + range (so a hand-edited or API-supplied value fails as
    # a ConfigError, not a crash-looping service); unknown keys are ignored.

    def _int(key: str, default: int) -> int:
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int):
            raise ConfigError(f"display.{key} must be an integer")
        lo, hi = DISPLAY_BOUNDS[key]
        if not lo <= value <= hi:
            raise ConfigError(f"display.{key} must be between {lo} and {hi}")
        return value

    def _number(key: str, default: float) -> float:
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ConfigError(f"display.{key} must be a number")
        lo, hi = DISPLAY_BOUNDS[key]
        if not lo <= value <= hi:
            raise ConfigError(f"display.{key} must be between {lo} and {hi}")
        return float(value)

    def _font(key: str, default: str) -> str:
        value = raw.get(key, default)
        if not isinstance(value, str) or not value:
            raise ConfigError(f"display.{key} must be a font name string")
        if not (FONTS_DIR / f"{value}.bdf").is_file():
            raise ConfigError(f"display.{key}: no bundled font named {value!r}")
        return value

    return Display(
        brightness=_int("brightness", DISPLAY_DEFAULTS["brightness"]),
        poll_interval_sec=_int("poll_interval_sec", DISPLAY_DEFAULTS["poll_interval_sec"]),
        api_limit=_int("api_limit", DISPLAY_DEFAULTS["api_limit"]),
        scroll_px_per_sec=_number("scroll_px_per_sec", DISPLAY_DEFAULTS["scroll_px_per_sec"]),
        font=_font("font", DISPLAY_DEFAULTS["font"]),
        header_font=_font("header_font", DISPLAY_DEFAULTS["header_font"]),
        gpio_slowdown=_int("gpio_slowdown", DISPLAY_DEFAULTS["gpio_slowdown"]),
        pwm_bits=_int("pwm_bits", DISPLAY_DEFAULTS["pwm_bits"]),
        pwm_lsb_nanoseconds=_int("pwm_lsb_nanoseconds", DISPLAY_DEFAULTS["pwm_lsb_nanoseconds"]),
    )


def _parse_one_color(where: str, value: object) -> RGB:
    """Coerce a config colour value to (r, g, b): accepts ``#RRGGBB`` or
    ``[r, g, b]`` (0–255)."""
    if isinstance(value, str):
        try:
            return _hex_to_rgb(value)
        except ValueError as exc:
            raise ConfigError(f"{where}: {exc}") from exc
    if isinstance(value, (list, tuple)) and len(value) == 3:
        rgb = []
        for component in value:
            if not isinstance(component, int) or isinstance(component, bool):
                raise ConfigError(f"{where} components must be integers 0-255")
            if not 0 <= component <= 255:
                raise ConfigError(f"{where} components must be in range 0-255")
            rgb.append(component)
        return (rgb[0], rgb[1], rgb[2])
    raise ConfigError(f"{where} must be a '#RRGGBB' string or [r, g, b] list")


def _parse_colors(raw: object) -> Colors:
    if not isinstance(raw, dict):
        raise ConfigError("'colors' must be an object if present")
    parsed: dict[str, RGB] = {}
    for role in COLOR_ROLES:
        if role in raw:
            parsed[role] = _parse_one_color(f"colors.{role}", raw[role])
    return Colors(**parsed)
