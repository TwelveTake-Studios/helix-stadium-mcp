"""Edit tools. Every write funnels through the safe_write gate — validate →
round-trip → atomic write + `.bak` → read-back. Errors block; nothing writes an
invalid preset. Registered only when the server is not in HELIX_MCP_READONLY mode.
"""
from __future__ import annotations

from ..defaults import get_template
from ..encoding import display_string, stored_value
from ..modeldefs import clamp_range, synth_template
from ..preset import (
    add_block,
    configure_snapshots,
    edit_param,
    find_block,
    move_block,
    remove_block,
    rename_preset,
    rename_snapshot,
    resolve_snapshot_index,
    set_active_snapshot,
    toggle_block,
)
from ..util import envelope as E
from ..writer import WriteBlocked, safe_write
from .read import _catalog, _load_preset


def _parse_value(s):
    """Coerce a tool string arg to number / bool / enum-label."""
    if isinstance(s, (int, float, bool)):
        return s
    low = str(s).strip().lower()
    if low in ("true", "on", "yes"):
        return True
    if low in ("false", "off", "no"):
        return False
    try:
        return float(s)
    except (TypeError, ValueError):
        return str(s).strip()  # enum label


def _do_write(cat, obj, path, data, summary, extra_warnings=None):
    try:
        res = safe_write(obj, path, cat)
    except WriteBlocked as wb:
        return E.err(E.VALIDATION_FAILED, wb.report.get("message", "write blocked"), data=wb.report)
    warnings = [*(extra_warnings or []), *res["warnings"]]
    return E.ok({**data, "backup": res["backup"]}, summary=summary, warnings=warnings)


def register(mcp, ctx) -> None:

    @mcp.tool(name="edit_param")
    def edit_param_tool(path: str, block: str, param: str, value: str,
                        path_num: int = 1, snapshot: str | None = None) -> dict:
        """Set a parameter on a block to a new value (in real display units, e.g. `8000`
        for 8 kHz, `-3` for -3 dB, or an enum label like `Guitar`), then safely write the
        preset. `block` is a block key like `b04`. `snapshot` (name or 1-based number)
        edits just that snapshot; omit it to edit the current value. A `.bak` is kept."""
        obj, e = _load_preset(path)
        if e:
            return e
        cat, e = _catalog(ctx)
        if e:
            return e
        try:
            _blk, slot0 = find_block(obj, path_num, block)
        except KeyError as ex:
            return E.err(E.NOT_FOUND, str(ex))
        model = slot0.get("model", "?")
        snap_idx = None
        if snapshot is not None:
            snap_idx = resolve_snapshot_index(obj, snapshot)
            if snap_idx is None:
                return E.err(E.NOT_FOUND, f"snapshot {snapshot!r} not found")
        warnings = []
        try:
            stored = stored_value(cat, model, param, _parse_value(value))
            rng = clamp_range(model, param)          # (min, max) for continuous params
            if rng is not None and not rng[0] <= stored <= rng[1]:
                clamped = max(rng[0], min(rng[1], stored))
                limit = display_string(cat, model, param, clamped)[0]
                warnings.append(f"{param} value out of range; clamped to {limit}")
                stored = clamped
            edit_param(obj, path_num, block, param, stored, snapshot=snap_idx)
        except (KeyError, ValueError, IndexError) as ex:
            return E.err(E.VALUE_OUT_OF_RANGE, str(ex))
        shown, _tag = display_string(cat, model, param, stored)
        where = f" (snapshot {snapshot})" if snapshot is not None else ""
        return _do_write(cat, obj, path, {"block": block, "param": param, "value": shown},
                         summary=f"{cat.friendly_name(model)} {param} -> {shown}{where}",
                         extra_warnings=warnings)

    @mcp.tool(name="toggle_block")
    def toggle_block_tool(path: str, block: str, enabled: bool, path_num: int = 1,
                          snapshot: str | None = None) -> dict:
        """Enable or disable a block, then write. `snapshot` (name or 1-based number) sets the
        bypass for just that scene (creating its per-snapshot automation); omit it to set the
        current bypass. A block bypassed per-snapshot turns on in some scenes and off in others."""
        obj, e = _load_preset(path)
        if e:
            return e
        cat, e = _catalog(ctx)
        if e:
            return e
        snap_idx = None
        if snapshot is not None:
            snap_idx = resolve_snapshot_index(obj, snapshot)
            if snap_idx is None:
                return E.err(E.NOT_FOUND, f"snapshot {snapshot!r} not found")
        try:
            blk = toggle_block(obj, path_num, block, enabled, snapshot=snap_idx)
        except (KeyError, IndexError) as ex:
            return E.err(E.NOT_FOUND, str(ex))
        name = cat.friendly_name((blk.get("slot") or [{}])[0].get("model", "?"))
        where = f" (snapshot {snapshot})" if snapshot is not None else ""
        return _do_write(cat, obj, path, {"block": block, "enabled": enabled},
                         summary=f"{name} -> {'on' if enabled else 'OFF'}{where}")

    @mcp.tool(name="configure_snapshots")
    def configure_snapshots_tool(path: str, names: str, colors: str | None = None) -> dict:
        """Define the preset's snapshots (scenes) from a comma-separated `names` list, e.g.
        `Rhythm,Lead,Clean`, then write. Marks that many snapshots valid (named, in order) and
        the rest unused. `colors` is an optional comma-separated list (auto/blue/purple/pink/
        green/red/orange/…) matched by position. Use before setting per-snapshot values."""
        obj, e = _load_preset(path)
        if e:
            return e
        cat, e = _catalog(ctx)
        if e:
            return e
        name_list = [n for n in names.split(",")]
        color_list = colors.split(",") if colors else None
        try:
            res = configure_snapshots(obj, name_list, color_list)
        except ValueError as ex:
            return E.err(E.VALUE_OUT_OF_RANGE, str(ex))
        return _do_write(cat, obj, path, res,
                         summary=f"{res['valid']} snapshot(s): {', '.join(res['names'])}")

    @mcp.tool(name="set_active_snapshot")
    def set_active_snapshot_tool(path: str, snapshot: str) -> dict:
        """Set which snapshot (scene) is active by name or 1-based number, then write. Loads
        each automated block/param to that scene's stored value — this is the state the preset
        opens in."""
        obj, e = _load_preset(path)
        if e:
            return e
        cat, e = _catalog(ctx)
        if e:
            return e
        idx = resolve_snapshot_index(obj, snapshot)
        if idx is None:
            return E.err(E.NOT_FOUND, f"snapshot {snapshot!r} not found")
        try:
            set_active_snapshot(obj, idx)
        except (IndexError, ValueError) as ex:
            return E.err(E.VALUE_OUT_OF_RANGE, str(ex))
        name = obj["preset"]["snapshots"][idx].get("name", idx + 1)
        return _do_write(cat, obj, path, {"active_snapshot": idx + 1},
                         summary=f"active snapshot -> {name!r}")

    @mcp.tool(name="rename_preset")
    def rename_preset_tool(path: str, name: str) -> dict:
        """Rename the preset (meta.name), then write."""
        obj, e = _load_preset(path)
        if e:
            return e
        cat, e = _catalog(ctx)
        if e:
            return e
        try:
            rename_preset(obj, name)
        except ValueError as ex:
            return E.err(E.VALUE_OUT_OF_RANGE, str(ex))
        return _do_write(cat, obj, path, {"name": name}, summary=f"renamed preset -> {name!r}")

    @mcp.tool(name="rename_snapshot")
    def rename_snapshot_tool(path: str, snapshot: str, name: str) -> dict:
        """Rename a snapshot (by current name or 1-based number), then write."""
        obj, e = _load_preset(path)
        if e:
            return e
        cat, e = _catalog(ctx)
        if e:
            return e
        idx = resolve_snapshot_index(obj, snapshot)
        if idx is None:
            return E.err(E.NOT_FOUND, f"snapshot {snapshot!r} not found")
        try:
            rename_snapshot(obj, idx, name)
        except (IndexError, ValueError) as ex:
            return E.err(E.VALUE_OUT_OF_RANGE, str(ex))
        return _do_write(cat, obj, path, {"snapshot": idx + 1, "name": name},
                         summary=f"renamed snapshot {idx + 1} -> {name!r}")

    @mcp.tool(name="remove_block")
    def remove_block_tool(path: str, block: str, path_num: int = 1) -> dict:
        """Remove a processing block from a path (its slot becomes empty), then write.
        The input and output blocks cannot be removed."""
        obj, e = _load_preset(path)
        if e:
            return e
        cat, e = _catalog(ctx)
        if e:
            return e
        try:
            _blk, slot0 = find_block(obj, path_num, block)
            name = cat.friendly_name(slot0.get("model", "?"))
            k = remove_block(obj, path_num, block)
        except (KeyError, ValueError) as ex:
            return E.err(E.VALUE_OUT_OF_RANGE, str(ex))
        return _do_write(cat, obj, path, {"removed": k}, summary=f"removed {name} ({k})")

    @mcp.tool(name="move_block")
    def move_block_tool(path: str, block: str, before: str | None = None,
                        after: str | None = None, path_num: int = 1) -> dict:
        """Reorder a processing block to just `before` or `after` another block (both are
        block keys like `b06`), then write. Changes the signal-chain order; serial paths only."""
        obj, e = _load_preset(path)
        if e:
            return e
        cat, e = _catalog(ctx)
        if e:
            return e
        try:
            _blk, slot0 = find_block(obj, path_num, block)
            name = cat.friendly_name(slot0.get("model", "?"))
            new_key = move_block(obj, path_num, block, before=before, after=after)
        except (KeyError, ValueError) as ex:
            return E.err(E.VALUE_OUT_OF_RANGE, str(ex))
        rel = f"before {before}" if before is not None else f"after {after}"
        return _do_write(cat, obj, path, {"block": new_key},
                         summary=f"moved {name} {rel} (now {new_key})")

    @mcp.tool(name="add_block")
    def add_block_tool(path: str, model: str, path_num: int = 1,
                       before: str | None = None, after: str | None = None) -> dict:
        """Add a new block for a model (by id or friendly name, e.g. `Teemah!`) at its Line 6
        factory defaults, then write. Placed at the end of the chain, or `before`/`after` another
        block (block keys). The default block is built from your install's model definitions, so
        any model in the catalog can be added."""
        obj, e = _load_preset(path)
        if e:
            return e
        cat, e = _catalog(ctx)
        if e:
            return e
        mid = cat.find_model_id(model)
        if not mid:
            return E.err(E.NOT_FOUND, f"unknown model: {model!r}")
        template = synth_template(mid) or get_template(mid)
        if template is None:
            return E.err(E.NOT_FOUND,
                         f"could not build a default block for {cat.friendly_name(mid)} ({mid}); "
                         "your Helix Stadium model definitions could not be read from the install")
        try:
            new_key = add_block(obj, path_num, template, before=before, after=after)
        except (KeyError, ValueError) as ex:
            return E.err(E.VALUE_OUT_OF_RANGE, str(ex))
        return _do_write(cat, obj, path, {"block": new_key, "model": mid},
                         summary=f"added {cat.friendly_name(mid)} ({new_key})")

    @mcp.tool(name="create_preset")
    def create_preset_tool(path: str, name: str = "New Preset") -> dict:
        """Create a new blank preset (input → output, empty processing chain, 8 snapshots) and
        write it to `path`. Then build it up with `add_block` / `edit_param` / snapshot tools.
        This is the canvas the generation flow starts from. Built from your install's model
        definitions."""
        cat, e = _catalog(ctx)
        if e:
            return e
        from ..defaults import load_empty
        from ..modeldefs import synth_empty
        obj = synth_empty(name) or load_empty()   # synth from model-defs; external-template fallback
        if obj is None:
            return E.err(E.NOT_FOUND, "could not build a blank preset — your Helix Stadium model "
                                      "definitions could not be read from the install")
        obj["meta"]["name"] = name
        return _do_write(cat, obj, path, {"name": name}, summary=f"created blank preset {name!r}")
