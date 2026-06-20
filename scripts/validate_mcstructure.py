from __future__ import annotations

import os
import sys

from bedrock_nbt import read_root_compound


EXPECTED_SIZE = [96, 128, 96]


def fail(message: str) -> None:
    raise SystemExit(f"Validation failed: {message}")


def main() -> None:
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("out", "inverted_library.mcstructure")
    if not os.path.exists(path):
        fail(f"file does not exist: {path}")

    root = read_root_compound(path)
    size = root.get("size")
    if size != EXPECTED_SIZE:
        fail(f"size is {size}, expected {EXPECTED_SIZE}")

    structure = root.get("structure")
    if not isinstance(structure, dict):
        fail("missing structure compound")

    palette = structure.get("palette", {}).get("default", {}).get("block_palette", [])
    if not palette:
        fail("palette is empty")

    block_indices = structure.get("block_indices")
    if not isinstance(block_indices, list) or len(block_indices) < 2:
        fail("block_indices must contain two layers")

    expected_length = size[0] * size[1] * size[2]
    primary = block_indices[0]
    secondary = block_indices[1]
    if len(primary) != expected_length:
        fail(f"primary block_indices length is {len(primary)}, expected {expected_length}")
    if len(secondary) != expected_length:
        fail(f"secondary block_indices length is {len(secondary)}, expected {expected_length}")

    air_index = 0
    for i, entry in enumerate(palette):
        if entry.get("name") == "minecraft:air":
            air_index = i
            break
    non_air = sum(1 for value in primary if value != air_index and value >= 0)
    air_ratio = 1 - non_air / expected_length
    if air_ratio > 0.995:
        fail(f"air ratio is too high: {air_ratio:.2%}")

    secondary_bad = sum(1 for value in secondary if value != -1 and value != air_index)
    if secondary_bad:
        fail(f"secondary layer contains {secondary_bad} non-empty entries")

    print("Validation passed")
    print(f"File: {path}")
    print(f"Size: {size}")
    print(f"Palette entries: {len(palette)}")
    print(f"Primary block_indices: {len(primary)}")
    print(f"Secondary block_indices: {len(secondary)}")
    print(f"Non-air blocks: {non_air}")
    print(f"Air ratio: {air_ratio:.2%}")


if __name__ == "__main__":
    main()
