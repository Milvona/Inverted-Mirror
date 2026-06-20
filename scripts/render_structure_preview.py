from __future__ import annotations

import math
import os
import sys
from typing import Iterable

from PIL import Image, ImageDraw

from bedrock_nbt import read_root_compound


COLORS = {
    "air": (0, 0, 0, 0),
    "bookshelf": (181, 103, 35, 255),
    "dark_oak_planks": (88, 54, 32, 255),
    "spruce_planks": (116, 79, 45, 255),
    "deepslate_bricks": (48, 51, 57, 255),
    "deepslate_tiles": (34, 38, 45, 255),
    "stone_bricks": (105, 111, 111, 255),
    "sea_lantern": (192, 255, 236, 255),
    "glowstone": (255, 214, 91, 255),
    "shroomlight": (245, 167, 76, 255),
    "pink_stained_glass": (255, 98, 190, 210),
    "lime_stained_glass": (149, 255, 80, 210),
    "yellow_stained_glass": (255, 240, 82, 210),
    "cyan_stained_glass": (62, 224, 241, 210),
    "white_stained_glass": (255, 255, 255, 220),
    "blue_stained_glass": (54, 118, 255, 215),
    "packed_ice": (107, 190, 255, 255),
    "oxidized_copper": (68, 164, 151, 255),
    "weathered_copper": (86, 142, 126, 255),
    "gold_block": (255, 200, 38, 255),
    "moss_block": (72, 120, 58, 255),
    "azalea_leaves": (66, 145, 72, 255),
}


def load_structure(path: str) -> tuple[list[int], list[str], list[int]]:
    root = read_root_compound(path)
    size = root["size"]
    structure = root["structure"]
    blocks = structure["block_indices"][0]
    palette = [
        entry["name"].split("minecraft:", 1)[-1]
        for entry in structure["palette"]["default"]["block_palette"]
    ]
    return blocks, palette, size


def idx(x: int, y: int, z: int, sx: int, sz: int) -> int:
    return x + z * sx + y * sx * sz


def iter_non_air(blocks: list[int], palette: list[str], size: list[int]) -> Iterable[tuple[int, int, int, str]]:
    sx, sy, sz = size
    for y in range(sy):
        base_y = y * sx * sz
        for z in range(sz):
            base = base_y + z * sx
            for x in range(sx):
                palette_id = blocks[base + x]
                if palette_id > 0:
                    yield x, y, z, palette[palette_id]


def shade(color: tuple[int, int, int, int], factor: float) -> tuple[int, int, int, int]:
    return (
        min(255, int(color[0] * factor)),
        min(255, int(color[1] * factor)),
        min(255, int(color[2] * factor)),
        color[3],
    )


def draw_projected(
    blocks: list[int],
    palette: list[str],
    size: list[int],
    out_path: str,
    mode: str,
    canvas: tuple[int, int],
) -> None:
    sx, sy, sz = size
    img = Image.new("RGBA", canvas, (15, 17, 22, 255))
    draw = ImageDraw.Draw(img, "RGBA")

    if mode == "iso":
        scale = 6
        ox = canvas[0] // 2
        oy = 250
        items = sorted(iter_non_air(blocks, palette, size), key=lambda p: p[0] + p[2] + p[1])
        for x, y, z, name in items:
            px = ox + (x - z) * scale
            py = oy + (x + z) * scale * 0.45 - y * scale * 0.72
            color = COLORS.get(name, (200, 200, 200, 255))
            if name.endswith("stained_glass") or name in ("sea_lantern", "glowstone", "shroomlight"):
                draw.ellipse((px - 4, py - 4, px + 4, py + 4), fill=color)
            else:
                draw.rectangle((px - 3, py - 3, px + 3, py + 3), fill=shade(color, 0.92 + min(0.18, y / sy * 0.18)))
    elif mode == "front":
        scale = 7
        ox = (canvas[0] - sx * scale) // 2
        oy = canvas[1] - 28
        for y in range(sy):
            for x in range(sx):
                chosen = 0
                for z in range(sz - 1, -1, -1):
                    value = blocks[idx(x, y, z, sx, sz)]
                    if value > 0:
                        chosen = value
                        break
                if chosen:
                    color = COLORS.get(palette[chosen], (200, 200, 200, 255))
                    x0 = ox + x * scale
                    y0 = oy - (y + 1) * scale + 1
                    x1 = ox + (x + 1) * scale - 1
                    y1 = oy - y * scale
                    draw.rectangle((x0, y0, x1, y1), fill=color)
    elif mode == "side":
        scale = 7
        ox = (canvas[0] - sz * scale) // 2
        oy = canvas[1] - 28
        for y in range(sy):
            for z in range(sz):
                chosen = 0
                for x in range(sx):
                    value = blocks[idx(x, y, z, sx, sz)]
                    if value > 0:
                        chosen = value
                        break
                if chosen:
                    color = COLORS.get(palette[chosen], (200, 200, 200, 255))
                    x0 = ox + z * scale
                    y0 = oy - (y + 1) * scale + 1
                    x1 = ox + (z + 1) * scale - 1
                    y1 = oy - y * scale
                    draw.rectangle((x0, y0, x1, y1), fill=color)
    elif mode == "top":
        scale = 7
        ox = (canvas[0] - sx * scale) // 2
        oy = (canvas[1] - sz * scale) // 2
        for z in range(sz):
            for x in range(sx):
                chosen = 0
                top_y = 0
                for y in range(sy - 1, -1, -1):
                    value = blocks[idx(x, y, z, sx, sz)]
                    if value > 0:
                        chosen = value
                        top_y = y
                        break
                if chosen:
                    color = shade(COLORS.get(palette[chosen], (200, 200, 200, 255)), 0.76 + 0.24 * top_y / sy)
                    draw.rectangle((ox + x * scale, oy + z * scale, ox + (x + 1) * scale - 1, oy + (z + 1) * scale - 1), fill=color)
    else:
        raise ValueError(f"Unknown render mode: {mode}")

    img.convert("RGB").save(out_path)


def main() -> None:
    source = sys.argv[1] if len(sys.argv) > 1 else os.path.join("out", "inverted_library.mcstructure")
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join("out", "previews")
    os.makedirs(out_dir, exist_ok=True)
    blocks, palette, size = load_structure(source)
    draw_projected(blocks, palette, size, os.path.join(out_dir, "iso.png"), "iso", (1200, 1000))
    draw_projected(blocks, palette, size, os.path.join(out_dir, "front.png"), "front", (820, 940))
    draw_projected(blocks, palette, size, os.path.join(out_dir, "side.png"), "side", (820, 940))
    draw_projected(blocks, palette, size, os.path.join(out_dir, "top.png"), "top", (820, 820))
    print(f"Wrote previews to {out_dir}")


if __name__ == "__main__":
    main()
