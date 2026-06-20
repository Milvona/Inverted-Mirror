from __future__ import annotations

import math
import os
from collections import Counter
from dataclasses import dataclass, field

from PIL import Image, ImageDraw

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
    lower_taper_mask: set[tuple[int, int, int]] = field(default_factory=set)
    bottom_root_mask: set[tuple[int, int, int]] = field(default_factory=set)
    curb_mask: set[tuple[int, int, int]] = field(default_factory=set)
    support_mask: set[tuple[int, int, int]] = field(default_factory=set)
    bridge_mask: set[tuple[int, int, int]] = field(default_factory=set)
    landing_pad_mask: set[tuple[int, int, int]] = field(default_factory=set)
    main_ring_masks: dict[str, set[tuple[int, int, int]]] = field(default_factory=dict)
    stair_masks: dict[str, set[tuple[int, int, int]]] = field(default_factory=dict)
    protected_mask: set[tuple[int, int, int]] = field(default_factory=set)
    removed_debug: list[tuple[int, int, int, str]] = field(default_factory=list)
    detached_edge_blocks_removed: int = 0
    detached_noise_removed: int = 0
    detached_lantern_parts_removed: int = 0
    floating_support_blocks_removed: int = 0
    removed_internal_clutter_count: int = 0
    repaired_walkway_blocks: int = 0
    repaired_bridge_blocks: int = 0

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
            if category in PROTECTED_TAGS:
                self.protect(x, y, z)
        return True

    def carve(self, x: int, y: int, z: int) -> bool:
        if (x, y, z) in self.protected_mask:
            return False
        return self.set(x, y, z, "air", "air")

    def force_carve(self, x: int, y: int, z: int) -> bool:
        return self.set(x, y, z, "air", "air")

    def remove_tagged(self, x: int, y: int, z: int, reason: str) -> bool:
        if (x, y, z) in self.protected_mask:
            return False
        if not self.is_solid(x, y, z):
            return False
        self.removed_debug.append((x, y, z, reason))
        return self.carve(x, y, z)

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


PROTECTED_TAGS = {
    "spiral_deck",
    "bridge_deck",
    "landing_pad",
    "doorway_frame",
    "main_ring_corridor",
    "stair",
    "atrium_rim",
    "central_crystal_core",
}


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
    for y, radius, height in ((44, 22, 22), (72, 25, 22), (100, 20, 16)):
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
                s.set(x, y, z, "deepslate_bricks", "doorway_frame")
                s.protect(x, y, z)
        for w in range(-half - 1, half + 2):
            x = round(dock.doorway_center_x + tx * w)
            z = round(dock.doorway_center_z + tz * w)
            s.set(x, dock.walk_y + dock.opening_height + 1, z, "dark_oak_log", "doorway_frame")
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
        slab_radius = {"lower": 22, "middle": 25, "upper": 20}[str(level["name"])]
        rim_radius = slab_radius - 2
        for y in range(level["floor_slab_min_y"], level["floor_slab_max_y"] + 1):
            for z in range(CZ - slab_radius - 1, CZ + slab_radius + 2):
                for x in range(CX - slab_radius - 1, CX + slab_radius + 2):
                    if is_inside_octagon(x, z, CX, CZ, slab_radius) and get_radial_distance(x, z) >= 6:
                        r = get_radial_distance(x, z)
                        block = "deepslate_bricks" if r >= rim_radius or y < level["floor_slab_max_y"] else floor_block(x, z)
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


def build_main_ring_corridor(s: Structure) -> None:
    for level in LEVELS:
        mask: set[tuple[int, int, int]] = set()
        y = level["walk_y"]
        for z in range(CZ - 14, CZ + 15):
            for x in range(CX - 14, CX + 15):
                r = get_radial_distance(x, z)
                if 8 <= r <= 13 and is_inside_octagon(x, z, CX, CZ, 15):
                    block = "deepslate_tiles" if int(r) in (8, 13) else floor_block(x, z)
                    s.set(x, y, z, block, "main_ring_corridor")
                    s.set(x, y - 1, z, "deepslate_bricks", "main_ring_corridor")
                    mask.add((x, y, z))
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


def strengthen_vertical_continuity(s: Structure, docking_points: list[DockingPoint]) -> None:
    dock_angles = [get_polar_angle(d.doorway_center_x, d.doorway_center_z) for d in docking_points]
    for angle in range(0, 360, 45):
        if any(angle_delta(angle, da) < 10 for da in dock_angles):
            continue
        rad = math.radians(angle)
        radius = 22 if angle % 90 == 0 else 21
        column_half = 1 if angle % 90 == 0 else 0
        cx = round(CX + math.cos(rad) * radius)
        cz = round(CZ + math.sin(rad) * radius)
        for y in range(42, 121):
            for dz in range(-column_half, column_half + 1):
                for dx in range(-column_half, column_half + 1):
                    if column_half and abs(dx) + abs(dz) > 1:
                        continue
                    block = "deepslate_bricks" if y % 7 in (0, 1, 2, 3) else "dark_oak_log"
                    s.set(cx + dx, y, cz + dz, block, "main_pillar")
                    s.protect(cx + dx, y, cz + dz)
    for y in (44, 50, 68, 72, 78, 96, 100, 106):
        for z in range(CZ - 25, CZ + 26):
            for x in range(CX - 25, CX + 26):
                r = oct_metric(x - CX, z - CZ)
                if 22.0 <= r <= 24.5 and is_inside_octagon(x, z, CX, CZ, 25):
                    block = "deepslate_bricks" if y in (44, 72, 100, 106) else "dark_oak_log"
                    if (x + z + y) % 4 != 0:
                        s.set(x, y, z, block, "ring_beam")
                        s.protect(x, y, z)


MEZZANINE_MASKS: dict[str, set[tuple[int, int, int]]] = {}


def angle_in_sector(angle: float, sector: tuple[float, float]) -> bool:
    a0, a1 = sector
    if a0 <= a1:
        return a0 <= angle <= a1
    return angle >= a0 or angle <= a1


def build_mezzanine_platforms(s: Structure, docking_points: list[DockingPoint]) -> None:
    configs = [
        ("lower", 50, [(145, 205), (255, 325), (10, 55)], 4),
        ("middle", 78, [(20, 75), (115, 165), (200, 250), (295, 340)], 6),
    ]
    dock_angles = [get_polar_angle(d.doorway_center_x, d.doorway_center_z) for d in docking_points]
    for name, y, sectors, shelf_height in configs:
        mask: set[tuple[int, int, int]] = set()
        for z in range(CZ - 24, CZ + 25):
            for x in range(CX - 24, CX + 25):
                r = get_radial_distance(x, z)
                a = get_polar_angle(x, z)
                if not (15 <= r <= 22 and is_inside_octagon(x, z, CX, CZ, 24)):
                    continue
                if any(angle_delta(a, da) < 18 for da in dock_angles):
                    continue
                if not any(angle_in_sector(a, sector) for sector in sectors):
                    continue
                rim = r >= 21 or r <= 15.8
                s.set(x, y, z, "deepslate_tiles" if rim else floor_block(x, z), "mezzanine_floor")
                s.set(x, y - 1, z, "dark_oak_planks", "mezzanine_floor")
                mask.add((x, y, z))
                for clear_y in range(y + 1, y + 4):
                    s.carve(x, clear_y, z)
                if 18 <= r <= 22 and int(a) % 9 not in (0, 1, 2):
                    for yy in range(y + 1, y + shelf_height + 1):
                        if yy % 4 == 0 or int(a) % 21 == 0:
                            s.set(x, yy, z, "dark_oak_log", "mezzanine_bookshelf")
                        else:
                            s.set(x, yy, z, "bookshelf", "mezzanine_bookshelf")
        MEZZANINE_MASKS[name] = mask


def build_short_mezzanine_stair(
    s: Structure,
    key: str,
    base_y: int,
    top_y: int,
    start: tuple[int, int],
    direction: tuple[int, int],
) -> None:
    sx, sz = start
    dx, dz = direction
    perp = (-dz, dx)
    mask = s.stair_masks.setdefault(key, set())
    steps = top_y - base_y
    for i in range(steps + 1):
        y = base_y + i
        cx = sx + dx * (i + 1)
        cz = sz + dz * (i + 1)
        for w in range(-1, 2):
            x = cx + perp[0] * w
            z = cz + perp[1] * w
            s.set(x, y, z, "stone_bricks" if w == 0 else "deepslate_tiles", "stair")
            s.set(x, y - 1, z, "deepslate_bricks", "stair")
            mask.add((x, y, z))
            s.protect(x, y, z)
            s.protect(x, y - 1, z)
            for clear_y in range(y + 1, y + 4):
                s.carve(x, clear_y, z)


def build_mezzanine_stairs(s: Structure) -> None:
    build_short_mezzanine_stair(s, "lower_mezzanine_A", 45, 50, (52, 60), (-1, 0))
    build_short_mezzanine_stair(s, "lower_mezzanine_B", 45, 50, (76, 69), (1, 0))
    build_short_mezzanine_stair(s, "middle_mezzanine_A", 73, 78, (54, 55), (-1, 0))
    build_short_mezzanine_stair(s, "middle_mezzanine_B", 73, 78, (74, 74), (1, 0))


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
            s.set(x, y, z, "deepslate_tiles" if w else "stone_bricks", "stair")
            s.set(x, y - 1, z, "deepslate_bricks", "stair")
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


def enhance_library_readability(s: Structure, docking_points: list[DockingPoint]) -> None:
    dock_angles = [get_polar_angle(d.doorway_center_x, d.doorway_center_z) for d in docking_points]
    configs = [
        ("lower", 45, 4, (18, 21), (120, 170, 205, 250, 300, 340)),
        ("middle", 73, 7, (17, 23), (25, 70, 115, 160, 205, 250, 295, 340)),
    ]
    for name, walk_y, height, r_range, angles in configs:
        for angle in angles:
            if any(angle_delta(angle, da) < 18 for da in dock_angles):
                continue
            rad = math.radians(angle)
            normal = (math.cos(rad), math.sin(rad))
            tangent = (-math.sin(rad), math.cos(rad))
            for w in range(-4, 5):
                for depth in range(0, 2):
                    r = r_range[1] - depth
                    x = round(CX + normal[0] * r + tangent[0] * w)
                    z = round(CZ + normal[1] * r + tangent[1] * w)
                    if get_radial_distance(x, z) < 15:
                        continue
                    for y in range(walk_y + 1, walk_y + height + 1):
                        frame = abs(w) == 4 or y in (walk_y + 1, walk_y + height) or w == 0 and y % 3 == 0
                        block = "dark_oak_log" if frame else "bookshelf"
                        s.set(x, y, z, block, "bookshelf_zone")
    # Small paired reading counters near the ring, low enough to keep the crystal visible.
    for walk_y, angles in ((45, (150, 210, 320)), (73, (35, 145, 215, 325))):
        for angle in angles:
            rad = math.radians(angle)
            tangent = (-math.sin(rad), math.cos(rad))
            bx = round(CX + math.cos(rad) * 12)
            bz = round(CZ + math.sin(rad) * 12)
            for w in range(-2, 3):
                x = round(bx + tangent[0] * w)
                z = round(bz + tangent[1] * w)
                s.set(x, walk_y + 1, z, "bookshelf", "low_shelf")
                if w in (-2, 2):
                    s.set(x, walk_y + 2, z, "dark_oak_planks", "low_shelf")


def cleanup_internal_clutter(s: Structure, docking_points: list[DockingPoint] | None = None) -> None:
    removed = 0
    for level in LEVELS:
        y = level["walk_y"]
        for z in range(CZ - 14, CZ + 15):
            for x in range(CX - 14, CX + 15):
                r = get_radial_distance(x, z)
                if 8 <= r <= 13:
                    for yy in range(y + 1, y + 4):
                        if (x, yy, z) not in s.protected_mask and s.is_solid(x, yy, z):
                            s.removed_debug.append((x, yy, z, "internal"))
                            s.carve(x, yy, z)
                            removed += 1
        for z in range(CZ - 7, CZ + 8):
            for x in range(CX - 7, CX + 8):
                if is_inside_octagon(x, z, CX, CZ, 6):
                    for yy in range(level["room_min_y"], level["room_max_y"] + 1):
                        cat = s.categories[index(x, yy, z)] if in_bounds(x, yy, z) else "air"
                        if (x, yy, z) not in s.protected_mask and s.is_solid(x, yy, z) and cat != "central_crystal_core":
                            s.removed_debug.append((x, yy, z, "internal"))
                            s.carve(x, yy, z)
                            removed += 1
    if docking_points:
        for dock in docking_points:
            fx, fz = dock.facing_vector
            tx, tz = dock.tangent_vector
            flen = max(1.0, math.hypot(fx, fz))
            back_x, back_z = -fx / flen, -fz / flen
            half = dock.opening_width // 2
            for depth in range(-1, 6):
                for w in range(-half, half + 1):
                    x = round(dock.doorway_center_x + tx * w + back_x * depth)
                    z = round(dock.doorway_center_z + tz * w + back_z * depth)
                    for yy in range(dock.walk_y + 1, dock.walk_y + dock.opening_height):
                        if s.is_solid(x, yy, z) and (x, yy, z) not in s.protected_mask:
                            s.removed_debug.append((x, yy, z, "doorway"))
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
    build_mezzanine_platforms(s, docking_points)
    build_mezzanine_stairs(s)
    enhance_library_readability(s, docking_points)
    strengthen_vertical_continuity(s, docking_points)
    carve_openings(s, docking_points)
    cleanup_internal_clutter(s, docking_points)


def soften_lower_outer_platform(s: Structure, docking_points: list[DockingPoint]) -> None:
    dock_angles = [get_polar_angle(d.doorway_center_x, d.doorway_center_z) for d in docking_points if d.walk_y == 45]
    for y in range(42, 45):
        for z in range(CZ - 27, CZ + 28):
            for x in range(CX - 27, CX + 28):
                if not in_bounds(x, y, z):
                    continue
                r = get_radial_distance(x, z)
                if r < 20 or r > 26:
                    continue
                cat = s.categories[index(x, y, z)]
                if cat not in {"library_core", "ring_beam"}:
                    continue
                a = get_polar_angle(x, z)
                near_dock = any(angle_delta(a, da) < 26 for da in dock_angles)
                near_column = any(angle_delta(a, p) < 5 for p in range(0, 360, 45))
                if near_dock or near_column:
                    continue
                # Leave alternating stone teeth instead of a continuous visual disk.
                if (int(a // 9) + int(r) + y) % 3 != 0:
                    s.removed_debug.append((x, y, z, "lower_platform_soften"))
                    s.carve(x, y, z)


def carve_front_cut_visibility(s: Structure) -> None:
    for yy in range(48, 101):
        for z in range(CZ + 6, CZ + 28):
            span = int(6 + (z - (CZ + 6)) * 0.35)
            for x in range(CX - span, CX + span + 1):
                if yy % 28 not in (0, 1, 2):
                    s.carve(x, yy, z)


LOWER_TAPER_END = 0.30
UPPER_TAPER_START = 0.82
BOTTOM_APEX_ROOT_Y = 38
BOTTOM_APEX_ROOT_RADIUS = 7


def smoothstep(u: float) -> float:
    u = max(0.0, min(1.0, u))
    return u * u * (3.0 - 2.0 * u)


def walkway_point(t: float) -> tuple[float, float, int, float]:
    if t < LOWER_TAPER_END:
        u = smoothstep(t / LOWER_TAPER_END)
        theta0 = -math.pi * 1.62
        theta = theta0 + math.pi * 1.82 * u
        radius = 9.5 + (40.5 - 9.5) * (u ** 0.9)
        radius += 0.7 * math.sin(theta * 1.7) * u
        y = round(BOTTOM_APEX_ROOT_Y + (49 - BOTTOM_APEX_ROOT_Y) * u)
        return theta, radius, y, t

    if t <= UPPER_TAPER_START:
        u = (t - LOWER_TAPER_END) / (UPPER_TAPER_START - LOWER_TAPER_END)
        theta0 = -math.pi * 1.62 + math.pi * 1.82
        theta = theta0 + math.pi * 3.45 * u
        radius = 41.5 + 3.0 * math.sin(theta * 0.8) + 1.3 * math.sin(theta * 2.0) + 1.2 * u
        y = round(52 + (92 - 52) * u)
        return theta, radius, y, t

    u = smoothstep((t - UPPER_TAPER_START) / (1.0 - UPPER_TAPER_START))
    theta0 = -math.pi * 1.62 + math.pi * 1.82 + math.pi * 3.45
    theta = theta0 + math.pi * 1.07 * u
    radius = 42.0 - 17.0 * (u ** 1.2) + 0.8 * math.sin(theta * 1.3)
    y = round(92 + (104 - 92) * u)
    return theta, radius, y, t


def walkway_width_at(t: float) -> float:
    if t < LOWER_TAPER_END:
        u = smoothstep(t / LOWER_TAPER_END)
        return 2.0 + (4.0 - 2.0) * u
    if t > UPPER_TAPER_START:
        u = smoothstep((t - UPPER_TAPER_START) / (1.0 - UPPER_TAPER_START))
        return 4.0 - 1.4 * u
    return 4.0


def build_spiral_walkway(s: Structure, turns: float = 2.5, y_start: int = 34, y_end: int = 104) -> list[tuple[float, float, int]]:
    points: list[tuple[float, float, int]] = []
    steps = 1650
    width = 4.0
    for step in range(steps + 1):
        t = step / steps
        theta, radius, y, _ = walkway_point(t)
        local_width = walkway_width_at(t)
        px = CX + math.cos(theta) * radius
        pz = CZ + math.sin(theta) * radius
        radial = (math.cos(theta), math.sin(theta))
        tangent = (-math.sin(theta), math.cos(theta))
        half_width = local_width / 2
        for z in range(math.floor(pz - local_width), math.ceil(pz + local_width + 1)):
            for x in range(math.floor(px - local_width), math.ceil(px + local_width + 1)):
                cross = (x - px) * radial[0] + (z - pz) * radial[1]
                along = (x - px) * tangent[0] + (z - pz) * tangent[1]
                if abs(cross) <= half_width and abs(along) <= 1.85:
                    edge = abs(cross) > half_width - 0.7
                    s.set(x, y, z, "deepslate_bricks" if edge else "stone_bricks", "spiral_deck")
                    s.set(x, y - 1, z, "deepslate_tiles" if edge else "deepslate_bricks", "spiral_deck")
                    s.deck_mask.add((x, y, z))
                    if t < LOWER_TAPER_END:
                        s.lower_taper_mask.add((x, y, z))
        if step % 18 == 0:
            points.append((theta, radius, y))
    return points


def neighbor4(x: int, y: int, z: int) -> list[tuple[int, int, int]]:
    return [(x + 1, y, z), (x - 1, y, z), (x, y, z + 1), (x, y, z - 1)]


def build_walkway_edges(s: Structure) -> None:
    edge_candidates: set[tuple[int, int, int]] = set()
    for x, y, z in s.deck_mask:
        for nx, ny, nz in neighbor4(x, y, z):
            if (nx, ny, nz) not in s.deck_mask and (nx, ny, nz) not in s.bridge_mask:
                edge_candidates.add((nx, y + 1, nz))
    for i, (x, y, z) in enumerate(sorted(edge_candidates)):
        if (x * 17 + z * 31 + y) % 10 in (0, 1, 2):
            continue
        if any(n in s.deck_mask or n in s.bridge_mask for n in neighbor4(x, y - 1, z)):
            s.set(x, y, z, "deepslate_bricks", "spiral_curb")
            s.curb_mask.add((x, y, z))
    # Connected ribs and underside supports. They always touch deck at the top.
    for i, (x, y, z) in enumerate(sorted(s.deck_mask)):
        is_lower = (x, y, z) in s.lower_taper_mask
        spacing = 310 if is_lower else 155
        if i % spacing != 0:
            continue
        support_len = (2 + ((x * 13 + z * 7 + y) % 3)) if is_lower else (3 + ((x * 13 + z * 7 + y) % 5))
        for yy in range(y - support_len, y):
            s.set(x, yy, z, "deepslate_bricks", "spiral_support")
            s.support_mask.add((x, yy, z))


def build_bottom_taper_root(s: Structure) -> None:
    y = BOTTOM_APEX_ROOT_Y
    for yy, radius in ((y + 4, 12), (y + 2, 9), (y + 1, 8), (y, 7), (y - 1, 5)):
        for z in range(CZ - radius - 1, CZ + radius + 2):
            for x in range(CX - radius - 1, CX + radius + 2):
                r = oct_metric(x - CX, z - CZ)
                if radius - 2 <= r <= radius:
                    block = "deepslate_tiles" if yy >= y else "deepslate_bricks"
                    s.set(x, yy, z, block, "bottom_root")
                    s.bottom_root_mask.add((x, yy, z))
    for yy, radius in ((y + 3, 6), (y + 2, 5), (y + 1, 4)):
        for z in range(CZ - radius, CZ + radius + 1):
            for x in range(CX - radius, CX + radius + 1):
                if oct_metric(x - CX, z - CZ) <= radius and oct_metric(x - CX, z - CZ) >= max(2, radius - 1):
                    s.set(x, yy, z, "deepslate_bricks", "bottom_root")
                    s.bottom_root_mask.add((x, yy, z))
    # Narrow neck from lower taper start toward the crystal root.
    theta, radius, start_y, _ = walkway_point(0.0)
    sx = round(CX + math.cos(theta) * radius)
    sz = round(CZ + math.sin(theta) * radius)
    steps = max(abs(sx - CX), abs(sz - CZ), 1)
    for i in range(steps + 1):
        u = i / steps
        x = round(sx + (CX - sx) * u)
        z = round(sz + (CZ - sz) * u)
        yy = round(start_y + (y - start_y) * u)
        width = 1 if i < steps * 0.55 else 2
        for dz in range(-width, width + 1):
            for dx in range(-width, width + 1):
                if abs(dx) + abs(dz) <= width:
                    s.set(x + dx, yy, z + dz, "stone_bricks" if i < steps - 2 else "deepslate_tiles", "bottom_root")
                    s.set(x + dx, yy - 1, z + dz, "deepslate_bricks", "bottom_root")
                    s.bottom_root_mask.add((x + dx, yy, z + dz))
                    s.lower_taper_mask.add((x + dx, yy, z + dz))
                    s.deck_mask.add((x + dx, yy, z + dz))
    # Small luminous socket where the blue pendant begins.
    for yy in range(y - 2, y + 2):
        for dz in range(-2, 3):
            for dx in range(-2, 3):
                if abs(dx) + abs(dz) <= 2:
                    block = "sea_lantern" if yy == y - 1 and abs(dx) + abs(dz) <= 1 else "cyan_stained_glass"
                    s.set(CX + dx, yy, CZ + dz, block, "bottom_crystal")


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


def tag_at(s: Structure, p: tuple[int, int, int]) -> str:
    x, y, z = p
    if not in_bounds(x, y, z):
        return "air"
    return s.categories[index(x, y, z)]


def neighbors6(p: tuple[int, int, int]) -> list[tuple[int, int, int]]:
    x, y, z = p
    return [
        (x + 1, y, z), (x - 1, y, z),
        (x, y + 1, z), (x, y - 1, z),
        (x, y, z + 1), (x, y, z - 1),
    ]


def neighbors18(p: tuple[int, int, int]) -> list[tuple[int, int, int]]:
    x, y, z = p
    out: list[tuple[int, int, int]] = []
    for dy in (-1, 0, 1):
        for dz in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == dy == dz == 0:
                    continue
                if abs(dx) + abs(dy) + abs(dz) <= 2:
                    out.append((x + dx, y + dy, z + dz))
    return out


def near_any_tag(s: Structure, p: tuple[int, int, int], tags: set[str], use_18: bool = True) -> bool:
    candidates = neighbors18(p) if use_18 else neighbors6(p)
    return any(tag_at(s, n) in tags for n in candidates)


def cleanup_detached_walkway_details(s: Structure) -> None:
    attached_tags = {
        "spiral_deck",
        "spiral_curb",
        "bridge_deck",
        "landing_pad",
        "library_core",
        "roof",
        "main_ring_corridor",
    }
    removed_curb = 0
    for p in list(s.curb_mask):
        if tag_at(s, p) != "spiral_curb":
            s.curb_mask.discard(p)
            continue
        if not near_any_tag(s, p, {"spiral_deck", "bridge_deck"}, True):
            if s.remove_tagged(*p, "curb"):
                removed_curb += 1
                s.curb_mask.discard(p)

    removed_support = 0
    for p in list(s.support_mask):
        if tag_at(s, p) != "spiral_support":
            s.support_mask.discard(p)
            continue
        x, y, z = p
        top_connected = tag_at(s, (x, y + 1, z)) in {"spiral_deck", "spiral_curb", "spiral_support", "bridge_deck"}
        side_connected = near_any_tag(s, p, {"spiral_deck", "spiral_curb", "spiral_support", "bridge_deck"}, False)
        if not top_connected and not side_connected:
            if s.remove_tagged(*p, "support"):
                removed_support += 1
                s.support_mask.discard(p)

    removed_noise = 0
    removed_lantern = 0
    for i, cat in enumerate(list(s.categories)):
        if cat not in {"decoration_noise", "lantern_branch", "lantern_chain", "lantern_body"}:
            continue
        x, y, z = coords_from_flat_index(i)
        p = (x, y, z)
        if cat == "decoration_noise":
            keep = near_any_tag(s, p, attached_tags, True)
            if not keep and s.remove_tagged(x, y, z, "noise"):
                removed_noise += 1
        elif cat == "lantern_branch":
            keep = near_any_tag(s, p, {"spiral_deck", "spiral_curb", "bridge_deck", "lantern_branch", "lantern_chain"}, True)
            if not keep and s.remove_tagged(x, y, z, "lantern"):
                removed_lantern += 1
        elif cat == "lantern_chain":
            keep = tag_at(s, (x, y + 1, z)) in {"lantern_chain", "lantern_branch", "spiral_deck", "spiral_curb", "bridge_deck"} or near_any_tag(s, p, {"lantern_body"}, False)
            if not keep and s.remove_tagged(x, y, z, "lantern"):
                removed_lantern += 1
        elif cat == "lantern_body":
            keep = near_any_tag(s, p, {"lantern_body", "lantern_chain"}, True)
            if not keep and s.remove_tagged(x, y, z, "lantern"):
                removed_lantern += 1

    s.detached_edge_blocks_removed += removed_curb
    s.floating_support_blocks_removed += removed_support
    s.detached_noise_removed = removed_noise
    s.detached_lantern_parts_removed = removed_lantern


def coords_from_flat_index(i: int) -> tuple[int, int, int]:
    x = i // (SIZE_Z * SIZE_Y)
    y = (i // SIZE_Z) % SIZE_Y
    z = i % SIZE_Z
    return x, y, z


def cleanup_floating_blocks(s: Structure) -> None:
    cleanup_detached_edge_blocks(s)
    cleanup_detached_walkway_details(s)


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
            s.set(x, y, z, "stone_bricks", "spiral_deck")
            s.set(x, y - 1, z, "deepslate_bricks", "spiral_deck")
            s.deck_mask.add((x, y, z))
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
        min_expected = max(20, dock.landing_width * dock.landing_depth)
        print(f"platform level {dock.level} connected: {count >= min_expected} flood_blocks={count}")

    for report in s.bridge_reports:
        connected = report["connected_to_landing"] and report["connected_to_spiral"]
        print(f"bridge {report['bridge_id']} connected: {connected}")

    deck_start = next(iter(s.deck_mask)) if s.deck_mask else None
    deck_connected = deck_start is not None and flood_count(s.deck_mask, deck_start) == len(s.deck_mask)
    print(f"spiral walkway deck connected: {deck_connected}")
    print(f"detached_edge_blocks_removed: {s.detached_edge_blocks_removed}")
    print(f"floating_support_blocks_removed: {s.floating_support_blocks_removed}")


def validate_walkable_connectivity(s: Structure, docking_points: list[DockingPoint]) -> dict[str, object]:
    deck_connected = bool(s.deck_mask) and flood_count(s.deck_mask, next(iter(s.deck_mask))) == len(s.deck_mask)
    if not deck_connected:
        s.repaired_walkway_blocks += repair_deck_connectivity(s)
        deck_connected = bool(s.deck_mask) and flood_count(s.deck_mask, next(iter(s.deck_mask))) == len(s.deck_mask)

    bridge_results: dict[str, bool] = {}
    landing_results: dict[str, bool] = {}
    blocked_doorways = 0
    for dock in docking_points:
        bridge = bridge_blocks_for_floor(s, dock.walk_y)
        landing = {p for p in s.landing_pad_mask if p[1] == dock.walk_y}
        ring = s.main_ring_masks.get(dock.level_name, set())
        bridge_ok = mask_touches(bridge, s.deck_mask) and mask_touches(bridge, landing)
        if not bridge_ok:
            before = len(s.bridge_mask)
            build_connection_bridges(s, [dock])
            s.repaired_bridge_blocks += max(0, len(s.bridge_mask) - before)
            bridge = bridge_blocks_for_floor(s, dock.walk_y)
            bridge_ok = mask_touches(bridge, s.deck_mask) and mask_touches(bridge, landing)
        bridge_results[dock.level_name] = bridge_ok
        landing_results[dock.level_name] = mask_touches(landing, ring)
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
    lower_mezz_stairs = s.stair_masks.get("lower_mezzanine_A", set()) | s.stair_masks.get("lower_mezzanine_B", set())
    middle_mezz_stairs = s.stair_masks.get("middle_mezzanine_A", set()) | s.stair_masks.get("middle_mezzanine_B", set())
    lower_mezz = MEZZANINE_MASKS.get("lower", set())
    middle_mezz = MEZZANINE_MASKS.get("middle", set())
    lower_mezz_connected = mask_touches(lower_mezz_stairs, s.main_ring_masks.get("lower", set())) and mask_touches(lower_mezz_stairs, lower_mezz)
    middle_mezz_connected = mask_touches(middle_mezz_stairs, s.main_ring_masks.get("middle", set())) and mask_touches(middle_mezz_stairs, middle_mezz)
    stair_a_connected = mask_touches(stair_a, s.main_ring_masks.get("lower", set())) and mask_touches(stair_a, s.main_ring_masks.get("middle", set()))
    stair_b_connected = mask_touches(stair_b, s.main_ring_masks.get("middle", set())) and mask_touches(stair_b, s.main_ring_masks.get("upper", set()))
    report: dict[str, object] = {
        "spiral_deck_connected": deck_connected,
        "lower_bridge_connected": bridge_results.get("lower", False),
        "middle_bridge_connected": bridge_results.get("middle", False),
        "upper_bridge_connected": bridge_results.get("upper", False),
        "lower_landing_to_ring_connected": landing_results.get("lower", False),
        "middle_landing_to_ring_connected": landing_results.get("middle", False),
        "upper_landing_to_ring_connected": landing_results.get("upper", False),
        "stair_A_connected": stair_a_connected,
        "stair_B_connected": stair_b_connected,
        "lower_mezzanine_connected": lower_mezz_connected,
        "middle_mezzanine_connected": middle_mezz_connected,
        "blocked_doorways": blocked_doorways,
        "repaired_walkway_blocks": s.repaired_walkway_blocks,
        "repaired_bridge_blocks": s.repaired_bridge_blocks,
        "all_bridges_connected": all(bridge_results.values()) if bridge_results else False,
        "all_landings_connected_to_ring": all(landing_results.values()) if landing_results else False,
    }
    for key, value in report.items():
        print(f"{key}: {value}")
    return report


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
                if is_inside_octagon(x, z, CX, CZ, 5) and s.is_solid(x, y, z) and s.categories[index(x, y, z)] != "central_crystal_core":
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
    category: str = "bridge_deck",
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
        for off in range(-1, 2):
            x = round(cx + perp[0] * off)
            z = round(cz + perp[1] * off)
            s.set(x, y, z, "stone_bricks", category)
            s.set(x, y - 1, z, "deepslate_bricks", category)
            bridge_blocks.add((x, y, z))
            s.bridge_mask.add((x, y, z))
            if abs(off) == 1 and i % 3 == 0:
                s.set(x, y + 1, z, "deepslate_bricks", category)
        last = (cx, cz)
    return bridge_blocks


def repair_bridge_endpoint(s: Structure, point: tuple[int, int, int]) -> int:
    repaired = 0
    x, y, z = point
    for dz in range(-1, 2):
        for dx in range(-1, 2):
            if s.set(x + dx, y, z + dz, "stone_bricks", "bridge_deck"):
                repaired += 1
            s.set(x + dx, y - 1, z + dz, "deepslate_bricks", "bridge_deck")
            s.bridge_mask.add((x + dx, y, z + dz))
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


def bridge_blocks_for_floor(s: Structure, y: int) -> set[tuple[int, int, int]]:
    return {p for p in s.bridge_mask if p[1] == y}


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
    s.bridge_reports.clear()
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
            repaired += repair_bridge_endpoint(s, start)
            for dx in range(-1, 2):
                for dz in range(-1, 2):
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


def repair_docking_connections(s: Structure, docking_points: list[DockingPoint]) -> None:
    build_landing_pads(s, docking_points)
    connect_landing_to_ring_corridor(s, docking_points)
    carve_openings(s, docking_points)
    build_connection_bridges(s, docking_points)
    for dock in docking_points:
        ring = s.main_ring_masks.get(dock.level_name, set())
        landing = {p for p in s.landing_pad_mask if p[1] == dock.walk_y}
        if not mask_touches(landing, ring):
            fx, fz = dock.facing_vector
            length = max(1.0, math.hypot(fx, fz))
            nx, nz = fx / length, fz / length
            y = dock.walk_y
            for r in range(13, 28):
                cx = round(CX + nx * r)
                cz = round(CZ + nz * r)
                for w in range(-2, 3):
                    x = round(cx + dock.tangent_vector[0] * w)
                    z = round(cz + dock.tangent_vector[1] * w)
                    if s.set(x, y, z, "stone_bricks", "landing_pad"):
                        s.repaired_bridge_blocks += 1
                    s.set(x, y - 1, z, "deepslate_bricks", "landing_pad")
                    s.landing_pad_mask.add((x, y, z))
        for report in s.bridge_reports:
            if report["floor"] == dock.walk_y and (not report["connected_to_landing"] or not report["connected_to_spiral"]):
                s.repaired_bridge_blocks += int(report["repaired_blocks_count"])


def build_lantern_on_branch(s: Structure, theta: float, radius: float, y: int, color_index: int) -> None:
    colors = [
        ("cyan_stained_glass", "sea_lantern"),
        ("yellow_stained_glass", "glowstone"),
        ("pink_stained_glass", "sea_lantern"),
        ("lime_stained_glass", "shroomlight"),
    ]
    length = 4 + (color_index * 2) % 4
    start = radius + 4
    end = min(radius + 4 + length, 61)
    for r in range(round(start), round(end) + 1):
        x = round(CX + math.cos(theta) * r)
        z = round(CZ + math.sin(theta) * r)
        s.set(x, y, z, "dark_oak_log" if color_index % 2 else "deepslate_bricks", "lantern_branch")
    lx = round(CX + math.cos(theta) * (end + 1))
    lz = round(CZ + math.sin(theta) * (end + 1))
    chain_len = 3 + color_index % 2
    for yy in range(y - chain_len, y + 1):
        s.set(lx, yy, lz, "iron_bars", "lantern_chain")
    glass, core = colors[color_index % len(colors)]
    cy = y - chain_len - 2
    lantern_radius = 1
    for dy in range(-lantern_radius, lantern_radius + 1):
        for dz in range(-1, 2):
            for dx in range(-1, 2):
                if abs(dx) + abs(dy) + abs(dz) <= 3:
                    s.set(lx + dx, cy + dy, lz + dz, glass, "lantern_body")
    s.set(lx, cy, lz, core, "lantern_body")
    s.set(lx, cy - 2, lz, "iron_bars", "lantern_chain")


def build_structural_lantern_branch(s: Structure, theta: float, radius: float, y: int, branch_index: int) -> None:
    length = 3 + branch_index % 3
    for r in range(round(radius + 3), round(radius + 3 + length) + 1):
        x = round(CX + math.cos(theta) * r)
        z = round(CZ + math.sin(theta) * r)
        s.set(x, y, z, "dark_oak_log" if branch_index % 2 else "deepslate_bricks", "lantern_branch")


def build_lantern_branches_along_spiral(s: Structure, lantern_count: int = 18) -> int:
    branch_slots = 24
    lit = 0
    for i in range(branch_slots):
        t = (i + 0.45) / branch_slots
        theta, radius, y, _ = walkway_point(t)
        if t < 0.12:
            if i % 3 == 0:
                build_structural_lantern_branch(s, theta, radius, y - 1, i)
            continue
        if lit < lantern_count and i % 5 != 1:
            build_lantern_on_branch(s, theta, radius, y - 1, lit)
            lit += 1
        else:
            build_structural_lantern_branch(s, theta, radius, y - 1, i)
    return lit


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
                s.set(cx + dx, y, cz + dz, block, "central_crystal_core")


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
            s.set(round(CX + math.cos(rad) * 8), y, round(CZ + math.sin(rad) * 8), "sea_lantern", "central_crystal_core")


def build_ordered_magic_crystal_core(s: Structure) -> None:
    build_central_crystal_core(s)


def build_roof_spire(s: Structure) -> None:
    # Transition arcade between upper library and roof.
    for y, radius in ((106, 25), (107, 25), (108, 24), (109, 23)):
        for z in range(CZ - radius - 2, CZ + radius + 3):
            for x in range(CX - radius - 2, CX + radius + 3):
                r = oct_metric(x - CX, z - CZ)
                if radius - 2.2 <= r <= radius:
                    s.set(x, y, z, "deepslate_bricks" if y < 108 else "deepslate_tiles", "roof")
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x = round(CX + math.cos(rad) * 22)
        z = round(CZ + math.sin(rad) * 22)
        for y in range(101, 111):
            if y % 3 != 1:
                s.set(x, y, z, "deepslate_bricks", "roof")
    for angle in range(0, 360, 22):
        if angle % 45 == 0:
            continue
        rad = math.radians(angle)
        for y in (107, 108):
            x = round(CX + math.cos(rad) * 21)
            z = round(CZ + math.sin(rad) * 21)
            s.set(x, y, z, "cyan_stained_glass" if angle % 44 == 0 else "deepslate_tiles", "roof")

    tiers = [
        (110, 120, 23, 18, 5),
        (121, 134, 18, 10, 4),
        (135, 149, 10, 3, 3),
    ]
    band_ys = {110, 120, 121, 134, 135, 149}
    for y0, y1, r0, r1, cavity in tiers:
        for y in range(y0, y1 + 1):
            t = 0 if y1 == y0 else (y - y0) / (y1 - y0)
            radius = round(r0 + (r1 - r0) * (t ** 0.82))
            cavity_radius = min(cavity, max(2, radius - 4))
            for z in range(CZ - radius - 2, CZ + radius + 3):
                for x in range(CX - radius - 2, CX + radius + 3):
                    r = oct_metric(x - CX, z - CZ)
                    if r > radius:
                        continue
                    a = angle_of(x - CX, z - CZ)
                    outer_shell = radius - 2.0 <= r <= radius
                    rib = any(angle_delta(a, p) < 3.5 for p in range(0, 360, 45)) and r >= cavity_radius
                    band = y in band_ys and r >= cavity_radius
                    inner_eave = y in (120, 134) and cavity_radius + 1 <= r <= cavity_radius + 3
                    if r < cavity_radius and 114 <= y <= 145:
                        s.carve(x, y, z)
                        continue
                    if outer_shell or rib or band or inner_eave:
                        if rib or band or inner_eave:
                            block = "deepslate_tiles"
                        else:
                            block = "weathered_copper" if (int(a // 45) + y // 6) % 4 == 0 else "oxidized_copper"
                        s.set(x, y, z, block, "roof")

    for y in range(112, 147):
        block = "deepslate_bricks" if y % 5 else "sea_lantern"
        s.set(CX, y, CZ, block, "roof")
    for y in range(116, 128):
        if y % 3 == 0:
            for angle in range(0, 360, 90):
                rad = math.radians(angle)
                s.set(round(CX + math.cos(rad) * 4), y, round(CZ + math.sin(rad) * 4), "deepslate_tiles", "roof")
    for y in range(150, 157):
        s.set(CX, y, CZ, "gold_block", "roof")
    for y in range(153, 157):
        s.set(CX + 1, y, CZ, "gold_block", "roof")
        s.set(CX - 1, y, CZ, "gold_block", "roof")


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


DEBUG_BG = (13, 15, 21, 255)
DEBUG_TAG_COLORS = {
    "spiral_deck": (132, 138, 142, 230),
    "bottom_root": (160, 170, 168, 245),
    "bridge_deck": (220, 224, 214, 245),
    "landing_pad": (248, 214, 88, 245),
    "main_ring_corridor": (126, 78, 44, 220),
    "doorway_frame": (86, 105, 128, 240),
    "spiral_curb": (62, 70, 82, 210),
    "spiral_support": (56, 62, 72, 190),
}


def save_debug_top(
    s: Structure,
    out_path: str,
    tags: set[str],
    overlays: list[tuple[int, int, int, tuple[int, int, int, int]]] | None = None,
) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas = (1100, 1100)
    min_x, max_x = 0, SIZE_X - 1
    min_z, max_z = 0, SIZE_Z - 1
    scale = min((canvas[0] - 80) / SIZE_X, (canvas[1] - 80) / SIZE_Z)
    ox = (canvas[0] - SIZE_X * scale) / 2
    oy = (canvas[1] - SIZE_Z * scale) / 2
    img = Image.new("RGBA", canvas, DEBUG_BG)
    draw = ImageDraw.Draw(img, "RGBA")
    for y in range(SIZE_Y):
        shade = 0.45 + 0.55 * (y / max(1, SIZE_Y - 1))
        for z in range(min_z, max_z + 1):
            for x in range(min_x, max_x + 1):
                cat = s.categories[index(x, y, z)]
                if cat not in tags:
                    continue
                base = DEBUG_TAG_COLORS.get(cat, (210, 210, 210, 220))
                color = (int(base[0] * shade), int(base[1] * shade), int(base[2] * shade), base[3])
                x0 = ox + x * scale
                y0 = oy + z * scale
                draw.rectangle((x0, y0, x0 + scale, y0 + scale), fill=color)
    if overlays:
        for x, _y, z, color in overlays:
            x0 = ox + x * scale
            y0 = oy + z * scale
            r = max(3, scale * 1.8)
            draw.ellipse((x0 - r, y0 - r, x0 + r, y0 + r), fill=color)
    img.convert("RGB").save(out_path)


def save_debug_mask_top(
    out_path: str,
    mask: set[tuple[int, int, int]],
    color: tuple[int, int, int, int],
    overlays: list[tuple[int, int, int, tuple[int, int, int, int]]] | None = None,
) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas = (1100, 1100)
    scale = min((canvas[0] - 80) / SIZE_X, (canvas[1] - 80) / SIZE_Z)
    ox = (canvas[0] - SIZE_X * scale) / 2
    oy = (canvas[1] - SIZE_Z * scale) / 2
    img = Image.new("RGBA", canvas, DEBUG_BG)
    draw = ImageDraw.Draw(img, "RGBA")
    for x, y, z in sorted(mask, key=lambda p: p[1]):
        shade = 0.55 + 0.45 * (y / max(1, SIZE_Y - 1))
        c = (int(color[0] * shade), int(color[1] * shade), int(color[2] * shade), color[3])
        x0 = ox + x * scale
        y0 = oy + z * scale
        draw.rectangle((x0, y0, x0 + scale, y0 + scale), fill=c)
    if overlays:
        for x, _y, z, ocolor in overlays:
            x0 = ox + x * scale
            y0 = oy + z * scale
            r = max(4, scale * 2.2)
            draw.ellipse((x0 - r, y0 - r, x0 + r, y0 + r), fill=ocolor)
    img.convert("RGB").save(out_path)


def save_roof_cutaway(s: Structure, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    canvas = (900, 900)
    min_x, max_x = CX - 30, CX + 30
    min_y, max_y = 100, 158
    scale = min((canvas[0] - 80) / (max_x - min_x + 1), (canvas[1] - 80) / (max_y - min_y + 1))
    ox = (canvas[0] - (max_x - min_x + 1) * scale) / 2
    oy = canvas[1] - 40
    img = Image.new("RGBA", canvas, DEBUG_BG)
    draw = ImageDraw.Draw(img, "RGBA")
    colors = {
        "roof": (50, 210, 190, 230),
        "air": (32, 38, 52, 80),
        "central_crystal_core": (230, 255, 250, 230),
    }
    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            chosen = "air"
            cat = s.categories[index(x, y, CZ)] if in_bounds(x, y, CZ) else "air"
            if cat == "roof" or cat == "central_crystal_core":
                chosen = cat
            if chosen == "air":
                continue
            color = colors[chosen]
            x0 = ox + (x - min_x) * scale
            y0 = oy - (y - min_y + 1) * scale
            draw.rectangle((x0, y0, x0 + scale, y0 + scale), fill=color)
    # Mark intended internal cavity.
    for y in range(114, 146):
        for x in range(CX - 5, CX + 6):
            x0 = ox + (x - min_x) * scale
            y0 = oy - (y - min_y + 1) * scale
            draw.rectangle((x0, y0, x0 + scale, y0 + scale), outline=(255, 230, 80, 140))
    img.convert("RGB").save(out_path)


def write_debug_previews(s: Structure, docking_points: list[DockingPoint]) -> None:
    out_dir = os.path.join("out", "previews")
    save_debug_top(
        s,
        os.path.join(out_dir, "debug_spiral_deck.png"),
        {"spiral_deck", "bridge_deck", "landing_pad"},
    )
    overlays: list[tuple[int, int, int, tuple[int, int, int, int]]] = []
    for dock in docking_points:
        overlays.append((dock.doorway_center_x, dock.walk_y, dock.doorway_center_z, (255, 72, 72, 255)))
        overlays.append((dock.landing_center_x, dock.walk_y, dock.landing_center_z, (255, 230, 72, 255)))
    save_debug_top(
        s,
        os.path.join(out_dir, "debug_docking.png"),
        {"bridge_deck", "landing_pad", "main_ring_corridor", "doorway_frame", "spiral_deck"},
        overlays,
    )
    removal_overlays = [(x, y, z, (255, 42, 42, 255)) for x, y, z, _reason in s.removed_debug]
    save_debug_top(
        s,
        os.path.join(out_dir, "debug_cleanup_removed.png"),
        {"spiral_deck", "bridge_deck", "landing_pad", "spiral_curb", "spiral_support"},
        removal_overlays,
    )
    save_roof_cutaway(s, os.path.join(out_dir, "roof_cutaway.png"))
    lower_mask = set(s.lower_taper_mask) | set(s.bottom_root_mask)
    lower_overlays = [(CX, BOTTOM_APEX_ROOT_Y, CZ, (70, 235, 255, 255))]
    save_debug_mask_top(
        os.path.join(out_dir, "debug_lower_taper_only.png"),
        lower_mask,
        (150, 164, 166, 245),
        lower_overlays,
    )


def main() -> None:
    s = Structure()
    build_central_library_core(s)
    docking_points = define_docking_points()
    rebuild_internal_system(s, docking_points)
    soften_lower_outer_platform(s, docking_points)
    build_ordered_magic_crystal_core(s)
    build_spiral_walkway(s)
    deck_repaired_blocks = repair_deck_connectivity(s)
    s.repaired_walkway_blocks += deck_repaired_blocks
    repair_docking_connections(s, docking_points)
    build_bottom_taper_root(s)
    build_walkway_edges(s)
    lantern_count = build_lantern_branches_along_spiral(s)
    build_roof_spire(s)
    build_hanging_bottom_crystal(s)
    repair_docking_connections(s, docking_points)
    cleanup_floating_blocks(s)
    cleanup_internal_clutter(s, docking_points)
    walkable_report = validate_walkable_connectivity(s, docking_points)
    write_debug_previews(s, docking_points)
    write_mcstructure(s)

    counts = Counter(s.blocks)
    non_air = len(s.blocks) - counts[0]
    print(f"Wrote {OUT_PATH}")
    print(f"Palette entries: {len(BLOCKS)}")
    print(f"Non-air blocks: {non_air}")
    print(f"total_non_air_blocks: {non_air}")
    print(f"Bookshelf blocks: {counts[PALETTE['bookshelf']]}")
    print(f"spiral_deck_blocks: {len(s.deck_mask)}")
    print(f"lower_taper_blocks: {len(s.lower_taper_mask)}")
    print(f"bottom_root_blocks: {len(s.bottom_root_mask)}")
    print(f"spiral_curb_blocks: {sum(1 for p in s.curb_mask if tag_at(s, p) == 'spiral_curb')}")
    print(f"spiral_support_blocks: {sum(1 for p in s.support_mask if tag_at(s, p) == 'spiral_support')}")
    print(f"bridge_deck_blocks: {len(s.bridge_mask)}")
    print(f"landing_pad_blocks: {len(s.landing_pad_mask)}")
    print(f"Lantern count: {lantern_count}")
    print(f"Lantern blocks: {s.stats['lantern_branch'] + s.stats['lantern_chain'] + s.stats['lantern_body']}")
    print(f"Central crystal blocks: {s.stats['central_crystal_core']}")
    print(f"Roof blocks: {s.stats['roof']}")
    print(f"Bottom crystal blocks: {s.stats['bottom_crystal']}")
    print(f"detached_curb_removed: {s.detached_edge_blocks_removed}")
    print(f"detached_support_removed: {s.floating_support_blocks_removed}")
    print(f"detached_noise_removed: {s.detached_noise_removed}")
    print(f"detached_lantern_parts_removed: {s.detached_lantern_parts_removed}")
    print(f"removed_internal_clutter_count: {s.removed_internal_clutter_count}")
    print(f"repaired_walkway_blocks: {s.repaired_walkway_blocks}")
    print(f"repaired_bridge_blocks: {s.repaired_bridge_blocks}")
    print(f"blocked_doorways_after_cleanup: {walkable_report['blocked_doorways']}")
    print(f"spiral_deck_connected: {walkable_report['spiral_deck_connected']}")
    print(f"all_bridges_connected: {walkable_report['all_bridges_connected']}")
    print(f"all_landings_connected_to_ring: {walkable_report['all_landings_connected_to_ring']}")
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
