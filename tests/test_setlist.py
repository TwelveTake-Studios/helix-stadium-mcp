"""Setlist assembly tests on synthetic presets."""
from pathlib import Path

from helix_stadium_mcp.codec import write_hsp
from helix_stadium_mcp.setlist import build_setlist


def _blk(model, pos, endpoint, btype):
    return {"@enabled": {"value": True}, "favorite": 0,
            "harness": {"@enabled": {"value": True}}, "path": 0, "position": pos,
            "endpoint": endpoint, "type": btype,
            "slot": [{"@enabled": {"value": True}, "model": model, "params": {}, "version": 0}]}


def _preset(name):
    snaps = [{"name": "S1", "color": "blue", "expsw": 1, "source": 0, "tempo": 120.0, "valid": True}]
    snaps += [{"name": f"S{i}", "expsw": -1, "source": 0, "tempo": 120.0, "valid": False}
              for i in range(2, 9)]
    return {
        "meta": {"color": "auto", "device_id": 1, "device_version": 1, "info": "", "name": name},
        "preset": {
            "flow": [{"@enabled": {"value": True},
                      "b00": _blk("P35_InputInst1", 0, "b13", "input"),
                      "b13": _blk("P35_OutputMatrix", 13, "b00", "output")}],
            "params": {"tempo": 120.0, "activesnapshot": 0, "activeexpsw": 1,
                       "inst1Z": "FirstEnabled", "inst2Z": "FirstEnabled"},
            "snapshots": snaps, "sources": {},
            "xyctrl": {"rbtime": 0.5, "rubberband": 1, "x": 0, "y": 0},
        },
    }


def test_build_setlist(tmp_path):
    p1 = tmp_path / "a.hsp"
    p1.write_bytes(write_hsp(_preset("Red House")))
    p2 = tmp_path / "b.hsp"
    p2.write_bytes(write_hsp(_preset("My Song")))
    res = build_setlist("Clinic", [str(p1), str(p2)], str(tmp_path))
    assert res["ok"]
    folder = Path(res["folder"])
    assert (folder / "01 - Red House.hsp").exists()
    assert (folder / "02 - My Song.hsp").exists()
    assert (folder / "setlist.json").exists()
    assert (folder / "SETLIST.md").exists()
    assert [s["song"] for s in res["songs"]] == ["Red House", "My Song"]


def test_build_setlist_aborts_on_invalid(tmp_path):
    good = tmp_path / "g.hsp"
    good.write_bytes(write_hsp(_preset("Good")))
    bad = tmp_path / "bad.hsp"
    bad.write_bytes(write_hsp({"meta": {}, "preset": {"flow": "x"}}))
    res = build_setlist("X", [str(good), str(bad)], str(tmp_path))
    assert not res["ok"] and res["errors"]
    assert not (tmp_path / "X").exists()   # nothing written when a member is invalid
