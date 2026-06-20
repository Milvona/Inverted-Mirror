from __future__ import annotations

import os
import sys
from typing import Iterable

from PIL import Image, ImageDraw

from bedrock_nbt import read_root_compound
from coordinate_order import coords_from_mc_index, mc_index


COLORS = {
    "air": (0, 0, 0, 0),
    "bookshelf": (202, 112, 32, 255),
    "dark_oak_planks": (83, 48, 27, 255),
    "spruce_planks": (130, 84, 43, 255),
    "dark_oak_log": (57, 35, 23, 255),
    "deepslate_bricks": (68, 72, 80, 255),
    "deepslate_tiles": (48, 54, 64, 255),
    "stone_bricks": (136, 140, 136, 255),
    "iron_bars": (166, 168, 160, 255),
    "sea_lantern": (214, 255, 244, 255),
    "glowstone": (255, 224, 83, 255),
    "shroomlight": (255, 163, 72, 255),
    "pink_stained_glass": (255, 75, 188, 238),
    "lime_stained_glass": (137, 255, 75, 238),
    "yellow_stained_glass": (255, 244, 60, 238),
    "cyan_stained_glass": (50, 232, 252, 238),
    "white_stained_glass": (255, 255, 255, 242),
    "blue_stained_glass": (58, 128, 255, 236),
    "packed_ice": (117, 205, 255, 255),
    "oxidized_copper": (42, 196, 176, 255),
    "weathered_copper": (88, 163, 142, 255),
    "cut_copper": (178, 107, 55, 255),
    "gold_block": (255, 202, 36, 255),
    "moss_block": (75, 123, 58, 255),
    "azalea_leaves": (64, 151, 76, 255),
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
    structure = root["structure"]
    palette = [entry["name"].split("minecraft:", 1)[-1] for entry in structure["palette"]["default"]["block_palette"]]
    return structure["block_indices"][0], palette, root["size"]


def idx(x: int, y: int, z: int, sx: int, sy: int, sz: int) -> int:
    return mc_index(x, y, z, sx, sy, sz)


def iter_non_air(blocks: list[int], palette: list[str], size: list[int]) -> Iterable[tuple[int, int, int, str]]:
    sx, sy, sz = size
    for i, v in enumerate(blocks):
        if v > 0:
            x, y, z = coords_from_mc_index(i, sx, sy, sz)
            yield x, y, z, palette[v]


def shade(color: tuple[int, int, int, int], factor: float) -> tuple[int, int, int, int]:
    return (
        max(0, min(255, int(color[0] * factor))),
        max(0, min(255, int(color[1] * factor))),
        max(0, min(255, int(color[2] * factor))),
        color[3],
    )


def bounds(points: list[tuple[int, int, int, str]]) -> tuple[int, int, int, int, int, int]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    zs = [p[2] for p in points]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


BG = (13, 15, 21, 255)


def save_fitted(img: Image.Image, out_path: str, canvas: tuple[int, int], fill: float = 0.88) -> None:
    px = img.load()
    min_x, min_y = img.size
    max_x = max_y = -1
    for y in range(img.size[1]):
        for x in range(img.size[0]):
            if px[x, y] != BG:
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
    if max_x < 0:
        img.convert("RGB").save(out_path)
        return
    pad = 18
    crop = img.crop((
        max(0, min_x - pad),
        max(0, min_y - pad),
        min(img.size[0], max_x + pad + 1),
        min(img.size[1], max_y + pad + 1),
    ))
    scale = min(canvas[0] * fill / crop.size[0], canvas[1] * fill / crop.size[1])
    resized = crop.resize((max(1, int(crop.size[0] * scale)), max(1, int(crop.size[1] * scale))), Image.Resampling.LANCZOS)
    fitted = Image.new("RGBA", canvas, BG)
    fitted.alpha_composite(resized, ((canvas[0] - resized.size[0]) // 2, (canvas[1] - resized.size[1]) // 2))
    fitted.convert("RGB").save(out_path)


def draw_iso_voxels(
    points: list[tuple[int, int, int, str]],
    out_path: str,
    canvas: tuple[int, int],
    cutaway: bool = False,
    fill: float = 0.88,
    max_scale: float = 8.0,
) -> None:
    if cutaway:
        points = [
            p for p in points
            if not (p[2] > 68 and 40 <= p[1] <= 112 and 45 <= p[0] <= 83 and p[3] not in LIGHT_BLOCKS)
        ]
    min_x, max_x, min_y, max_y, min_z, max_z = bounds(points)

    def project(x: float, y: float, z: float, s: float) -> tuple[float, float]:
        return (x - z) * s, (x + z) * s * 0.5 - y * s

    corners = [project(x, y, z, 1.0) for x in (min_x, max_x) for y in (min_y, max_y) for z in (min_z, max_z)]
    raw_w = max(p[0] for p in corners) - min(p[0] for p in corners)
    raw_h = max(p[1] for p in corners) - min(p[1] for p in corners)
    scale = min((canvas[0] * fill) / max(1, raw_w), (canvas[1] * fill) / max(1, raw_h), max_scale)
    corners = [project(x, y, z, scale) for x in (min_x, max_x) for y in (min_y, max_y) for z in (min_z, max_z)]
    ox = canvas[0] / 2 - (max(p[0] for p in corners) + min(p[0] for p in corners)) / 2
    oy = canvas[1] / 2 - (max(p[1] for p in corners) + min(p[1] for p in corners)) / 2

    img = Image.new("RGBA", canvas, BG)
    draw = ImageDraw.Draw(img, "RGBA")
    s = scale
    h = s
    items = sorted(points, key=lambda p: (p[0] + p[2], p[1], p[2]))
    for x, y, z, name in items:
        px, py = project(x, y, z, s)
        px += ox
        py += oy
        top = [(px, py - h), (px + s, py - h / 2), (px, py), (px - s, py - h / 2)]
        left = [(px - s, py - h / 2), (px, py), (px, py + h), (px - s, py + h / 2)]
        right = [(px, py), (px + s, py - h / 2), (px + s, py + h / 2), (px, py + h)]
        base = COLORS.get(name, (210, 210, 210, 255))
        if name in LIGHT_BLOCKS:
            glow = int(max(4, s * 1.4))
            draw.ellipse((px - glow, py - glow, px + glow, py + glow), fill=(base[0], base[1], base[2], 42))
            top_c = shade(base, 1.18)
            left_c = shade(base, 0.96)
            right_c = shade(base, 1.05)
        else:
            top_c = shade(base, 1.08)
            left_c = shade(base, 0.72)
            right_c = shade(base, 0.88)
        draw.polygon(left, fill=left_c)
        draw.polygon(right, fill=right_c)
        draw.polygon(top, fill=top_c)
    save_fitted(img, out_path, canvas, fill)


def draw_elevation(blocks: list[int], palette: list[str], size: list[int], out_path: str, mode: str, canvas: tuple[int, int]) -> None:
    sx, sy, sz = size
    pts = list(iter_non_air(blocks, palette, size))
    min_x, max_x, min_y, max_y, min_z, max_z = bounds(pts)
    w = max_x - min_x + 1 if mode == "front" else max_z - min_z + 1
    h = max_y - min_y + 1
    scale = min((canvas[0] - 60) / w, (canvas[1] - 60) / h, 7.0)
    ox = (canvas[0] - w * scale) / 2
    oy = canvas[1] - 30 - (canvas[1] - 60 - h * scale) / 2
    img = Image.new("RGBA", canvas, BG)
    draw = ImageDraw.Draw(img, "RGBA")
    if mode == "front":
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                chosen = 0
                depth = 0.8
                for z in range(max_z, min_z - 1, -1):
                    v = blocks[idx(x, y, z, sx, sy, sz)]
                    if v > 0:
                        chosen = v
                        depth = 0.68 + 0.32 * ((z - min_z) / max(1, max_z - min_z))
                        break
                if chosen:
                    name = palette[chosen]
                    factor = 1.15 if name in LIGHT_BLOCKS else depth
                    color = shade(COLORS.get(name, (210, 210, 210, 255)), factor)
                    x0 = ox + (x - min_x) * scale
                    y0 = oy - (y - min_y + 1) * scale
                    draw.rectangle((x0, y0, x0 + scale, y0 + scale), fill=color)
    else:
        for y in range(min_y, max_y + 1):
            for z in range(min_z, max_z + 1):
                chosen = 0
                depth = 0.8
                for x in range(min_x, max_x + 1):
                    v = blocks[idx(x, y, z, sx, sy, sz)]
                    if v > 0:
                        chosen = v
                        depth = 0.68 + 0.32 * ((max_x - x) / max(1, max_x - min_x))
                        break
                if chosen:
                    name = palette[chosen]
                    factor = 1.15 if name in LIGHT_BLOCKS else depth
                    color = shade(COLORS.get(name, (210, 210, 210, 255)), factor)
                    x0 = ox + (z - min_z) * scale
                    y0 = oy - (y - min_y + 1) * scale
                    draw.rectangle((x0, y0, x0 + scale, y0 + scale), fill=color)
    save_fitted(img, out_path, canvas, 0.92)


def draw_top(blocks: list[int], palette: list[str], size: list[int], out_path: str, canvas: tuple[int, int]) -> None:
    sx, sy, sz = size
    pts = list(iter_non_air(blocks, palette, size))
    min_x, max_x, min_y, max_y, min_z, max_z = bounds(pts)
    w = max_x - min_x + 1
    h = max_z - min_z + 1
    scale = min((canvas[0] - 70) / w, (canvas[1] - 70) / h, 7.5)
    ox = (canvas[0] - w * scale) / 2
    oy = (canvas[1] - h * scale) / 2
    img = Image.new("RGBA", canvas, BG)
    draw = ImageDraw.Draw(img, "RGBA")
    for y in range(min_y, max_y + 1):
        hf = 0.58 + 0.42 * ((y - min_y) / max(1, max_y - min_y))
        for z in range(min_z, max_z + 1):
            for x in range(min_x, max_x + 1):
                v = blocks[idx(x, y, z, sx, sy, sz)]
                if v <= 0:
                    continue
                name = palette[v]
                color = shade(COLORS.get(name, (210, 210, 210, 255)), 1.18 if name in LIGHT_BLOCKS else hf)
                alpha = 230 if name in LIGHT_BLOCKS else 68
                if name in ("deepslate_bricks", "deepslate_tiles", "stone_bricks"):
                    alpha = 95
                x0 = ox + (x - min_x) * scale
                y0 = oy + (z - min_z) * scale
                draw.rectangle((x0, y0, x0 + scale, y0 + scale), fill=(color[0], color[1], color[2], alpha))
    save_fitted(img, out_path, canvas, 0.92)


def draw_interior_top(
    blocks: list[int],
    palette: list[str],
    size: list[int],
    out_path: str,
    walk_y: int,
    canvas: tuple[int, int],
) -> None:
    sx, sy, sz = size
    cx, cz = sx // 2, sz // 2
    min_x, max_x = cx - 34, cx + 34
    min_z, max_z = cz - 34, cz + 34
    min_y, max_y = walk_y, walk_y + 8
    w = max_x - min_x + 1
    h = max_z - min_z + 1
    scale = min((canvas[0] - 70) / w, (canvas[1] - 70) / h)
    ox = (canvas[0] - w * scale) / 2
    oy = (canvas[1] - h * scale) / 2
    img = Image.new("RGBA", canvas, BG)
    draw = ImageDraw.Draw(img, "RGBA")
    for y in range(min_y, max_y + 1):
        hf = 0.75 + 0.25 * ((y - min_y) / max(1, max_y - min_y))
        for z in range(min_z, max_z + 1):
            for x in range(min_x, max_x + 1):
                if not (0 <= x < sx and 0 <= y < sy and 0 <= z < sz):
                    continue
                v = blocks[idx(x, y, z, sx, sy, sz)]
                if v <= 0:
                    continue
                name = palette[v]
                color = shade(COLORS.get(name, (210, 210, 210, 255)), 1.15 if name in LIGHT_BLOCKS else hf)
                alpha = 240 if name in LIGHT_BLOCKS else 150
                if y == min_y:
                    alpha = 230
                x0 = ox + (x - min_x) * scale
                y0 = oy + (z - min_z) * scale
                draw.rectangle((x0, y0, x0 + scale, y0 + scale), fill=(color[0], color[1], color[2], alpha))
    save_fitted(img, out_path, canvas, 0.94)


def main() -> None:
    source = sys.argv[1] if len(sys.argv) > 1 else os.path.join("out", "inverted_library.mcstructure")
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join("out", "previews")
    os.makedirs(out_dir, exist_ok=True)
    blocks, palette, size = load_structure(source)
    points = list(iter_non_air(blocks, palette, size))
    if not points:
        raise SystemExit("No non-air blocks to render")
    draw_iso_voxels(points, os.path.join(out_dir, "iso.png"), (1500, 1200), fill=0.88, max_scale=8.0)
    draw_iso_voxels(points, os.path.join(out_dir, "iso_close.png"), (1500, 1200), fill=0.94, max_scale=10.0)
    draw_iso_voxels(points, os.path.join(out_dir, "cutaway.png"), (1500, 1200), cutaway=True, fill=0.88, max_scale=8.0)
    draw_iso_voxels(points, os.path.join(out_dir, "cutaway_close.png"), (1500, 1200), cutaway=True, fill=0.94, max_scale=10.0)
    draw_elevation(blocks, palette, size, os.path.join(out_dir, "front.png"), "front", (1050, 1150))
    draw_elevation(blocks, palette, size, os.path.join(out_dir, "side.png"), "side", (1050, 1150))
    draw_top(blocks, palette, size, os.path.join(out_dir, "top.png"), (1050, 1050))
    draw_interior_top(blocks, palette, size, os.path.join(out_dir, "interior_lower_top.png"), 45, (1000, 1000))
    draw_interior_top(blocks, palette, size, os.path.join(out_dir, "interior_middle_top.png"), 73, (1000, 1000))
    draw_interior_top(blocks, palette, size, os.path.join(out_dir, "interior_upper_top.png"), 101, (1000, 1000))
    print(f"Wrote previews to {out_dir}")


if __name__ == "__main__":
    main()
