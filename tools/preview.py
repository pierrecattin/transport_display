"""Render the panel layout to a PNG on a dev machine (no hardware needed).

    python tools/preview.py [out.png] [scale]

Uses src.layout.FrameComposer with representative data so you can eyeball the
clock, per-station headers, bus numbers, scrolling destinations and minutes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config  # noqa: E402
from src.layout import FrameComposer, StationGroup  # noqa: E402
from src.transport import Departure  # noqa: E402


def _dep(number: str, label: str) -> Departure:
    # The preview only draws number + label; the destination just needs to be
    # unique per row, so reuse the label.
    return Departure(number=number, destination=label, label=label, departure_ts=0)


ROOT = Path(__file__).resolve().parent.parent
PREVIEW_DIR = ROOT / "preview"


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else PREVIEW_DIR / "preview.png"
    scale = int(sys.argv[2]) if len(sys.argv) > 2 else 8

    out.parent.mkdir(parents=True, exist_ok=True)

    # Use the repo config's fonts + colours so the preview reflects edits.
    # The live config.json is untracked; fresh checkouts fall back to the example.
    cfg_path = ROOT / "config.json"
    if not cfg_path.exists():
        cfg_path = ROOT / "config.example.json"
    cfg = load_config(cfg_path)
    d = cfg.display
    composer = FrameComposer(d.font, d.header_font, d.scroll_px_per_sec, cfg.colors)
    groups = [
        StationGroup("8591041", "Buchegg", [(_dep("40", "Bucheggplatz"), 4)]),
        StationGroup(
            "8591285",
            "Neuaffoltern",
            [
                (_dep("32", "Strassenverkehrsamt"), 7),
                (_dep("61", "Strassenverkehrsamt"), 12),
                (_dep("62", "Wallisellen"), 15),
            ],
        ),
    ]

    img = composer.compose(groups, "16:32", now=2.0)  # now>0 -> some scroll offset
    big = img.resize((img.width * scale, img.height * scale), resample=0)  # nearest
    big.save(out)
    print(f"Wrote {out} ({img.width}x{img.height} scaled x{scale})")


if __name__ == "__main__":
    main()
