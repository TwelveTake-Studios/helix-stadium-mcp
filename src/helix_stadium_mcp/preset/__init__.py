"""Typed navigation + human rendering over a parsed .hsp object.

Signal-flow derivation, snapshot handling, and the plain-English ``explain`` view
that combines the codec, catalog, and encoding.
"""
from __future__ import annotations

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


def block_summary(catalog, blk: dict, max_params: int = 6) -> dict:
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
        "type": blk.get("type", ""),
        "model": model,
        "name": catalog.friendly_name(model),
        "state": state,
        "tags": tags,
        "params": shown,
    }


def summarize(catalog, obj: dict) -> dict:
    meta = obj.get("meta", {})
    preset = obj.get("preset", {})
    p = preset.get("params", {})
    paths = []
    for path_obj in preset.get("flow", []):
        blocks = [block_summary(catalog, blk) for _bkey, blk in ordered_blocks(path_obj)]
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
            tagstr = f"  [{', '.join(b['tags'])}]" if b["tags"] else ""
            pstr = ("  ·  " + " | ".join(f"{p['id']} {p['display']}" for p in b["params"])) \
                if b["params"] else ""
            lines.append(f"  [{b['type']}] {b['name']} — {b['state']}{tagstr}{pstr}")
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
