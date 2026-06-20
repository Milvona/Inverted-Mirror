"""Small Bedrock little-endian NBT reader/writer for .mcstructure files."""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from typing import Any


TAG_END = 0
TAG_BYTE = 1
TAG_SHORT = 2
TAG_INT = 3
TAG_LONG = 4
TAG_FLOAT = 5
TAG_DOUBLE = 6
TAG_BYTE_ARRAY = 7
TAG_STRING = 8
TAG_LIST = 9
TAG_COMPOUND = 10
TAG_INT_ARRAY = 11
TAG_LONG_ARRAY = 12


@dataclass(frozen=True)
class NbtList:
    item_type: int
    items: list[Any]


@dataclass(frozen=True)
class NbtCompound:
    items: dict[str, Any]


@dataclass(frozen=True)
class NbtByte:
    value: int


@dataclass(frozen=True)
class NbtInt:
    value: int


def _write_string(buf: io.BytesIO, value: str) -> None:
    data = value.encode("utf-8")
    buf.write(struct.pack("<H", len(data)))
    buf.write(data)


def _read_exact(buf: io.BytesIO, length: int) -> bytes:
    data = buf.read(length)
    if len(data) != length:
        raise ValueError("Unexpected end of NBT data")
    return data


def _read_string(buf: io.BytesIO) -> str:
    length = struct.unpack("<H", _read_exact(buf, 2))[0]
    return _read_exact(buf, length).decode("utf-8")


def _tag_type(value: Any) -> int:
    if isinstance(value, NbtByte):
        return TAG_BYTE
    if isinstance(value, NbtInt) or isinstance(value, int):
        return TAG_INT
    if isinstance(value, str):
        return TAG_STRING
    if isinstance(value, NbtList):
        return TAG_LIST
    if isinstance(value, NbtCompound) or isinstance(value, dict):
        return TAG_COMPOUND
    raise TypeError(f"Unsupported NBT value: {value!r}")


def _write_payload(buf: io.BytesIO, tag_type: int, value: Any) -> None:
    if tag_type == TAG_BYTE:
        buf.write(struct.pack("<b", value.value if isinstance(value, NbtByte) else value))
    elif tag_type == TAG_INT:
        buf.write(struct.pack("<i", value.value if isinstance(value, NbtInt) else value))
    elif tag_type == TAG_STRING:
        _write_string(buf, value)
    elif tag_type == TAG_LIST:
        if not isinstance(value, NbtList):
            raise TypeError("TAG_List values must use NbtList")
        buf.write(struct.pack("<b", value.item_type))
        buf.write(struct.pack("<i", len(value.items)))
        for item in value.items:
            _write_payload(buf, value.item_type, item)
    elif tag_type == TAG_COMPOUND:
        items = value.items if isinstance(value, NbtCompound) else value
        for name, child in items.items():
            child_type = _tag_type(child)
            buf.write(struct.pack("<b", child_type))
            _write_string(buf, name)
            _write_payload(buf, child_type, child)
        buf.write(struct.pack("<b", TAG_END))
    else:
        raise TypeError(f"Unsupported NBT tag type: {tag_type}")


def write_root_compound(path: str, root: dict[str, Any], name: str = "") -> None:
    buf = io.BytesIO()
    buf.write(struct.pack("<b", TAG_COMPOUND))
    _write_string(buf, name)
    _write_payload(buf, TAG_COMPOUND, root)
    with open(path, "wb") as file:
        file.write(buf.getvalue())


def _read_payload(buf: io.BytesIO, tag_type: int) -> Any:
    if tag_type == TAG_BYTE:
        return struct.unpack("<b", _read_exact(buf, 1))[0]
    if tag_type == TAG_SHORT:
        return struct.unpack("<h", _read_exact(buf, 2))[0]
    if tag_type == TAG_INT:
        return struct.unpack("<i", _read_exact(buf, 4))[0]
    if tag_type == TAG_LONG:
        return struct.unpack("<q", _read_exact(buf, 8))[0]
    if tag_type == TAG_FLOAT:
        return struct.unpack("<f", _read_exact(buf, 4))[0]
    if tag_type == TAG_DOUBLE:
        return struct.unpack("<d", _read_exact(buf, 8))[0]
    if tag_type == TAG_STRING:
        return _read_string(buf)
    if tag_type == TAG_LIST:
        item_type = struct.unpack("<b", _read_exact(buf, 1))[0]
        length = struct.unpack("<i", _read_exact(buf, 4))[0]
        return [_read_payload(buf, item_type) for _ in range(length)]
    if tag_type == TAG_COMPOUND:
        result: dict[str, Any] = {}
        while True:
            child_type = struct.unpack("<b", _read_exact(buf, 1))[0]
            if child_type == TAG_END:
                return result
            name = _read_string(buf)
            result[name] = _read_payload(buf, child_type)
    if tag_type == TAG_INT_ARRAY:
        length = struct.unpack("<i", _read_exact(buf, 4))[0]
        return [struct.unpack("<i", _read_exact(buf, 4))[0] for _ in range(length)]
    raise TypeError(f"Unsupported NBT tag type while reading: {tag_type}")


def read_root_compound(path: str) -> dict[str, Any]:
    with open(path, "rb") as file:
        buf = io.BytesIO(file.read())
    root_type = struct.unpack("<b", _read_exact(buf, 1))[0]
    if root_type != TAG_COMPOUND:
        raise ValueError("Root tag is not a compound")
    _read_string(buf)
    return _read_payload(buf, TAG_COMPOUND)
