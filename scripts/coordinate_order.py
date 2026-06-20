from __future__ import annotations


def mc_index(x: int, y: int, z: int, sx: int, sy: int, sz: int) -> int:
    return x * sy * sz + y * sz + z


def coords_from_mc_index(i: int, sx: int, sy: int, sz: int) -> tuple[int, int, int]:
    x = i // (sz * sy)
    y = (i // sz) % sy
    z = i % sz
    return x, y, z
