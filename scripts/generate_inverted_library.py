from __future__ import annotations

import math
import os
from collections import Counter
from dataclasses import dataclass, field

from bedrock_nbt import NbtCompound, NbtInt, NbtList, TAG_COMPOUND, TAG_INT, TAG_LIST, write_root_compound


SIZE_X = 96
SIZE_Y = 128
SIZE_Z = 96
CX = 48
CZ = 48
OUT_PATH = os.path.join("out", "inverted_library.mcstructure")

FLOORS = (34, 58, 82)

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


def oct_radius(dx: int | float, dz: int | float) -> float:
    return max(abs(dx), abs(dz)) + 0.42 * min(abs(dx), abs(dz))


def angle_deg(dx: int | float, dz: int | float) -> float:
    return (math.degrees(math.atan2(dz, dx)) + 360.0) % 360.0


def angular_distance(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


@dataclass
class Structure:
    blocks: list[int] = field(default_factory=lambda: [0] * (SIZE_X * SIZE_Y * SIZE_Z))
    categories: list[str] = field(default_factory=lambda: ["air"] * (SIZE_X * SIZE_Y * SIZE_Z))
    stats: Counter = field(default_factory=Counter)

    def set(self, x: int, y: int, z: int, block: str, category: str = "general") -> bool:
        if not in_bounds(x, y, z):
            return False
        i = index(x, y, z)
        old_block = self.blocks[i]
        old_category = self.categories[i]
        new_block = PALETTE[block]
        if old_block == new_block and old_category == category:
            return False
        if old_block != 0:
            self.stats[old_category] -= 1
        self.blocks[i] = new_block
        self.categories[i] = category
        if new_block != 0:
            self.stats[category] += 1
        return True

    def set_disc(self, cx: int, y: int, cz: int, radius: int, block: str, category: str) -> None:
        rr = radius * radius
        for z in range(cz - radius, cz + radius + 1):
            for x in range(cx - radius, cx + radius + 1):
                if (x - cx) * (x - cx) + (z - cz) * (z - cz) <= rr:
                    self.set(x, y, z, block, category)


def block_palette() -> NbtList:
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
                    "block_palette": block_palette(),
                    "block_position_data": NbtCompound({}),
                }),
            }),
        }),
    }
    write_root_compound(OUT_PATH, root)


def floor_material(x: int, z: int) -> str:
    if (x + z) % 11 == 0:
        return "deepslate_tiles"
    if (x * 3 + z) % 7 == 0:
        return "spruce_planks"
    return "dark_oak_planks"


def build_floor_platform(s: Structure, level_y: int, radius_x: int, radius_z: int, open_sides: tuple[int, ...]) -> None:
    atrium_radius = 5
    for y in (level_y - 2, level_y - 1, level_y):
        for z in range(CZ - radius_z - 2, CZ + radius_z + 3):
            for x in range(CX - radius_x - 2, CX + radius_x + 3):
                dx = (x - CX) / radius_x
                dz = (z - CZ) / radius_z
                outer = max(abs(dx), abs(dz)) + 0.38 * min(abs(dx), abs(dz))
                inner = math.hypot(x - CX, z - CZ)
                if outer <= 1.0 and inner >= atrium_radius:
                    rim = outer > 0.82 or y < level_y
                    block = "deepslate_bricks" if rim else floor_material(x, z)
                    s.set(x, y, z, block, "library_core")
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        px = round(CX + math.cos(rad) * (radius_x - 2))
        pz = round(CZ + math.sin(rad) * (radius_z - 2))
        for y in range(level_y + 1, level_y + 5):
            s.set(px, y, pz, "deepslate_bricks", "library_core")
    for side in open_sides:
        rad = math.radians(side)
        for r in range(radius_x - 4, radius_x + 1):
            s.set(round(CX + math.cos(rad) * r), level_y + 1, round(CZ + math.sin(rad) * r), "sea_lantern", "library_core")


def build_bookshelf_walls(s: Structure, level_y: int, height: int, inner_radius: int, outer_radius: int) -> None:
    openings = (35, 145, 235, 325)
    for y in range(level_y + 1, level_y + height + 1):
        local_y = y - level_y
        for z in range(CZ - outer_radius - 1, CZ + outer_radius + 2):
            for x in range(CX - outer_radius - 1, CX + outer_radius + 2):
                dx = x - CX
                dz = z - CZ
                r = oct_radius(dx, dz)
                if not inner_radius <= r <= outer_radius:
                    continue
                a = angle_deg(dx, dz)
                is_open = any(angular_distance(a, opening) < 17 and 4 <= local_y <= height - 3 for opening in openings)
                if is_open:
                    continue
                is_pillar = any(angular_distance(a, pillar) < 5 for pillar in range(0, 360, 45))
                is_band = local_y in (1, 2, height - 1, height) or local_y % 8 == 0
                if is_pillar or is_band:
                    block = "deepslate_bricks"
                elif local_y % 5 == 0:
                    block = "dark_oak_planks"
                else:
                    block = "bookshelf"
                s.set(x, y, z, block, "library_core")
    for y in range(level_y + 4, level_y + height - 1, 5):
        for angle in (80, 100, 170, 190, 260, 280, 350, 10):
            rad = math.radians(angle)
            for r in range(inner_radius - 2, inner_radius + 2):
                s.set(round(CX + math.cos(rad) * r), y, round(CZ + math.sin(rad) * r), "bookshelf", "library_core")
                if y % 10 == 4:
                    s.set(round(CX + math.cos(rad) * (r - 1)), y + 1, round(CZ + math.sin(rad) * (r - 1)), "moss_block", "library_core")


def build_central_library_core(s: Structure) -> None:
    for i, floor_y in enumerate(FLOORS):
        build_floor_platform(s, floor_y, 21 - i, 19 - i, (35, 145, 235, 325))
        wall_height = 17 if floor_y < 82 else 10
        build_bookshelf_walls(s, floor_y, wall_height, 15 - i // 2, 18 - i // 2)
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        for r in (12, 18):
            x = round(CX + math.cos(rad) * r)
            z = round(CZ + math.sin(rad) * r)
            for y in range(30, 94):
                if y % 6 in (0, 1, 2, 3):
                    s.set(x, y, z, "deepslate_bricks", "library_core")
                else:
                    s.set(x, y, z, "dark_oak_planks", "library_core")
    for y in range(36, 88, 6):
        for angle in range(0, 360, 45):
            rad = math.radians(angle + 22.5)
            s.set(round(CX + math.cos(rad) * 13), y, round(CZ + math.sin(rad) * 13), "azalea_leaves", "library_core")


def build_spiral_walkway(
    s: Structure,
    turns: float = 2.5,
    radius_start: float = 30.0,
    radius_end: float = 41.0,
    y_start: int = 28,
    y_end: int = 88,
    width: int = 5,
) -> list[tuple[float, int, float, float, float]]:
    samples: list[tuple[float, int, float, float, float]] = []
    max_theta = math.tau * turns
    steps = 1450
    for step in range(steps + 1):
        t = step / steps
        theta = -math.pi * 0.72 + max_theta * t
        radius = radius_start + (radius_end - radius_start) * t + 1.3 * math.sin(theta * 1.7)
        y = round(y_start + (y_end - y_start) * t)
        px = CX + math.cos(theta) * radius
        pz = CZ + math.sin(theta) * radius
        half_width = width / 2.0
        for z in range(math.floor(pz - half_width - 1), math.ceil(pz + half_width + 2)):
            for x in range(math.floor(px - half_width - 1), math.ceil(px + half_width + 2)):
                dist = math.hypot(x - px, z - pz)
                if dist <= half_width:
                    edge = dist > half_width - 0.85
                    s.set(x, y, z, "deepslate_bricks" if edge else "stone_bricks", "spiral_walkway")
                    s.set(x, y - 1, z, "deepslate_tiles" if edge else "deepslate_bricks", "spiral_walkway")
        if step % 24 == 0:
            samples.append((theta, y, radius, px, pz))
    return samples


def build_lantern_branches_along_spiral(s: Structure, lantern_count: int = 30) -> int:
    colors = [
        ("yellow_stained_glass", "glowstone"),
        ("pink_stained_glass", "sea_lantern"),
        ("lime_stained_glass", "shroomlight"),
        ("cyan_stained_glass", "sea_lantern"),
        ("white_stained_glass", "glowstone"),
    ]
    max_theta = math.tau * 2.5
    for i in range(lantern_count):
        t = (i + 0.35) / lantern_count
        theta = -math.pi * 0.72 + max_theta * t
        radius = 30.0 + (41.0 - 30.0) * t + 1.3 * math.sin(theta * 1.7)
        y = round(28 + (88 - 28) * t)
        branch_len = 4 + (i % 3)
        start_r = radius + 2
        end_r = min(radius + 2 + branch_len, 44.0)
        for r in range(round(start_r), round(end_r) + 1):
            x = round(CX + math.cos(theta) * r)
            z = round(CZ + math.sin(theta) * r)
            s.set(x, y, z, "deepslate_bricks", "lanterns")
            s.set(x, y - 1, z, "deepslate_tiles", "lanterns")
        lx = round(CX + math.cos(theta) * (end_r + 1))
        lz = round(CZ + math.sin(theta) * (end_r + 1))
        drop = 1 + (i % 2)
        for chain_y in range(y - drop, y + 1):
            s.set(lx, chain_y, lz, "gold_block", "lanterns")
        glass, core = colors[i % len(colors)]
        size = 1 if i % 5 else 2
        cy = y - drop - 2
        for dy in range(-size, size + 1):
            for dz in range(-size, size + 1):
                for dx in range(-size, size + 1):
                    if abs(dx) + abs(dz) + abs(dy) <= size + 1:
                        s.set(lx + dx, cy + dy, lz + dz, glass, "lanterns")
        s.set(lx, cy, lz, core, "lanterns")
        s.set(lx, cy - size - 1, lz, core, "lanterns")
    return lantern_count


def crystal_span(y: int) -> int:
    if y < 47 or y > 71:
        return 1
    if 50 <= y <= 66:
        return 3
    return 2


def build_central_crystal_core(s: Structure) -> None:
    colors = [
        "white_stained_glass",
        "yellow_stained_glass",
        "pink_stained_glass",
        "lime_stained_glass",
        "cyan_stained_glass",
        "sea_lantern",
        "glowstone",
    ]
    for y in range(42, 75):
        span = crystal_span(y)
        color = colors[(y - 42) // 3 % len(colors)]
        for dz in range(-span, span + 1):
            for dx in range(-span, span + 1):
                diamond = abs(dx) + abs(dz)
                if diamond <= span + (1 if y % 2 == 0 else 0):
                    s.set(CX + dx, y, CZ + dz, color, "central_crystal")
        if y % 4 == 0:
            s.set(CX, y, CZ, "sea_lantern", "central_crystal")
    for y in (47, 55, 63, 71):
        for angle in range(0, 360, 45):
            rad = math.radians(angle)
            for r in range(4, 7):
                s.set(round(CX + math.cos(rad) * r), y, round(CZ + math.sin(rad) * r), "sea_lantern", "central_crystal")


def build_roof_spire(s: Structure) -> None:
    tiers = [
        (92, 95, 22, 20, True),
        (96, 103, 18, 14, False),
        (104, 106, 17, 15, True),
        (107, 114, 14, 8, False),
        (115, 117, 10, 8, True),
        (118, 124, 7, 1, False),
    ]
    for y0, y1, r0, r1, eave in tiers:
        for y in range(y0, y1 + 1):
            t = 0 if y1 == y0 else (y - y0) / (y1 - y0)
            radius = round(r0 + (r1 - r0) * t)
            for z in range(CZ - radius - 2, CZ + radius + 3):
                for x in range(CX - radius - 2, CX + radius + 3):
                    r = oct_radius(x - CX, z - CZ)
                    if r <= radius:
                        edge = r >= radius - 1.3
                        band = y in (92, 95, 104, 106, 115, 117)
                        rib = any(angular_distance(angle_deg(x - CX, z - CZ), a) < 3 for a in range(0, 360, 45))
                        if (band and r >= radius - 2.5) or rib:
                            block = "deepslate_tiles"
                        else:
                            block = "oxidized_copper" if (x + z + y) % 4 else "weathered_copper"
                        s.set(x, y, z, block, "roof")
    for y in range(124, 128):
        s.set(CX, y, CZ, "gold_block", "roof")


def build_hanging_bottom_crystal(s: Structure) -> None:
    for y in range(4, 31):
        t = (y - 4) / 26.0
        radius = max(1, round(1 + 6.2 * (t ** 1.55)))
        for z in range(CZ - radius - 1, CZ + radius + 2):
            for x in range(CX - radius - 1, CX + radius + 2):
                r = abs(x - CX) + abs(z - CZ) * 0.82
                if r <= radius:
                    edge = r >= radius - 1.2
                    if edge:
                        block = "blue_stained_glass"
                    elif (x + y + z) % 6 == 0:
                        block = "sea_lantern"
                    elif (x - z + y) % 3 == 0:
                        block = "cyan_stained_glass"
                    else:
                        block = "packed_ice"
                    s.set(x, y, z, block, "bottom_crystal")
    for y in range(7, 30, 5):
        s.set(CX, y, CZ, "sea_lantern", "bottom_crystal")
        s.set(CX + 1, y, CZ, "cyan_stained_glass", "bottom_crystal")
        s.set(CX - 1, y, CZ, "cyan_stained_glass", "bottom_crystal")


def main() -> None:
    s = Structure()
    build_central_library_core(s)
    build_spiral_walkway(s, turns=2.5, radius_start=30.0, radius_end=41.0, y_start=28, y_end=88, width=4)
    lantern_count = build_lantern_branches_along_spiral(s)
    build_central_crystal_core(s)
    build_roof_spire(s)
    build_hanging_bottom_crystal(s)
    write_mcstructure(s)

    block_counts = Counter(s.blocks)
    non_air = len(s.blocks) - block_counts[0]
    print(f"Wrote {OUT_PATH}")
    print(f"Palette entries: {len(BLOCKS)}")
    print(f"Non-air blocks: {non_air}")
    print(f"Spiral walkway blocks: {s.stats['spiral_walkway']}")
    print(f"Lantern count: {lantern_count}")
    print(f"Lantern blocks: {s.stats['lanterns']}")
    print(f"Central crystal blocks: {s.stats['central_crystal']}")
    print(f"Roof blocks: {s.stats['roof']}")
    print(f"Bottom crystal blocks: {s.stats['bottom_crystal']}")


if __name__ == "__main__":
    main()
