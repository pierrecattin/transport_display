"""LED matrix hardware I/O.

Wraps the hzeller ``rgbmatrix`` library: configures the panel, and on each
frame pushes a PIL image (built by :class:`~src.layout.FrameComposer`) to a
double-buffered ``FrameCanvas`` via ``SetImage`` + ``SwapOnVSync`` for tear-free
updates.

``rgbmatrix`` only imports on the Pi, so this module is never imported by the
dev-machine unit tests / preview tool.
"""

from __future__ import annotations

import logging

from rgbmatrix import RGBMatrix, RGBMatrixOptions

from .config import Config
from .layout import PANEL_H, PANEL_W, FrameComposer, StationGroup

log = logging.getLogger(__name__)

__all__ = ["Renderer", "StationGroup"]


class Renderer:
    def __init__(self, config: Config) -> None:
        d = config.display

        options = RGBMatrixOptions()
        options.rows = PANEL_H
        options.cols = PANEL_W
        options.chain_length = 1
        options.parallel = 1
        options.hardware_mapping = "adafruit-hat-pwm"
        options.gpio_slowdown = d.gpio_slowdown
        options.pwm_bits = d.pwm_bits
        options.pwm_lsb_nanoseconds = d.pwm_lsb_nanoseconds
        options.brightness = d.brightness
        options.drop_privileges = True  # start as root, drop after GPIO init

        # Load fonts BEFORE constructing RGBMatrix: RGBMatrix() drops privileges
        # to user 'daemon', which can't read the .bdf files under the service
        # user's home (home is not world-traversable on Bookworm/trixie).
        self.composer = FrameComposer(
            d.font, d.header_font, d.scroll_px_per_sec, config.colors
        )

        self.matrix = RGBMatrix(options=options)
        self.canvas = self.matrix.CreateFrameCanvas()

    def render(self, groups: list[StationGroup], clock_text: str, now: float) -> bool:
        """Compose and display one frame.

        Returns whether the frame contains scrolling content, so the caller
        can drop to a low idle frame rate when nothing moves.
        """
        img = self.composer.compose(groups, clock_text, now)
        self.canvas.SetImage(img, 0, 0)
        self.canvas = self.matrix.SwapOnVSync(self.canvas)
        return self.composer.scrolling

    def clear(self) -> None:
        self.matrix.Clear()
