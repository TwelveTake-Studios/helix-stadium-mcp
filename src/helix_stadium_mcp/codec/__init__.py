"""Byte-exact .hsp codec: read/write Helix Stadium preset files losslessly.

Python's stdlib ``json`` natively preserves int-vs-float (``1`` vs ``1.0``) and the
exact stored double, so no type-preserving tokenizer is needed — only the custom
:mod:`.serialize` (key order + float formatting) closes byte-exactness.
"""
from __future__ import annotations

import json

from .magic import MAGIC, has_magic, strip_magic
from .serialize import serialize

__all__ = ["MAGIC", "has_magic", "read_hsp", "write_hsp", "round_trip"]


def read_hsp(data: bytes) -> dict:
    """Bytes of an .hsp file -> parsed preset object (int/float kinds preserved)."""
    return json.loads(strip_magic(data).decode("utf-8"))


def write_hsp(obj: dict) -> bytes:
    """Preset object -> exact .hsp bytes (magic + canonical JSON, no trailing newline)."""
    return MAGIC + serialize(obj).encode("utf-8")


def round_trip(data: bytes) -> bytes:
    """read then write; for a valid .hsp this returns ``data`` unchanged."""
    return write_hsp(read_hsp(data))
