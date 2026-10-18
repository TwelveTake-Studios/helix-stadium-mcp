"""Footswitches, expression pedals, scribble strips, snapshot control, Command Center.

Layout reverse-engineered from Helix Stadium XL firmware 1.4.0 exports (one change per
export, diffed). What is PROVEN by a capture vs INFERRED is marked per item; inferred
shapes follow the nearest proven one and are flagged in the tool descriptions.

- A controller lives on the thing it drives: ``@enabled.controller`` for a block's
  bypass (``type: targetbypass``), ``params.<P>.controller`` for a parameter (``type: param``).
- ``preset.sources`` holds one entry per physical control, keyed by its source id (as a
  string): footswitches carry ``fs_label`` / ``fs_color`` / ``fs_topidx``; the unit adds
  ``bypass: false`` once something is assigned (runtime state; never edited here).
- Several blocks on one switch simply share the source id (PROVEN).
- Command Center commands live in ``preset.commands[<source id>]`` as an ordered list.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from ..preset import _ensure_snapshot_array, find_block

# --- control ids -----------------------------------------------------------------------
# PROVEN: page A ids 0x01010100+i and page B ids 0x01010200+i exist (12 each) in every
# export; EXP 1 / EXP 2 pedals; one toe switch. INFERRED: index i == physical switch i+1.
_PAGE_A, _PAGE_B = 0x01010100, 0x01010200
EXP1, EXP2 = 0x01020100, 0x01020101
TOE = 0x01010500

SWITCHES: dict[str, int] = {
    **{f"A{i + 1}": _PAGE_A + i for i in range(12)},
    **{f"B{i + 1}": _PAGE_B + i for i in range(12)},
    "TOE": TOE,
}
PEDALS = {"EXP1": EXP1, "EXP2": EXP2}

# the app's color list (res/strings appStrings_eng.json /snapshot/color/*); "red" PROVEN
COLORS = ("auto", "white", "red", "oranged", "orangel", "yellow", "green", "bluel", "blue",
          "violet", "pink", "off")


def _norm(name: str) -> str:
    s = re.sub(r"[\s_\-]+", "", str(name).upper())
    s = s.removeprefix("STOMP").removeprefix("FS")
    return {"EXP1TOE": "TOE", "TOESWITCH": "TOE", "EXPTOE": "TOE"}.get(s, s)


def switch_id(name: str) -> int:
    """'Stomp A1' / 'a1' / 'B12' / 'toe' -> source id."""
    sid = SWITCHES.get(_norm(name))
    if sid is None:
        raise KeyError(f"unknown footswitch {name!r}; use A1..A12, B1..B12 or TOE")
    return sid


def pedal_id(name: str) -> int:
    sid = PEDALS.get(_norm(name))
    if sid is None:
        raise KeyError(f"unknown expression pedal {name!r}; use EXP1 or EXP2")
    return sid


def control_name(source) -> str | None:
    """Reverse lookup for display: 16843008 -> 'Stomp A1'."""
    for n, sid in {**SWITCHES, **PEDALS}.items():
        if sid == source:
            return n if n.startswith(("EXP", "TOE")) else f"Stomp {n}"
    return None


def _sources(obj: dict) -> dict:
    return obj.setdefault("preset", {}).setdefault("sources", {})


def _touch_source(obj: dict, sid: int) -> dict:
    """The unit adds ``{"bypass": false}`` to a source once anything is assigned to it."""
    src = _sources(obj).setdefault(str(sid), {})
    src.setdefault("bypass", False)
    return src


# --- controller assignment -----------------------------------------------------------------

def _controller(source: int, ctype: str, behavior: str, lo, hi, bypassed: bool) -> dict:
    # copied field-for-field from what the unit writes (captures 00 and 09)
    return {"behavior": behavior, "bypassed": bypassed, "curve": "linear", "delay": 0,
            "goid": 0, "max": hi, "midisource": 0, "min": lo, "source": source,
            "threshold": 0.0, "type": ctype}


def _holder(obj: dict, path_num: int, block, target: str) -> tuple[dict, dict]:
    blk, slot0 = find_block(obj, path_num, block)
    if target == "bypass":
        return blk, blk.setdefault("@enabled", {"value": True})
    pv = (slot0.get("params") or {}).get(target)
    if not isinstance(pv, dict) or "value" not in pv:
        raise KeyError(f"param {target!r} not found on block {block}")
    return blk, pv


def assign_switch(obj: dict, path_num: int, block, switch: str, target: str = "bypass",
                  behavior: str = "latching", lo=None, hi=None) -> int:
    """Put a block's bypass (PROVEN) or one of its params (INFERRED) on a footswitch.
    Re-assigning replaces the holder's previous controller. Returns the source id."""
    if behavior not in ("latching", "momentary"):
        raise ValueError("behavior must be 'latching' or 'momentary'")
    sid = switch_id(switch)
    _blk, h = _holder(obj, path_num, block, target)
    if target == "bypass":
        h["controller"] = _controller(sid, "targetbypass", behavior, False, True, False)
    else:
        if lo is None or hi is None:
            raise ValueError("a parameter on a footswitch needs min and max")
        h["controller"] = _controller(sid, "param", behavior, lo, hi, False)
    src = _touch_source(obj, sid)
    # PROVEN (04->05): adding a 2nd block to a switch points the strip at the new one.
    # The toe switch has no strip (11): leave it without one.
    if "fs_label" in src:
        src["fs_topidx"] = max(0, len(assignments_for(obj, sid)) - 1)
    return sid


def assign_pedal(obj: dict, path_num: int, block, param: str, pedal: str, lo, hi) -> int:
    """Sweep a param between ``lo`` and ``hi`` (stored units) from EXP 1 / EXP 2. PROVEN."""
    sid = pedal_id(pedal)
    _blk, pv = _holder(obj, path_num, block, param)
    # the unit writes bypassed: true on new pedal assignments and parks the value at min
    pv["controller"] = _controller(sid, "param", "continuous", lo, hi, True)
    pv["value"] = type(pv["value"])(lo) if not isinstance(pv["value"], bool) else pv["value"]
    _touch_source(obj, sid)
    return sid


def unassign(obj: dict, path_num: int, block, target: str = "bypass") -> bool:
    _blk, h = _holder(obj, path_num, block, target)
    return h.pop("controller", None) is not None


def assignments_for(obj: dict, sid: int) -> list[tuple[str, str]]:
    """Every (block key, target) on this source, in signal order."""
    out = []
    for path_obj in obj.get("preset", {}).get("flow", []):
        for k, blk in sorted(path_obj.items(), key=lambda kv: str(kv[0])):
            if not (k.startswith("b") and isinstance(blk, dict)):
                continue
            if ((blk.get("@enabled") or {}).get("controller") or {}).get("source") == sid:
                out.append((k, "bypass"))
            for pid, pv in ((blk.get("slot") or [{}])[0].get("params") or {}).items():
                if isinstance(pv, dict) and (pv.get("controller") or {}).get("source") == sid:
                    out.append((k, pid))
    return out


# --- scribble strip -----------------------------------------------------------------------

def set_switch_look(obj: dict, switch: str, label: str | None = None,
                    color: str | None = None) -> dict:
    """Scribble-strip label and LED color for a footswitch. PROVEN (07, 08)."""
    sid = switch_id(switch)
    src = _sources(obj).get(str(sid))
    if not isinstance(src, dict) or "fs_label" not in src:
        raise KeyError(f"switch {switch} has no label slot in this preset")
    if label is not None:   # ponytail: no length cap; the unit's limit isn't known yet
        src["fs_label"] = label
    if color is not None:
        c = color.strip().lower()
        if c not in COLORS:
            raise ValueError(f"color must be one of: {', '.join(COLORS)}")
        src["fs_color"] = c
    return src


# --- snapshot control ---------------------------------------------------------------------

def set_snapshot_control(obj: dict, path_num: int, block, target: str, enabled: bool) -> bool:
    """Turn snapshot control on/off for a block's bypass ("Snapshots Set Bypass", PROVEN
    12->13: the per-snapshot array is removed) or a param (INFERRED: same array shape)."""
    _blk, h = _holder(obj, path_num, block, target)
    if enabled:
        _ensure_snapshot_array(obj, h)
    else:
        h.pop("snapshots", None)
    return enabled


# --- Command Center -----------------------------------------------------------------------
# File "type" -> commanddefs key for a footswitch command. "MIDI" -> "MIDI-FS" PROVEN (14);
# "PresetSnapshot" PROVEN (15); the rest follow the same naming and are unverified.
_FS_DEFS = {"PresetSnapshot": "PresetSnapshot", "Song": "Song", "Looper": "Looper",
            "Utility": "Utility", "ExtAmp": "ExtAmp", "MIDI": "MIDI-FS", "HotKey": "HotKey"}


def load_command_defs(res_dir: str, device_id: int) -> dict:
    """The install's command definitions for this device (newest firmware variant)."""
    folder = os.path.join(res_dir, "commanddefs")
    best, best_ver = None, -1
    dec = json.JSONDecoder()
    for fn in os.listdir(folder):
        text = Path(folder, fn).read_text(encoding="utf-8")
        head, i = dec.raw_decode(text)
        ids = [int(x, 16) for x in head.get("id", [])]
        ver = int(head.get("ver", "0"), 16)
        if device_id in ids and ver > best_ver:
            best, best_ver = dec.raw_decode(text[i:].lstrip())[0], ver
    if best is None:
        raise FileNotFoundError(f"no command definitions for device {device_id:#x}")
    return best


def add_command(obj: dict, defs: dict, switch: str, ctype: str, params: dict | None = None,
                behavior: str = "latching") -> dict:
    """Append a Command Center command to a footswitch. Params not given take their
    defaults; names and ranges are checked against the install's definitions."""
    key = _FS_DEFS.get(ctype)
    if key is None or key not in defs:
        raise ValueError(f"command type must be one of: {', '.join(_FS_DEFS)}")
    pdefs = defs[key].get("params", {})
    params = dict(params or {})
    unknown = set(params) - set(pdefs)
    if unknown:
        raise KeyError(f"unknown {ctype} param(s) {sorted(unknown)}; valid: {sorted(pdefs)}")
    out = {}
    for name, d in pdefs.items():
        if name == "toggle":            # a top-level field in the file, not a param
            continue
        v = params.get(name, d["def"])
        if d["type"] == "i":
            v = int(v)
        elif d["type"] == "f":
            v = float(v)
        if not d["min"] <= v <= d["max"]:
            raise ValueError(f"{name} must be {d['min']}..{d['max']} (got {v})")
        out[name] = {"value": v}
    sid = switch_id(switch)
    cmds = obj["preset"].setdefault("commands", {}).setdefault(str(sid), [])
    cmd = {"behavior": behavior, "curve": "linear", "delay": 0, "goid": 0,
           "ordinal": len(cmds), "params": out, "threshold": 0.0, "toggle": False,
           "type": ctype}
    cmds.append(cmd)
    return cmd


def clear_commands(obj: dict, switch: str) -> int:
    cmds = obj.get("preset", {}).get("commands", {})
    removed = cmds.pop(str(switch_id(switch)), [])
    if not cmds:
        obj["preset"].pop("commands", None)   # the unit omits the key when empty (00..13)
    return len(removed)
