"""Write-gate tests on a synthetic valid preset."""
import os

import pytest

from helix_stadium_mcp.codec import read_hsp, write_hsp
from helix_stadium_mcp.writer import WriteBlocked, round_trip_check, safe_write


def _block(model, pos, btype, params, endpoint):
    return {
        "@enabled": {"value": True}, "favorite": 0,
        "harness": {"@enabled": {"value": True}},
        "path": 0, "position": pos, "endpoint": endpoint, "type": btype,
        "slot": [{"@enabled": {"value": True}, "model": model, "params": params, "version": 0}],
    }


def _valid_preset():
    snaps = [{"name": "S1", "color": "blue", "expsw": 1, "source": 0, "tempo": 120.0, "valid": True}]
    snaps += [{"name": f"S{i}", "expsw": -1, "source": 0, "tempo": 120.0, "valid": False}
              for i in range(2, 9)]
    return {
        "meta": {"color": "auto", "device_id": 1, "device_version": 1, "info": "", "name": "T"},
        "preset": {
            "flow": [{
                "@enabled": {"value": True},
                "b00": _block("P35_InputInst1", 0, "input", {"Trim": {"value": 0.0}}, "b13"),
                "b13": _block("P35_OutputMatrix", 13, "output", {"gain": {"value": 0.0}}, "b00"),
            }],
            "params": {"tempo": 120.0, "activesnapshot": 0, "activeexpsw": 1,
                       "inst1Z": "FirstEnabled", "inst2Z": "FirstEnabled"},
            "snapshots": snaps,
            "sources": {},
            "xyctrl": {"rbtime": 0.5, "rubberband": 1, "x": 0, "y": 0},
        },
    }


def test_round_trip_check_ok():
    rt = round_trip_check(_valid_preset())
    assert rt["ok"], rt["issues"]


def test_safe_write_new_file_no_backup(tmp_path):
    p = tmp_path / "t.hsp"
    obj = _valid_preset()
    res = safe_write(obj, str(p))
    assert res["ok"] and res["backup"] is None
    assert p.read_bytes() == write_hsp(obj)
    assert read_hsp(p.read_bytes()) == obj


def test_safe_write_backs_up_existing(tmp_path):
    p = tmp_path / "t.hsp"
    obj = _valid_preset()
    safe_write(obj, str(p))
    original_bytes = p.read_bytes()

    obj["meta"]["name"] = "T2"
    res = safe_write(obj, str(p))
    assert res["backup"] == str(p) + ".bak"
    assert os.path.exists(res["backup"])
    assert open(res["backup"], "rb").read() == original_bytes   # backup is the OLD file
    assert read_hsp(p.read_bytes())["meta"]["name"] == "T2"      # new file has the edit


def test_safe_write_blocks_invalid_and_writes_nothing(tmp_path):
    p = tmp_path / "t.hsp"
    with pytest.raises(WriteBlocked):
        safe_write({"meta": {}}, str(p))   # missing 'preset' -> validation error
    assert not p.exists()
