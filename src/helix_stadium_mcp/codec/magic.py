"""The 8-byte .hsp magic header."""
from __future__ import annotations

MAGIC = b"rpshnosj"  # 8 ASCII bytes, immediately followed by the JSON '{'


def has_magic(data: bytes) -> bool:
    return data[:len(MAGIC)] == MAGIC


def strip_magic(data: bytes) -> bytes:
    """Return the JSON body after the magic header, or raise if absent."""
    if not has_magic(data):
        raise ValueError(f"not an .hsp file: bad magic {data[:8]!r}")
    return data[len(MAGIC):]
