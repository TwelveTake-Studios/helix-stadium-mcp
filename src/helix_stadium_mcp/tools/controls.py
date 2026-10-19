"""Footswitch / expression / scribble-strip / snapshot-control / Command Center tools.

Same safety gate as every other write. Each tool takes an optional ``save_as``: write the
result to a new file instead of over ``path`` (read-only originals are refused anyway).
"""
from __future__ import annotations

import json

from .. import controls as C
from ..encoding import stored_value
from ..preset import find_block
from ..util import envelope as E
from .edit import _do_write, _parse_value
from .read import _catalog, _load_preset


def register(mcp, ctx) -> None:

    def run(path, save_as, fn):
        """Load -> fn(obj, cat) -> (data, summary) -> safe write to save_as or path."""
        obj, e = _load_preset(path)
        if e:
            return e
        cat, e = _catalog(ctx)
        if e:
            return e
        try:
            data, summary = fn(obj, cat)
        except (KeyError, ValueError, IndexError, FileNotFoundError) as ex:
            return E.err(E.VALUE_OUT_OF_RANGE, str(ex).strip("'\""))
        return _do_write(cat, obj, save_as or path, data, summary=summary)

    def stored(cat, obj, path_num, block, param, v):
        _blk, slot0 = find_block(obj, path_num, block)
        return stored_value(cat, slot0.get("model", "?"), param, _parse_value(v))

    @mcp.tool(name="assign_footswitch")
    def assign_footswitch(path: str, block: str, switch: str, behavior: str = "latching",
                          param: str | None = None, min: str | None = None,
                          max: str | None = None, path_num: int = 1,
                          save_as: str | None = None) -> dict:
        """Put a block on a footswitch: `switch` is A1..A12 (Stomp page A), B1..B12 (page B)
        or TOE (the expression pedal's toe switch). `behavior` is latching or momentary.
        Several blocks can share one switch — call once per block. Without `param` the switch
        turns the block on/off; with `param` (plus `min`/`max` in display units) it flips that
        parameter between the two values instead. Not yet confirmed on the unit: the toe
        switch."""
        def fn(obj, cat):
            target = param or "bypass"
            lo = hi = None
            if param:
                if min is None or max is None:
                    raise ValueError("a parameter on a footswitch needs min and max")
                lo = stored(cat, obj, path_num, block, param, min)
                hi = stored(cat, obj, path_num, block, param, max)
            C.assign_switch(obj, path_num, block, switch, target, behavior, lo, hi)
            return ({"block": block, "switch": switch, "target": target, "behavior": behavior},
                    f"{block} {target} -> {switch} ({behavior})")
        return run(path, save_as, fn)

    @mcp.tool(name="assign_expression")
    def assign_expression(path: str, block: str, param: str, pedal: str, min: str, max: str,
                          path_num: int = 1, save_as: str | None = None) -> dict:
        """Sweep a block parameter with an expression pedal: `pedal` is EXP1 or EXP2, `min`
        (heel) and `max` (toe) in display units, e.g. `10` and `60` for 10 %..60 %."""
        def fn(obj, cat):
            lo = stored(cat, obj, path_num, block, param, min)
            hi = stored(cat, obj, path_num, block, param, max)
            C.assign_pedal(obj, path_num, block, param, pedal, lo, hi)
            return ({"block": block, "param": param, "pedal": pedal, "min": min, "max": max},
                    f"{block} {param} on {pedal} ({min}..{max})")
        return run(path, save_as, fn)

    @mcp.tool(name="unassign_controller")
    def unassign_controller(path: str, block: str, target: str = "bypass", path_num: int = 1,
                            save_as: str | None = None) -> dict:
        """Remove a footswitch/pedal assignment from a block's on/off (`target` = bypass) or
        from one of its parameters (`target` = the param id)."""
        def fn(obj, cat):
            if not C.unassign(obj, path_num, block, target):
                raise KeyError(f"{block} {target} has no assignment")
            return {"block": block, "target": target}, f"cleared {block} {target} assignment"
        return run(path, save_as, fn)

    @mcp.tool(name="set_switch_label")
    def set_switch_label(path: str, switch: str, label: str | None = None,
                         color: str | None = None, save_as: str | None = None) -> dict:
        """Set a footswitch's scribble-strip text and/or LED color. `switch` is A1..A12 or
        B1..B12. Colors: off, auto, white, red, orange, light orange, yellow, green, turquoise,
        blue, purple, pink. An empty label goes back to the block's name."""
        def fn(obj, cat):
            src = C.set_switch_look(obj, switch, label, color)
            return ({"switch": switch, "label": src["fs_label"], "color": src["fs_color"]},
                    f"{switch}: '{src['fs_label']}' {src['fs_color']}")
        return run(path, save_as, fn)

    @mcp.tool(name="set_snapshot_bypass")
    def set_snapshot_bypass(path: str, block: str, enabled: bool, path_num: int = 1,
                            save_as: str | None = None) -> dict:
        """Turn "Snapshots Set Bypass" on or off for a block. On: each snapshot remembers
        whether the block is on. Off: snapshots leave the block's on/off alone."""
        def fn(obj, cat):
            C.set_snapshot_control(obj, path_num, block, "bypass", enabled)
            return ({"block": block, "snapshots_set_bypass": enabled},
                    f"{block} Snapshots Set Bypass -> {'on' if enabled else 'off'}")
        return run(path, save_as, fn)

    @mcp.tool(name="set_param_snapshot_control")
    def set_param_snapshot_control(path: str, block: str, param: str, enabled: bool,
                                   path_num: int = 1, save_as: str | None = None) -> dict:
        """Make a parameter snapshot-controlled (each snapshot keeps its own value; set them
        with edit_param's `snapshot` argument) or turn that off (one value for all)."""
        def fn(obj, cat):
            C.set_snapshot_control(obj, path_num, block, param, enabled)
            return ({"block": block, "param": param, "snapshot_controlled": enabled},
                    f"{block} {param} snapshot control -> {'on' if enabled else 'off'}")
        return run(path, save_as, fn)

    @mcp.tool(name="add_command")
    def add_command(path: str, switch: str, type: str, params: str = "{}",
                    behavior: str = "latching", save_as: str | None = None) -> dict:
        """Add a Command Center command to a footswitch (A1..A12, B1..B12). `type` is one of
        MIDI, PresetSnapshot, Song, Looper, Utility, ExtAmp, HotKey. `params` is a JSON object
        of that type's settings by name, e.g. for MIDI `{"MIDI Ch": 2, "Command": 1, "CC#": 13,
        "Value": 127}`; unset ones take Line 6's defaults and every value is range-checked
        against your install. Option numbers (Command, Action) are raw. All seven types, and
        two commands on one switch, survive a round trip through the unit unchanged
        (2026-10-18); that the unit then sends the right MIDI was not checked."""
        def fn(obj, cat):
            defs = C.load_command_defs(str(cat.res), int(obj["meta"]["device_id"]))
            cmd = C.add_command(obj, defs, switch, type, json.loads(params or "{}"), behavior)
            return ({"switch": switch, "command": cmd},
                    f"{switch}: added {type} command #{cmd['ordinal']}")
        return run(path, save_as, fn)

    @mcp.tool(name="clear_commands")
    def clear_commands(path: str, switch: str, save_as: str | None = None) -> dict:
        """Remove every Command Center command from a footswitch."""
        def fn(obj, cat):
            n = C.clear_commands(obj, switch)
            return {"switch": switch, "removed": n}, f"{switch}: removed {n} command(s)"
        return run(path, save_as, fn)
