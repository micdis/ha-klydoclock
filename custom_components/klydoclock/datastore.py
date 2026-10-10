"""Minimal reader for AndroidX "Preferences DataStore" files (protobuf)."""

from __future__ import annotations

import struct
from typing import Any


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return result, pos


def _fields(buf: bytes):
    pos = 0
    while pos < len(buf):
        key, pos = _varint(buf, pos)
        number, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _varint(buf, pos)
        elif wire == 1:
            value, pos = buf[pos : pos + 8], pos + 8
        elif wire == 2:
            length, pos = _varint(buf, pos)
            value, pos = buf[pos : pos + length], pos + length
        elif wire == 5:
            value, pos = buf[pos : pos + 4], pos + 4
        else:
            raise ValueError(f"unsupported wire type {wire}")
        if pos > len(buf):
            raise ValueError("truncated message")
        yield number, value


def _value(buf: bytes) -> Any:
    """Decode a datastore `Value` message (a oneof)."""
    for number, raw in _fields(buf):
        if number == 1:  # boolean
            return bool(raw)
        if number == 2:  # float
            return struct.unpack("<f", raw)[0]
        if number in (3, 4):  # int32 / int64
            return raw - (1 << 64) if raw >= 1 << 63 else raw
        if number == 5:  # string
            return raw.decode("utf-8", "replace")
        if number == 6:  # string set
            return [v.decode("utf-8", "replace") for n, v in _fields(raw) if n == 1]
        if number == 7:  # double
            return struct.unpack("<d", raw)[0]
        if number == 8:  # bytes
            return raw
    return None


def parse_preferences(buf: bytes) -> dict[str, Any]:
    """Return the key/value map stored in a preferences_pb file."""
    result: dict[str, Any] = {}
    for number, entry in _fields(buf):
        if number != 1:
            continue
        key = None
        value = None
        for sub, raw in _fields(entry):
            if sub == 1:
                key = raw.decode("utf-8", "replace")
            elif sub == 2:
                value = _value(raw)
        if key is not None:
            result[key] = value
    return result
