"""Read/explain tools (v1, read-only)."""
from __future__ import annotations

import json
from pathlib import Path

from ..codec import read_hsp
from ..preset import explain_text, resolve_snapshot_index, snapshot_diff, summarize
from ..util import envelope as E


def _load_preset(path: str):
    """Return (obj, None) or (None, error_envelope)."""
    p = Path(path)
    try:
        data = p.read_bytes()
    except FileNotFoundError:
        return None, E.err(E.NOT_FOUND, f"No such file: {path}")
    except OSError as e:
        return None, E.err(E.IO_ERROR, f"Cannot read {path}: {e}")
    try:
        return read_hsp(data), None
    except (ValueError, json.JSONDecodeError) as e:
        return None, E.err(E.PARSE_ERROR, f"Not a valid .hsp file: {e}")


def _catalog(ctx):
    try:
        return ctx.catalog, None
    except FileNotFoundError as e:
        return None, E.err(E.INSTALL_NOT_FOUND, str(e))


def register(mcp, ctx) -> None:

    @mcp.tool(name="read_preset")
    def read_preset(path: str) -> dict:
        """Parse a Helix Stadium .hsp preset file and return a structured summary:
        name, tempo, snapshots, and each signal path's blocks with their models and
        key parameters in real display units."""
        obj, e = _load_preset(path)
        if e:
            return e
        cat, e = _catalog(ctx)
        if e:
            return e
        data = summarize(cat, obj)
        return E.ok(data, summary=f"{data['name']}: {len(data['paths'])} path(s), "
                                  f"{len(data['snapshots'])} snapshot(s)")

    @mcp.tool(name="explain_preset")
    def explain_preset(path: str) -> dict:
        """Explain a .hsp preset in plain English: the full signal chain of each path
        with friendly model names, on/off state, per-snapshot and footswitch tags, and
        parameters rendered in real units (dB, Hz, ms, %)."""
        obj, e = _load_preset(path)
        if e:
            return e
        cat, e = _catalog(ctx)
        if e:
            return e
        text = explain_text(cat, obj)
        return E.ok({"text": text}, summary=f"Explained {obj.get('meta', {}).get('name', path)}")

    @mcp.tool(name="diff_snapshots")
    def diff_snapshots(path: str, a: str, b: str) -> dict:
        """Compare two snapshots of a .hsp preset and list what changes between them —
        each differing block-bypass and parameter, with values in real units. `a` and
        `b` are snapshot names (e.g. 'Rhythm') or 1-based numbers (e.g. '3')."""
        obj, e = _load_preset(path)
        if e:
            return e
        cat, e = _catalog(ctx)
        if e:
            return e
        ia, ib = resolve_snapshot_index(obj, a), resolve_snapshot_index(obj, b)
        if ia is None:
            return E.err(E.NOT_FOUND, f"snapshot not found: {a!r}")
        if ib is None:
            return E.err(E.NOT_FOUND, f"snapshot not found: {b!r}")
        d = snapshot_diff(cat, obj, ia, ib)
        return E.ok(d, summary=f"{len(d['changes'])} change(s) "
                               f"{d['a']['name']} -> {d['b']['name']}")
