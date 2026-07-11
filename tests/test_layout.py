"""Unit tests for the pure-PIL frame composition (no hardware needed)."""

from pathlib import Path

from src.config import Colors, load_config
from src.layout import (
    PANEL_H,
    PANEL_W,
    FrameComposer,
    StationGroup,
    _dim,
    fit_text,
    text_w,
)
from src.transport import Departure

FIXTURE_CONFIG = Path(__file__).parent / "fixtures" / "config.json"


def _composer() -> FrameComposer:
    cfg = load_config(FIXTURE_CONFIG)
    d = cfg.display
    return FrameComposer(d.font, d.header_font, d.scroll_px_per_sec, cfg.colors)


def _dep(number: str, label: str) -> Departure:
    return Departure(number=number, destination=label, label=label, departure_ts=0)


def _group(label: str, *, stale: bool = False, station_id: str = "1") -> StationGroup:
    return StationGroup(
        station_id=station_id, name="Station", departures=[(_dep("9", label), 5)], stale=stale
    )


def test_fit_text_truncates_to_width() -> None:
    c = _composer()
    long = "Strassenverkehrsamt und noch viel mehr Text"
    fitted = fit_text(c.header_font, long, 40)
    assert text_w(c.header_font, fitted) <= 40
    assert long.startswith(fitted)
    # Degenerate width -> empty, not an infinite loop.
    assert fit_text(c.header_font, long, 0) == ""


def test_compose_returns_panel_sized_frame_with_content() -> None:
    c = _composer()
    img = c.compose([_group("Bucheggplatz")], "16:32", now=0.0)
    assert img.size == (PANEL_W, PANEL_H)
    assert img.getbbox() is not None  # something was actually drawn


def test_short_label_does_not_scroll_long_label_does() -> None:
    c = _composer()
    c.compose([_group("Kurz")], "16:32", now=0.0)
    assert c.scrolling is False
    c.compose([_group("Ein sehr langer Endhaltestellenname der nie passt")], "16:32", now=0.0)
    assert c.scrolling is True


def test_scroll_offset_advances_and_wraps() -> None:
    c = _composer()
    period = 50
    first = c._scroll_offset("k", now=0.0, period=period)
    assert first == 0
    later = c._scroll_offset("k", now=0.2, period=period)
    assert 0 < later < period
    # A huge gap is clamped by MAX_DT, and the offset always stays in-period.
    assert 0 <= c._scroll_offset("k", now=1000.0, period=period) < period


def test_scroll_state_pruned_for_rows_no_longer_shown() -> None:
    c = _composer()
    long_label = "Ein sehr langer Endhaltestellenname der nie passt"
    c.compose([_group(long_label)], "16:32", now=0.0)
    assert len(c._offsets) == 1
    c.compose([_group("Kurz")], "16:32", now=0.5)
    assert c._offsets == {}


def test_stale_group_renders_dimmer() -> None:
    c = _composer()
    fresh = c.compose([_group("Bucheggplatz")], "16:32", now=0.0)
    stale = c.compose([_group("Bucheggplatz", stale=True)], "16:32", now=0.0)
    # Compare total light emitted outside the clock area (the clock never dims).
    box = (0, 8, PANEL_W, PANEL_H)
    fresh_sum = sum(sum(px) for px in fresh.crop(box).getdata())
    stale_sum = sum(sum(px) for px in stale.crop(box).getdata())
    assert 0 < stale_sum < fresh_sum


def test_dim_scales_down_but_keeps_visible() -> None:
    assert _dim((255, 100, 0)) == (102, 40, 0)
    assert _dim(Colors().clock) < Colors().clock
