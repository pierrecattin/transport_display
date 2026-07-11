"""FastAPI app for the config web UI.

Endpoints (all under ``/api``):

* ``GET  /config``  – the current ``config.json`` (raw).
* ``PUT  /config``  – validate (via :func:`src.config.parse_config`), write
  atomically, then restart the display service.
* ``GET  /meta``    – defaults + field hints so the form can render generically.
* ``GET  /fonts``   – the bundled ``.bdf`` font stems.
* ``POST /preview`` – render a (possibly unsaved) config to a PNG, no hardware.
* ``GET  /status``  – whether the display service is active.
* ``POST /restart`` – restart the display service.
* ``POST /power``   – start/stop the display service (``{"on": bool}``); stopping
  blanks the panel and halts the API polling.

The built React app under ``web/dist`` is mounted at ``/`` when present.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Response
from fastapi.staticfiles import StaticFiles

from src.config import (
    COLOR_DEFAULTS,
    COLOR_ROLES,
    DISPLAY_BOUNDS,
    DISPLAY_DEFAULTS,
    FONTS_DIR,
    Config,
    ConfigError,
    parse_config,
)
from src.layout import FrameComposer, StationGroup
from src.transport import Departure

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("TRANSPORT_DISPLAY_CONFIG", ROOT / "config.json"))
WEB_DIST = ROOT / "web" / "dist"
DISPLAY_SERVICE = os.environ.get("TRANSPORT_DISPLAY_SERVICE", "transport_display.service")
# Set on the dev machine so saving doesn't try to poke a non-existent service.
NO_RESTART = bool(os.environ.get("TRANSPORT_DISPLAY_NO_RESTART"))

# Label + input step for the "display" number inputs; min/max come from
# src.config.DISPLAY_BOUNDS (also enforced server-side) so UI hints and
# validation can't drift apart.
_DISPLAY_FIELD_UI: list[tuple[str, str, int]] = [
    ("brightness", "Brightness", 1),
    ("poll_interval_sec", "Poll interval (s)", 5),
    ("api_limit", "API limit", 1),
    ("scroll_px_per_sec", "Scroll speed (px/s)", 1),
    ("gpio_slowdown", "GPIO slowdown", 1),
    ("pwm_bits", "PWM bits", 1),
    ("pwm_lsb_nanoseconds", "PWM LSB (ns)", 10),
]
DISPLAY_FIELDS: list[dict[str, Any]] = [
    {
        "key": key,
        "label": label,
        "min": DISPLAY_BOUNDS[key][0],
        "max": DISPLAY_BOUNDS[key][1],
        "step": step,
    }
    for key, label, step in _DISPLAY_FIELD_UI
]

COLOR_ROLE_LABELS: dict[str, str] = {
    "clock": "Clock",
    "header": "Station header",
    "number": "Bus number",
    "dest": "Destination",
    "minutes": "Minutes",
}

app = FastAPI(title="Transport display config")

# Deliberately NO CORS middleware: the API is unauthenticated, so allowing
# cross-origin requests would let any web page someone on the LAN visits drive
# it (rewrite the config, stop the display). Browsers block cross-origin
# PUT/POST without CORS headers, and no legitimate caller is cross-origin --
# the built SPA is served same-origin from this app, and `npm run dev`
# reaches the API through Vite's server-side /api proxy.


def _systemctl(args: list[str], *, sudo: bool) -> tuple[bool, str]:
    """Best-effort systemctl call. Returns (ok, detail). Never raises."""
    if shutil.which("systemctl") is None:
        return False, "systemctl not available"
    cmd = (["sudo"] if sudo else []) + ["systemctl", *args]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)
    detail = (proc.stdout or proc.stderr).strip()
    return proc.returncode == 0, detail


def _restart_display() -> dict[str, Any]:
    if NO_RESTART:
        return {"ok": False, "detail": "restart disabled (dev)"}
    ok, detail = _systemctl(["restart", DISPLAY_SERVICE], sudo=True)
    return {"ok": ok, "detail": detail}


def _set_power(on: bool) -> dict[str, Any]:
    """Start or stop the display service. Stopping (SIGTERM) makes the display
    blank the panel and stop polling the API; ``Restart=always`` does not fight
    an explicit ``stop``."""
    if NO_RESTART:
        return {"ok": False, "detail": "power control disabled (dev)"}
    ok, detail = _systemctl(["start" if on else "stop", DISPLAY_SERVICE], sudo=True)
    return {"ok": ok, "detail": detail}


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


@app.get("/api/config")
def get_config() -> Any:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"{CONFIG_PATH.name} not found")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail=f"config is not valid JSON: {exc}")


@app.put("/api/config")
def put_config(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Validate then atomically replace config.json, keeping a .bak, and restart."""
    try:
        parse_config(payload)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if CONFIG_PATH.exists():
        shutil.copy2(CONFIG_PATH, CONFIG_PATH.parent / (CONFIG_PATH.name + ".bak"))
    # Unique temp name (concurrent saves must not clobber each other's
    # half-written file) + fsync so a power cut can't leave a truncated config.
    fd, tmp_name = tempfile.mkstemp(
        dir=CONFIG_PATH.parent, prefix=CONFIG_PATH.name + ".", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=4, ensure_ascii=False)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, CONFIG_PATH)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return {"ok": True, "restart": _restart_display()}


@app.get("/api/meta")
def get_meta() -> dict[str, Any]:
    return {
        "display_defaults": DISPLAY_DEFAULTS,
        "display_fields": DISPLAY_FIELDS,
        "color_defaults": COLOR_DEFAULTS,
        "color_roles": [
            {"key": role, "label": COLOR_ROLE_LABELS[role]} for role in COLOR_ROLES
        ],
    }


@app.get("/api/fonts")
def get_fonts() -> list[str]:
    return sorted(p.stem for p in FONTS_DIR.glob("*.bdf"))


@app.get("/api/status")
def get_status() -> dict[str, Any]:
    ok, detail = _systemctl(["is-active", DISPLAY_SERVICE], sudo=False)
    return {"active": ok, "detail": detail or "unknown"}


@app.post("/api/restart")
def post_restart() -> dict[str, Any]:
    return _restart_display()


@app.post("/api/power")
def post_power(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Turn the display on (start) or off (stop)."""
    return _set_power(bool(payload.get("on")))


def _sample_groups(cfg: Config) -> list[StationGroup]:
    """Representative departures (using the configured labels) for the preview."""
    groups: list[StationGroup] = []
    for station in cfg.stations:
        base = max(station.min_time, 1)
        deps = [
            (Departure(number=c.number, label=c.label, departure_ts=0), base + i * 3)
            for i, c in enumerate(station.connections)
        ]
        groups.append(
            StationGroup(station_id=station.id, name=station.display_name, departures=deps)
        )
    return groups


@app.post("/api/preview")
def post_preview(
    payload: dict[str, Any] = Body(...), scale: int = 4
) -> Response:
    """Render the given (unsaved) config to a scaled PNG. No hardware, no restart."""
    scale = max(1, min(scale, 16))
    try:
        cfg = parse_config(payload)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    d = cfg.display
    try:
        composer = FrameComposer(d.font, d.header_font, d.scroll_px_per_sec, cfg.colors)
    except (FileNotFoundError, OSError) as exc:
        raise HTTPException(status_code=400, detail=f"font error: {exc}")

    img = composer.compose(_sample_groups(cfg), "16:32", now=2.0)
    big = img.resize((img.width * scale, img.height * scale), resample=0)  # nearest
    buf = io.BytesIO()
    big.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png")


# Serve the built SPA at "/" (added last so the /api routes win). Only mounted
# when the build is present, so the backend still starts on a dev machine that
# hasn't run `npm run build`.
if WEB_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIST), html=True), name="web")
