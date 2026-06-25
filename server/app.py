"""FastAPI app for the config web UI.

Endpoints (all under ``/api``):

* ``GET  /config``  – the current ``config.json`` (raw).
* ``PUT  /config``  – validate (via :func:`src.config.load_config`), write
  atomically, then restart the display service.
* ``GET  /meta``    – defaults + field hints so the form can render generically.
* ``GET  /fonts``   – the bundled ``.bdf`` font stems.
* ``POST /preview`` – render a (possibly unsaved) config to a PNG, no hardware.
* ``GET  /status``  – whether the display service is active.
* ``POST /restart`` – restart the display service.

The built React app under ``web/dist`` is mounted at ``/`` when present.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from src.config import (
    COLOR_DEFAULTS,
    COLOR_ROLES,
    DISPLAY_DEFAULTS,
    Config,
    ConfigError,
    load_config,
)
from src.layout import FONTS_DIR, FrameComposer, StationGroup
from src.transport import Departure

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("TRANSPORT_DISPLAY_CONFIG", ROOT / "config.json"))
WEB_DIST = ROOT / "web" / "dist"
DISPLAY_SERVICE = os.environ.get("TRANSPORT_DISPLAY_SERVICE", "transport_display.service")
# Set on the dev machine so saving doesn't try to poke a non-existent service.
NO_RESTART = bool(os.environ.get("TRANSPORT_DISPLAY_NO_RESTART"))

# Hints for the "display" number inputs (key -> sensible UI bounds).
DISPLAY_FIELDS: list[dict[str, Any]] = [
    {"key": "brightness", "label": "Brightness", "min": 1, "max": 100, "step": 1},
    {"key": "poll_interval_sec", "label": "Poll interval (s)", "min": 10, "max": 600, "step": 5},
    {"key": "api_limit", "label": "API limit", "min": 1, "max": 100, "step": 1},
    {"key": "scroll_px_per_sec", "label": "Scroll speed (px/s)", "min": 0, "max": 100, "step": 1},
    {"key": "gpio_slowdown", "label": "GPIO slowdown", "min": 0, "max": 5, "step": 1},
    {"key": "pwm_bits", "label": "PWM bits", "min": 1, "max": 11, "step": 1},
    {"key": "pwm_lsb_nanoseconds", "label": "PWM LSB (ns)", "min": 50, "max": 3000, "step": 10},
]

COLOR_ROLE_LABELS: dict[str, str] = {
    "clock": "Clock",
    "header": "Station header",
    "number": "Bus number",
    "dest": "Destination",
    "minutes": "Minutes",
}

app = FastAPI(title="Transport display config")

# LAN-only, no auth (see plan); permissive CORS keeps the Vite dev server happy.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    tmp = CONFIG_PATH.parent / (CONFIG_PATH.name + ".tmp")
    tmp.write_text(json.dumps(payload, indent=4, ensure_ascii=False), encoding="utf-8")
    try:
        load_config(tmp)
    except ConfigError as exc:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception:
        tmp.unlink(missing_ok=True)
        raise

    if CONFIG_PATH.exists():
        shutil.copy2(CONFIG_PATH, CONFIG_PATH.parent / (CONFIG_PATH.name + ".bak"))
    os.replace(tmp, CONFIG_PATH)
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
    tmp = CONFIG_PATH.parent / (CONFIG_PATH.name + ".preview.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    try:
        cfg = load_config(tmp)
    except ConfigError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        tmp.unlink(missing_ok=True)

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
