"""Optional fallback templates for ``add_block`` and ``create_preset``.

The primary source of a default block (and the blank canvas) is synthesized at runtime from
the install's model definitions (see :mod:`helix_stadium_mcp.modeldefs`). As a fallback, a
default block for a model — or a blank preset — can be loaded from an external JSON template
file if one is configured; when neither is available the caller degrades gracefully.

Locations: ``HELIX_MODEL_DEFAULTS`` (else ``<repo>/reference/model_defaults.json``) for block
templates, ``HELIX_EMPTY_PRESET`` (else ``<repo>/reference/empty_preset.json``) for the blank
canvas.
"""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path

_cache: dict | None = None
_cache_path: str | None = None


def default_path() -> str:
    env = os.environ.get("HELIX_MODEL_DEFAULTS")
    if env:
        return env
    return str(Path(__file__).resolve().parents[2] / "reference" / "model_defaults.json")


def load_defaults(path: str | None = None) -> dict:
    """Return ``{model_id: block_template}``; empty dict if the file is absent."""
    global _cache, _cache_path
    p = path or default_path()
    if _cache is None or _cache_path != p:
        try:
            _cache = json.loads(Path(p).read_text(encoding="utf-8"))
        except FileNotFoundError:
            _cache = {}
        _cache_path = p
    return _cache


def get_template(model_id: str, path: str | None = None) -> dict | None:
    tmpl = load_defaults(path).get(model_id)
    return copy.deepcopy(tmpl) if tmpl is not None else None


# -- blank canvas (for create_preset) --------------------------------------
def empty_path() -> str:
    env = os.environ.get("HELIX_EMPTY_PRESET")
    if env:
        return env
    return str(Path(__file__).resolve().parents[2] / "reference" / "empty_preset.json")


def load_empty(path: str | None = None) -> dict | None:
    try:
        return json.loads(Path(path or empty_path()).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
