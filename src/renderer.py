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

from rgbmatrix import RGBMatrix, RGBMatrixOptions  # type: ignore

from .config import Config
from .layout import FrameComposer, StationGroup

log = logging.getLogger(__name__)

__all__ = ["Renderer", "StationGroup"]


class Renderer:
    def __init__(self, config: Config) -> None:
        d = config.display

        options = RGBMatrixOptions()
        options.rows = 64
        options.cols = 128
        options.chain_length = 1
        options.parallel = 1
        options.hardware_mapping = "adafruit-hat-pwm"
        options.gpio_slowdown = d.gpio_slowdown
        options.pwm_bits = d.pwm_bits
        options.pwm_lsb_nanoseconds = d.pwm_lsb_nanoseconds
        options.brightness = d.brightness
        options.drop_privileges = True  # start as root, drop after GPIO init

        self.matrix = RGBMatrix(options=options)
        self.canvas = self.matrix.CreateFrameCanvas()
        self.composer = FrameComposer(d.font, d.header_font, d.scroll_px_per_sec)

    def render(self, groups: list[StationGroup], clock_text: str, now: float) -> None:
        """Compose and display one frame."""
        img = self.composer.compose(groups, clock_text, now)
        self.canvas.SetImage(img, 0, 0)
        self.canvas = self.matrix.SwapOnVSync(self.canvas)

    def clear(self) -> None:
        self.matrix.Clear()
