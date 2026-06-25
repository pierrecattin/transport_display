"""Pure-PIL frame composition for the 128x64 panel.

Kept free of any ``rgbmatrix`` import so the layout and scrolling can be unit
tested and previewed (as a PNG) on a dev machine without the hardware. The
hardware I/O lives in :mod:`renderer`.

Layout (grouped by station, soonest departures that fit):

    Buchegg            16:32      <- station header (left) + clock (right)
    40  Bucheggplatz       4'     <- number | dest (scrolls if long) | mins'
    Neuaffolt
    32  Strassenverkeh…    7'
    61  Strassenverkeh…   12'
"""

from __future__ import annotations

import math
import tempfile
from pathlib import Path

from PIL import BdfFontFile, Image, ImageDraw, ImageFont

from .config import Colors
from .transport import Departure

PANEL_W = 128
PANEL_H = 64

FONTS_DIR = Path(__file__).resolve().parent.parent / "fonts"
_FONT_CACHE_DIR = Path(tempfile.gettempdir()) / "transport_display_fonts"

# Render colours live in the config now (src.config.Colors); the defaults there
# match what this module used to hardcode.

SCROLL_GAP = 12  # px of blank between the looped copies of a scrolling label
ROW_PAD = 1  # px between rows
STATION_GAP = 1  # extra px between station groups
ZONE_GAP = 2  # px between number/dest/minutes zones
MAX_DT = 0.5  # clamp scroll delta so a reappearing row doesn't jump


class StationGroup:
    """A station's header label plus its visible (departure, minutes) rows."""

    def __init__(
        self, station_id: str, name: str, departures: list[tuple[Departure, int]]
    ) -> None:
        self.station_id = station_id
        self.name = name
        self.departures = departures


def load_pil_font(bdf_path: Path) -> ImageFont.ImageFont:
    """Load a .bdf bitmap font as a PIL font (pixel-perfect).

    Pillow can't read .bdf directly at draw time, so we compile it once to its
    .pil/.pbm pair in a temp cache dir and load that.
    """
    _FONT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    stem = bdf_path.stem
    pil_path = _FONT_CACHE_DIR / f"{stem}.pil"
    if not pil_path.exists():
        with open(bdf_path, "rb") as fh:
            BdfFontFile.BdfFontFile(fh).save(str(_FONT_CACHE_DIR / stem))
    return ImageFont.load(str(pil_path))


def text_w(font: ImageFont.ImageFont, text: str) -> int:
    # Pillow's stubs leave the bitmap-font (ImageFont.ImageFont) methods untyped.
    return int(math.ceil(font.getlength(text)))  # type: ignore[no-untyped-call]


def font_height(font: ImageFont.ImageFont) -> int:
    """Cell height of a bitmap font (PIL bitmap fonts have no getmetrics())."""
    bbox = font.getbbox("Agjy0123")  # type: ignore[no-untyped-call]
    return int(bbox[3] - bbox[1])


def fit_text(font: ImageFont.ImageFont, text: str, max_w: int) -> str:
    """Truncate ``text`` so it fits in ``max_w`` px (no ellipsis: BDF is Latin-1)."""
    while text and text_w(font, text) > max_w:
        text = text[:-1]
    return text


class FrameComposer:
    """Builds a 128x64 PIL frame from station groups + a clock string.

    Holds fonts, the fixed column geometry, and per-row horizontal scroll state.
    """

    def __init__(
        self,
        body_font_name: str,
        header_font_name: str,
        scroll_px_per_sec: float,
        colors: Colors | None = None,
    ):
        self.colors = colors if colors is not None else Colors()
        self.body_font = load_pil_font(FONTS_DIR / f"{body_font_name}.bdf")
        self.header_font = load_pil_font(FONTS_DIR / f"{header_font_name}.bdf")

        self.body_h = font_height(self.body_font)
        self.header_h = font_height(self.header_font)
        self.row_h = self.body_h + ROW_PAD

        # Fixed column zones so rows line up across stations.
        self.num_zone_w = text_w(self.body_font, "N99")
        self.min_zone_w = text_w(self.body_font, "99'")
        self.dest_x0 = self.num_zone_w + ZONE_GAP
        self.dest_col_w = PANEL_W - self.min_zone_w - ZONE_GAP - self.dest_x0

        self.scroll_px_per_sec = scroll_px_per_sec
        # key -> (offset_px, last_wall_time) for continuous scrolling.
        self._offsets: dict[str, tuple[float, float]] = {}

    def compose(self, groups: list[StationGroup], clock_text: str, now: float) -> Image.Image:
        img = Image.new("RGB", (PANEL_W, PANEL_H))
        draw = ImageDraw.Draw(img)

        clock_w = text_w(self.header_font, clock_text)
        clock_x = PANEL_W - clock_w

        seen: set[str] = set()
        y = 0
        for group in groups:
            if y + self.header_h > PANEL_H:
                break
            # First header shares the top row with the clock; clip it short.
            header_max = (clock_x - ZONE_GAP) if y == 0 else PANEL_W
            header = fit_text(self.header_font, group.name, max(0, header_max))
            draw.text((0, y), header, font=self.header_font, fill=self.colors.header)
            y += self.header_h + ROW_PAD

            filled = False
            for dep, mins in group.departures:
                if y + self.row_h > PANEL_H:
                    filled = True
                    break
                key = f"{group.station_id}|{dep.number}|{dep.label}"
                seen.add(key)
                self._draw_row(img, draw, y, dep, mins, key, now)
                y += self.row_h
            if filled:
                break  # screen is full -> stop adding stations
            y += STATION_GAP

        # Clock drawn last so nothing overlaps it.
        draw.text((clock_x, 0), clock_text, font=self.header_font, fill=self.colors.clock)

        # Forget scroll state for rows no longer shown (bounds the dict).
        self._offsets = {k: v for k, v in self._offsets.items() if k in seen}
        return img

    def _draw_row(
        self,
        img: Image.Image,
        draw: ImageDraw.ImageDraw,
        y: int,
        dep: Departure,
        mins: int,
        key: str,
        now: float,
    ) -> None:
        # Bus number, left, uncropped.
        draw.text((0, y), dep.number, font=self.body_font, fill=self.colors.number)

        # Minutes, right-aligned, uncropped, Swiss "7'" notation.
        mins_text = f"{mins}'"
        mins_w = text_w(self.body_font, mins_text)
        draw.text((PANEL_W - mins_w, y), mins_text, font=self.body_font, fill=self.colors.minutes)

        # Destination, clipped to its column, scrolling if too wide.
        self._draw_dest(img, draw, self.dest_x0, y, dep.label, key, now)

    def _draw_dest(
        self,
        img: Image.Image,
        draw: ImageDraw.ImageDraw,
        x0: int,
        y: int,
        text: str,
        key: str,
        now: float,
    ) -> None:
        w = text_w(self.body_font, text)
        col_w = self.dest_col_w
        if w <= col_w:
            draw.text((x0, y), text, font=self.body_font, fill=self.colors.dest)
            return

        period = w + SCROLL_GAP
        off = self._scroll_offset(key, now, period)
        col = Image.new("RGB", (col_w, self.row_h))
        cd = ImageDraw.Draw(col)
        cd.text((-off, 0), text, font=self.body_font, fill=self.colors.dest)
        cd.text((-off + period, 0), text, font=self.body_font, fill=self.colors.dest)
        img.paste(col, (x0, y))

    def _scroll_offset(self, key: str, now: float, period: int) -> int:
        off, last = self._offsets.get(key, (0.0, now))
        dt = min(max(0.0, now - last), MAX_DT)
        off = (off + self.scroll_px_per_sec * dt) % period
        self._offsets[key] = (off, now)
        return int(off)
