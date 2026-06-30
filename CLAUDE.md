# CLAUDE.md

Guidance for working in this repo. See [README.md](README.md) for the full
hardware/setup story; this file covers what's non-obvious when editing the code.

## What this is

A headless Raspberry Pi 3B drives a 128×64 HUB75E RGB LED matrix (Adafruit RGB
Matrix Bonnet #3211) to show next VBZ bus departures from
`transport.opendata.ch`, grouped by station, with a clock and horizontally
scrolling destination labels.

## Architecture (data flow)

`config.json` → `config.py` (load/validate) → poller thread in `__main__.py`
fetches each station once/minute via `transport.py` → shared `state` dict (under
a lock) holds raw `Departure`s → 30fps render loop builds `StationGroup`s
(`layout.py` composes a PIL frame) → `renderer.py` pushes it to the panel.

| File | Responsibility |
|------|----------------|
| `src/config.py` | Parse/validate `config.json`; dataclasses `Config/Station/Connection/Display`. Resolves each connection's on-screen `label`. |
| `src/transport.py` | API client + parsing. `parse_departures` matches on `(number, to)`; `visible_departures` applies `min_time` + live countdown. No rendering. |
| `src/layout.py` | **Pure PIL, no `rgbmatrix` import.** `FrameComposer.compose()` builds the 128×64 image; holds fonts, column geometry, and scroll state. |
| `src/renderer.py` | **Only** module importing `rgbmatrix`. Thin wrapper: options + `SetImage`/`SwapOnVSync`. |
| `src/__main__.py` | `Poller` thread + render loop + signal-based shutdown. Entry: `python3 -m src`. |
| `server/` | FastAPI backend for the config web UI. Reuses `load_config` (validation) + `FrameComposer` (PNG preview); **never** imports `renderer`/`rgbmatrix`. Entry: `python3 -m server` (own venv `webenv/`, own service on :8080). |
| `web/` | React+TS config UI (Vite). Built on the dev machine; `web/dist/` is committed and served by `server/`. |

## Key conventions / gotchas

- **rgbmatrix lives in a venv, not system Python.** Adafruit's installer refuses
  Debian's externally-managed Python, so `setup_pi.sh` builds the bindings into a
  `--system-site-packages` venv at `env/` and rewrites the systemd unit's
  `ExecStart` to `env/bin/python3 -m src`. The venv still sees apt-installed
  Pillow/requests. Don't switch the service back to `/usr/bin/python3`.
- **`rgbmatrix` only on the Pi.** Keep its import isolated to `renderer.py`. Tests,
  `layout.py`, and `tools/preview.py` must stay importable on the dev machine
  (which has no `rgbmatrix`). If you need new render logic testable off-Pi, put it
  in `layout.py`, not `renderer.py`.
- **Direction matching:** `connections[].destination` is matched against the API
  `to` field (the line's terminal *in the desired direction*), not an intermediate
  stop. E.g. line 32 → `"Zürich, Strassenverkehrsamt"` selects that direction.
- **Countdown is live between polls.** The API is polled once/minute, but minutes
  and the `min_time` filter are recomputed every frame from cached
  `departure_ts`. Don't move that logic into the poller.
- **Fonts are BDF → PIL.** Pillow can't read `.bdf` at draw time, so `layout.py`
  compiles them once (`BdfFontFile`) into a temp cache. PIL *bitmap* fonts have no
  `getmetrics()`; use `font_height()`/`text_w()` (getbbox/getlength) instead.
- **Scrolling:** per-row x-offset keyed by `station_id|number|label`, advanced by a
  wall-clock delta clamped to `MAX_DT` (avoids jumps after a frame stall). The
  destination column is pixel-clipped via a sub-image paste, not `fit_text`
  truncation (that's only for headers).
- **`config.json` is committed and deployed via git** — it's the live config, not
  an example. Edit deliberately. It's also written at runtime by the web UI
  (`PUT /api/config`), which validates via `load_config` and keeps a `.bak`.
- **Render colours live in the config now.** `src/config.py` owns `COLOR_DEFAULTS`
  + the `Colors` dataclass (the single source of truth — they match what
  `layout.py` used to hardcode); `FrameComposer` takes a `Colors`. Add a new
  colour by extending `COLOR_ROLES`/`COLOR_DEFAULTS`/`Colors`, not by hardcoding.
- **Config changes need a restart.** The display loads config once at startup and
  several `display` knobs only apply at `RGBMatrix`/`FrameComposer` construction,
  so the web UI applies edits by rewriting `config.json` + `systemctl restart
  transport_display.service` (via a narrow `sudoers` rule). There's no live reload.
  That same `sudoers` rule also allows `start`/`stop` for the web UI's screen
  on/off button (`POST /api/power`); stopping sends SIGTERM, which makes
  `__main__.py` `renderer.clear()` the panel and stop polling. Widening it means
  editing the `SUDOERS_LINE` in `setup_pi.sh` and re-running it on the Pi.
- **`web/dist/` is committed** (the Pi has no Node). Rebuild with `cd web && npm
  run build` and commit the output whenever you change the UI.
- **`setup_pi.sh` must stay LF** (enforced in `.gitattributes`, which also covers
  `*.service`) or it won't run on the Pi. It's idempotent; keep it that way.

## Dev workflow

- You run on the **dev machine, not the Pi**. Never hand-edit on the Pi; deploy by
  `git push` then `git pull` on the Pi (see README).
- Tests: `python -m pytest tests/` (runs without hardware).
- Type-check: `python -m mypy` (strict; config in `mypy.ini`). Install dev tooling
  with `pip install -r requirements-dev.txt`. `rgbmatrix` is treated as untyped
  (no stubs, Pi-only), so `renderer.py` still type-checks off-Pi.
- Preview the layout without hardware: `python tools/preview.py preview.png 8`.
- Web UI dev (Windows/PowerShell): `$env:TRANSPORT_DISPLAY_NO_RESTART = "1"; python
  -m server` (backend on :8080, won't poke systemd) + `cd web; npm run dev` (Vite
  proxies `/api`). PowerShell has no inline `VAR=value` prefix — set the env var as
  its own statement. `mypy` and `pytest` cover `server/`; the React app is
  type-checked by `npm run build`.
- Panel is driven with `adafruit-hat-pwm`, `gpio_slowdown=2`, `rows=64 cols=128`;
  the Pi has core 3 isolated (`isolcpus=3`) and onboard sound disabled.
