"""Footswitch / pedal / scribble strip / snapshot control / Command Center.

Two layers:
- synthetic presets (always run);
- replay: apply the new edit to capture N-1 and require capture N, ignoring only fields
  shown to change on their own. Captures are user exports (never committed): put them in
  ./captures as 00.hsp..15.hsp, else these skip.
"""
import copy
import os
from pathlib import Path

import pytest

from helix_stadium_mcp import controls as C
from helix_stadium_mcp.codec import read_hsp
from helix_stadium_mcp.preset import explain_text
from helix_stadium_mcp.writer import WriteBlocked, safe_write

CAPS = Path(__file__).resolve().parent.parent / "captures"
A1, A2, B2 = C.SWITCHES["A1"], C.SWITCHES["A2"], C.SWITCHES["B2"]

# a minimal MIDI-FS / PresetSnapshot def set (same shape as the install's commanddefs)
DEFS = {
    "MIDI-FS": {"params": {
        "Action": {"type": "i", "def": 0, "min": 0, "max": 3},
        "Command": {"type": "i", "def": 0, "min": 0, "max": 3},
        "MIDI Ch": {"type": "i", "def": 1, "min": 1, "max": 16},
        "CC#": {"type": "i", "def": 0, "min": 0, "max": 127}}},
    "PresetSnapshot": {"params": {
        "Action": {"type": "i", "def": 0, "min": 0, "max": 3},
        "Command": {"type": "i", "def": 0, "min": 0, "max": 7}}},
}


def _blk(model, params, ctrl_src=None):
    en = {"value": True, "snapshots": [True] + [None] * 7}
    if ctrl_src:
        en["controller"] = C._controller(ctrl_src, "targetbypass", "latching", False, True, False)
    return {"@enabled": en, "position": 1, "type": "fx",
            "slot": [{"model": model, "params": {k: {"value": v} for k, v in params.items()}}]}


def _preset():
    sources = {str(s): {"fs_color": "auto", "fs_label": "", "fs_topidx": 0}
               for n, s in C.SWITCHES.items() if n != "TOE"}
    snaps = [{"name": "S1", "valid": True}] + [{"name": f"S{i}", "valid": False} for i in range(2, 9)]
    b2 = _blk("Delay", {"Mix": 0.3, "Feedback": 0.4}, ctrl_src=A2)
    b2["position"] = 2
    return {"meta": {"name": "T", "device_id": 0x260000},
            "preset": {"params": {"activesnapshot": 0}, "snapshots": snaps, "sources": sources,
                       "flow": [{"b01": _blk("Drive", {"Gain": 0.5}, ctrl_src=A1), "b02": b2}]}}


# --- switch names -------------------------------------------------------------------------

def test_switch_names():
    assert C.switch_id("Stomp A1") == C.switch_id("a1") == 16843008     # PROVEN id
    assert C.switch_id("B2") == 16843265 and C.switch_id("toe") == 16844032
    assert C.pedal_id("EXP 2") == 16908545
    assert C.control_name(16843265) == "Stomp B2" and C.control_name(16908544) == "EXP1"
    with pytest.raises(KeyError):
        C.switch_id("C1")


# --- footswitch: momentary/latching, several blocks per switch, param on a switch --------

def test_footswitch_behavior_and_sharing():
    obj = _preset()
    C.assign_switch(obj, 1, "b02", "A1", behavior="momentary")
    en = obj["preset"]["flow"][0]["b02"]["@enabled"]
    assert en["controller"]["source"] == A1 and en["controller"]["behavior"] == "momentary"
    assert C.assignments_for(obj, A1) == [("b01", "bypass"), ("b02", "bypass")]
    assert obj["preset"]["sources"][str(A1)]["fs_topidx"] == 1
    assert obj["preset"]["sources"][str(A1)]["bypass"] is False
    with pytest.raises(ValueError):
        C.assign_switch(obj, 1, "b02", "A1", behavior="toggle")


def test_param_on_footswitch():
    obj = _preset()
    C.assign_switch(obj, 1, "b02", "A3", target="Mix", lo=0.1, hi=0.8)
    c = obj["preset"]["flow"][0]["b02"]["slot"][0]["params"]["Mix"]["controller"]
    assert (c["type"], c["min"], c["max"], c["source"]) == ("param", 0.1, 0.8, C.switch_id("A3"))
    with pytest.raises(ValueError):
        C.assign_switch(obj, 1, "b02", "A3", target="Mix")              # min/max required
    assert C.unassign(obj, 1, "b02", "Mix") and not C.unassign(obj, 1, "b02", "Mix")


# --- expression pedals ---------------------------------------------------------------------

def test_expression_pedal():
    obj = _preset()
    C.assign_pedal(obj, 1, "b02", "Feedback", "EXP1", 0.1, 0.6)
    pv = obj["preset"]["flow"][0]["b02"]["slot"][0]["params"]["Feedback"]
    c = pv["controller"]
    assert (c["source"], c["behavior"], c["min"], c["max"]) == (C.EXP1, "continuous", 0.1, 0.6)
    assert pv["value"] == 0.1                                  # parked at heel, like the unit
    assert obj["preset"]["sources"][str(C.EXP1)] == {"bypass": False}
    with pytest.raises(KeyError):
        C.assign_pedal(obj, 1, "b02", "Nope", "EXP1", 0, 1)


def test_reader_names_controls_and_does_not_call_pedals_disabled():
    obj = _preset()
    C.assign_pedal(obj, 1, "b02", "Feedback", "EXP2", 0.0, 1.0)
    C.set_switch_look(obj, "A1", label="Crunch", color="red")

    class Cat:
        controls = {}
        def friendly_name(self, m): return m
        def param_def(self, m, p): return None
    text = explain_text(Cat(), obj)
    assert "Stomp A1 'Crunch' (red) -> bypass" in text
    assert "EXP2 -> Feedback" in text and "(disabled)" not in text


# --- scribble strip ------------------------------------------------------------------------

def test_switch_label_and_color():
    obj = _preset()
    C.set_switch_look(obj, "B2", label="Test", color="Red")
    assert obj["preset"]["sources"][str(B2)]["fs_label"] == "Test"
    assert obj["preset"]["sources"][str(B2)]["fs_color"] == "red"
    with pytest.raises(ValueError):
        C.set_switch_look(obj, "B2", color="plaid")
    with pytest.raises(KeyError):
        C.set_switch_look(obj, "TOE", label="x")                       # no strip on the toe


# --- snapshot control ----------------------------------------------------------------------

def test_snapshots_set_bypass():
    obj = _preset()
    en = obj["preset"]["flow"][0]["b01"]["@enabled"]
    C.set_snapshot_control(obj, 1, "b01", "bypass", False)
    assert "snapshots" not in en
    C.set_snapshot_control(obj, 1, "b01", "bypass", True)
    assert en["snapshots"] == [True] + [None] * 7


def test_param_snapshot_control():
    obj = _preset()
    pv = obj["preset"]["flow"][0]["b02"]["slot"][0]["params"]["Mix"]
    C.set_snapshot_control(obj, 1, "b02", "Mix", True)
    assert pv["snapshots"] == [0.3] + [None] * 7
    C.set_snapshot_control(obj, 1, "b02", "Mix", False)
    assert "snapshots" not in pv


# --- Command Center ------------------------------------------------------------------------

def test_commands_add_validate_clear():
    obj = _preset()
    cmd = C.add_command(obj, DEFS, "A1", "MIDI", {"MIDI Ch": 2, "CC#": 13, "Command": 1})
    assert cmd["type"] == "MIDI" and cmd["ordinal"] == 0
    assert cmd["params"]["MIDI Ch"] == {"value": 2} and cmd["params"]["Action"] == {"value": 0}
    assert C.add_command(obj, DEFS, "A1", "PresetSnapshot", {"Command": 2})["ordinal"] == 1
    with pytest.raises(ValueError):
        C.add_command(obj, DEFS, "A1", "MIDI", {"CC#": 200})            # out of range
    with pytest.raises(KeyError):
        C.add_command(obj, DEFS, "A1", "MIDI", {"Bogus": 1})
    with pytest.raises(ValueError):
        C.add_command(obj, DEFS, "A1", "Teleport")
    assert C.clear_commands(obj, "A1") == 2 and "commands" not in obj["preset"]


# --- safety gate: originals are never overwritten -----------------------------------------

def test_safe_write_refuses_read_only_original(tmp_path):
    from helix_stadium_mcp.codec import write_hsp
    p = tmp_path / "orig.hsp"
    p.write_bytes(write_hsp(_preset()))
    os.chmod(p, 0o444)
    before = p.read_bytes()
    try:
        with pytest.raises(WriteBlocked) as ex:
            safe_write(_preset(), str(p))
        assert ex.value.report["phase"] == "protect"
        assert p.read_bytes() == before and not (tmp_path / "orig.hsp.bak").exists()
    finally:
        os.chmod(p, 0o644)


# --- replay against the unit's own exports -------------------------------------------------

def _cap(n):
    f = CAPS / f"{n:02d}.hsp"
    if not f.exists():
        pytest.skip(f"capture {f.name} not present")
    return read_hsp(f.read_bytes())


def _strip_noise(obj):
    """Drop fields the unit changes on its own (cursor, runtime switch state, EXP state)."""
    o = copy.deepcopy(obj)
    p = o["preset"]
    p.pop("cursor", None)
    p["params"].pop("activeexpsw", None)
    for s in p["sources"].values():
        s.pop("bypass", None)
    for s in p["snapshots"]:
        s.pop("expsw", None)
    return o


REPLAYS = {
    4: lambda o: C.assign_switch(o, 1, "b02", "A2", behavior="momentary"),
    5: lambda o: C.assign_switch(o, 1, "b02", "A1", behavior="latching"),
    6: lambda o: C.assign_switch(o, 1, "b03", "B2"),
    7: lambda o: C.set_switch_look(o, "B2", label="Test"),
    8: lambda o: C.set_switch_look(o, "B2", color="red"),
    10: lambda o: C.assign_pedal(o, 1, "b03", "Mix", "EXP2", 0.0, 1.0),
    11: lambda o: C.assign_switch(o, 1, "b03", "TOE"),
    13: lambda o: C.set_snapshot_control(o, 1, "b01", "bypass", False),
}


@pytest.mark.parametrize("n", sorted(REPLAYS))
def test_replay_matches_unit(n):
    before, after = _cap(n - 1), _cap(n)
    if n == 10:   # the unit parks the *previous* pedal (EXP1 Feedback) at toe on this export
        before["preset"]["flow"][0]["b02"]["slot"][0]["params"]["Feedback"]["value"] = \
            after["preset"]["flow"][0]["b02"]["slot"][0]["params"]["Feedback"]["value"]
    REPLAYS[n](before)
    assert _strip_noise(before) == _strip_noise(after)


@pytest.mark.install
def test_replay_commands_match_unit():
    from helix_stadium_mcp.config import resolve_res_dir
    before, after14, after15 = _cap(13), _cap(14), _cap(15)
    defs = C.load_command_defs(str(resolve_res_dir(None)), before["meta"]["device_id"])
    C.set_switch_look(before, "B2", label="", color="auto")       # 14 also reset the strip
    C.add_command(before, defs, "A1", "MIDI", {"MIDI Ch": 2, "Command": 1, "CC#": 13,
                                               "Value": 13, "Velocity": 100})
    assert _strip_noise(before) == _strip_noise(after14)
    C.clear_commands(before, "A1")
    C.add_command(before, defs, "A1", "PresetSnapshot", {"Command": 2})
    assert _strip_noise(before) == _strip_noise(after15)
