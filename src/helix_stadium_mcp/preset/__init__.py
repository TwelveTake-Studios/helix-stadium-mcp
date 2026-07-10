"""Typed navigation + human rendering over a parsed .hsp object.

Signal-flow derivation, snapshot handling, and the plain-English ``explain`` view
that combines the codec, catalog, and encoding.
"""
from __future__ import annotations

import copy

from ..encoding import display_string, sync_note_label

# behind-the-scenes params not surfaced in a human summary
_SKIP_PREFIX = ("AmpCab",)
_SKIP = {"IrData", "EvtIdx"}


def _snap_val(catalog, model_id: str, pid: str, v) -> str:
    """Render a snapshot value, mapping SyncSelect* to its note-division label."""
    if pid.startswith("SyncSelect"):
        label = sync_note_label(catalog, v)
        if label:
            return label
    return display_string(catalog, model_id, pid, v)[0]


def ordered_blocks(path_obj: dict) -> list[tuple[str, dict]]:
    blocks = {k: v for k, v in path_obj.items() if k.startswith("b") and isinstance(v, dict)}
    return sorted(blocks.items(), key=lambda kv: kv[1].get("position", 0))


def valid_snapshots(obj: dict) -> list[dict]:
    return [s for s in obj.get("preset", {}).get("snapshots", []) if s.get("valid")]


def _block_state(blk: dict, slot0: dict) -> tuple[str, list[str]]:
    en = blk.get("@enabled", {})
    state = "on" if en.get("value") else "OFF"
    tags = []
    params = slot0.get("params") or {}
    has_snap = "snapshots" in en or any(
        isinstance(pv, dict) and "snapshots" in pv for pv in params.values())
    if has_snap:
        tags.append("per-snapshot")
    if "controller" in en:
        tags.append("footswitch")
    return state, tags


def render_param(catalog, model_id: str, pid: str, pv: dict, params: dict) -> str:
    """Display string for one param, tempo-sync aware (uses sibling params)."""
    val = pv.get("value")
    pdef = catalog.param_def(model_id, pid)
    # a time/rate param that is currently tempo-synced -> show the note division
    if pdef and pdef.get("sync") and pdef.get("note"):
        if (params.get(pdef["sync"]) or {}).get("value"):
            label = sync_note_label(catalog, (params.get(pdef["note"]) or {}).get("value"))
            if label:
                return label
    # a sync-select param -> show the note-division name
    if pid.startswith("SyncSelect"):
        label = sync_note_label(catalog, val)
        if label:
            return label
    return display_string(catalog, model_id, pid, val)[0]


def _controller_info(catalog, model_id: str, target: str, ctrl: dict, sources: dict) -> dict:
    """Describe one footswitch/expression controller on a block: its target (``bypass`` or a
    param id), the source id it's bound to, its behavior, and — for a parameter controller —
    the sweep range in real display units."""
    info = {
        "target": target,
        "source": ctrl.get("source"),
        "behavior": ctrl.get("behavior"),
    }
    if ctrl.get("bypassed"):
        info["assignment_disabled"] = True
    src = sources.get(str(ctrl.get("source"))) if isinstance(sources, dict) else None
    if isinstance(src, dict) and src.get("fs_label"):
        info["label"] = src["fs_label"]
    if target != "bypass":                       # parameter controller -> render its range
        lo, hi = ctrl.get("min"), ctrl.get("max")
        if isinstance(lo, (int, float)) and not isinstance(lo, bool):
            info["min"] = display_string(catalog, model_id, target, lo)[0]
        if isinstance(hi, (int, float)) and not isinstance(hi, bool):
            info["max"] = display_string(catalog, model_id, target, hi)[0]
    return info


def _block_controllers(catalog, blk: dict, model_id: str, sources: dict) -> list[dict]:
    """Every controller assignment on a block: the bypass footswitch (if any) plus any
    per-parameter controllers (e.g. a momentary footswitch swelling a delay's Mix)."""
    out = []
    en = blk.get("@enabled") or {}
    if isinstance(en.get("controller"), dict):
        out.append(_controller_info(catalog, model_id, "bypass", en["controller"], sources))
    for pid, pv in ((blk.get("slot") or [{}])[0].get("params") or {}).items():
        if isinstance(pv, dict) and isinstance(pv.get("controller"), dict):
            out.append(_controller_info(catalog, model_id, pid, pv["controller"], sources))
    return out


def block_summary(catalog, blk: dict, key: str | None = None, sources: dict | None = None,
                  max_params: int = 6) -> dict:
    slot0 = (blk.get("slot") or [{}])[0]
    model = slot0.get("model", "?")
    state, tags = _block_state(blk, slot0)
    params = slot0.get("params") or {}
    shown = []
    for pid, pv in params.items():
        if pid in _SKIP or pid.startswith(_SKIP_PREFIX):
            continue
        if isinstance(pv, dict) and "value" in pv:
            shown.append({"id": pid, "display": render_param(catalog, model, pid, pv, params)})
        if len(shown) >= max_params:
            break
    return {
        "key": key,
        "type": blk.get("type", ""),
        "model": model,
        "name": catalog.friendly_name(model),
        "state": state,
        "tags": tags,
        "controllers": _block_controllers(catalog, blk, model, sources or {}),
        "params": shown,
    }


def summarize(catalog, obj: dict) -> dict:
    meta = obj.get("meta", {})
    preset = obj.get("preset", {})
    p = preset.get("params", {})
    sources = preset.get("sources", {})
    paths = []
    for path_obj in preset.get("flow", []):
        blocks = [block_summary(catalog, blk, key=bkey, sources=sources)
                  for bkey, blk in ordered_blocks(path_obj)]
        paths.append(blocks)
    return {
        "name": meta.get("name"),
        "tempo": p.get("tempo"),
        "input_z": p.get("inst1Z"),
        "active_snapshot": p.get("activesnapshot"),
        "snapshots": [{"name": s.get("name"), "color": s.get("color")}
                      for s in valid_snapshots(obj)],
        "paths": paths,
    }


def explain_text(catalog, obj: dict) -> str:
    s = summarize(catalog, obj)
    lines = [f"# {s['name']}",
             f"tempo {s['tempo']} BPM | input-Z {s['input_z']} | active snapshot #{s['active_snapshot']}"]
    snaps = ", ".join(f"{i+1}. {sn['name']} ({sn['color']})" for i, sn in enumerate(s["snapshots"]))
    lines.append(f"\nSnapshots: {snaps}")
    for pi, blocks in enumerate(s["paths"], start=1):
        lines.append(f"\n## Path {pi}")
        for b in blocks:
            bkey = f"{b['key']} " if b.get("key") else ""
            tagstr = f"  [{', '.join(b['tags'])}]" if b["tags"] else ""
            pstr = ("  ·  " + " | ".join(f"{p['id']} {p['display']}" for p in b["params"])) \
                if b["params"] else ""
            lines.append(f"  {bkey}[{b['type']}] {b['name']} — {b['state']}{tagstr}{pstr}")
            for c in b.get("controllers", []):
                rng = f" [{c['min']}..{c['max']}]" if ("min" in c and "max" in c) else ""
                lbl = f" '{c['label']}'" if c.get("label") else ""
                dis = " (disabled)" if c.get("assignment_disabled") else ""
                beh = c.get("behavior") or "controller"
                lines.append(f"      ctrl: {beh} FS source {c['source']}{lbl}"
                             f" -> {c['target']}{rng}{dis}")
    return "\n".join(lines)


# --- snapshots ------------------------------------------------------------
def resolve_snapshot_index(obj: dict, ident) -> int | None:
    """Resolve a snapshot name or 1-based number to a 0-based index (or None)."""
    snaps = obj.get("preset", {}).get("snapshots", [])
    if isinstance(ident, int):
        return ident - 1 if 1 <= ident <= len(snaps) else None
    s = str(ident).strip()
    if s.isdigit():
        i = int(s) - 1
        return i if 0 <= i < len(snaps) else None
    for i, sn in enumerate(snaps):
        if (sn.get("name") or "").lower() == s.lower():
            return i
    return None


def snapshot_diff(catalog, obj: dict, a_idx: int, b_idx: int) -> dict:
    """Report every block-bypass and parameter that differs between two snapshots."""
    preset = obj.get("preset", {})
    snaps = preset.get("snapshots", [])

    def both_set(arr) -> bool:
        return (isinstance(arr, list) and a_idx < len(arr) and b_idx < len(arr)
                and arr[a_idx] is not None and arr[b_idx] is not None)

    changes: list[dict] = []
    for pi, path_obj in enumerate(preset.get("flow", []), start=1):
        for _bkey, blk in ordered_blocks(path_obj):
            slot0 = (blk.get("slot") or [{}])[0]
            model = slot0.get("model", "?")
            bname = catalog.friendly_name(model)
            es = (blk.get("@enabled") or {}).get("snapshots")
            if both_set(es) and es[a_idx] != es[b_idx]:
                changes.append({"block": bname, "param": "bypass",
                                "from": "on" if es[a_idx] else "off",
                                "to": "on" if es[b_idx] else "off"})
            for pid, pv in (slot0.get("params") or {}).items():
                if not isinstance(pv, dict):
                    continue
                ps = pv.get("snapshots")
                if both_set(ps) and ps[a_idx] != ps[b_idx]:
                    changes.append({"block": bname, "param": pid,
                                    "from": _snap_val(catalog, model, pid, ps[a_idx]),
                                    "to": _snap_val(catalog, model, pid, ps[b_idx])})

    def label(i):
        return {"index": i + 1, "name": snaps[i].get("name") if i < len(snaps) else None}

    return {"a": label(a_idx), "b": label(b_idx), "changes": changes}


# --- mutation helpers -------------------------------------------
def _norm_block_key(key) -> str:
    """'b4' / '4' / 'b04' -> 'b04'."""
    s = str(key).strip().lower()
    if s.startswith("b"):
        s = s[1:]
    return "b" + s.zfill(2)


def _coerce_like(new, existing):
    """Coerce ``new`` to the numeric TYPE of ``existing`` (preserves int-vs-float)."""
    if isinstance(existing, bool):
        return bool(new)
    if isinstance(existing, int) and not isinstance(existing, bool):
        return int(round(float(new)))
    if isinstance(existing, float):
        return float(new)
    return new


def find_block(obj: dict, path_num: int, block_key) -> tuple[dict, dict]:
    """Return ``(block, slot0)`` for a 1-based path number and block key."""
    flow = obj.get("preset", {}).get("flow", [])
    if not 1 <= path_num <= len(flow):
        raise KeyError(f"path {path_num} not found (preset has {len(flow)} path(s))")
    k = _norm_block_key(block_key)
    blk = flow[path_num - 1].get(k)
    if not isinstance(blk, dict):
        raise KeyError(f"block {k} not found on path {path_num}")
    return blk, (blk.get("slot") or [{}])[0]


def _active_snapshot(obj: dict) -> int:
    return obj.get("preset", {}).get("params", {}).get("activesnapshot", 0)


def _snapshots(obj: dict) -> list:
    return obj.get("preset", {}).get("snapshots", [])


def _automatable_holders(obj: dict):
    """Yield every value-holder that can carry per-snapshot automation: each block's
    ``@enabled`` and each of its slot-0 params (both keyed ``value``/``snapshots``)."""
    for path_obj in obj.get("preset", {}).get("flow", []):
        for k, blk in path_obj.items():
            if not (k.startswith("b") and isinstance(blk, dict)):
                continue
            en = blk.get("@enabled")
            if isinstance(en, dict):
                yield en
            for pv in ((blk.get("slot") or [{}])[0].get("params") or {}).values():
                if isinstance(pv, dict) and "value" in pv:
                    yield pv


def _ensure_snapshot_array(obj: dict, holder: dict) -> list:
    """Return ``holder['snapshots']``, creating it on demand: a per-scene array seeded with
    the holder's current value at every valid snapshot index, ``None`` at unused slots."""
    snaps = holder.get("snapshots")
    if isinstance(snaps, list):
        return snaps
    snapshots = _snapshots(obj)
    n = len(snapshots) or 8
    cur = holder.get("value")
    arr = [cur if (i < len(snapshots) and snapshots[i].get("valid")) else None for i in range(n)]
    holder["snapshots"] = arr
    return arr


def edit_param(obj: dict, path_num: int, block_key, param_id: str, stored, snapshot=None) -> dict:
    """Set a param's stored value (coerced to its existing numeric type).

    ``snapshot=None`` edits the current value (and its active-snapshot slot, keeping the
    value==snapshots[active] invariant). An int ``snapshot`` edits that scene's slot,
    creating the per-snapshot automation array on first use. Returns the mutated block.
    """
    _blk, slot0 = find_block(obj, path_num, block_key)
    pv = (slot0.get("params") or {}).get(param_id)
    if not isinstance(pv, dict) or "value" not in pv:
        raise KeyError(f"param {param_id!r} not found on block {_norm_block_key(block_key)}")
    coerced = _coerce_like(stored, pv["value"])
    active = _active_snapshot(obj)
    if snapshot is None:
        pv["value"] = coerced
        snaps = pv.get("snapshots")
        if isinstance(snaps, list) and 0 <= active < len(snaps):
            snaps[active] = coerced
    else:
        snaps = _ensure_snapshot_array(obj, pv)
        if not 0 <= snapshot < len(snaps):
            raise IndexError(f"snapshot index {snapshot} out of range [0,{len(snaps) - 1}]")
        snaps[snapshot] = coerced
        if snapshot == active:
            pv["value"] = coerced
    return _blk


def toggle_block(obj: dict, path_num: int, block_key, enabled: bool, snapshot=None) -> dict:
    """Enable/disable a block. ``snapshot=None`` sets the current bypass (and the active-
    snapshot slot); an int ``snapshot`` sets that scene's bypass, creating the per-snapshot
    automation array on first use."""
    blk, _ = find_block(obj, path_num, block_key)
    en = blk.setdefault("@enabled", {})
    active = _active_snapshot(obj)
    val = bool(enabled)
    if snapshot is None:
        en["value"] = val
        snaps = en.get("snapshots")
        if isinstance(snaps, list) and 0 <= active < len(snaps):
            snaps[active] = val
    else:
        snaps = _ensure_snapshot_array(obj, en)
        if not 0 <= snapshot < len(snaps):
            raise IndexError(f"snapshot index {snapshot} out of range [0,{len(snaps) - 1}]")
        snaps[snapshot] = val
        if snapshot == active:
            en["value"] = val
    return blk


def configure_snapshots(obj: dict, names: list[str], colors: list[str] | None = None) -> dict:
    """Define the preset's scenes: mark the first ``len(names)`` snapshots valid with the
    given names (and optional colors), invalidate the rest, and reshape any existing
    automation arrays to match. Returns ``{"valid": n, "names": [...]}``."""
    snapshots = _snapshots(obj)
    if not isinstance(snapshots, list) or not snapshots:
        raise ValueError("preset has no snapshots to configure")
    names = [str(n).strip() for n in names if str(n).strip()]
    count = len(names)
    if not 1 <= count <= len(snapshots):
        raise ValueError(f"need 1..{len(snapshots)} snapshot names (got {count})")
    for i, snap in enumerate(snapshots):
        snap["valid"] = i < count
        if i < count:
            snap["name"] = names[i]
            snap["expsw"] = 1                 # valid scenes carry a real expression-switch state
            snap.setdefault("color", "auto")
            if colors and i < len(colors) and str(colors[i]).strip():
                snap["color"] = str(colors[i]).strip()
    # reshape automation: seed newly-valid slots from the current value, null unused ones
    for holder in _automatable_holders(obj):
        snaps = holder.get("snapshots")
        if not isinstance(snaps, list):
            continue
        while len(snaps) < len(snapshots):
            snaps.append(None)
        for i in range(len(snapshots)):
            if i < count:
                if snaps[i] is None:
                    snaps[i] = holder.get("value")
            else:
                snaps[i] = None
    # keep the active snapshot pointing at a valid scene
    if _active_snapshot(obj) >= count:
        set_active_snapshot(obj, 0)
    return {"valid": count, "names": names}


def set_active_snapshot(obj: dict, index: int) -> int:
    """Make snapshot ``index`` active: set ``activesnapshot`` and load each automated
    holder's value from that scene's slot (keeping the value==snapshots[active] invariant)."""
    snapshots = _snapshots(obj)
    if not 0 <= index < len(snapshots):
        raise IndexError(f"snapshot index {index} out of range [0,{len(snapshots) - 1}]")
    if not snapshots[index].get("valid"):
        raise ValueError(f"snapshot {index + 1} is not configured (call configure_snapshots first)")
    obj.setdefault("preset", {}).setdefault("params", {})["activesnapshot"] = index
    for holder in _automatable_holders(obj):
        snaps = holder.get("snapshots")
        if isinstance(snaps, list) and index < len(snaps) and snaps[index] is not None:
            holder["value"] = snaps[index]
    return index


def rename_preset(obj: dict, name: str) -> None:
    if not name:
        raise ValueError("preset name cannot be empty")
    obj.setdefault("meta", {})["name"] = name


def rename_snapshot(obj: dict, index: int, name: str) -> None:
    snaps = obj.get("preset", {}).get("snapshots", [])
    if not 0 <= index < len(snaps):
        raise IndexError(f"snapshot index {index} out of range")
    snaps[index]["name"] = name


def _processing_blocks(path_obj: dict) -> list[tuple[str, dict]]:
    """Processing blocks (positions 1..12) of a path, in signal order."""
    return sorted(
        ((k, v) for k, v in path_obj.items()
         if k.startswith("b") and isinstance(v, dict) and 1 <= v.get("position", 0) <= 12),
        key=lambda kv: kv[1]["position"],
    )


def remove_block(obj: dict, path_num: int, block_key) -> str:
    """Delete a processing block (leaving its slot empty). Refuses input/output blocks."""
    blk, _ = find_block(obj, path_num, block_key)
    if blk.get("type") in ("input", "output"):
        raise ValueError("cannot remove the input or output block (a path needs both)")
    k = _norm_block_key(block_key)
    del obj["preset"]["flow"][path_num - 1][k]
    return k


def move_block(obj: dict, path_num: int, block_key, before=None, after=None) -> str:
    """Reorder a processing block to just before/after another, re-packing the chain to
    contiguous positions. Returns the block's new key. Signal order is what changes;
    input (b00) / output (b13) are untouched."""
    if (before is None) == (after is None):
        raise ValueError("specify exactly one of 'before' or 'after'")
    path_obj = obj["preset"]["flow"][path_num - 1]
    proc = _processing_blocks(path_obj)
    by_key = dict(proc)
    key = _norm_block_key(block_key)
    ref_key = _norm_block_key(before if before is not None else after)
    if key not in by_key:
        raise KeyError(f"{key} is not a movable processing block on path {path_num}")
    if ref_key not in by_key:
        raise KeyError(f"reference block {ref_key} not found among processing blocks")
    if key == ref_key:
        raise ValueError("cannot move a block relative to itself")

    order = [v for _, v in proc]
    moving, ref = by_key[key], by_key[ref_key]
    order.remove(moving)
    idx = order.index(ref)
    order.insert(idx if before is not None else idx + 1, moving)

    for k, _ in proc:            # clear old processing keys, then re-key contiguously
        del path_obj[k]
    for i, blk in enumerate(order, start=1):
        blk["position"] = i
        path_obj[f"b{i:02d}"] = blk
    return f"b{order.index(moving) + 1:02d}"


def add_block(obj: dict, path_num: int, template: dict, before=None, after=None) -> str:
    """Insert a new block (from a default ``template``) into a path, re-packing the chain.

    Placed at the end (before output) by default, or just ``before``/``after`` another block.
    Returns the new block's key. Raises if the path is full (12 processing blocks max).
    """
    if before is not None and after is not None:
        raise ValueError("specify at most one of 'before' or 'after'")
    path_obj = obj["preset"]["flow"][path_num - 1]
    proc = _processing_blocks(path_obj)
    if len(proc) >= 12:
        raise ValueError("path is full (12 processing blocks max)")

    new_blk = copy.deepcopy(template)
    new_blk.setdefault("path", 0)
    order = [v for _, v in proc]
    if before is not None or after is not None:
        by_key = dict(proc)
        ref_key = _norm_block_key(before if before is not None else after)
        if ref_key not in by_key:
            raise KeyError(f"reference block {ref_key} not found on path {path_num}")
        idx = order.index(by_key[ref_key])
        order.insert(idx if before is not None else idx + 1, new_blk)
    else:
        order.append(new_blk)   # default: end of the chain, just before output

    for k, _ in proc:
        del path_obj[k]
    for i, blk in enumerate(order, start=1):
        blk["position"] = i
        path_obj[f"b{i:02d}"] = blk
    return f"b{order.index(new_blk) + 1:02d}"
