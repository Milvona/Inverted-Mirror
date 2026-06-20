from __future__ import annotations

import os

from bedrock_nbt import NbtCompound, NbtInt, NbtList, TAG_COMPOUND, TAG_INT, TAG_LIST, read_root_compound, write_root_compound
from coordinate_order import coords_from_mc_index, mc_index


SIZE = [4, 4, 4]
OUT_PATH = os.path.join("out", "coordinate_test.mcstructure")
BLOCKS = [
    "air",
    "gold_block",
    "redstone_block",
    "emerald_block",
    "diamond_block",
]
PALETTE = {name: i for i, name in enumerate(BLOCKS)}
EXPECTED = {
    (0, 0, 0): "gold_block",
    (1, 0, 0): "redstone_block",
    (0, 1, 0): "emerald_block",
    (0, 0, 1): "diamond_block",
}


def block_palette() -> NbtList:
    return NbtList(TAG_COMPOUND, [
        NbtCompound({
            "name": f"minecraft:{name}",
            "states": NbtCompound({}),
            "version": NbtInt(18163713),
        })
        for name in BLOCKS
    ])


def write_test_structure() -> None:
    sx, sy, sz = SIZE
    blocks = [PALETTE["air"]] * (sx * sy * sz)
    for (x, y, z), block in EXPECTED.items():
        blocks[mc_index(x, y, z, sx, sy, sz)] = PALETTE[block]

    root = {
        "format_version": NbtInt(1),
        "size": NbtList(TAG_INT, SIZE),
        "structure": NbtCompound({
            "block_indices": NbtList(TAG_LIST, [
                NbtList(TAG_INT, blocks),
                NbtList(TAG_INT, [-1] * len(blocks)),
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
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    write_root_compound(OUT_PATH, root)


def read_test_structure() -> dict[tuple[int, int, int], str]:
    root = read_root_compound(OUT_PATH)
    sx, sy, sz = root["size"]
    structure = root["structure"]
    palette = [
        entry["name"].split("minecraft:", 1)[-1]
        for entry in structure["palette"]["default"]["block_palette"]
    ]
    blocks = structure["block_indices"][0]
    found: dict[tuple[int, int, int], str] = {}
    for i, palette_id in enumerate(blocks):
        if palette_id > 0:
            found[coords_from_mc_index(i, sx, sy, sz)] = palette[palette_id]
    return found


def main() -> None:
    write_test_structure()
    found = read_test_structure()
    if found != EXPECTED:
        raise SystemExit(f"Coordinate order test failed: expected {EXPECTED}, found {found}")

    print(f"Wrote {OUT_PATH}")
    print("Coordinate order test passed")
    for coords, block in sorted(found.items()):
        print(f"{coords}: {block}")


if __name__ == "__main__":
    main()
