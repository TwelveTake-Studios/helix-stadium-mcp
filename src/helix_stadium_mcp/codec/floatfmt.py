"""Byte-exact float formatting for the .hsp serializer.

The app writes floats as the shortest decimal that round-trips to the stored
double, ALWAYS in fixed (non-scientific) notation. Python's ``repr(float)`` already
gives the shortest round-tripping decimal; the only divergence is small/large
magnitudes where ``repr`` uses ``e`` notation, which we expand to fixed decimal
via ``Decimal`` without altering any significant digit.
"""
from __future__ import annotations

import struct
from decimal import Decimal


def to_decimal_string(f: float) -> str:
    """Shortest round-trip decimal for ``f``, forced to fixed (non-scientific)."""
    r = repr(f)
    if "e" in r or "E" in r:
        return format(Decimal(r), "f")
    return r


def fround32(f: float) -> float:
    """Round a float through single precision (many stored params are float32)."""
    return struct.unpack("f", struct.pack("f", f))[0]
