"""Snapshot-diff + validation tests on synthetic fixtures."""
from helix_stadium_mcp.preset import resolve_snapshot_index, snapshot_diff
from helix_stadium_mcp.validation import validate


class FakeCatalog:
    controls: dict = {}

    def friendly_name(self, model_id):
        return {"AmpX": "Amp X"}.get(model_id, model_id)

    def param_def(self, model_id, param_id):
        return None  # -> display_string falls back to a plain number

    def resolve(self, model_id):
        return {"name": "Amp X"} if model_id == "AmpX" else None


def _preset():
    snaps = [{"name": "Rhythm", "valid": True}, {"name": "Lead", "valid": True}]
    snaps += [{"name": f"S{i}", "valid": False} for i in range(3, 9)]
    return {
        "meta": {"name": "T"},
        "preset": {
            "snapshots": snaps,
            "flow": [{
                "b00": {
                    "type": "amp", "position": 0, "@enabled": {"value": True},
                    "slot": [{"model": "AmpX", "params": {
                        "Drive": {"value": 0.5, "snapshots": [0.5, 0.8, None, None, None, None, None, None]},
                        "Bass": {"value": 0.4, "snapshots": [0.4, 0.4, None, None, None, None, None, None]},
                    }}],
                },
            }],
        },
    }


def test_resolve_snapshot_index():
    obj = _preset()
    assert resolve_snapshot_index(obj, "Rhythm") == 0
    assert resolve_snapshot_index(obj, "lead") == 1     # case-insensitive
    assert resolve_snapshot_index(obj, "2") == 1        # 1-based number
    assert resolve_snapshot_index(obj, "nope") is None


def test_snapshot_diff_reports_only_changes():
    d = snapshot_diff(FakeCatalog(), _preset(), 0, 1)
    changed = {c["param"] for c in d["changes"]}
    assert "Drive" in changed        # 0.5 -> 0.8
    assert "Bass" not in changed     # 0.4 -> 0.4 (unchanged)
    assert d["a"]["name"] == "Rhythm" and d["b"]["name"] == "Lead"


def test_validate_ok():
    assert validate(_preset())["errors"] == []


def test_validate_structural_errors():
    assert any("preset" in e for e in validate({"meta": {}})["errors"])
    assert any("flow" in e for e in validate({"meta": {}, "preset": {"flow": "x"}})["errors"])


def test_validate_unknown_model_warns():
    obj = _preset()
    obj["preset"]["flow"][0]["b00"]["slot"][0]["model"] = "GhostModel"
    res = validate(obj, FakeCatalog())
    assert any("GhostModel" in w for w in res["warnings"])


def test_validate_source_reference():
    obj = _preset()
    obj["preset"]["sources"] = {"16843015": {"bypass": True}}
    en = obj["preset"]["flow"][0]["b00"]["@enabled"]
    en["controller"] = {"source": 99999}
    assert any("99999" in w for w in validate(obj)["warnings"])
    en["controller"]["source"] = 16843015          # now it resolves
    assert not any("not in preset.sources" in w for w in validate(obj)["warnings"])


def _preset_with_controllers():
    """A bypass footswitch on b01 and a momentary param controller (a 'bloom') on b02.Mix."""
    snaps = [{"name": "A", "valid": True}] + [{"name": f"S{i}", "valid": False} for i in range(2, 9)]
    return {
        "meta": {"name": "C"},
        "preset": {
            "snapshots": snaps,
            "sources": {"16843018": {"fs_label": "BLOOM", "fs_color": "auto"}},
            "flow": [{
                "b01": {
                    "type": "fx", "position": 1,
                    "@enabled": {"value": True, "controller": {
                        "source": 16843015, "behavior": "momentary", "type": "targetbypass"}},
                    "slot": [{"model": "AmpX", "params": {"Gain": {"value": 0.5}}}],
                },
                "b02": {
                    "type": "fx", "position": 2, "@enabled": {"value": True},
                    "slot": [{"model": "AmpX", "params": {"Mix": {"value": 0.03, "controller": {
                        "source": 16843018, "behavior": "momentary", "type": "param",
                        "min": 0.03, "max": 0.4}}}}],
                },
            }],
        },
    }


def test_summary_exposes_block_keys_and_controllers():
    from helix_stadium_mcp.preset import explain_text, summarize
    obj = _preset_with_controllers()
    blocks = summarize(FakeCatalog(), obj)["paths"][0]
    assert [b["key"] for b in blocks] == ["b01", "b02"]                 # keys exposed, in order
    assert blocks[0]["controllers"] == [                                # bypass footswitch on b01
        {"target": "bypass", "source": 16843015, "behavior": "momentary"}]
    c = blocks[1]["controllers"][0]                                     # the 'bloom' on b02.Mix
    assert c["target"] == "Mix" and c["source"] == 16843018 and c["behavior"] == "momentary"
    assert "min" in c and "max" in c and c["label"] == "BLOOM"          # range + sources label
    txt = explain_text(FakeCatalog(), obj)
    assert "b01 " in txt and "b02 " in txt and "ctrl:" in txt and "16843018" in txt


_SYNC_NOTES = ["1/1", "1/2 Dotted", "1/2", "1/2 Triplet", "1/4 Dotted", "1/4",
               "1/4 Triplet", "1/8 Dotted", "1/8"]


class SyncCatalog:
    controls = {"sync_note": {"format": _SYNC_NOTES}}

    def param_def(self, model_id, param_id):
        if param_id == "Time":
            return {"id": "Time", "display_tag": "time_ms",
                    "sync": "TempoSync1", "note": "SyncSelect1"}
        return None

    def friendly_name(self, m):
        return m


def test_render_param_tempo_sync():
    from helix_stadium_mcp.preset import render_param
    params = {"TempoSync1": {"value": True}, "SyncSelect1": {"value": 7},
              "Time": {"value": 0.082}}
    cat = SyncCatalog()
    # synced Time -> note division; the SyncSelect param -> note name
    assert render_param(cat, "Delay", "Time", params["Time"], params) == "1/8 Dotted"
    assert render_param(cat, "Delay", "SyncSelect1", params["SyncSelect1"], params) == "1/8 Dotted"


# --- edit helpers -----------------------------------------------
def test_edit_param_current_syncs_active_snapshot():
    from helix_stadium_mcp.preset import edit_param, find_block
    obj = _preset()
    edit_param(obj, 1, "b00", "Drive", 0.7)          # active snapshot is 0
    _blk, slot0 = find_block(obj, 1, "b00")
    pv = slot0["params"]["Drive"]
    assert pv["value"] == 0.7 and isinstance(pv["value"], float)
    assert pv["snapshots"][0] == 0.7                 # active-snapshot slot synced


def test_edit_param_specific_snapshot_leaves_current():
    from helix_stadium_mcp.preset import edit_param, find_block
    obj = _preset()
    edit_param(obj, 1, "b00", "Drive", 0.9, snapshot=1)   # snapshot 1 (not active)
    pv = find_block(obj, 1, "b00")[1]["params"]["Drive"]
    assert pv["snapshots"][1] == 0.9
    assert pv["value"] == 0.5                         # current value unchanged


def test_edit_param_block_key_forms_and_unknown():
    import pytest
    from helix_stadium_mcp.preset import edit_param
    edit_param(_preset(), 1, "0", "Drive", 0.6)       # 'b00' == '0'
    with pytest.raises(KeyError):
        edit_param(_preset(), 1, "b00", "Nonexistent", 1.0)


def test_toggle_block():
    from helix_stadium_mcp.preset import find_block, toggle_block
    obj = _preset()
    toggle_block(obj, 1, "b00", False)
    assert find_block(obj, 1, "b00")[0]["@enabled"]["value"] is False


def _chain_preset():
    def blk(model, pos, btype, endpoint=None):
        b = {"@enabled": {"value": True}, "favorite": 0,
             "harness": {"@enabled": {"value": True}}, "path": 0, "position": pos, "type": btype,
             "slot": [{"@enabled": {"value": True}, "model": model, "params": {}, "version": 0}]}
        if endpoint:
            b["endpoint"] = endpoint
        return b
    snaps = [{"name": "S1", "color": "blue", "expsw": 1, "source": 0, "tempo": 120.0, "valid": True}]
    snaps += [{"name": f"S{i}", "expsw": -1, "source": 0, "tempo": 120.0, "valid": False}
              for i in range(2, 9)]
    return {
        "meta": {"color": "auto", "device_id": 1, "device_version": 1, "info": "", "name": "C"},
        "preset": {
            "flow": [{
                "@enabled": {"value": True},
                "b00": blk("P35_InputInst1", 0, "input", "b13"),
                "b01": blk("Drive", 1, "fx"),
                "b02": blk("Amp", 2, "amp"),
                "b03": blk("Delay", 3, "fx"),
                "b13": blk("P35_OutputMatrix", 13, "output", "b00"),
            }],
            "params": {"tempo": 120.0, "activesnapshot": 0, "activeexpsw": 1,
                       "inst1Z": "FirstEnabled", "inst2Z": "FirstEnabled"},
            "snapshots": snaps, "sources": {},
            "xyctrl": {"rbtime": 0.5, "rubberband": 1, "x": 0, "y": 0},
        },
    }


def _order(obj):
    from helix_stadium_mcp.preset import _processing_blocks
    return [v["slot"][0]["model"] for _, v in _processing_blocks(obj["preset"]["flow"][0])]


def test_remove_block():
    from helix_stadium_mcp.preset import remove_block
    obj = _chain_preset()
    remove_block(obj, 1, "b02")
    assert _order(obj) == ["Drive", "Delay"]


def test_remove_block_refuses_io():
    import pytest
    from helix_stadium_mcp.preset import remove_block
    with pytest.raises(ValueError):
        remove_block(_chain_preset(), 1, "b13")


def test_move_block_before_repacks_and_validates():
    from helix_stadium_mcp.preset import _processing_blocks, move_block
    from helix_stadium_mcp.validation import validate
    obj = _chain_preset()
    move_block(obj, 1, "b03", before="b02")           # Delay before Amp
    assert _order(obj) == ["Drive", "Delay", "Amp"]
    assert [v["position"] for _, v in _processing_blocks(obj["preset"]["flow"][0])] == [1, 2, 3]
    assert validate(obj)["errors"] == []


def test_move_block_after():
    from helix_stadium_mcp.preset import move_block
    obj = _chain_preset()
    move_block(obj, 1, "b01", after="b03")            # Drive after Delay
    assert _order(obj) == ["Amp", "Delay", "Drive"]


def test_move_block_needs_exactly_one_ref():
    import pytest
    from helix_stadium_mcp.preset import move_block
    with pytest.raises(ValueError):
        move_block(_chain_preset(), 1, "b01", before="b02", after="b03")


_TEMPLATE = {
    "@enabled": {"value": True}, "favorite": 0,
    "harness": {"@enabled": {"value": True},
                "params": {"EvtIdx": {"value": -1}, "bypass": {"value": False}, "upper": {"value": True}}},
    "path": 0, "type": "fx",
    "slot": [{"@enabled": {"value": True}, "model": "NewFx", "params": {"Mix": {"value": 0.5}}, "version": 0}],
}


def test_add_block_at_end_validates():
    from helix_stadium_mcp.preset import add_block
    from helix_stadium_mcp.validation import validate
    obj = _chain_preset()
    add_block(obj, 1, _TEMPLATE)
    assert _order(obj) == ["Drive", "Amp", "Delay", "NewFx"]
    assert validate(obj)["errors"] == []


def test_add_block_before():
    from helix_stadium_mcp.preset import add_block
    obj = _chain_preset()
    add_block(obj, 1, _TEMPLATE, before="b02")          # before Amp
    assert _order(obj) == ["Drive", "NewFx", "Amp", "Delay"]


def test_add_block_deepcopies_template():
    from helix_stadium_mcp.preset import add_block, find_block
    obj = _chain_preset()
    k = add_block(obj, 1, _TEMPLATE)
    find_block(obj, 1, k)[1]["params"]["Mix"]["value"] = 0.9   # mutate the inserted block
    assert _TEMPLATE["slot"][0]["params"]["Mix"]["value"] == 0.5   # template untouched


# --- snapshot generation ----------------------------------------
def _gen_preset():
    """8 snapshot slots (only slot 0 valid), one block whose param has NO automation yet."""
    snaps = [{"name": f"SNAPSHOT {i + 1}", "color": "auto", "expsw": 1, "source": 0,
              "tempo": 120.0, "valid": i == 0} for i in range(8)]
    return {
        "meta": {"name": "G"},
        "preset": {
            "params": {"activesnapshot": 0},
            "snapshots": snaps,
            "flow": [{
                "b01": {"type": "fx", "position": 1, "@enabled": {"value": True},
                        "slot": [{"model": "FxX", "version": 0,
                                  "params": {"Gain": {"value": 0.5}}}]},
            }],
        },
    }


def test_configure_snapshots_sets_validity_names_colors():
    from helix_stadium_mcp.preset import configure_snapshots
    obj = _gen_preset()
    res = configure_snapshots(obj, ["Rhythm", "Lead", "Clean"], ["blue", "pink", "green"])
    assert res == {"valid": 3, "names": ["Rhythm", "Lead", "Clean"]}
    snaps = obj["preset"]["snapshots"]
    assert [s["valid"] for s in snaps] == [True, True, True] + [False] * 5
    assert snaps[1]["name"] == "Lead" and snaps[1]["color"] == "pink"


def test_configure_snapshots_count_bounds():
    import pytest
    from helix_stadium_mcp.preset import configure_snapshots
    with pytest.raises(ValueError):
        configure_snapshots(_gen_preset(), [])                 # too few
    with pytest.raises(ValueError):
        configure_snapshots(_gen_preset(), [f"S{i}" for i in range(9)])  # too many


def test_edit_param_auto_creates_automation():
    from helix_stadium_mcp.preset import configure_snapshots, edit_param, find_block
    obj = _gen_preset()
    configure_snapshots(obj, ["Rhythm", "Lead"])
    edit_param(obj, 1, "b01", "Gain", 0.9, snapshot=1)         # Lead; no array yet
    pv = find_block(obj, 1, "b01")[1]["params"]["Gain"]
    assert pv["snapshots"] == [0.5, 0.9, None, None, None, None, None, None]
    assert pv["value"] == 0.5                                  # active (Rhythm) unchanged


def test_toggle_block_per_snapshot_auto_creates():
    from helix_stadium_mcp.preset import configure_snapshots, find_block, toggle_block
    obj = _gen_preset()
    configure_snapshots(obj, ["Rhythm", "Lead"])
    toggle_block(obj, 1, "b01", False, snapshot=0)             # off in Rhythm
    en = find_block(obj, 1, "b01")[0]["@enabled"]
    assert en["snapshots"] == [False, True, None, None, None, None, None, None]
    assert en["value"] is False                               # active == 0 synced


def test_set_active_snapshot_loads_values():
    from helix_stadium_mcp.preset import (configure_snapshots, edit_param, find_block,
                                          set_active_snapshot)
    obj = _gen_preset()
    configure_snapshots(obj, ["Rhythm", "Lead"])
    edit_param(obj, 1, "b01", "Gain", 0.9, snapshot=1)         # Lead=0.9, Rhythm stays 0.5
    set_active_snapshot(obj, 1)                                # switch to Lead
    pv = find_block(obj, 1, "b01")[1]["params"]["Gain"]
    assert obj["preset"]["params"]["activesnapshot"] == 1
    assert pv["value"] == 0.9                                  # value now Lead's


def test_set_active_snapshot_rejects_unconfigured():
    import pytest
    from helix_stadium_mcp.preset import set_active_snapshot
    with pytest.raises(ValueError):
        set_active_snapshot(_gen_preset(), 5)                  # slot 5 not valid


def test_configure_snapshots_reshapes_existing_automation():
    from helix_stadium_mcp.preset import configure_snapshots, edit_param, find_block
    obj = _gen_preset()
    configure_snapshots(obj, ["Rhythm", "Lead", "Clean"])
    edit_param(obj, 1, "b01", "Gain", 0.9, snapshot=2)         # Clean=0.9
    configure_snapshots(obj, ["Rhythm", "Lead"])               # shrink to 2 scenes
    pv = find_block(obj, 1, "b01")[1]["params"]["Gain"]
    assert pv["snapshots"][2] is None                          # unused slot nulled
    assert pv["snapshots"][:2] == [0.5, 0.5]


def test_configure_snapshots_resets_active_if_invalidated():
    from helix_stadium_mcp.preset import configure_snapshots, set_active_snapshot
    obj = _gen_preset()
    configure_snapshots(obj, ["Rhythm", "Lead", "Clean"])
    set_active_snapshot(obj, 2)                                # active = Clean
    configure_snapshots(obj, ["Rhythm", "Lead"])              # Clean now invalid
    assert obj["preset"]["params"]["activesnapshot"] == 0     # reset to a valid scene
