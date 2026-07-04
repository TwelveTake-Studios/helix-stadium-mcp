"""Canonical .hsp JSON serializer.

Reproduces the app's output byte-for-byte: 2-space indent, ``": "`` after keys,
``,`` between members, keys sorted by RAW code point (so numeric-looking string
keys sort lexically, not numerically — the ``preset.sources`` trap), no trailing
newline. ``bool`` is dispatched before ``int`` (bool is an int subclass in Python).
"""
from __future__ import annotations

import json

from .floatfmt import to_decimal_string


def _enc_str(s: str) -> str:
    # Delegate string/key escaping to json (matches the app); keep UTF-8.
    return json.dumps(s, ensure_ascii=False)


def serialize(obj, level: int = 0) -> str:
    pad = "  " * level
    child = "  " * (level + 1)

    if isinstance(obj, dict):
        if not obj:
            return "{}"
        body = ",\n".join(
            f"{child}{_enc_str(k)}: {serialize(obj[k], level + 1)}"
            for k in sorted(obj.keys())  # raw code-point sort; numeric-str keys lexical
        )
        return "{\n" + body + "\n" + pad + "}"

    if isinstance(obj, list):
        if not obj:
            return "[]"
        body = ",\n".join(f"{child}{serialize(v, level + 1)}" for v in obj)
        return "[\n" + body + "\n" + pad + "]"

    if obj is None:
        return "null"
    if isinstance(obj, bool):          # MUST precede int
        return "true" if obj else "false"
    if isinstance(obj, int):
        return str(obj)
    if isinstance(obj, float):
        return to_decimal_string(obj)
    if isinstance(obj, str):
        return _enc_str(obj)

    raise TypeError(f"cannot serialize {type(obj)!r} in .hsp")
