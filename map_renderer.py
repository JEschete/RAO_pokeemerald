from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


TILE_SIZE = 8
METATILE_SIZE = 16
TILES_PER_ROW = 16
NUM_TILES_IN_PRIMARY = 512
NUM_METATILES_IN_PRIMARY = 512
NUM_PALS_IN_PRIMARY = 6
METATILE_ID_MASK = 0x03FF
QUADRANTS = ((0, 0), (8, 0), (0, 8), (8, 8))


@dataclass(frozen=True, slots=True)
class Tileset:
    """One decompiled Emerald tileset: 8x8 tiles, 16x16 metatiles, palettes."""

    tiles: tuple[bytes, ...]
    metatiles: bytes
    attributes: bytes
    palettes: tuple[tuple[tuple[int, int, int], ...], ...]

    @property
    def metatile_count(self) -> int:
        return len(self.metatiles) // 16


def load_palette(path: Path) -> tuple[tuple[int, int, int], ...]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "JASC-PAL":
        raise ValueError(f"Not a JASC palette: {path}")
    colors = []
    for line in lines[3:]:
        parts = line.split()
        if len(parts) < 3:
            continue
        colors.append((int(parts[0]), int(parts[1]), int(parts[2])))
    if not colors:
        raise ValueError(f"Palette has no colors: {path}")
    return tuple(colors)


def _load_tiles(path: Path) -> tuple[bytes, ...]:
    image = Image.open(path)
    if image.mode != "P":
        image = image.convert("P")
    width, height = image.size
    data = image.tobytes()
    columns = width // TILE_SIZE
    tiles = []
    for index in range(columns * (height // TILE_SIZE)):
        left = (index % columns) * TILE_SIZE
        top = (index // columns) * TILE_SIZE
        tile = bytearray(TILE_SIZE * TILE_SIZE)
        for y in range(TILE_SIZE):
            start = (top + y) * width + left
            tile[y * TILE_SIZE:(y + 1) * TILE_SIZE] = data[start:start + TILE_SIZE]
        tiles.append(bytes(tile))
    return tuple(tiles)


def load_tileset(directory: Path) -> Tileset:
    palette_dir = directory / "palettes"
    palettes = []
    for index in range(16):
        path = palette_dir / f"{index:02d}.pal"
        palettes.append(load_palette(path) if path.is_file() else ((0, 0, 0),) * 16)
    return Tileset(
        _load_tiles(directory / "tiles.png"),
        (directory / "metatiles.bin").read_bytes(),
        (directory / "metatile_attributes.bin").read_bytes(),
        tuple(palettes),
    )


def _tile_pixels(tile: bytes, x_flip: bool, y_flip: bool) -> bytes:
    if not x_flip and not y_flip:
        return tile
    rows = [tile[y * TILE_SIZE:(y + 1) * TILE_SIZE] for y in range(TILE_SIZE)]
    if y_flip:
        rows.reverse()
    if x_flip:
        rows = [row[::-1] for row in rows]
    return b"".join(rows)


def render_metatile(
    canvas: bytearray,
    stride: int,
    origin_x: int,
    origin_y: int,
    metatile_id: int,
    primary: Tileset,
    secondary: Tileset,
) -> None:
    """Composite one 16x16 metatile: bottom layer opaque, top layer keyed on index 0."""
    if metatile_id < NUM_METATILES_IN_PRIMARY:
        source, base = primary, metatile_id
    else:
        source, base = secondary, metatile_id - NUM_METATILES_IN_PRIMARY
    offset = base * 16
    entries = source.metatiles[offset:offset + 16]
    if len(entries) < 16:
        return
    for slot in range(8):
        entry = entries[slot * 2] | (entries[slot * 2 + 1] << 8)
        tile_id = entry & 0x03FF
        x_flip = bool(entry & 0x0400)
        y_flip = bool(entry & 0x0800)
        palette_id = (entry >> 12) & 0x0F
        if tile_id < NUM_TILES_IN_PRIMARY:
            tiles = primary.tiles
            index = tile_id
        else:
            tiles = secondary.tiles
            index = tile_id - NUM_TILES_IN_PRIMARY
        if index >= len(tiles):
            continue
        palette_source = primary if palette_id < NUM_PALS_IN_PRIMARY else secondary
        palette = palette_source.palettes[palette_id]
        pixels = _tile_pixels(tiles[index], x_flip, y_flip)
        quad_x, quad_y = QUADRANTS[slot & 3]
        transparent = slot >= 4
        for y in range(TILE_SIZE):
            row = (origin_y + quad_y + y) * stride
            for x in range(TILE_SIZE):
                color_index = pixels[y * TILE_SIZE + x]
                if transparent and color_index == 0:
                    continue
                red, green, blue = palette[color_index % len(palette)]
                target = (row + origin_x + quad_x + x) * 3
                canvas[target] = red
                canvas[target + 1] = green
                canvas[target + 2] = blue


def render_layout(
    blocks: bytes,
    width: int,
    height: int,
    primary: Tileset,
    secondary: Tileset,
    output: Path,
) -> Path:
    """Render a decompiled map.bin blockdata grid to a PNG."""
    if width <= 0 or height <= 0:
        raise ValueError("Emerald map layout needs a positive size")
    if len(blocks) < width * height * 2:
        raise ValueError(
            f"Emerald blockdata is short: expected {width * height * 2} bytes, "
            f"got {len(blocks)}"
        )
    stride = width * METATILE_SIZE
    canvas = bytearray(stride * height * METATILE_SIZE * 3)
    for index in range(width * height):
        block = blocks[index * 2] | (blocks[index * 2 + 1] << 8)
        render_metatile(
            canvas,
            stride,
            (index % width) * METATILE_SIZE,
            (index // width) * METATILE_SIZE,
            block & METATILE_ID_MASK,
            primary,
            secondary,
        )
    image = Image.frombytes(
        "RGB", (stride, height * METATILE_SIZE), bytes(canvas)
    )
    _save_png(image, output)
    return output

REGION_COLS = 32
REGION_ROWS = 20
REGION_TILE = 8


def render_region_map(root: Path, output: Path, scale: int = 3) -> Path:
    """Compose the Pokedex region map from its tileset and tilemap."""
    graphics = root / "graphics" / "pokedex"
    source = Image.open(graphics / "region_map.png")
    palette_bytes = source.getpalette() or []
    palette = [
        tuple(palette_bytes[index * 3 : index * 3 + 3]) for index in range(256)
    ]
    if len(palette) < 256:
        raise ValueError("Region map palette is incomplete")
    tilemap = (graphics / "region_map.bin").read_bytes()
    pixels = source.tobytes()
    width = source.size[0]
    columns = width // REGION_TILE

    def tile_rows(tile_id: int) -> list[bytes]:
        left = (tile_id % columns) * REGION_TILE
        top = (tile_id // columns) * REGION_TILE
        return [
            pixels[(top + y) * width + left : (top + y) * width + left + REGION_TILE]
            for y in range(REGION_TILE)
        ]

    image = Image.new("RGB", (REGION_COLS * REGION_TILE, REGION_ROWS * REGION_TILE))
    target = image.load()
    for row in range(REGION_ROWS):
        for column in range(REGION_COLS):
            offset = (row * REGION_COLS + column) * 2
            if offset + 1 >= len(tilemap):
                continue
            entry = tilemap[offset] | (tilemap[offset + 1] << 8)
            rows = tile_rows(entry & 0x03FF)
            if entry & 0x0800:
                rows = rows[::-1]
            for y in range(REGION_TILE):
                line = rows[y][::-1] if entry & 0x0400 else rows[y]
                for x in range(REGION_TILE):
                    target[
                        column * REGION_TILE + x, row * REGION_TILE + y
                    ] = palette[line[x]]
    if scale > 1:
        image = image.resize(
            (image.width * scale, image.height * scale), Image.NEAREST
        )
    _save_png(image, output)
    return output


def _save_png(image: Image.Image, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        image.save(temporary, format="PNG", optimize=True)
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
