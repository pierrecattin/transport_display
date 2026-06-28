# Bus departure LED matrix display

A headless Raspberry Pi 3B drives a **128×64 HUB75E** RGB LED matrix (via an
**Adafruit RGB Matrix Bonnet #3211**) to show the next bus departures for several
Zürich VBZ stops, using live data from
[`transport.opendata.ch`](https://transport.opendata.ch).

For each stop it shows, grouped by station:

```
Buchegg            16:32      ← station header (left) + clock (top-right)
40  Bucheggplatz       4'     ← bus number | destination | minutes to departure
Neuaffolt
32  Strassenverkeh…    7'     ← long destinations scroll horizontally
61  Strassenverkeh…   12'
```

- Bus **number** (left, uncropped), **destination** label (middle, clipped to its
  column and scrolling horizontally when too long), **minutes** until the planned
  departure (right, `N'`).
- **Clock** (`HH:MM`) top-right.
- Departures leaving sooner than a per-station `min_time` are hidden.
- Only the soonest departures that fit on the panel are shown.
- The API is polled once per minute; the minute countdown and `min_time` filter are
  recomputed every frame, so the board stays live between polls.

## Hardware

- Raspberry Pi 3B, Raspberry Pi OS Lite (headless)
- 128×64 P2.5 1/32-scan RGB matrix (HUB75E)
- Adafruit RGB Matrix Bonnet #3211 — **E and pin 8 bridged** (large-panel
  addressing) and **GPIO4↔GPIO18 bridged** (PWM "quality" mod, needs sound off)
- 5V 10A supply into the bonnet's barrel jack

The panel is driven with `--led-rows=64 --led-cols=128
--led-gpio-mapping=adafruit-hat-pwm --led-slowdown-gpio=2` (set in code via
`RGBMatrixOptions`).

## Layout of this repo

```
config.json                 # stations / connections / labels + display options
setup_pi.sh                 # one-time Pi provisioning (run on the Pi)
transport_display.service   # systemd unit
fonts/                      # bundled BDF bitmap fonts (from rpi-rgb-led-matrix)
src/
  __main__.py               # poller thread + render loop + clean shutdown
  config.py                 # load/validate config.json
  transport.py              # API client, parsing, filtering, countdown
  layout.py                 # pure-PIL frame composition (no hardware dep)
  renderer.py               # rgbmatrix hardware I/O
server/                     # FastAPI backend for the config web UI (no hardware dep)
web/                        # React + TS config UI (src + committed dist/)
tests/                      # unit tests (run on the dev machine)
tools/preview.py            # render the layout to a PNG without hardware
```

## Configuration — `config.json`

```jsonc
{
  "stations": [
    {
      "id": "8591285",                  // transport.opendata.ch station id
      "display_name": "Neuaffoltern",   // required header label drawn on screen
      "min_time": 5,                    // hide departures sooner than this many minutes
      "connections": [
        // match on bus number + direction (the API "to"/terminal field)
        { "number": "32", "destination": "Zürich, Strassenverkehrsamt" }
      ]
    }
  ],
  // map the API destination to a short on-screen label
  "destination_labels": { "Zürich, Strassenverkehrsamt": "Strassenverkehrsamt" },
  // all optional, with sane defaults
  "display": {
    "brightness": 60, "poll_interval_sec": 60, "api_limit": 30,
    "scroll_px_per_sec": 20, "font": "6x10", "header_font": "5x7",
    "gpio_slowdown": 2, "pwm_bits": 11, "pwm_lsb_nanoseconds": 130
  },
  // optional; per-role render colours as #RRGGBB, defaults shown
  "colors": {
    "clock": "#FFB000", "header": "#00C8FF", "number": "#FFDC00",
    "dest": "#EBEBEB", "minutes": "#00E650"
  }
}
```

Rather than hand-editing this file, you can change everything above (plus the
fonts and colours) from a browser — see **Config web UI** below.

Note: `destination` is the line's **terminal in the desired direction**, matched
against the API `to` field. E.g. VBZ line 32 runs *Holzerhurd ↔
Strassenverkehrsamt*; setting `"destination": "Zürich, Strassenverkehrsamt"`
selects the direction toward Strassenverkehrsamt. If a `destination` has no entry
in `destination_labels`, the label falls back to the name with a leading `City, `
stripped.

## Config web UI

A small React app (served by a FastAPI backend, both on the Pi) lets you edit
the whole config from a browser on the LAN — stations & connections, destination
labels, the `display` tunables, the fonts, and the five render colours — with a
**live PNG preview** of the panel before you apply. After installing (it's part
of `setup_pi.sh`), open:

```
http://kaeferpi.local:8080
```

"Save & Apply" validates the config, writes `config.json` (keeping a `.bak`), and
restarts the display service so the change takes effect. The header also has a
**Turn screen off / on** button that stops (or starts) the display service —
stopping blanks the panel and halts the API polling. There is **no
authentication** — it's intended for a trusted home LAN only. The backend runs
unprivileged and is allowed (via a narrow `sudoers` rule) to restart/start/stop
*only* the display service.

## First-time setup on the Pi

```bash
# on the Pi (cloned to /home/pierre/transport_display)
cd ~/transport_display
sudo bash setup_pi.sh
sudo reboot
```

`setup_pi.sh` is idempotent and:
1. installs system deps (`python3`, `python3-pillow`, `python3-requests`, …),
2. sets the timezone to `Europe/Zurich`,
3. installs the RGB matrix library via Adafruit's installer (**choose Bonnet +
   Quality**) into a venv at `env/` — Adafruit's `rgb-matrix.py` won't install into
   Debian's externally-managed system Python, so the bindings (and the service)
   use a `--system-site-packages` venv that still sees apt-installed
   Pillow/requests,
4. provisions a second venv (`webenv/`) with FastAPI/uvicorn for the config web UI,
5. disables onboard sound (blacklist `snd_bcm2835` + `dtparam=audio=off`) — required
   by the E↔8 / GPIO4↔18 mods,
6. isolates CPU core 3 (`isolcpus=3`) for the panel's refresh thread,
7. installs and enables the `transport_display` systemd service,
8. installs a narrow `sudoers` rule + the `transport_display_config` web-UI service
   (port 8080).

A reboot is required for the CPU-isolation and audio changes. Verify after reboot:

```bash
cat /proc/cmdline          # contains isolcpus=3
lsmod | grep snd_bcm2835   # empty (the onboard analog audio that conflicts with
                           # the matrix PWM; HDMI audio modules may remain, that's fine)
systemctl status transport_display
journalctl -u transport_display -f
```

## Development & deployment

Develop on the dev machine; **never hand-edit code on the Pi**. Deploy by pulling:

```bash
# dev machine
git commit -am "…"
git push

# Pi
ssh pierre@kaeferpi.local 'cd ~/transport_display && git pull && sudo systemctl restart transport_display'
```

Run the tests and preview the layout on the dev machine (no hardware needed):

```bash
python -m pytest tests/
python tools/preview.py preview.png 8   # writes a scaled PNG of the layout
```

### Config web UI development

The React app is **built on the dev machine** and its `web/dist/` committed (the
Pi has no Node toolchain — it just serves the static build after a `git pull`).

```bash
# build the UI and commit the output
cd web && npm install && npm run build      # -> web/dist (committed)
```

Work on the UI with hot reload against a locally-run backend (two terminals):

```bash
# bash / macOS / Linux
pip install -r requirements-dev.txt
TRANSPORT_DISPLAY_NO_RESTART=1 python -m server   # terminal 1: backend on :8080
cd web && npm run dev                              # terminal 2: Vite proxies /api -> :8080
```

```powershell
# Windows PowerShell (env var is its own statement, no inline VAR=value prefix)
pip install -r requirements-dev.txt
$env:TRANSPORT_DISPLAY_NO_RESTART = "1"; python -m server   # terminal 1
cd web; npm run dev                                          # terminal 2
```

`TRANSPORT_DISPLAY_NO_RESTART=1` stops the dev backend trying to restart a
(non-existent) service when you save. Set `VITE_API_TARGET`
(e.g. `http://kaeferpi.local:8080`) to point `npm run dev` at the Pi instead of a
local backend.
