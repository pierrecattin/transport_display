"""Entry point: poll the transport API in the background and render the board.

Run with ``python3 -m src`` from the project root (the systemd unit does this).
A config path may be given as the first argument; it defaults to ``config.json``
next to the project root.
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING

from .config import Config, load_config
from .transport import (
    Departure,
    fetch_station,
    parse_departures,
    visible_departures,
)
from .weather import Temps, fetch_weather

if TYPE_CHECKING:
    from .layout import StationGroup, TempReadout

log = logging.getLogger("transport_display")

TARGET_FPS = 30  # while a destination label is scrolling
IDLE_FPS = 4  # otherwise only the clock/minutes change (at most once a second)
# A station renders dimmed once its last successful poll is older than this
# many poll intervals (with a floor so short intervals don't flicker stale).
STALE_POLLS = 3
STALE_MIN_SEC = 180.0
ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.json"


@dataclass
class StationState:
    """Latest known data for one station (shared between threads)."""

    departures: list[Departure] = field(default_factory=list)
    last_ok: float | None = None  # wall time of last successful fetch


@dataclass
class WeatherState:
    """Latest known weather-gateway readings (shared between threads)."""

    temps: Temps | None = None
    last_ok: float | None = None  # wall time of last successful fetch


class Poller(threading.Thread):
    """Fetches every station (and the weather gateway, when configured) once
    per ``poll_interval_sec`` until stopped."""

    def __init__(
        self,
        config: Config,
        state: dict[str, StationState],
        weather: WeatherState,
        lock: threading.Lock,
    ):
        super().__init__(name="poller", daemon=True)
        self._config = config
        self._state = state
        self._weather = weather
        self._lock = lock
        self._stop = threading.Event()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                self._poll_once()
            except Exception:
                # One bad poll (unexpected payload shape, transient OS error,
                # ...) must not kill the thread: a dead poller leaves the
                # render loop showing silently decaying data forever.
                log.exception("Poll cycle failed; retrying next interval")
            self._stop.wait(self._config.display.poll_interval_sec)

    def _poll_once(self) -> None:
        for station in self._config.stations:
            if self._stop.is_set():
                return
            board = fetch_station(station.id, self._config.display.api_limit)
            if board is None:
                continue  # keep last good data
            deps = parse_departures(board, station.connections)
            with self._lock:
                st = self._state[station.id]
                st.departures = deps
                st.last_ok = time.time()
            log.info("Polled %s (%s): %d matching", station.id, station.display_name, len(deps))

        if self._config.weather.url and not self._stop.is_set():
            temps = fetch_weather(self._config.weather.url)
            if temps is not None:  # on failure keep last good data
                with self._lock:
                    self._weather.temps = temps
                    self._weather.last_ok = time.time()
                log.info("Polled weather: in=%s out=%s", temps.indoor, temps.outdoor)


def _stale_after(config: Config) -> float:
    """Age (seconds) past which un-refreshed data renders dimmed."""
    return max(STALE_POLLS * config.display.poll_interval_sec, STALE_MIN_SEC)


def _build_groups(
    config: Config,
    state: dict[str, StationState],
    lock: threading.Lock,
    now: float,
) -> list[StationGroup]:
    from .layout import StationGroup  # local import keeps rgbmatrix off the dev path

    stale_after = _stale_after(config)
    groups: list[StationGroup] = []
    with lock:
        for station in config.stations:
            st = state[station.id]
            vis = visible_departures(st.departures, station.min_time, now)
            groups.append(
                StationGroup(
                    station_id=station.id,
                    name=station.display_name,
                    departures=vis,
                    # Dim the group when polls have been failing so an outage
                    # is visibly different from a live board.
                    stale=st.last_ok is not None and now - st.last_ok > stale_after,
                )
            )
    return groups


def _build_temps(
    config: Config,
    weather: WeatherState,
    lock: threading.Lock,
    now: float,
) -> TempReadout | None:
    from .layout import TempReadout  # local import keeps rgbmatrix off the dev path

    with lock:
        temps, last_ok = weather.temps, weather.last_ok
    if temps is None or last_ok is None:
        return None  # never fetched: draw nothing rather than a fake reading
    return TempReadout(
        indoor=temps.indoor,
        outdoor=temps.outdoor,
        stale=now - last_ok > _stale_after(config),
    )


def main(argv: list[str]) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    config_path = Path(argv[1]) if len(argv) > 1 else DEFAULT_CONFIG
    config = load_config(config_path)
    log.info("Loaded config: %d stations", len(config.stations))

    state: dict[str, StationState] = {s.id: StationState() for s in config.stations}
    weather = WeatherState()
    lock = threading.Lock()

    poller = Poller(config, state, weather, lock)
    poller.start()

    # Renderer import is deferred so config errors surface even off-Pi.
    from .renderer import Renderer

    renderer = Renderer(config)

    stopping = threading.Event()

    def _handle_signal(signum: int, _frame: FrameType | None) -> None:
        log.info("Received signal %s, shutting down", signum)
        stopping.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    try:
        while not stopping.is_set():
            frame_start = time.time()
            clock_text = datetime.now().strftime("%H:%M")
            groups = _build_groups(config, state, lock, frame_start)
            temps = _build_temps(config, weather, lock, frame_start)
            scrolling = renderer.render(groups, clock_text, frame_start, temps)

            # Full rate only while something scrolls; idle costs a Pi 3 much
            # less CPU (and heat) and nothing else changes faster than 1/s.
            target_dt = 1.0 / (TARGET_FPS if scrolling else IDLE_FPS)
            elapsed = time.time() - frame_start
            time.sleep(max(0.0, target_dt - elapsed))
    finally:
        poller.stop()
        renderer.clear()
        poller.join(timeout=2.0)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
