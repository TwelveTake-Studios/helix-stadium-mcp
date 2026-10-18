"""Live editing: read and change the preset that is loaded on the unit right now.

Changes go to the unit's working copy (like turning a knob on the unit): nothing is saved
until the user saves on the unit, so switching away from the preset without saving undoes
them. Write tools are removed by HELIX_MCP_READONLY like every other write.
"""
from __future__ import annotations

import os

from .. import live as L
from ..encoding import display_string, stored_value
from ..modeldefs import load_modeldefs
from ..util import envelope as E
from .edit import _parse_value
from .read import _catalog


def _defs():
    md = load_modeldefs()
    return md, {r["id"]: k for k, r in md.items() if isinstance(r, dict) and "id" in r}


def _pid(md, model, name):
    p = (md.get(model) or {}).get("params", {}).get(name)
    if p is None:
        raise KeyError(f"{model} has no parameter {name!r}")
    return p["id"], p


def _view(cat, md, blk):
    pnames = {p["id"]: n for n, p in (md.get(blk["model"]) or {}).get("params", {}).items()}
    params = {}
    for pid, p in blk["params"].items():
        n = pnames.get(pid)
        if n:
            params[n] = display_string(cat, blk["model"], n, p["value"])[0] + \
                (" (per snapshot)" if p["snap"] else "")
    friendly = cat.friendly_name(blk["model"])
    return {"path": blk["path"], "position": blk["position"], "model": blk["model"],
            "name": friendly, "on": blk["enabled"], "params": params}


def register(mcp, ctx) -> None:

    def guarded(fn):
        try:
            return fn()
        except (ConnectionError, OSError) as ex:
            return E.err(E.IO_ERROR, f"can't reach the unit: {ex}")
        except (KeyError, ValueError) as ex:
            return E.err(E.VALUE_OUT_OF_RANGE, str(ex).strip("'\""))

    @mcp.tool(name="live_read")
    def live_read() -> dict:
        """Read the preset loaded on the unit right now, over the network: every block with
        its path, position, on/off and parameters in real units, plus `preset_id`. Pass
        `path`, `position`, `model` and `preset_id` from here to the live_* edit tools."""
        cat, e = _catalog(ctx)
        if e:
            return e
        md, names = _defs()

        def go():
            with L.Unit() as u:
                pid, eb = u.property("server.active.preset.id"), u.edit_buffer()
            blks = [_view(cat, md, b) for b in L.blocks(eb, names)
                    if not b["model"].startswith(("P35_Input", "P35_Output"))]
            return E.ok({"preset_id": pid, "blocks": blks},
                        summary=f"preset {pid}: {len(blks)} block(s)")
        return guarded(go)

    if os.environ.get("HELIX_MCP_READONLY", "").strip().lower() in ("1", "true", "yes", "on"):
        return

    def fresh(u, preset_id, path, position):
        if u.property("server.active.preset.id") != preset_id:
            raise ValueError("a different preset is loaded on the unit now; read it again")
        md, names = _defs()
        return md, names, L.find(u.edit_buffer(), names, path, position)

    @mcp.tool(name="live_set_param")
    def live_set_param(preset_id: int, path: int, position: int, model: str, param: str,
                       value: str) -> dict:
        """Change one knob on the unit right now (not saved until the user saves on the
        unit). `value` is in real units, e.g. `7` for Drive 7 or `35` for 35 %. Get the other
        arguments from live_read. Only knob-style (continuous) parameters on path 1 are
        supported so far; snapshot-controlled parameters are refused."""
        cat, e = _catalog(ctx)
        if e:
            return e

        def go():
            with L.Unit() as u:
                md, names, blk = fresh(u, preset_id, path, position)
                pid, pdef = _pid(md, model, param)
                L.check_target(blk, model, pid, pdef)
                v = float(stored_value(cat, model, param, _parse_value(value)))
                if not pdef["min"] <= v <= pdef["max"]:
                    raise ValueError(f"{param} must stay in its range")
                before = blk["params"][pid]["value"]
                u.call("/ParamValueSet", "iiiifi", path - 1, position, blk["slot"], pid, v, -1)
                after = L.find(u.edit_buffer(), names, path, position)["params"][pid]["value"]
            if abs(after - v) > 1e-4:
                raise ValueError(f"the unit did not take the change ({param} still "
                                 f"{display_string(cat, model, param, after)[0]})")
            show = lambda x: display_string(cat, model, param, x)[0]
            return E.ok({"param": param, "before": show(before), "after": show(after)},
                        summary=f"{param}: {show(before)} -> {show(after)} (not saved)")
        return guarded(go)

    @mcp.tool(name="live_toggle_block")
    def live_toggle_block(preset_id: int, path: int, position: int, model: str,
                          on: bool) -> dict:
        """Turn a block on or off on the unit right now (not saved until the user saves on
        the unit). Get the arguments from live_read."""
        def go():
            with L.Unit() as u:
                _md, names, blk = fresh(u, preset_id, path, position)
                L.check_target(blk, model)
                u.call("/BlockEnableSet", "iii", path - 1, position, int(on))
                after = L.find(u.edit_buffer(), names, path, position)["enabled"]
            if after != on:
                raise ValueError("the unit did not take the change")
            return E.ok({"model": model, "on": after},
                        summary=f"{model} {'on' if after else 'off'} (not saved)")
        return guarded(go)

    @mcp.tool(name="live_snapshot")
    def live_snapshot(snapshot: int) -> dict:
        """Switch the unit to snapshot 1-8 right now."""
        if not 1 <= snapshot <= 8:
            return E.err(E.VALUE_OUT_OF_RANGE, "snapshot must be 1-8")

        def go():
            with L.Unit() as u:
                _r, status = u.call("/activateSnapshot", "i", snapshot - 1)
            return E.ok({"snapshot": snapshot, "status": status},
                        summary=f"sent snapshot {snapshot}")
        return guarded(go)
