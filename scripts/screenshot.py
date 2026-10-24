#!/usr/bin/env python3
"""Render the rot demo dashboard to an SVG screenshot.

Textual's ``save_screenshot`` produces an SVG that preserves fonts, colors and
the terminal grid, which makes it a good fit for README images.  If Chrome or
Chromium is installed, ``--png`` also rasterizes that SVG at its native size.

Examples:
    .venv/bin/python scripts/screenshot.py
    .venv/bin/python scripts/screenshot.py --size 120x36 --output /tmp/rot.svg
    .venv/bin/python scripts/screenshot.py --png screenshots/rot-demo.png
"""

from __future__ import annotations

import argparse
import asyncio
import re
import shutil
import subprocess
import sys
from pathlib import Path

from rot.app import RotApp
from rot.demo import demo_snapshot

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "screenshots" / "rot-demo.svg"
CHROME_CANDIDATES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")


def _parse_size(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d+)\s*[x×]\s*(\d+)\s*", value)
    if not match:
        raise argparse.ArgumentTypeError("size must look like 150x48")
    width, height = (int(part) for part in match.groups())
    if width < 60 or height < 20:
        raise argparse.ArgumentTypeError("size must be at least 60x20")
    return width, height


def _chrome() -> str | None:
    for name in CHROME_CANDIDATES:
        binary = shutil.which(name)
        if binary:
            return binary
    return None


def _rasterize(svg: Path, png: Path) -> None:
    chrome = _chrome()
    if chrome is None:
        raise SystemExit("google-chrome or chromium not found; cannot write a PNG")
    view_box = re.search(r'viewBox="0 0 ([\d.]+) ([\d.]+)"', svg.read_text(encoding="utf-8"))
    if not view_box:
        raise SystemExit(f"could not read the SVG viewBox from {svg}")
    width, height = (int(float(part)) + 1 for part in view_box.groups())
    png.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            chrome,
            "--headless",
            "--disable-gpu",
            "--no-sandbox",
            "--hide-scrollbars",
            f"--window-size={width},{height}",
            f"--screenshot={png}",
            svg.resolve().as_uri(),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


async def capture(
    output: Path,
    *,
    width: int,
    height: int,
    settle: int = 4,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    app = RotApp(demo_snapshot(), demo=True)
    async with app.run_test(size=(width, height)) as pilot:
        for _ in range(max(1, settle)):
            await pilot.pause()
        app.save_screenshot(filename=output.name, path=str(output.parent))
    return output


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--size",
        type=_parse_size,
        default=(150, 48),
        metavar="WxH",
        help="terminal size to capture (default: 150x48)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"SVG destination (default: {DEFAULT_OUTPUT.relative_to(ROOT)})",
    )
    parser.add_argument(
        "--settle",
        type=int,
        default=4,
        help="layout passes to wait through before capturing (default: 4)",
    )
    parser.add_argument(
        "--png",
        type=Path,
        metavar="PATH",
        help="also rasterize the SVG with headless Chrome",
    )
    args = parser.parse_args(argv)

    output = args.output
    if output.suffix.lower() != ".svg":
        parser.error("--output must end in .svg (Textual always writes SVG)")
    width, height = args.size
    asyncio.run(capture(output, width=width, height=height, settle=args.settle))
    print(f"wrote {output}")
    if args.png:
        _rasterize(output, args.png)
        print(f"wrote {args.png}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
