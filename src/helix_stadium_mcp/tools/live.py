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

_FIXED = {"input", "output", "split", "join", "harness", "none"}


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

    def _where(eb, names):
        return {(b["path"], b["position"]): b["model"] for b in L.blocks(eb, names) if b["slot"] == 0}

    def _movable(md, model):
        # I/O, splits and merges have their own tools
        if model.startswith(("P35_", "#")) or (md.get(model) or {}).get("category") in _FIXED:
            raise ValueError(f"{model} can't be added, moved or removed live")

    @mcp.tool(name="live_add_block")
    def live_add_block(preset_id: int, path: int, position: int, model: str) -> dict:
        """Add a block to an EMPTY spot on the unit right now (not saved until the user
        saves): effects, amps, preamps, cabs, IRs, FX loops, sends or returns. `model` is a model id from search_models
        (e.g. HD2_DistKinkyBoostMono). `position` is 1-12, or 15-26 on a path with a split
        (its second lane), and must be free in live_read. An amp brings its own cab: the
        unit adds it, and `added` lists every block that appeared."""
        def go():
            md, names = _defs()
            rec = md.get(model)
            if not rec:
                raise KeyError(f"unknown model {model!r}; use search_models")
            _movable(md, model)
            with L.Unit() as u:
                eb = active(u, preset_id)
                L.free_position(eb, path, position)
                u.call("/ModelSet", "iiii", path - 1, position, 0, rec["id"])
                now = _where(u.edit_buffer(), names)
            if now.get((path, position)) != model:
                raise ValueError("the unit did not add the block")
            before = _where(eb, names)
            added = [{"path": p, "position": q, "model": m}
                     for (p, q), m in sorted(now.items()) if before.get((p, q)) != m]
            return E.ok({"path": path, "position": position, "model": model, "added": added},
                        summary=f"added {model} at path {path} position {position}"
                                f"{f' (+{len(added) - 1} more)' if len(added) > 1 else ''} (not saved)")
        return guarded(go)

    @mcp.tool(name="live_move_block")
    def live_move_block(preset_id: int, path: int, position: int, model: str,
                        to_path: int, to_position: int) -> dict:
        """Move a block to an EMPTY spot, on the same path or the other one, right now (not
        saved until the user saves). Same position rules as live_add_block."""
        def go():
            md, names = _defs()
            with L.Unit() as u:
                eb = active(u, preset_id)
                L.check_target(L.find(eb, names, path, position), model)
                _movable(md, model)
                L.free_position(eb, to_path, to_position)
                u.call("/doAgenda", "b", L.pack([{"cmnd": L.cmd("movb"), "fl_s": path - 1,
                                                  "bl_s": position, "fl_d": to_path - 1,
                                                  "bl_d": to_position}]))
                now = _where(u.edit_buffer(), names)
            if now.get((to_path, to_position)) != model or (path, position) in now:
                raise ValueError("the unit did not move the block")
            return E.ok({"path": to_path, "position": to_position, "model": model},
                        summary=f"moved {model} to path {to_path} position {to_position} (not saved)")
        return guarded(go)

    @mcp.tool(name="live_remove_block")
    def live_remove_block(preset_id: int, path: int, position: int, model: str) -> dict:
        """Delete a block right now (not saved until the user saves). Get the arguments from
        live_read. Splits and I/O blocks are refused."""
        def go():
            md, names = _defs()
            with L.Unit() as u:
                eb = active(u, preset_id)
                L.check_target(L.find(eb, names, path, position), model)
                _movable(md, model)
                u.call("/doAgenda", "b", L.pack([{"cmnd": L.cmd("clrb"), "flow": path - 1,
                                                  "bloc": position}]))
                now = _where(u.edit_buffer(), names)
            if (path, position) in now:
                raise ValueError("the unit did not remove the block")
            return E.ok({"path": path, "position": position, "model": model},
                        summary=f"removed {model} from path {path} position {position} (not saved)")
        return guarded(go)

    @mcp.tool(name="live_add_split")
    def live_add_split(preset_id: int, path: int, position: int) -> dict:
        """Split a path into two lanes at an EMPTY spot (a Y split, like Add Split in the
        app), right now (not saved until the user saves). The second lane is positions 15-26:
        add blocks there with live_add_block."""
        def go():
            md, names = _defs()
            if not 1 <= position <= 12:
                raise ValueError("a split goes at position 1-12")
            with L.Unit() as u:
                eb = active(u, preset_id)
                if L.has_split(eb, path):
                    raise ValueError(f"path {path} already has a split")
                L.free_position(eb, path, position)
                f, ids = path - 1, {k: md[k]["id"] for k in ("P35_OutputMatrix", "P35_AppDSPSplitY")}
                # ponytail: bblk = position + 14 is from one capture (split at 2 -> 16);
                # the read-back below catches it if that's wrong
                u.call("/doAgenda", "b", L.pack([
                    {"cmnd": L.cmd("setm"), "flow": f, "bloc": 27, "slot": 0,
                     "modl": ids["P35_OutputMatrix"], "type": 9},
                    {"cmnd": L.cmd("setm"), "flow": f, "bloc": position, "slot": 0,
                     "modl": ids["P35_AppDSPSplitY"], "type": 3},
                    {"cmnd": L.cmd("spld"), "flow": f, "bloc": position, "bblk": position + 14}]))
                now = _where(u.edit_buffer(), names)
            if now.get((path, position)) != "P35_AppDSPSplitY" or now.get((path, 27)) != "P35_OutputMatrix":
                raise ValueError("the unit did not add the split")
            return E.ok({"path": path, "position": position},
                        summary=f"split path {path} at position {position}; second lane is 15-26 (not saved)")
        return guarded(go)

    def _setm(md, f, bloc, model, typ):
        return {"cmnd": L.cmd("setm"), "flow": f, "bloc": bloc, "slot": 0,
                "modl": md[model]["id"], "type": typ}

    def _split_at(eb, names, path):
        return next(((q, m) for (p, q), m in _where(eb, names).items()
                     if p == path and m.startswith("P35_AppDSPSplit")), (None, None))

    def _merge_at(eb, names, path):
        return next((q for (p, q), m in _where(eb, names).items()
                     if p == path and m == "P35_AppDSPJoin"), None)

    @mcp.tool(name="live_replace_block")
    def live_replace_block(preset_id: int, path: int, position: int, model: str,
                           new_model: str) -> dict:
        """Swap the block at a spot for a different model, in place, right now (not saved
        until the user saves). Same models as live_add_block. The new block starts at its
        default settings."""
        def go():
            md, names = _defs()
            rec = md.get(new_model)
            if not rec:
                raise KeyError(f"unknown model {new_model!r}; use search_models")
            _movable(md, new_model)
            with L.Unit() as u:
                eb = active(u, preset_id)
                L.check_target(L.find(eb, names, path, position), model)
                _movable(md, model)
                u.call("/ModelSet", "iiii", path - 1, position, 0, rec["id"])
                now = _where(u.edit_buffer(), names)
            if now.get((path, position)) != new_model:
                raise ValueError("the unit did not replace the block")
            return E.ok({"path": path, "position": position, "model": new_model},
                        summary=f"{model} -> {new_model} at path {path} position {position} (not saved)")
        return guarded(go)

    @mcp.tool(name="live_set_io")
    def live_set_io(preset_id: int, path: int, end: str, model: str) -> dict:
        """Change a path's input or output right now (not saved until the user saves).
        `end` is `input` or `output`; `model` is a P35_Input... / P35_Output... id from
        list_models (e.g. P35_InputInst1, P35_OutputQtrInch)."""
        def go():
            md, names = _defs()
            if end not in ("input", "output") or (md.get(model) or {}).get("category") != end:
                raise ValueError(f"{model} is not an {end} model")
            if model in ("P35_OutputMatrix", "P35_OutputNone"):
                raise ValueError(f"{model} is set by the split and merge tools")
            pos = 0 if end == "input" else 13
            with L.Unit() as u:
                active(u, preset_id)
                u.call("/ModelSet", "iiii", path - 1, pos, 0, md[model]["id"])
                now = _where(u.edit_buffer(), names)
            if now.get((path, pos)) != model:
                raise ValueError(f"the unit did not change the {end}")
            return E.ok({"path": path, end: model}, summary=f"path {path} {end}: {model} (not saved)")
        return guarded(go)

    @mcp.tool(name="live_set_split_type")
    def live_set_split_type(preset_id: int, path: int, kind: str) -> dict:
        """Change a path's split type right now (not saved until the user saves): `Y`,
        `AB`, `XOver` (crossover) or `Dyn` (dynamic)."""
        def go():
            md, names = _defs()
            model = f"P35_AppDSPSplit{kind}"
            if model not in md:
                raise ValueError("kind is Y, AB, XOver or Dyn")
            with L.Unit() as u:
                eb = active(u, preset_id)
                pos, _ = _split_at(eb, names, path)
                if pos is None:
                    raise ValueError(f"path {path} has no split")
                u.call("/ModelSet", "iiii", path - 1, pos, 0, md[model]["id"])
                now = _where(u.edit_buffer(), names)
            if now.get((path, pos)) != model:
                raise ValueError("the unit did not change the split")
            return E.ok({"path": path, "position": pos, "model": model},
                        summary=f"path {path} split is now {kind} (not saved)")
        return guarded(go)

    @mcp.tool(name="live_add_merge")
    def live_add_merge(preset_id: int, path: int, position: int) -> dict:
        """Join a split path's two lanes back together at an EMPTY spot after the split,
        right now (not saved until the user saves)."""
        def go():
            md, names = _defs()
            with L.Unit() as u:
                eb = active(u, preset_id)
                sp, _ = _split_at(eb, names, path)
                if sp is None or _merge_at(eb, names, path) is not None:
                    raise ValueError(f"path {path} needs a split and no merge yet")
                if not sp < position <= 12:
                    raise ValueError(f"the merge goes after the split, at {sp + 1}-12")
                L.free_position(eb, path, position)
                if any(p == path and position + 14 <= q <= 26 for p, q in _where(eb, names)):
                    raise ValueError("the second lane has blocks past that spot; move them first")
                f = path - 1
                # from capture 5: the lane's output goes to None, the join links bloc+14
                u.call("/doAgenda", "b", L.pack([
                    _setm(md, f, 27, "P35_OutputNone", 9), _setm(md, f, position, "P35_AppDSPJoin", 4),
                    {"cmnd": L.cmd("jono"), "flow": f, "bloc": position, "bblk": position + 14}]))
                now = _where(u.edit_buffer(), names)
            if now.get((path, position)) != "P35_AppDSPJoin":
                raise ValueError("the unit did not add the merge")
            return E.ok({"path": path, "position": position},
                        summary=f"merged path {path} at position {position} (not saved)")
        return guarded(go)

    @mcp.tool(name="live_remove_merge")
    def live_remove_merge(preset_id: int, path: int) -> dict:
        """Remove a path's merge right now (not saved until the user saves): the second lane
        gets its own output again."""
        def go():
            md, names = _defs()
            with L.Unit() as u:
                eb = active(u, preset_id)
                pos = _merge_at(eb, names, path)
                if pos is None:
                    raise ValueError(f"path {path} has no merge")
                u.call("/doAgenda", "b", L.pack([
                    _setm(md, path - 1, 27, "P35_OutputMatrix", 9),
                    {"cmnd": L.cmd("clrb"), "flow": path - 1, "bloc": pos}]))
                now = _where(u.edit_buffer(), names)
            if (path, pos) in now or now.get((path, 27)) != "P35_OutputMatrix":
                raise ValueError("the unit did not remove the merge")
            return E.ok({"path": path}, summary=f"removed path {path}'s merge (not saved)")
        return guarded(go)

    @mcp.tool(name="live_remove_split")
    def live_remove_split(preset_id: int, path: int) -> dict:
        """Remove a path's split right now (not saved until the user saves). Refused while
        the path has a merge or blocks in its second lane: remove those first."""
        def go():
            md, names = _defs()
            with L.Unit() as u:
                eb = active(u, preset_id)
                pos, _ = _split_at(eb, names, path)
                if pos is None:
                    raise ValueError(f"path {path} has no split")
                if _merge_at(eb, names, path) is not None:
                    raise ValueError("remove the merge first (live_remove_merge)")
                if any(p == path and 15 <= q <= 26 for p, q in _where(eb, names)):
                    raise ValueError("the second lane still has blocks; move or remove them first")
                u.call("/doAgenda", "b", L.pack([
                    _setm(md, path - 1, 14, "P35_InputNone", 8),
                    {"cmnd": L.cmd("clrb"), "flow": path - 1, "bloc": pos}]))
                eb = u.edit_buffer()
            if L.has_split(eb, path):
                raise ValueError("the unit did not remove the split")
            return E.ok({"path": path}, summary=f"removed path {path}'s split (not saved)")
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
