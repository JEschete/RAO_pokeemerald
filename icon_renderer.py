"""Pillow rendering for species mini-icons.

Each pokeemerald species folder carries a 32x64 indexed icon.png holding two
animation frames. Only the first frame is used: it is cropped to its opaque
bounds, scaled down to a rail-friendly square, and bottom-aligned so icons of
different heights sit on a common baseline.

This module lives outside the game package because it imports Pillow; the
cache that calls it stays image-library free and receives this function.
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

ICON_SIZE = 20
FRAME_BOX = (0, 0, 32, 32)


def render_icon(source: Path, target: Path, size: int = ICON_SIZE) -> Path:
    with Image.open(source) as sheet:
        frame = sheet.convert("RGBA").crop(FRAME_BOX)
    bounds = frame.getbbox()
    if bounds is not None:
        frame = frame.crop(bounds)
    width, height = frame.size
    scale = size / max(width, height, 1)
    frame = frame.resize(
        (max(1, round(width * scale)), max(1, round(height * scale))),
        Image.NEAREST,
    )
    square = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    square.paste(frame, ((size - frame.width) // 2, size - frame.height))
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        square.save(temporary, format="PNG")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return target
