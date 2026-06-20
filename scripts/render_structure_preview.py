from __future__ import annotations

import os
import sys
from typing import Iterable

from PIL import Image, ImageDraw

from bedrock_nbt import read_root_compound


COLORS = {
    "air": (0, 0, 0, 0),
    "bookshelf": (196, 111, 35, 255),
    "dark_oak_planks": (78, 45, 26, 255),
    "spruce_planks": (126, 84, 45, 255),
    "deepslate_bricks": (48, 51, 58, 255),
    "deepslate_tiles": (31, 35, 43, 255),
    "stone_bricks": (116, 121, 121, 255),
    "sea_lantern": (205, 255, 243, 255),
    "glowstone": (255, 220, 84, 255),
    "shroomlight": (255, 162, 74, 255),
    "pink_stained_glass": (255, 82, 190, 230),
    "lime_stained_glass": (138, 255, 77, 230),
    "yellow_stained_glass": (255, 242, 66, 230),
    "cyan_stained_glass": (56, 232, 250, 230),
    "white_stained_glass": (255, 255, 255, 235),
    "blue_stained_glass": (58, 125, 255, 230),
    "packed_ice": (112, 199, 255, 255),
    "oxidized_copper": (54, 181, 165, 255),
    "weathered_copper": (78, 143, 128, 255),
    "gold_block": (255, 201, 36, 255),
    "moss_block": (72, 122, 58, 255),
    "azalea_leaves": (62, 151, 76, 255),
}

LIGHT_BLOCKS = {
    "sea_lantern",
    "glowstone",
    "shroomlight",
    "pink_stained_glass",
    "lime_stained_glass",
    "yellow_stained_glass",
    "cyan_stained_glass",
    "white_stained_glass",
    "blue_stained_glass",
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


def bounds(points: list[tuple[int, int, int, str]]) -> tuple[int, int, int, int, int, int]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def shade(color: tuple[int, int, int, int], factor: float) -> tuple[int, int, int, int]:
    return (
        max(0, min(255, int(color[0] * factor))),
        max(0, min(255, int(color[1] * factor))),
        max(0, min(255, int(color[2] * factor))),
        color[3],
    )


def draw_iso(points: list[tuple[int, int, int, str]], out_path: str, canvas: tuple[int, int]) -> None:
    img = Image.new("RGBA", canvas, (13, 15, 21, 255))
    draw = ImageDraw.Draw(img, "RGBA")
    min_x, max_x, min_y, max_y, min_z, max_z = bounds(points)

    def project(x: float, y: float, z: float, scale: float) -> tuple[float, float]:
        return (x - z) * scale, (x + z) * scale * 0.47 - y * scale * 0.82

    corners = [
        project(x, y, z, 1.0)
        for x in (min_x, max_x)
        for y in (min_y, max_y)
        for z in (min_z, max_z)
    ]
    proj_w = max(p[0] for p in corners) - min(p[0] for p in corners)
    proj_h = max(p[1] for p in corners) - min(p[1] for p in corners)
    scale = min((canvas[0] - 90) / max(1, proj_w), (canvas[1] - 70) / max(1, proj_h), 7.0)
    corners = [
        project(x, y, z, scale)
        for x in (min_x, max_x)
        for y in (min_y, max_y)
        for z in (min_z, max_z)
    ]
    ox = canvas[0] / 2 - (max(p[0] for p in corners) + min(p[0] for p in corners)) / 2
    oy = canvas[1] / 2 - (max(p[1] for p in corners) + min(p[1] for p in corners)) / 2

    items = sorted(points, key=lambda p: p[0] + p[2] + p[1] * 0.65)
    px_size = max(3, int(scale * 0.85))
    for x, y, z, name in items:
        px, py = project(x, y, z, scale)
        px += ox
        py += oy
        color = COLORS.get(name, (210, 210, 210, 255))
        depth = 0.78 + 0.22 * ((y - min_y) / max(1, max_y - min_y))
        if name in LIGHT_BLOCKS:
            glow = max(5, px_size + 2)
            draw.ellipse((px - glow, py - glow, px + glow, py + glow), fill=(color[0], color[1], color[2], 70))
            draw.ellipse((px - px_size, py - px_size, px + px_size, py + px_size), fill=color)
        else:
            draw.rectangle((px - px_size, py - px_size, px + px_size, py + px_size), fill=shade(color, depth))

    img.convert("RGB").save(out_path)


def draw_elevation(
    blocks: list[int],
    palette: list[str],
    size: list[int],
    out_path: str,
    axis: str,
    canvas: tuple[int, int],
) -> None:
    sx, sy, sz = size
    img = Image.new("RGBA", canvas, (13, 15, 21, 255))
    draw = ImageDraw.Draw(img, "RGBA")
    points = list(iter_non_air(blocks, palette, size))
    min_x, max_x, min_y, max_y, min_z, max_z = bounds(points)
    w = max_x - min_x + 1 if axis == "front" else max_z - min_z + 1
    h = max_y - min_y + 1
    scale = min((canvas[0] - 60) / w, (canvas[1] - 55) / h, 8.0)
    ox = (canvas[0] - w * scale) / 2
    oy = canvas[1] - 28 - (canvas[1] - 55 - h * scale) / 2

    if axis == "front":
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                chosen = 0
                chosen_z = min_z
                for z in range(max_z, min_z - 1, -1):
                    value = blocks[idx(x, y, z, sx, sz)]
                    if value > 0:
                        chosen = value
                        chosen_z = z
                        break
                if chosen:
                    name = palette[chosen]
                    depth = 0.72 + 0.28 * ((chosen_z - min_z) / max(1, max_z - min_z))
                    color = COLORS.get(name, (210, 210, 210, 255))
                    if name in LIGHT_BLOCKS:
                        color = shade(color, 1.08)
                    else:
                        color = shade(color, depth)
                    x0 = ox + (x - min_x) * scale
                    y0 = oy - (y - min_y + 1) * scale
                    draw.rectangle((x0, y0, x0 + scale, y0 + scale), fill=color)
    else:
        for y in range(min_y, max_y + 1):
            for z in range(min_z, max_z + 1):
                chosen = 0
                chosen_x = min_x
                for x in range(min_x, max_x + 1):
                    value = blocks[idx(x, y, z, sx, sz)]
                    if value > 0:
                        chosen = value
                        chosen_x = x
                        break
                if chosen:
                    name = palette[chosen]
                    depth = 0.72 + 0.28 * ((max_x - chosen_x) / max(1, max_x - min_x))
                    color = COLORS.get(name, (210, 210, 210, 255))
                    if name in LIGHT_BLOCKS:
                        color = shade(color, 1.08)
                    else:
                        color = shade(color, depth)
                    x0 = ox + (z - min_z) * scale
                    y0 = oy - (y - min_y + 1) * scale
                    draw.rectangle((x0, y0, x0 + scale, y0 + scale), fill=color)

    img.convert("RGB").save(out_path)


def draw_top(blocks: list[int], palette: list[str], size: list[int], out_path: str, canvas: tuple[int, int]) -> None:
    sx, sy, sz = size
    img = Image.new("RGBA", canvas, (13, 15, 21, 255))
    draw = ImageDraw.Draw(img, "RGBA")
    points = list(iter_non_air(blocks, palette, size))
    min_x, max_x, min_y, max_y, min_z, max_z = bounds(points)
    w = max_x - min_x + 1
    h = max_z - min_z + 1
    scale = min((canvas[0] - 70) / w, (canvas[1] - 70) / h, 8.5)
    ox = (canvas[0] - w * scale) / 2
    oy = (canvas[1] - h * scale) / 2

    # Draw every occupied layer with transparency instead of only the top block.
    # This makes the 2.5-turn rising spiral readable in plan view.
    for y in range(min_y, max_y + 1):
        height_factor = 0.55 + 0.45 * ((y - min_y) / max(1, max_y - min_y))
        for z in range(min_z, max_z + 1):
            for x in range(min_x, max_x + 1):
                value = blocks[idx(x, y, z, sx, sz)]
                if value <= 0:
                    continue
                name = palette[value]
                color = shade(COLORS.get(name, (210, 210, 210, 255)), 1.15 if name in LIGHT_BLOCKS else height_factor)
                alpha = 235 if name in LIGHT_BLOCKS else 72
                if name in ("deepslate_bricks", "deepslate_tiles", "stone_bricks"):
                    alpha = 96
                if name in ("oxidized_copper", "weathered_copper"):
                    alpha = 110
                x0 = ox + (x - min_x) * scale
                y0 = oy + (z - min_z) * scale
                draw.rectangle((x0, y0, x0 + scale, y0 + scale), fill=(color[0], color[1], color[2], alpha))

    img.convert("RGB").save(out_path)


def main() -> None:
    source = sys.argv[1] if len(sys.argv) > 1 else os.path.join("out", "inverted_library.mcstructure")
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join("out", "previews")
    os.makedirs(out_dir, exist_ok=True)
    blocks, palette, size = load_structure(source)
    points = list(iter_non_air(blocks, palette, size))
    if not points:
        raise SystemExit("No non-air blocks to render")
    draw_iso(points, os.path.join(out_dir, "iso.png"), (1300, 1050))
    draw_elevation(blocks, palette, size, os.path.join(out_dir, "front.png"), "front", (920, 980))
    draw_elevation(blocks, palette, size, os.path.join(out_dir, "side.png"), "side", (920, 980))
    draw_top(blocks, palette, size, os.path.join(out_dir, "top.png"), (920, 920))
    print(f"Wrote previews to {out_dir}")


if __name__ == "__main__":
    main()
