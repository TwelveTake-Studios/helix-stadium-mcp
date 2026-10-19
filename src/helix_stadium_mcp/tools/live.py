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
        except (KeyError, ValueError, IndexError) as ex:
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

    @mcp.tool(name="live_list_presets")
    def live_list_presets() -> dict:
        """The presets stored on the unit (user and factory), with the ids that
        live_load_preset takes."""
        def go():
            out = {}
            with L.Unit() as u:
                for name, cont in (("user", -2), ("factory", -1)):
                    replies, _ = u.call("/GetContainerContents", "i", cont,
                                        reply="/GetContainerContents")
                    raw = next(x for x in replies[-1][1] if isinstance(x, bytes))
                    out[name] = L.presets(raw)
            return E.ok(out, summary=f"{len(out['user'])} user, {len(out['factory'])} factory")
        return guarded(go)

    if os.environ.get("HELIX_MCP_READONLY", "").strip().lower() in ("1", "true", "yes", "on"):
        return

    def active(u, preset_id):
        if u.property("server.active.preset.id") != preset_id:
            raise ValueError("a different preset is loaded on the unit now; read it again")
        return u.edit_buffer()

    def fresh(u, preset_id, path, position):
        eb = active(u, preset_id)
        md, names = _defs()
        return md, names, L.find(eb, names, path, position), eb

    @mcp.tool(name="live_set_param")
    def live_set_param(preset_id: int, path: int, position: int, model: str, param: str,
                       value: str) -> dict:
        """Change one knob, switch or list setting on the unit right now (not saved until the user
        saves). `value` is in real units, e.g. `7` for Drive 7, `35` for 35 %, `on`/`off`.
        Get the other arguments from live_read. On a per-snapshot parameter this changes
        the ACTIVE snapshot's value only (switch with live_snapshot first). List-type
        settings take their label, e.g. `1/8` or a mic name."""
        cat, e = _catalog(ctx)
        if e:
            return e

        def go():
            with L.Unit() as u:
                md, names, blk, eb = fresh(u, preset_id, path, position)
                pid, pdef = _pid(md, model, param)
                L.check_target(blk, model, pid, pdef)
                v = stored_value(cat, model, param, _parse_value(value))
                if pdef["type"] in ("f", "i"):
                    v = float(v) if pdef["type"] == "f" else int(v)
                    if not pdef["min"] <= v <= pdef["max"]:
                        raise ValueError(f"{param} must stay in its range")
                    tags, args = "iiii" + pdef["type"] + "i", (v,)
                else:
                    v = bool(v)
                    tags, args = "iiii" + ("T" if v else "F") + "i", (v,)
                before = blk["params"][pid]["value"]
                u.call("/ParamValueSet", tags, path - 1, position, blk["slot"], pid, *args, -1)
                after = L.find(u.edit_buffer(), names, path, position)["params"][pid]["value"]
            if after != v and not (isinstance(v, float) and abs(after - v) < 1e-4):
                raise ValueError(f"the unit did not take the change ({param} still "
                                 f"{display_string(cat, model, param, after)[0]})")
            show = lambda x: display_string(cat, model, param, x)[0]
            snap = blk["params"][pid]["snap"]
            where = f" in snapshot {eb['cg__'].get('asnp', 0) + 1}" if snap else ""
            return E.ok({"param": param, "before": show(before), "after": show(after),
                         "snapshot": eb["cg__"].get("asnp", 0) + 1 if snap else None},
                        summary=f"{param}: {show(before)} -> {show(after)}{where} (not saved)")
        return guarded(go)

    @mcp.tool(name="live_toggle_block")
    def live_toggle_block(preset_id: int, path: int, position: int, model: str,
                          on: bool) -> dict:
        """Turn a block on or off on the unit right now (not saved until the user saves on
        the unit). Get the arguments from live_read."""
        def go():
            with L.Unit() as u:
                _md, names, blk, _eb = fresh(u, preset_id, path, position)
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
                u.call("/activateSnapshot", "i", snapshot - 1)
                now = u.edit_buffer()["cg__"].get("asnp")      # active snapshot, 0-based
            if now != snapshot - 1:
                raise ValueError("the unit did not switch snapshots")
            return E.ok({"snapshot": snapshot}, summary=f"snapshot {snapshot} is active")
        return guarded(go)

    @mcp.tool(name="live_add_block")
    def live_add_block(preset_id: int, path: int, position: int, model: str) -> dict:
        """Add a block to an EMPTY spot on the unit right now (not saved until the user
        saves). Effects only so far. `model` is a model id from search_models (e.g. HD2_DistKinkyBoostMono);
        `position` is 1-12 and must be free in live_read. It starts at the
        model's default settings."""
        def go():
            md, names = _defs()
            rec = md.get(model)
            if not rec:
                raise KeyError(f"unknown model {model!r}; use search_models")
            # ponytail: only an effect on the main lane was captured; amps, cabs, I/O and the
            # B lane (15-26, likely a split) need their own capture
            if rec.get("category") in ("amp", "preamp", "cab_ir_interp") or model.startswith("P35_"):
                raise ValueError("only effect blocks can be added live so far")
            if not 1 <= position <= 12:
                raise ValueError("live blocks can only be added at positions 1-12 so far")
            with L.Unit() as u:
                eb = active(u, preset_id)
                L.free_position(eb, path, position)
                u.call("/ModelSet", "iiii", path - 1, position, 0, rec["id"])
                got = L.find(u.edit_buffer(), names, path, position)["model"]
            if got != model:
                raise ValueError("the unit did not add the block")
            return E.ok({"path": path, "position": position, "model": model},
                        summary=f"added {model} at path {path} position {position} (not saved)")
        return guarded(go)

    @mcp.tool(name="live_load_preset")
    def live_load_preset(preset: int) -> dict:
        """Load a preset on the unit by its id from live_list_presets. Unsaved changes to
        the current preset are LOST: ask the user before loading."""
        def go():
            with L.Unit() as u:
                u.call("/LoadPresetWithCID", "i", preset)
                now = u.property("server.active.preset.id")
            if now != preset:
                raise ValueError("the unit did not load that preset")
            return E.ok({"preset_id": now}, summary=f"preset {now} loaded")
        return guarded(go)

    def user_presets(u):
        replies, _ = u.call("/GetContainerContents", "i", -2, reply="/GetContainerContents")
        return L.presets(next(x for x in replies[-1][1] if isinstance(x, bytes)))

    @mcp.tool(name="live_save_preset")
    def live_save_preset(preset_id: int) -> dict:
        """Save the unit's current changes over the loaded USER preset, same name and slot
        (like Save on the unit). This permanently replaces the stored preset: get the user's
        OK first. Factory presets are refused. `preset_id` is from live_read. Verified by
        reloading the preset and checking every block and value came back."""
        def go():
            with L.Unit() as u:
                eb = active(u, preset_id)
                before = user_presets(u)
                if preset_id not in {p["id"] for p in before}:
                    raise ValueError("only your own (user) presets can be saved live")
                want = L.flow_state(eb)
                # re-check right before saving: a preset switched on the unit since the
                # first check would otherwise be saved over this one
                # ponytail: still a one-round-trip window; the protocol has no atomic check
                if u.property("server.active.preset.id") != preset_id:
                    raise ValueError("a different preset was loaded on the unit; nothing saved")
                # the last two args are the block selected in the app; the input block
                # (path 1 position 0) is always there
                u.call("/SavePresetWithCID", "iii", preset_id, 0, 0)
                after = user_presets(u)
                # don't reload (which drops unsaved edits) if someone changed it meanwhile
                if L.flow_state(u.edit_buffer()) != want:
                    raise ValueError("the preset was changed on the unit during the save; "
                                     "saved but not checked, check it on the unit")
                u.call("/LoadPresetWithCID", "i", preset_id)
                snap = eb["cg__"].get("asnp", 0)        # loading may land on another snapshot
                u.call("/activateSnapshot", "i", snap)
                got = L.flow_state(u.edit_buffer())
            if after != before:
                raise ValueError("the unit's preset list changed unexpectedly during the save; "
                                 "check it on the unit")
            if got != want:
                raise ValueError("saved, but reloading the preset didn't bring every value back; "
                                 "check it on the unit")
            name = next(p["name"] for p in after if p["id"] == preset_id)
            return E.ok({"preset_id": preset_id, "name": name},
                        summary=f"saved '{name}' (reloaded and checked)")
        return guarded(go)
