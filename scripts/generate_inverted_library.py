from __future__ import annotations

import math
import os
from collections import Counter
from dataclasses import dataclass, field

from bedrock_nbt import NbtCompound, NbtInt, NbtList, TAG_COMPOUND, TAG_INT, TAG_LIST, write_root_compound
from coordinate_order import mc_index


SIZE_X = 128
SIZE_Y = 160
SIZE_Z = 128
CX = 64
CZ = 64
OUT_PATH = os.path.join("out", "inverted_library.mcstructure")

FLOORS = (45, 73, 101)
LEVELS = [
    {
        "name": "lower",
        "level": 1,
        "floor_slab_min_y": 42,
        "floor_slab_max_y": 44,
        "walk_y": 45,
        "room_min_y": 45,
        "room_max_y": 68,
        "next_walk_y": 73,
    },
    {
        "name": "middle",
        "level": 2,
        "floor_slab_min_y": 70,
        "floor_slab_max_y": 72,
        "walk_y": 73,
        "room_min_y": 73,
        "room_max_y": 96,
        "next_walk_y": 101,
    },
    {
        "name": "upper",
        "level": 3,
        "floor_slab_min_y": 98,
        "floor_slab_max_y": 100,
        "walk_y": 101,
        "room_min_y": 101,
        "room_max_y": 120,
        "next_walk_y": None,
    },
]

BLOCKS = [
    "air",
    "bookshelf",
    "dark_oak_planks",
    "spruce_planks",
    "dark_oak_log",
    "deepslate_bricks",
    "deepslate_tiles",
    "stone_bricks",
    "iron_bars",
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
    "cut_copper",
    "gold_block",
    "moss_block",
    "azalea_leaves",
]
PALETTE = {name: i for i, name in enumerate(BLOCKS)}


def index(x: int, y: int, z: int) -> int:
    return mc_index(x, y, z, SIZE_X, SIZE_Y, SIZE_Z)


def in_bounds(x: int, y: int, z: int) -> bool:
    return 0 <= x < SIZE_X and 0 <= y < SIZE_Y and 0 <= z < SIZE_Z


def oct_metric(dx: float, dz: float) -> float:
    return max(abs(dx), abs(dz)) + 0.43 * min(abs(dx), abs(dz))


def angle_of(dx: float, dz: float) -> float:
    return (math.degrees(math.atan2(dz, dx)) + 360.0) % 360.0


def angle_delta(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


@dataclass
class DockingPoint:
    level_name: str
    level: int
    walk_y: int
    angle: float
    doorway_center_x: int
    doorway_center_z: int
    facing_vector: tuple[int, int]
    tangent_vector: tuple[int, int]
    landing_center_x: int
    landing_center_z: int
    opening_width: int = 7
    opening_height: int = 8
    landing_width: int = 7
    landing_depth: int = 5

    @property
    def walkable_y(self) -> int:
        return self.walk_y

    @property
    def x(self) -> int:
        return self.landing_center_x

    @property
    def z(self) -> int:
        return self.landing_center_z

    @property
    def facing_direction(self) -> tuple[int, int]:
        return self.facing_vector

    @property
    def landing_size(self) -> int:
        return max(self.landing_width, self.landing_depth)


@dataclass
class Structure:
    blocks: list[int] = field(default_factory=lambda: [0] * (SIZE_X * SIZE_Y * SIZE_Z))
    categories: list[str] = field(default_factory=lambda: ["air"] * (SIZE_X * SIZE_Y * SIZE_Z))
    stats: Counter = field(default_factory=Counter)
    bridge_reports: list[dict[str, object]] = field(default_factory=list)
    deck_mask: set[tuple[int, int, int]] = field(default_factory=set)
    curb_mask: set[tuple[int, int, int]] = field(default_factory=set)
    support_mask: set[tuple[int, int, int]] = field(default_factory=set)
    bridge_mask: set[tuple[int, int, int]] = field(default_factory=set)
    landing_pad_mask: set[tuple[int, int, int]] = field(default_factory=set)
    main_ring_masks: dict[str, set[tuple[int, int, int]]] = field(default_factory=dict)
    stair_masks: dict[str, set[tuple[int, int, int]]] = field(default_factory=dict)
    protected_mask: set[tuple[int, int, int]] = field(default_factory=set)
    detached_edge_blocks_removed: int = 0
    floating_support_blocks_removed: int = 0
    removed_internal_clutter_count: int = 0

    def set(self, x: int, y: int, z: int, block: str, category: str = "general") -> bool:
        if not in_bounds(x, y, z):
            return False
        i = index(x, y, z)
        old = self.blocks[i]
        old_cat = self.categories[i]
        new = PALETTE[block]
        if old == new and old_cat == category:
            return False
        if old != 0:
            self.stats[old_cat] -= 1
        self.blocks[i] = new
        self.categories[i] = category
        if new != 0:
            self.stats[category] += 1
        return True

    def carve(self, x: int, y: int, z: int) -> bool:
        if (x, y, z) in self.protected_mask:
            return False
        return self.set(x, y, z, "air", "air")

    def force_carve(self, x: int, y: int, z: int) -> bool:
        return self.set(x, y, z, "air", "air")

    def is_solid(self, x: int, y: int, z: int) -> bool:
        return in_bounds(x, y, z) and self.blocks[index(x, y, z)] != PALETTE["air"]

    def is_solid_near(self, x: int, y: int, z: int, radius: int = 1) -> bool:
        for yy in range(y - radius, y + radius + 1):
            for zz in range(z - radius, z + radius + 1):
                for xx in range(x - radius, x + radius + 1):
                    if self.is_solid(xx, yy, zz):
                        return True
        return False

    def protect(self, x: int, y: int, z: int) -> None:
        if in_bounds(x, y, z):
            self.protected_mask.add((x, y, z))


def build_palette() -> NbtList:
    return NbtList(TAG_COMPOUND, [
        NbtCompound({
            "name": f"minecraft:{name}",
            "states": NbtCompound({}),
            "version": NbtInt(18163713),
        })
        for name in BLOCKS
    ])


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


def floor_block(x: int, z: int) -> str:
    if (x + 2 * z) % 13 == 0:
        return "spruce_planks"
    if (x - z) % 11 == 0:
        return "deepslate_tiles"
    return "dark_oak_planks"


def build_platform_shell(s: Structure, y: int, radius: int, category: str) -> None:
    atrium = 7
    for yy in range(y - 2, y + 1):
        for z in range(CZ - radius - 2, CZ + radius + 3):
            for x in range(CX - radius - 2, CX + radius + 3):
                r = oct_metric(x - CX, z - CZ)
                inner = math.hypot(x - CX, z - CZ)
                if r <= radius and inner >= atrium:
                    rim = r >= radius - 2.6 or yy < y
                    s.set(x, yy, z, "deepslate_bricks" if rim else floor_block(x, z), category)


def build_wall_segment(
    s: Structure,
    level_y: int,
    height: int,
    angle: float,
    radius: int,
    half_width: int,
    category: str,
) -> None:
    rad = math.radians(angle)
    tangent = (-math.sin(rad), math.cos(rad))
    normal = (math.cos(rad), math.sin(rad))
    open_front = angle in (45, 90, 135)
    for w in range(-half_width, half_width + 1):
        for thick in range(-1, 2):
            x = round(CX + normal[0] * (radius + thick) + tangent[0] * w)
            z = round(CZ + normal[1] * (radius + thick) + tangent[1] * w)
            for yy in range(level_y + 1, level_y + height + 1):
                ly = yy - level_y
                window = open_front and abs(w) <= 5 and 4 <= ly <= 15
                side_window = not open_front and abs(w) <= 3 and 7 <= ly <= 14 and angle in (0, 180)
                if window or side_window:
                    continue
                frame = abs(w) >= half_width - 1 or ly in (1, 2, height - 1, height) or ly % 7 == 0
                upright = w % 7 == 0
                if frame or upright:
                    block = "deepslate_bricks" if ly % 3 else "dark_oak_log"
                elif ly % 5 == 0:
                    block = "dark_oak_planks"
                else:
                    block = "bookshelf"
                s.set(x, yy, z, block, category)


def build_inner_bookshelves(s: Structure, level_y: int, height: int, category: str) -> None:
    for angle in (20, 160, 205, 250, 300, 340):
        rad = math.radians(angle)
        tangent = (-math.sin(rad), math.cos(rad))
        normal = (math.cos(rad), math.sin(rad))
        for w in range(-4, 5):
            for depth in range(0, 2):
                x = round(CX + normal[0] * (12 + depth) + tangent[0] * w)
                z = round(CZ + normal[1] * (12 + depth) + tangent[1] * w)
                for yy in range(level_y + 3, level_y + min(height, 16)):
                    if yy % 6 == 0 or abs(w) == 4:
                        s.set(x, yy, z, "dark_oak_planks", category)
                    else:
                        s.set(x, yy, z, "bookshelf", category)


def build_bookshelf_alcoves(s: Structure) -> None:
    for level_y, radius in ((44, 18), (72, 17), (100, 16)):
        for angle in (0, 25, 155, 180, 205, 245, 295, 335):
            rad = math.radians(angle)
            tangent = (-math.sin(rad), math.cos(rad))
            normal = (math.cos(rad), math.sin(rad))
            for w in range(-3, 4):
                for depth in range(0, 2):
                    x = round(CX + normal[0] * (radius - depth) + tangent[0] * w)
                    z = round(CZ + normal[1] * (radius - depth) + tangent[1] * w)
                    for yy in range(level_y + 4, level_y + 17):
                        bay_edge = abs(w) == 3 or yy in (level_y + 4, level_y + 10, level_y + 16)
                        s.set(x, yy, z, "dark_oak_log" if bay_edge else "bookshelf", "library_core")


def build_open_library_tier(s: Structure, level_y: int, floor_radius: int, height: int) -> None:
    build_platform_shell(s, level_y, floor_radius, "library_core")
    for angle in range(0, 360, 45):
        build_wall_segment(s, level_y, height, angle, floor_radius - 3, 8, "library_core")
    build_inner_bookshelves(s, level_y, height, "library_core")
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x = round(CX + math.cos(rad) * (floor_radius - 1))
        z = round(CZ + math.sin(rad) * (floor_radius - 1))
        for yy in range(level_y - 2, level_y + height + 3):
            s.set(x, yy, z, "deepslate_bricks" if yy % 5 else "dark_oak_log", "library_core")
    for angle in (70, 110, 250, 290):
        rad = math.radians(angle)
        for r in range(15, floor_radius - 2):
            s.set(round(CX + math.cos(rad) * r), level_y + 1, round(CZ + math.sin(rad) * r), "deepslate_tiles", "library_core")


def build_central_library_core(s: Structure) -> None:
    for y, radius, height in ((44, 24, 22), (72, 23, 22), (100, 21, 16)):
        build_open_library_tier(s, y, radius, height)
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        for r in (15, 23):
            x = round(CX + math.cos(rad) * r)
            z = round(CZ + math.sin(rad) * r)
            for yy in range(38, 110):
                if yy % 8 in (0, 1, 2, 3):
                    s.set(x, yy, z, "deepslate_bricks", "library_core")


def carve_atrium(s: Structure) -> None:
    for yy in range(39, 109):
        radius = 8 if 52 <= yy <= 100 else 7
        for z in range(CZ - radius, CZ + radius + 1):
            for x in range(CX - radius, CX + radius + 1):
                if math.hypot(x - CX, z - CZ) <= radius:
                    s.carve(x, yy, z)
    for floor in FLOORS:
        for z in range(CZ - 9, CZ + 10):
            for x in range(CX - 9, CX + 10):
                if math.hypot(x - CX, z - CZ) <= 8:
                    for yy in range(floor - 2, floor + 1):
                        s.carve(x, yy, z)


def is_inside_octagon(x: int, z: int, cx: int, cz: int, radius: int) -> bool:
    dx = abs(x - cx)
    dz = abs(z - cz)
    return max(dx, dz) <= radius and dx + dz <= int(radius * 1.42)


def get_radial_distance(x: int, z: int, cx: int = CX, cz: int = CZ) -> float:
    return math.hypot(x - cx, z - cz)


def get_polar_angle(x: int, z: int, cx: int = CX, cz: int = CZ) -> float:
    return angle_of(x - cx, z - cz)


def define_docking_points() -> list[DockingPoint]:
    result: list[DockingPoint] = []
    for level in LEVELS:
        walk_y = level["walk_y"]
        best = min(
            (abs(walkway_point(i / 2000)[2] - walk_y), i / 2000, walkway_point(i / 2000))
            for i in range(2001)
        )
        theta, _radius, _y, _ = best[2]
        fx = 1 if math.cos(theta) >= 0 else -1
        fz = 1 if math.sin(theta) >= 0 else -1
        if abs(math.cos(theta)) > abs(math.sin(theta)) * 1.7:
            fz = 0
        elif abs(math.sin(theta)) > abs(math.cos(theta)) * 1.7:
            fx = 0
        if fx == 0 and fz == 0:
            fx = 1
        length = max(1.0, math.hypot(fx, fz))
        nx, nz = fx / length, fz / length
        tx, tz = -fz, fx
        door_r = 22
        land_r = 27
        result.append(DockingPoint(
            level_name=str(level["name"]),
            level=int(level["level"]),
            walk_y=int(walk_y),
            angle=math.degrees(theta),
            doorway_center_x=round(CX + nx * door_r),
            doorway_center_z=round(CZ + nz * door_r),
            facing_vector=(fx, fz),
            tangent_vector=(tx, tz),
            landing_center_x=round(CX + nx * land_r),
            landing_center_z=round(CZ + nz * land_r),
            opening_width=7,
            opening_height=8 if level["name"] != "upper" else 7,
            landing_width=7,
            landing_depth=7 if level["name"] == "lower" else 5,
        ))
    return result


def carve_openings(s: Structure, docking_points: list[DockingPoint]) -> None:
    for dock in docking_points:
        fx, fz = dock.facing_vector
        tx, tz = dock.tangent_vector
        length = max(1.0, math.hypot(fx, fz))
        nx, nz = fx / length, fz / length
        back_x, back_z = -nx, -nz
        half = dock.opening_width // 2
        for depth in range(-2, 7):
            for w in range(-half, half + 1):
                x = round(dock.doorway_center_x + tx * w + back_x * depth)
                z = round(dock.doorway_center_z + tz * w + back_z * depth)
                for y in range(dock.walk_y, dock.walk_y + dock.opening_height + 1):
                    s.force_carve(x, y, z)
                    s.protect(x, y, z)
        # Clear headroom over the landing itself.
        for dx in range(-half, half + 1):
            for dz in range(-half, half + 1):
                if abs(dx) + abs(dz) <= half + 1:
                    for y in range(dock.walk_y + 1, dock.walk_y + 5):
                        s.force_carve(dock.landing_center_x + dx, y, dock.landing_center_z + dz)
        # Door frame.
        for side in (-half - 1, half + 1):
            for y in range(dock.walk_y, dock.walk_y + dock.opening_height + 1):
                x = round(dock.doorway_center_x + tx * side)
                z = round(dock.doorway_center_z + tz * side)
                s.set(x, y, z, "deepslate_bricks", "main_pillar")
                s.protect(x, y, z)
        for w in range(-half - 1, half + 2):
            x = round(dock.doorway_center_x + tx * w)
            z = round(dock.doorway_center_z + tz * w)
            s.set(x, dock.walk_y + dock.opening_height + 1, z, "dark_oak_log", "ring_beam")
            s.protect(x, dock.walk_y + dock.opening_height + 1, z)


def build_landing_pads(s: Structure, docking_points: list[DockingPoint]) -> None:
    for dock in docking_points:
        fx, fz = dock.facing_vector
        tx, tz = dock.tangent_vector
        half_w = dock.landing_width // 2
        half_d = dock.landing_depth // 2
        for w in range(-half_w, half_w + 1):
            for d in range(-half_d, half_d + 1):
                x = round(dock.landing_center_x + tx * w + fx * d)
                y = dock.walk_y
                z = round(dock.landing_center_z + tz * w + fz * d)
                block = "stone_bricks" if abs(w) < half_w and abs(d) < half_d else "deepslate_bricks"
                s.set(x, y, z, block, "landing_pad")
                s.set(x, y - 1, z, "deepslate_bricks", "landing_pad")
                s.landing_pad_mask.add((x, y, z))
                s.protect(x, y, z)
                s.protect(x, y - 1, z)


def clear_internal_volume(s: Structure) -> None:
    for y in range(42, 121):
        for z in range(CZ - 23, CZ + 24):
            for x in range(CX - 23, CX + 24):
                if is_inside_octagon(x, z, CX, CZ, 22):
                    s.carve(x, y, z)


def build_floor_slabs(s: Structure) -> None:
    for level in LEVELS:
        for y in range(level["floor_slab_min_y"], level["floor_slab_max_y"] + 1):
            for z in range(CZ - 25, CZ + 26):
                for x in range(CX - 25, CX + 26):
                    if is_inside_octagon(x, z, CX, CZ, 24) and get_radial_distance(x, z) >= 6:
                        r = get_radial_distance(x, z)
                        block = "deepslate_bricks" if r >= 22 or y < level["floor_slab_max_y"] else floor_block(x, z)
                        s.set(x, y, z, block, "library_core")


def build_regular_atrium(s: Structure) -> None:
    for y in range(45, 108):
        for z in range(CZ - 8, CZ + 9):
            for x in range(CX - 8, CX + 9):
                if is_inside_octagon(x, z, CX, CZ, 6):
                    s.carve(x, y, z)
                elif is_inside_octagon(x, z, CX, CZ, 7):
                    if y in (45, 73, 101):
                        s.set(x, y, z, "deepslate_bricks", "atrium_rim")
                        s.protect(x, y, z)
    for level in LEVELS:
        y = level["walk_y"]
        for dx, dz in ((0, -8), (0, 8), (8, 0), (-8, 0)):
            for a in range(-2, 3):
                for b in range(0, 3):
                    x = CX + (a if dx == 0 else b * (1 if dx > 0 else -1))
                    z = CZ + (a if dz == 0 else b * (1 if dz > 0 else -1))
                    if dx == 0:
                        z = CZ + dz + b * (1 if dz > 0 else -1)
                    else:
                        x = CX + dx + b * (1 if dx > 0 else -1)
                    s.set(x, y, z, "deepslate_tiles", "atrium_rim")
                    s.protect(x, y, z)


def build_main_ring_corridor(s: Structure) -> None:
    for level in LEVELS:
        mask: set[tuple[int, int, int]] = set()
        y = level["walk_y"]
        for z in range(CZ - 14, CZ + 15):
            for x in range(CX - 14, CX + 15):
                r = get_radial_distance(x, z)
                if 8 <= r <= 13 and is_inside_octagon(x, z, CX, CZ, 15):
                    block = "deepslate_tiles" if int(r) in (8, 13) else floor_block(x, z)
                    s.set(x, y, z, block, "main_ring")
                    s.set(x, y - 1, z, "deepslate_bricks", "main_ring")
                    mask.add((x, y, z))
                    s.protect(x, y, z)
                    s.protect(x, y - 1, z)
                    for clear_y in range(y + 1, y + 4):
                        s.carve(x, clear_y, z)
        s.main_ring_masks[str(level["name"])] = mask


def connect_landing_to_ring_corridor(s: Structure, docking_points: list[DockingPoint]) -> None:
    for dock in docking_points:
        fx, fz = dock.facing_vector
        tx, tz = dock.tangent_vector
        flen = max(1.0, math.hypot(fx, fz))
        nx, nz = fx / flen, fz / flen
        y = dock.walk_y
        for r in range(13, 28):
            cx = round(CX + nx * r)
            cz = round(CZ + nz * r)
            for w in range(-2, 3):
                x = round(cx + tx * w)
                z = round(cz + tz * w)
                s.set(x, y, z, "stone_bricks", "landing_pad")
                s.set(x, y - 1, z, "deepslate_bricks", "landing_pad")
                s.landing_pad_mask.add((x, y, z))
                s.protect(x, y, z)
                s.protect(x, y - 1, z)
                for clear_y in range(y + 1, y + 4):
                    s.carve(x, clear_y, z)


def build_main_pillars_and_beams(s: Structure, docking_points: list[DockingPoint]) -> None:
    dock_angles = [get_polar_angle(d.doorway_center_x, d.doorway_center_z) for d in docking_points]
    for angle in range(0, 360, 45):
        if any(angle_delta(angle, da) < 12 for da in dock_angles):
            continue
        rad = math.radians(angle)
        x = round(CX + math.cos(rad) * 21)
        z = round(CZ + math.sin(rad) * 21)
        for y in range(42, 121):
            block = "dark_oak_log" if y % 6 in (0, 1, 2) else "deepslate_bricks"
            s.set(x, y, z, block, "main_pillar")
            s.protect(x, y, z)
    for level in LEVELS:
        for y in (level["walk_y"] + 5, level["room_max_y"]):
            for z in range(CZ - 23, CZ + 24):
                for x in range(CX - 23, CX + 24):
                    r = get_radial_distance(x, z)
                    if 20 <= r <= 22 and is_inside_octagon(x, z, CX, CZ, 23):
                        if (x + z + y) % 3 != 0:
                            s.set(x, y, z, "dark_oak_log", "ring_beam")
                            s.protect(x, y, z)


def build_curved_block_stair(
    s: Structure,
    key: str,
    y_from: int,
    y_to: int,
    start_angle: float,
    end_angle: float,
) -> None:
    mask: set[tuple[int, int, int]] = set()
    steps = y_to - y_from
    for i in range(steps + 1):
        t = i / max(1, steps)
        y = y_from + i
        angle = math.radians(start_angle + (end_angle - start_angle) * t)
        radius = 14 + int(i % 2)
        cx = round(CX + math.cos(angle) * radius)
        cz = round(CZ + math.sin(angle) * radius)
        tangent = (-math.sin(angle), math.cos(angle))
        for w in range(-1, 2):
            x = round(cx + tangent[0] * w)
            z = round(cz + tangent[1] * w)
            s.set(x, y, z, "deepslate_tiles" if w else "stone_bricks", "stairs")
            s.set(x, y - 1, z, "deepslate_bricks", "stairs")
            mask.add((x, y, z))
            s.protect(x, y, z)
            s.protect(x, y - 1, z)
            for clear_y in range(y + 1, y + 4):
                s.carve(x, clear_y, z)
    s.stair_masks[key] = mask


def place_outer_bookshelf_walls(s: Structure, docking_points: list[DockingPoint]) -> None:
    dock_angles = [get_polar_angle(d.doorway_center_x, d.doorway_center_z) for d in docking_points]
    stair_skip = {"lower": (210, 320), "middle": (30, 140), "upper": (30, 140)}
    for level in LEVELS:
        name = str(level["name"])
        height = 7 if name == "middle" else 5
        density_mod = 3 if name == "middle" else 4
        for z in range(CZ - 23, CZ + 24):
            for x in range(CX - 23, CX + 24):
                r = get_radial_distance(x, z)
                if not (18 <= r <= 22 and is_inside_octagon(x, z, CX, CZ, 24)):
                    continue
                a = get_polar_angle(x, z)
                if any(angle_delta(a, da) < 18 for da in dock_angles):
                    continue
                skip0, skip1 = stair_skip[name]
                in_stair = skip0 <= a <= skip1 if skip0 < skip1 else a >= skip0 or a <= skip1
                if in_stair:
                    continue
                if int(a // 12) % density_mod == 0:
                    continue
                for yy in range(level["walk_y"] + 1, min(level["walk_y"] + height + 1, level["room_max_y"] + 1)):
                    edge = yy in (level["walk_y"] + 1, level["walk_y"] + height) or int(a) % 18 == 0
                    s.set(x, yy, z, "dark_oak_log" if edge else "bookshelf", "bookshelf_zone")


def place_quadrant_bookshelves(s: Structure) -> None:
    quadrant_centers = {
        "lower": [(54, 55), (74, 55)],
        "middle": [(52, 52), (76, 52), (52, 76), (76, 76)],
        "upper": [(54, 74), (74, 54)],
    }
    for level in LEVELS:
        name = str(level["name"])
        height = 6 if name == "middle" else 4
        for cx, cz in quadrant_centers[name]:
            for dx in range(-4, 5):
                for depth in range(0, 2):
                    x = cx + dx
                    z = cz + depth
                    r = get_radial_distance(x, z)
                    if r < 14 or r > 18:
                        continue
                    for y in range(level["walk_y"] + 1, level["walk_y"] + height + 1):
                        edge = abs(dx) == 4 or y in (level["walk_y"] + 1, level["walk_y"] + height)
                        s.set(x, y, z, "dark_oak_log" if edge else "bookshelf", "bookshelf_zone")


def place_low_atrium_shelves(s: Structure) -> None:
    for level in (LEVELS[0], LEVELS[2]):
        y = level["walk_y"] + 1
        for angle in (25, 155, 205, 335):
            rad = math.radians(angle)
            x = round(CX + math.cos(rad) * 10)
            z = round(CZ + math.sin(rad) * 10)
            s.set(x, y, z, "bookshelf", "low_shelf")
            s.set(x, y + 1, z, "dark_oak_planks", "low_shelf")


def cleanup_internal_clutter(s: Structure) -> None:
    removed = 0
    for level in LEVELS:
        y = level["walk_y"]
        for z in range(CZ - 14, CZ + 15):
            for x in range(CX - 14, CX + 15):
                r = get_radial_distance(x, z)
                if 8 <= r <= 13:
                    for yy in range(y + 1, y + 4):
                        if (x, yy, z) not in s.protected_mask and s.is_solid(x, yy, z):
                            s.carve(x, yy, z)
                            removed += 1
        for z in range(CZ - 7, CZ + 8):
            for x in range(CX - 7, CX + 8):
                if is_inside_octagon(x, z, CX, CZ, 6):
                    for yy in range(level["room_min_y"], level["room_max_y"] + 1):
                        if (x, yy, z) not in s.protected_mask and s.is_solid(x, yy, z):
                            s.carve(x, yy, z)
                            removed += 1
    s.removed_internal_clutter_count = removed


def rebuild_internal_system(s: Structure, docking_points: list[DockingPoint]) -> None:
    clear_internal_volume(s)
    build_floor_slabs(s)
    build_regular_atrium(s)
    build_main_ring_corridor(s)
    carve_openings(s, docking_points)
    build_landing_pads(s, docking_points)
    connect_landing_to_ring_corridor(s, docking_points)
    build_main_pillars_and_beams(s, docking_points)
    build_curved_block_stair(s, "stair_A", 45, 73, 210, 320)
    build_curved_block_stair(s, "stair_B", 73, 101, 30, 140)
    place_outer_bookshelf_walls(s, docking_points)
    place_quadrant_bookshelves(s)
    place_low_atrium_shelves(s)
    carve_openings(s, docking_points)
    cleanup_internal_clutter(s)


def carve_front_cut_visibility(s: Structure) -> None:
    for yy in range(48, 101):
        for z in range(CZ + 6, CZ + 28):
            span = int(6 + (z - (CZ + 6)) * 0.35)
            for x in range(CX - span, CX + span + 1):
                if yy % 28 not in (0, 1, 2):
                    s.carve(x, yy, z)


def walkway_point(t: float) -> tuple[float, float, int, float]:
    theta = 5 * math.pi * t - math.pi * 0.58
    base_radius = 42.0
    radius = base_radius + 3.2 * math.sin(theta * 0.8) + 1.4 * math.sin(theta * 2.0) + 1.6 * t
    for floor_t in ((44 - 34) / 70, (72 - 34) / 70, (100 - 34) / 70):
        closeness = max(0.0, 1.0 - abs(t - floor_t) / 0.055)
        radius -= 4.5 * closeness
    y = round(34 + 70 * t)
    return theta, radius, y, t


def build_spiral_walkway(s: Structure, turns: float = 2.5, y_start: int = 34, y_end: int = 104) -> list[tuple[float, float, int]]:
    points: list[tuple[float, float, int]] = []
    steps = 1650
    width = 4.2
    for step in range(steps + 1):
        t = step / steps
        theta, radius, y, _ = walkway_point(t)
        px = CX + math.cos(theta) * radius
        pz = CZ + math.sin(theta) * radius
        radial = (math.cos(theta), math.sin(theta))
        tangent = (-math.sin(theta), math.cos(theta))
        half_width = width / 2
        for z in range(math.floor(pz - width), math.ceil(pz + width + 1)):
            for x in range(math.floor(px - width), math.ceil(px + width + 1)):
                cross = (x - px) * radial[0] + (z - pz) * radial[1]
                along = (x - px) * tangent[0] + (z - pz) * tangent[1]
                if abs(cross) <= half_width and abs(along) <= 1.85:
                    chip = abs(cross) > half_width - 0.55 and (step // 17 + x + z) % 9 == 0
                    if chip:
                        continue
                    edge = abs(cross) > half_width - 0.7
                    s.set(x, y, z, "deepslate_bricks" if edge else "stone_bricks", "spiral_walkway")
                    s.set(x, y - 1, z, "deepslate_tiles" if edge else "deepslate_bricks", "spiral_walkway")
                    s.deck_mask.add((x, y, z))
                    s.protect(x, y, z)
                    s.protect(x, y - 1, z)
        if step % 18 == 0:
            points.append((theta, radius, y))
    return points


def neighbor4(x: int, y: int, z: int) -> list[tuple[int, int, int]]:
    return [(x + 1, y, z), (x - 1, y, z), (x, y, z + 1), (x, y, z - 1)]


def build_walkway_edges(s: Structure) -> None:
    edge_candidates: set[tuple[int, int, int]] = set()
    for x, y, z in s.deck_mask:
        for nx, ny, nz in neighbor4(x, y, z):
            if (nx, ny, nz) not in s.deck_mask:
                edge_candidates.add((nx, y + 1, nz))
    for i, (x, y, z) in enumerate(sorted(edge_candidates)):
        if (x * 17 + z * 31 + y) % 11 in (0, 1):
            continue
        if any(n in s.deck_mask for n in neighbor4(x, y - 1, z)):
            s.set(x, y, z, "deepslate_bricks", "walkway_edge")
            s.curb_mask.add((x, y, z))
    # Connected ribs and underside supports. They always touch the deck above.
    for i, (x, y, z) in enumerate(sorted(s.deck_mask)):
        if i % 115 != 0:
            continue
        for yy in range(y - 4, y):
            s.set(x, yy, z, "deepslate_bricks", "walkway_support")
            s.support_mask.add((x, yy, z))


def cleanup_detached_edge_blocks(s: Structure) -> None:
    removed_edges = 0
    for x, y, z in list(s.curb_mask):
        attached = any(n in s.deck_mask for n in neighbor4(x, y - 1, z))
        attached = attached or any((x + dx, y - 1, z + dz) in s.deck_mask for dx in (-1, 0, 1) for dz in (-1, 0, 1))
        if not attached and (x, y, z) not in s.protected_mask:
            s.carve(x, y, z)
            s.curb_mask.discard((x, y, z))
            removed_edges += 1
    removed_supports = 0
    for x, y, z in list(s.support_mask):
        attached = (x, y + 1, z) in s.deck_mask or (x, y + 1, z) in s.support_mask
        attached = attached or any((x + dx, y + 1, z + dz) in s.deck_mask for dx in (-1, 0, 1) for dz in (-1, 0, 1))
        if not attached and (x, y, z) not in s.protected_mask:
            s.carve(x, y, z)
            s.support_mask.discard((x, y, z))
            removed_supports += 1
    s.detached_edge_blocks_removed = removed_edges
    s.floating_support_blocks_removed = removed_supports


def cleanup_floating_blocks(s: Structure) -> None:
    cleanup_detached_edge_blocks(s)


def flood_count(mask: set[tuple[int, int, int]], start: tuple[int, int, int]) -> int:
    if start not in mask:
        return 0
    seen = {start}
    stack = [start]
    while stack:
        x, y, z = stack.pop()
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == dy == dz == 0:
                        continue
                    n = (x + dx, y + dy, z + dz)
                    if n in mask and n not in seen:
                        seen.add(n)
                        stack.append(n)
    return len(seen)


def mask_components(mask: set[tuple[int, int, int]]) -> list[set[tuple[int, int, int]]]:
    remaining = set(mask)
    components: list[set[tuple[int, int, int]]] = []
    while remaining:
        start = remaining.pop()
        comp = {start}
        stack = [start]
        while stack:
            x, y, z = stack.pop()
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == dy == dz == 0:
                            continue
                        n = (x + dx, y + dy, z + dz)
                        if n in remaining:
                            remaining.remove(n)
                            comp.add(n)
                            stack.append(n)
        components.append(comp)
    return components


def add_deck_connection(s: Structure, a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    ax, ay, az = a
    bx, by, bz = b
    steps = max(abs(bx - ax), abs(by - ay), abs(bz - az), 1)
    added = 0
    for i in range(steps + 1):
        t = i / steps
        cx = round(ax + (bx - ax) * t)
        cy = round(ay + (by - ay) * t)
        cz = round(az + (bz - az) * t)
        for dx in range(-1, 2):
            x, y, z = cx + dx, cy, cz
            if (x, y, z) not in s.deck_mask:
                added += 1
            s.set(x, y, z, "stone_bricks", "spiral_walkway")
            s.set(x, y - 1, z, "deepslate_bricks", "spiral_walkway")
            s.deck_mask.add((x, y, z))
            s.protect(x, y, z)
            s.protect(x, y - 1, z)
    return added


def repair_deck_connectivity(s: Structure) -> int:
    repaired = 0
    while True:
        components = mask_components(s.deck_mask)
        if len(components) <= 1:
            return repaired
        components.sort(key=len, reverse=True)
        main = components[0]
        other = components[-1]
        best = min(
            ((abs(a[0] - b[0]) + abs(a[1] - b[1]) * 2 + abs(a[2] - b[2]), a, b) for a in other for b in main),
            key=lambda item: item[0],
        )
        repaired += add_deck_connection(s, best[1], best[2])


def validate_connectivity(s: Structure, docking_points: list[DockingPoint]) -> None:
    for dock in docking_points:
        platform_mask: set[tuple[int, int, int]] = set()
        y = dock.walkable_y
        for z in range(CZ - 30, CZ + 31):
            for x in range(CX - 30, CX + 31):
                if s.is_solid(x, y, z):
                    platform_mask.add((x, y, z))
        count = flood_count(platform_mask, (dock.x, y, dock.z))
        print(f"platform level {dock.level} connected: {count >= dock.landing_size * dock.landing_size} flood_blocks={count}")

    for report in s.bridge_reports:
        connected = report["connected_to_landing"] and report["connected_to_spiral"]
        print(f"bridge {report['bridge_id']} connected: {connected}")

    deck_start = next(iter(s.deck_mask)) if s.deck_mask else None
    deck_connected = deck_start is not None and flood_count(s.deck_mask, deck_start) == len(s.deck_mask)
    print(f"spiral walkway deck connected: {deck_connected}")
    print(f"detached_edge_blocks_removed: {s.detached_edge_blocks_removed}")
    print(f"floating_support_blocks_removed: {s.floating_support_blocks_removed}")


def validate_interior_connectivity(s: Structure, docking_points: list[DockingPoint]) -> None:
    blocked_doorways = 0
    blocked_corridor = 0
    for level in LEVELS:
        name = str(level["name"])
        ring = s.main_ring_masks.get(name, set())
        ring_start = next(iter(ring)) if ring else None
        ring_connected = ring_start is not None and flood_count(ring, ring_start) == len(ring)
        print(f"{name}_ring_connected: {ring_connected}")
        for x, y, z in ring:
            for yy in range(y + 1, y + 4):
                if s.is_solid(x, yy, z):
                    blocked_corridor += 1

    for dock in docking_points:
        ring = s.main_ring_masks.get(dock.level_name, set())
        landing_cells = {p for p in s.landing_pad_mask if p[1] == dock.walk_y}
        docking_connected = mask_touches(landing_cells, ring)
        print(f"{dock.level_name}_docking_connected: {docking_connected}")
        fx, fz = dock.facing_vector
        tx, tz = dock.tangent_vector
        half = dock.opening_width // 2
        for w in range(-half, half + 1):
            x = round(dock.doorway_center_x + tx * w)
            z = round(dock.doorway_center_z + tz * w)
            for y in range(dock.walk_y + 1, dock.walk_y + dock.opening_height):
                if s.is_solid(x, y, z):
                    blocked_doorways += 1

    stair_a = s.stair_masks.get("stair_A", set())
    stair_b = s.stair_masks.get("stair_B", set())
    lower_ring = s.main_ring_masks.get("lower", set())
    middle_ring = s.main_ring_masks.get("middle", set())
    upper_ring = s.main_ring_masks.get("upper", set())
    stair_a_connected = mask_touches(stair_a, lower_ring) and mask_touches(stair_a, middle_ring)
    stair_b_connected = mask_touches(stair_b, middle_ring) and mask_touches(stair_b, upper_ring)
    print(f"stair_A_connected: {stair_a_connected}")
    print(f"stair_B_connected: {stair_b_connected}")

    atrium_blocked = 0
    for y in range(45, 108):
        for z in range(CZ - 6, CZ + 7):
            for x in range(CX - 6, CX + 7):
                if is_inside_octagon(x, z, CX, CZ, 5) and s.is_solid(x, y, z) and s.categories[index(x, y, z)] != "central_crystal":
                    atrium_blocked += 1
    print(f"atrium_clear_except_crystal: {atrium_blocked == 0}")
    print(f"blocked_doorway_count: {blocked_doorways}")
    print(f"blocked_corridor_cells_count: {blocked_corridor}")
    print(f"removed_internal_clutter_count: {s.removed_internal_clutter_count}")


def spiral_xyz(t: float) -> tuple[int, int, int, float, float]:
    theta, radius, y, _ = walkway_point(t)
    x = round(CX + math.cos(theta) * radius)
    z = round(CZ + math.sin(theta) * radius)
    return x, y, z, theta, radius


def nearest_spiral_point_for_dock(floor: int, dock: tuple[int, int, int]) -> tuple[int, int, int, float, float]:
    candidates = []
    for i in range(2001):
        t = i / 2000
        x, y, z, theta, radius = spiral_xyz(t)
        if abs(y - floor) > 4:
            continue
        dist = math.hypot(x - dock[0], z - dock[2]) + abs(y - floor) * 4
        candidates.append((dist, x, y, z, theta, radius))
    if not candidates:
        raise RuntimeError(f"No spiral point near floor {floor}")
    _, x, y, z, theta, radius = min(candidates, key=lambda item: item[0])
    return x, floor, z, theta, radius


def build_discrete_bridge(
    s: Structure,
    start: tuple[int, int, int],
    end: tuple[int, int, int],
    category: str = "spiral_walkway",
) -> set[tuple[int, int, int]]:
    bridge_blocks: set[tuple[int, int, int]] = set()
    sx, sy, sz = start
    ex, ey, ez = end
    y = ey
    dx = ex - sx
    dz = ez - sz
    steps = max(abs(dx), abs(dz), 1)
    perp_len = math.hypot(dx, dz) or 1.0
    perp = (-dz / perp_len, dx / perp_len)
    last: tuple[int, int] | None = None
    for i in range(steps + 1):
        t = i / steps
        cx = round(sx + dx * t)
        cz = round(sz + dz * t)
        if last is not None:
            lx, lz = last
            gap_steps = max(abs(cx - lx), abs(cz - lz), 1)
            for g in range(1, gap_steps):
                ix = round(lx + (cx - lx) * g / gap_steps)
                iz = round(lz + (cz - lz) * g / gap_steps)
                for off in range(-1, 2):
                    x = round(ix + perp[0] * off)
                    z = round(iz + perp[1] * off)
                    s.set(x, y, z, "stone_bricks", category)
                    s.set(x, y - 1, z, "deepslate_bricks", category)
                    bridge_blocks.add((x, y, z))
                    s.bridge_mask.add((x, y, z))
                    s.protect(x, y, z)
                    s.protect(x, y - 1, z)
        for off in range(-1, 2):
            x = round(cx + perp[0] * off)
            z = round(cz + perp[1] * off)
            s.set(x, y, z, "stone_bricks", category)
            s.set(x, y - 1, z, "deepslate_bricks", category)
            bridge_blocks.add((x, y, z))
            s.bridge_mask.add((x, y, z))
            s.protect(x, y, z)
            s.protect(x, y - 1, z)
            if abs(off) == 1 and i % 3 == 0:
                s.set(x, y + 1, z, "deepslate_bricks", category)
                s.protect(x, y + 1, z)
        last = (cx, cz)
    return bridge_blocks


def repair_bridge_endpoint(s: Structure, point: tuple[int, int, int]) -> int:
    repaired = 0
    x, y, z = point
    for dz in range(-1, 2):
        for dx in range(-1, 2):
            if s.set(x + dx, y, z + dz, "stone_bricks", "spiral_walkway"):
                repaired += 1
            s.set(x + dx, y - 1, z + dz, "deepslate_bricks", "spiral_walkway")
            s.bridge_mask.add((x + dx, y, z + dz))
            s.protect(x + dx, y, z + dz)
            s.protect(x + dx, y - 1, z + dz)
    return repaired


def mask_touches(a: set[tuple[int, int, int]], b: set[tuple[int, int, int]]) -> bool:
    for x, y, z in a:
        if (x, y, z) in b:
            return True
        for dy in (-1, 0, 1):
            for dz in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == dy == dz == 0:
                        continue
                    if (x + dx, y + dy, z + dz) in b:
                        return True
    return False


def validate_bridge_connectivity(
    bridge_blocks: set[tuple[int, int, int]],
    deck_mask: set[tuple[int, int, int]],
    landing_pad_mask: set[tuple[int, int, int]],
) -> tuple[bool, bool]:
    return mask_touches(bridge_blocks, deck_mask), mask_touches(bridge_blocks, landing_pad_mask)


def nearest_mask_point(point: tuple[int, int, int], mask: set[tuple[int, int, int]], max_radius: int = 10) -> tuple[int, int, int] | None:
    px, py, pz = point
    candidates = [
        (abs(x - px) + abs(y - py) * 3 + abs(z - pz), (x, y, z))
        for x, y, z in mask
        if abs(x - px) <= max_radius and abs(y - py) <= 4 and abs(z - pz) <= max_radius
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def build_connection_bridges(s: Structure, docking_points: list[DockingPoint]) -> None:
    for bridge_id, dock in enumerate(docking_points, start=1):
        dock_xyz = (dock.x, dock.walkable_y, dock.z)
        spiral = nearest_spiral_point_for_dock(dock.walkable_y, dock_xyz)
        start = (spiral[0], dock.walkable_y, spiral[2])
        end = dock_xyz
        bridge_blocks = build_discrete_bridge(s, start, end)
        repaired = 0
        spiral_ok, landing_ok = validate_bridge_connectivity(bridge_blocks, s.deck_mask, s.landing_pad_mask)
        if not spiral_ok:
            nearest_deck = nearest_mask_point(start, s.deck_mask)
            if nearest_deck is not None:
                extra = build_discrete_bridge(s, start, nearest_deck)
                repaired += len(extra)
                bridge_blocks.update(extra)
                s.deck_mask.update(extra)
            repaired += repair_bridge_endpoint(s, start)
            for dx in range(-1, 2):
                for dz in range(-1, 2):
                    s.deck_mask.add((start[0] + dx, start[1], start[2] + dz))
                    bridge_blocks.add((start[0] + dx, start[1], start[2] + dz))
        if not landing_ok:
            repaired += repair_bridge_endpoint(s, end)
            bridge_blocks.update((end[0] + dx, end[1], end[2] + dz) for dx in range(-1, 2) for dz in range(-1, 2))
        spiral_ok, landing_ok = validate_bridge_connectivity(bridge_blocks, s.deck_mask, s.landing_pad_mask)
        s.bridge_reports.append({
            "bridge_id": bridge_id,
            "floor": dock.walkable_y,
            "dock": end,
            "start": start,
            "end": end,
            "connected_to_landing": landing_ok,
            "connected_to_spiral": spiral_ok,
            "repaired_blocks_count": repaired,
        })


def build_lantern_on_branch(s: Structure, theta: float, radius: float, y: int, color_index: int) -> None:
    colors = [
        ("cyan_stained_glass", "sea_lantern"),
        ("lime_stained_glass", "shroomlight"),
        ("pink_stained_glass", "sea_lantern"),
        ("yellow_stained_glass", "glowstone"),
        ("white_stained_glass", "glowstone"),
    ]
    length = 5 + color_index % 4
    start = radius + 4
    end = min(radius + 4 + length, 61)
    for r in range(round(start), round(end) + 1):
        x = round(CX + math.cos(theta) * r)
        z = round(CZ + math.sin(theta) * r)
        s.set(x, y, z, "dark_oak_log" if color_index % 2 else "deepslate_bricks", "lanterns")
    lx = round(CX + math.cos(theta) * (end + 1))
    lz = round(CZ + math.sin(theta) * (end + 1))
    chain_len = 3 + color_index % 2
    for yy in range(y - chain_len, y + 1):
        s.set(lx, yy, lz, "iron_bars", "lanterns")
    glass, core = colors[color_index % len(colors)]
    cy = y - chain_len - 2
    lantern_radius = 1
    for dy in range(-lantern_radius, lantern_radius + 1):
        for dz in range(-1, 2):
            for dx in range(-1, 2):
                if abs(dx) + abs(dy) + abs(dz) <= 3:
                    s.set(lx + dx, cy + dy, lz + dz, glass, "lanterns")
    s.set(lx, cy, lz, core, "lanterns")
    s.set(lx, cy - 2, lz, "iron_bars", "lanterns")


def build_lantern_branches_along_spiral(s: Structure, lantern_count: int = 26) -> int:
    for i in range(lantern_count):
        t = (i + 0.45) / lantern_count
        theta, radius, y, _ = walkway_point(t)
        build_lantern_on_branch(s, theta, radius, y - 1, i)
    return lantern_count


def faceted_color(dx: int, dy: int, dz: int, shell_index: int) -> str:
    colors = ("cyan_stained_glass", "lime_stained_glass", "pink_stained_glass", "yellow_stained_glass")
    return colors[(dx * 7 + dz * 11 + shell_index) % len(colors)]


def build_single_crystal(
    s: Structure,
    cx: int,
    cz: int,
    y0: int,
    y1: int,
    max_radius: int,
    shell_index: int,
) -> None:
    mid = (y0 + y1) / 2
    half = max(1.0, (y1 - y0) / 2)
    for y in range(y0, y1 + 1):
        taper = max(0.0, 1.0 - abs(y - mid) / half)
        radius = max(1, round(1 + (max_radius - 1) * taper))
        for dz in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                d = abs(dx) + abs(dz)
                if d > radius:
                    continue
                core = d <= max(1, radius - 3)
                if core:
                    block = "sea_lantern" if (xhash := (dx * 11 + dz * 7 + y)) % 5 else "glowstone"
                    if xhash % 7 == 0:
                        block = "white_stained_glass"
                elif d >= radius - 1:
                    block = faceted_color(dx, y - y0, dz, shell_index)
                else:
                    block = "white_stained_glass" if (dx * dz + shell_index) % 5 == 0 else faceted_color(dx, y - y0, dz, shell_index + 1)
                s.set(cx + dx, y, cz + dz, block, "central_crystal")


def build_central_crystal_core(s: Structure) -> None:
    build_single_crystal(s, CX, CZ, 50, 108, 5, 0)
    satellites = [
        (CX + 5, CZ + 2, 60, 76, 2, 1),
        (CX - 5, CZ - 2, 62, 78, 2, 2),
        (CX - 2, CZ + 5, 77, 94, 2, 3),
        (CX + 2, CZ - 5, 80, 98, 2, 4),
    ]
    for args in satellites:
        build_single_crystal(s, *args)
    for y in (63, 73, 85):
        for angle in range(0, 360, 60):
            rad = math.radians(angle)
            s.set(round(CX + math.cos(rad) * 8), y, round(CZ + math.sin(rad) * 8), "sea_lantern", "central_crystal")


def build_ordered_magic_crystal_core(s: Structure) -> None:
    build_central_crystal_core(s)


def build_roof_spire(s: Structure) -> None:
    tiers = [
        (110, 114, 25, 22),
        (115, 125, 21, 16),
        (126, 136, 16, 10),
        (137, 147, 10, 4),
        (148, 151, 4, 2),
    ]
    eaves = {
        108: 27,
        109: 26,
        114: 23,
        125: 18,
        136: 12,
        147: 6,
    }
    for y, radius in eaves.items():
        for z in range(CZ - radius - 2, CZ + radius + 3):
            for x in range(CX - radius - 2, CX + radius + 3):
                r = oct_metric(x - CX, z - CZ)
                if radius - 3 <= r <= radius:
                    s.set(x, y, z, "deepslate_tiles", "roof")
                    s.set(x, y - 1, z, "deepslate_bricks", "roof")
    for y0, y1, r0, r1 in tiers:
        for y in range(y0, y1 + 1):
            t = 0 if y1 == y0 else (y - y0) / (y1 - y0)
            radius = round(r0 + (r1 - r0) * (t ** 0.75))
            for z in range(CZ - radius - 2, CZ + radius + 3):
                for x in range(CX - radius - 2, CX + radius + 3):
                    r = oct_metric(x - CX, z - CZ)
                    if r <= radius:
                        a = angle_of(x - CX, z - CZ)
                        rib = any(angle_delta(a, p) < 3 for p in range(0, 360, 45))
                        band = y in (114, 125, 136, 147)
                        if band or rib:
                            block = "deepslate_tiles"
                        else:
                            block = "weathered_copper" if (a // 45 + y // 5) % 5 == 0 else "oxidized_copper"
                        s.set(x, y, z, block, "roof")
    for y in range(151, 158):
        s.set(CX, y, CZ, "gold_block", "roof")
    for y in range(153, 158):
        for dz in (-1, 0, 1):
            if dz == 0:
                continue
            s.set(CX, y, CZ + dz, "gold_block", "roof")


def build_hanging_bottom_crystal(s: Structure) -> None:
    segments = [
        (30, 38, 3, 9),
        (13, 29, 1, 5),
        (6, 12, 1, 2),
    ]
    for y0, y1, r_tip, r_mid in segments:
        mid = (y0 + y1) / 2
        half = max(1.0, (y1 - y0) / 2)
        for y in range(y0, y1 + 1):
            taper = 1.0 - abs(y - mid) / half
            radius = max(r_tip, round(r_tip + (r_mid - r_tip) * taper))
            for z in range(CZ - radius, CZ + radius + 1):
                for x in range(CX - radius, CX + radius + 1):
                    d = abs(x - CX) + abs(z - CZ)
                    if d <= radius:
                        if d >= radius - 1:
                            block = "blue_stained_glass"
                        elif d <= 1:
                            block = "sea_lantern" if y % 3 else "white_stained_glass"
                        elif (x + y + z) % 5 == 0:
                            block = "sea_lantern"
                        else:
                            block = "cyan_stained_glass" if (x - z + y) % 2 else "packed_ice"
                        s.set(x, y, z, block, "bottom_crystal")
    for y in (29, 30, 12, 13, 6):
        s.set(CX, y, CZ, "sea_lantern", "bottom_crystal")
        s.set(CX + 1, y, CZ, "cyan_stained_glass", "bottom_crystal")
        s.set(CX - 1, y, CZ, "cyan_stained_glass", "bottom_crystal")


def main() -> None:
    s = Structure()
    build_central_library_core(s)
    docking_points = define_docking_points()
    rebuild_internal_system(s, docking_points)
    build_spiral_walkway(s)
    build_connection_bridges(s, docking_points)
    deck_repaired_blocks = repair_deck_connectivity(s)
    build_walkway_edges(s)
    lantern_count = build_lantern_branches_along_spiral(s)
    build_ordered_magic_crystal_core(s)
    build_roof_spire(s)
    build_hanging_bottom_crystal(s)
    carve_openings(s, docking_points)
    cleanup_floating_blocks(s)
    write_mcstructure(s)

    counts = Counter(s.blocks)
    non_air = len(s.blocks) - counts[0]
    print(f"Wrote {OUT_PATH}")
    print(f"Palette entries: {len(BLOCKS)}")
    print(f"Non-air blocks: {non_air}")
    print(f"Bookshelf blocks: {counts[PALETTE['bookshelf']]}")
    print(f"Spiral walkway blocks: {s.stats['spiral_walkway']}")
    print(f"Lantern count: {lantern_count}")
    print(f"Lantern blocks: {s.stats['lanterns']}")
    print(f"Central crystal blocks: {s.stats['central_crystal']}")
    print(f"Roof blocks: {s.stats['roof']}")
    print(f"Bottom crystal blocks: {s.stats['bottom_crystal']}")
    print(f"detached_edge_blocks_removed: {s.detached_edge_blocks_removed}")
    print(f"floating_support_blocks_removed: {s.floating_support_blocks_removed}")
    print(f"deck_connectivity_repaired_blocks: {deck_repaired_blocks}")
    for report in s.bridge_reports:
        print(
            "Bridge {bridge_id}: floor={floor} dock={dock} start={start} end={end} "
            "connected_to_landing={connected_to_landing} connected_to_spiral={connected_to_spiral} "
            "repaired_blocks_count={repaired_blocks_count}".format(**report)
        )
    validate_connectivity(s, docking_points)
    validate_interior_connectivity(s, docking_points)


if __name__ == "__main__":
    main()
