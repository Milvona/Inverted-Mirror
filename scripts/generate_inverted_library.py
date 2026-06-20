from __future__ import annotations

import math
import os
from collections import Counter

from bedrock_nbt import NbtCompound, NbtInt, NbtList, TAG_COMPOUND, TAG_INT, TAG_LIST, write_root_compound


SIZE_X = 96
SIZE_Y = 128
SIZE_Z = 96
CX = 48
CZ = 48
OUT_PATH = os.path.join("out", "inverted_library.mcstructure")


BLOCKS = [
    "air",
    "bookshelf",
    "dark_oak_planks",
    "spruce_planks",
    "deepslate_bricks",
    "deepslate_tiles",
    "stone_bricks",
    "sea_lantern",
    "glowstone",
    "shroomlight",
    "pink_stained_glass",
    "lime_stained_glass",
    "yellow_stained_glass",
    "cyan_stained_glass",
    "white_stained_glass",
    "blue_stained_glass",
    "packed_ice",
    "oxidized_copper",
    "weathered_copper",
    "gold_block",
    "moss_block",
    "azalea_leaves",
]
PALETTE = {name: index for index, name in enumerate(BLOCKS)}


def index(x: int, y: int, z: int) -> int:
    return x + z * SIZE_X + y * SIZE_X * SIZE_Z


def in_bounds(x: int, y: int, z: int) -> bool:
    return 0 <= x < SIZE_X and 0 <= y < SIZE_Y and 0 <= z < SIZE_Z


class Structure:
    def __init__(self) -> None:
        self.blocks = [0] * (SIZE_X * SIZE_Y * SIZE_Z)

    def set(self, x: int, y: int, z: int, block: str) -> None:
        if in_bounds(x, y, z):
            self.blocks[index(x, y, z)] = PALETTE[block]

    def fill_box(self, x0: int, y0: int, z0: int, x1: int, y1: int, z1: int, block: str) -> None:
        for y in range(y0, y1 + 1):
            for z in range(z0, z1 + 1):
                for x in range(x0, x1 + 1):
                    self.set(x, y, z, block)


def radius_at_octagon(dx: int, dz: int) -> float:
    return max(abs(dx), abs(dz)) + 0.42 * min(abs(dx), abs(dz))


def add_octagon_disk(s: Structure, y: int, radius: int, border: int = 2) -> None:
    for z in range(CZ - radius - 2, CZ + radius + 3):
        for x in range(CX - radius - 2, CX + radius + 3):
            r = radius_at_octagon(x - CX, z - CZ)
            if r <= radius:
                if r >= radius - border:
                    s.set(x, y, z, "deepslate_bricks")
                    s.set(x, y - 1, z, "deepslate_tiles")
                else:
                    material = "dark_oak_planks" if (x + z) % 5 else "spruce_planks"
                    s.set(x, y, z, material)
                    if (x + z) % 9 == 0:
                        s.set(x, y - 1, z, "deepslate_tiles")


def add_platforms(s: Structure) -> None:
    for y in (34, 58, 82):
        add_octagon_disk(s, y, 22, 3)
        for angle in range(0, 360, 15):
            rad = math.radians(angle)
            x = round(CX + math.cos(rad) * 22)
            z = round(CZ + math.sin(rad) * 22)
            s.set(x, y + 1, z, "deepslate_bricks")
            if angle % 45 == 0:
                s.set(x, y + 2, z, "sea_lantern")


def add_tower_walls(s: Structure) -> None:
    for y in range(30, 93):
        for angle in range(0, 360, 5):
            rad = math.radians(angle)
            radius = 18 + (1 if angle % 45 == 0 else 0)
            x = round(CX + math.cos(rad) * radius)
            z = round(CZ + math.sin(rad) * radius)
            open_arc = 18 < angle % 90 < 42
            near_floor = y in range(34, 39) or y in range(58, 63) or y in range(82, 87)
            if open_arc and not near_floor:
                continue
            if y % 24 in (0, 1, 2):
                block = "deepslate_bricks"
            elif y % 7 in (0, 1, 2, 3):
                block = "bookshelf"
            else:
                block = "dark_oak_planks"
            s.set(x, y, z, block)
            if angle % 45 == 0:
                s.set(x, y, z, "deepslate_bricks")
                s.set(x, y + 1, z, "deepslate_bricks")
    for y in range(32, 92, 4):
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            for r in range(13, 18):
                s.set(round(CX + math.cos(rad) * r), y, round(CZ + math.sin(rad) * r), "bookshelf")


def add_spiral_walkway(s: Structure) -> list[tuple[int, int, int, float]]:
    lantern_points: list[tuple[int, int, int, float]] = []
    steps = 900
    last_bridge_bucket = -1
    for i in range(steps + 1):
        t = i / steps
        angle = t * math.tau * 2.5 - math.pi / 2
        y = round(28 + t * 60)
        radius = 36 + 2.5 * math.sin(t * math.tau * 2.5)
        for width in range(-2, 3):
            rr = radius + width
            x = round(CX + math.cos(angle) * rr)
            z = round(CZ + math.sin(angle) * rr)
            block = "deepslate_bricks" if abs(width) == 2 else "stone_bricks"
            s.set(x, y, z, block)
            s.set(x, y - 1, z, "deepslate_bricks")
        bucket = int(t * 30)
        if bucket != last_bridge_bucket and bucket < 30:
            last_bridge_bucket = bucket
            bx = round(CX + math.cos(angle) * (radius + 7))
            bz = round(CZ + math.sin(angle) * (radius + 7))
            lantern_points.append((bx, y - 3, bz, angle))
            for arm_r in range(round(radius) + 3, round(radius) + 8):
                s.set(round(CX + math.cos(angle) * arm_r), y - 1, round(CZ + math.sin(angle) * arm_r), "deepslate_bricks")
    return lantern_points


def add_lanterns(s: Structure, points: list[tuple[int, int, int, float]]) -> None:
    colors = [
        ("pink_stained_glass", "sea_lantern"),
        ("lime_stained_glass", "shroomlight"),
        ("yellow_stained_glass", "glowstone"),
        ("cyan_stained_glass", "sea_lantern"),
        ("white_stained_glass", "glowstone"),
    ]
    for i, (x, y, z, _angle) in enumerate(points[:30]):
        glass, core = colors[i % len(colors)]
        s.set(x, y + 2, z, "gold_block")
        for dy in range(0, 3):
            for dz in range(-1, 2):
                for dx in range(-1, 2):
                    if abs(dx) + abs(dz) + abs(dy - 1) <= 2:
                        s.set(x + dx, y + dy, z + dz, glass)
        s.set(x, y + 1, z, core)
        s.set(x, y, z, core)


def add_central_crystal(s: Structure) -> None:
    sequence = ["pink_stained_glass", "sea_lantern", "lime_stained_glass", "glowstone", "yellow_stained_glass", "cyan_stained_glass", "white_stained_glass"]
    for y in range(44, 77):
        span = 1 + int(2.5 * math.sin((y - 44) / 32 * math.pi))
        block = sequence[(y - 44) // 3 % len(sequence)]
        for dz in range(-span, span + 1):
            for dx in range(-span, span + 1):
                if abs(dx) + abs(dz) <= span + 1:
                    s.set(CX + dx, y, CZ + dz, block)
        if y % 4 == 0:
            s.set(CX, y, CZ, "sea_lantern")


def add_roof(s: Structure) -> None:
    for y in range(92, 125):
        t = (y - 92) / 32
        radius = max(1, round(21 * (1 - t)))
        for z in range(CZ - radius - 1, CZ + radius + 2):
            for x in range(CX - radius - 1, CX + radius + 2):
                r = radius_at_octagon(x - CX, z - CZ)
                if r <= radius:
                    if r >= radius - 1 or y % 5 == 0:
                        block = "deepslate_tiles"
                    else:
                        block = "oxidized_copper" if (x + z + y) % 3 else "weathered_copper"
                    s.set(x, y, z, block)
    for y in range(122, 128):
        s.set(CX, y, CZ, "gold_block")


def add_bottom_crystal(s: Structure) -> None:
    for y in range(4, 31):
        t = (y - 4) / 26
        radius = max(1, round(17 * t))
        for z in range(CZ - radius, CZ + radius + 1):
            for x in range(CX - radius, CX + radius + 1):
                dist = math.hypot(x - CX, z - CZ)
                if dist <= radius:
                    if dist > radius - 2:
                        block = "blue_stained_glass"
                    elif (x + y + z) % 7 == 0:
                        block = "sea_lantern"
                    elif (x + z) % 3 == 0:
                        block = "cyan_stained_glass"
                    else:
                        block = "packed_ice"
                    s.set(x, y, z, block)


def add_greenery(s: Structure) -> None:
    for y in (36, 60, 84):
        for angle in range(0, 360, 30):
            if angle % 90 == 0:
                continue
            rad = math.radians(angle)
            x = round(CX + math.cos(rad) * 16)
            z = round(CZ + math.sin(rad) * 16)
            s.set(x, y + 1, z, "moss_block")
            s.set(x, y + 2, z, "azalea_leaves")
            s.set(x, y + 3, z, "azalea_leaves")


def build_palette() -> NbtList:
    entries = []
    for name in BLOCKS:
        entries.append(NbtCompound({
            "name": f"minecraft:{name}",
            "states": NbtCompound({}),
            "version": NbtInt(18163713),
        }))
    return NbtList(TAG_COMPOUND, entries)


def write_mcstructure(s: Structure) -> None:
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    root = {
        "format_version": NbtInt(1),
        "size": NbtList(TAG_INT, [SIZE_X, SIZE_Y, SIZE_Z]),
        "structure": NbtCompound({
            "block_indices": NbtList(TAG_LIST, [
                NbtList(TAG_INT, s.blocks),
                NbtList(TAG_INT, [-1] * len(s.blocks)),
            ]),
            "entities": NbtList(TAG_COMPOUND, []),
            "palette": NbtCompound({
                "default": NbtCompound({
                    "block_palette": build_palette(),
                    "block_position_data": NbtCompound({}),
                }),
            }),
        }),
    }
    write_root_compound(OUT_PATH, root)


def main() -> None:
    s = Structure()
    add_bottom_crystal(s)
    add_platforms(s)
    add_tower_walls(s)
    points = add_spiral_walkway(s)
    add_lanterns(s, points)
    add_central_crystal(s)
    add_roof(s)
    add_greenery(s)
    write_mcstructure(s)
    counts = Counter(s.blocks)
    print(f"Wrote {OUT_PATH}")
    print(f"Palette entries: {len(BLOCKS)}")
    print(f"Non-air blocks: {len(s.blocks) - counts[0]}")
    print(f"Lanterns: {min(30, len(points))}")


if __name__ == "__main__":
    main()
