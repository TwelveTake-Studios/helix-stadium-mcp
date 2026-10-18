"""Live protocol: encode exactly what the app sent (bytes from the 2026-10-18 capture),
and refuse every target the capture didn't prove."""
import pytest

from helix_stadium_mcp import live as L

# the app's own request frames, copied from the capture
BLOCK_OFF = bytes.fromhex("2f426c6f636b456e61626c65536574002c696969690000000000006c"
                          "000000000000000100000000")
DRIVE_047 = bytes.fromhex("2f506172616d56616c756553657400002c69696969696669000000000000006e"
                          "000000000000000100000000000000013ef0a3d7ffffffff")


def test_encode_matches_the_app():
    assert L.osc_encode("/BlockEnableSet", "iiii", (108, 0, 1, 0)) == BLOCK_OFF
    assert L.osc_encode("/ParamValueSet", "iiiiifi", (110, 0, 1, 0, 1, 0.47, -1)) == DRIVE_047
    assert L._GREETING[:12].hex() == "ff00000000000000017f0300" and len(L._GREETING) == 64


def test_decode_round_trip_and_fourcc():
    a, args = L.osc_decode(L.osc_encode("/x", "isf", (7, "hi", 0.5)))
    assert (a, args) == ("/x", [7, "hi", 0.5])
    assert L._fourcc({0x7366675F: {0x69645F5F: 3}}) == {"sfg_": {"id__": 3}}


def _eb():
    blk = lambda pos, bid, mid, parm: {
        "id__": bid, "type": 1, "enbl": 1,
        "mdls": [{"id__": mid, "parm": [{"pid_": p, "valu": v, "snap": s} for p, v, s in parm]}]}
    return {"sfg_": {"flow": [{"blks": [1, blk(1, 1, 339, [(1, 0.64, False), (2, True, False)]),
                                        2, blk(2, 2, 125, [(1, 0.08, True)]),
                                        9, blk(9, 10, 719, [(1, 0.5, False)])]},
                              {"blks": [0, blk(0, 28, 339, [(1, 0.5, False)])]}]}}


NAMES = {339: "Kinky", 125: "Delay", 719: "Preamp"}
FLOAT = {"type": "f"}


def test_guards():
    eb = _eb()
    drive = L.find(eb, NAMES, 1, 1)
    L.check_target(drive, "Kinky", 1, FLOAT)                         # the proven case
    with pytest.raises(ValueError, match="preset changed"):
        L.check_target(drive, "Delay", 1, FLOAT)
    with pytest.raises(ValueError, match="knob"):
        L.check_target(drive, "Kinky", 2, {"type": "b"})             # a switch param
    with pytest.raises(ValueError, match="snapshot"):
        L.check_target(L.find(eb, NAMES, 1, 2), "Delay", 1, FLOAT)
    with pytest.raises(ValueError, match="position and id"):
        L.check_target(L.find(eb, NAMES, 1, 9), "Preamp", 1, FLOAT)
    with pytest.raises(ValueError, match="path 2"):
        L.check_target(L.find(eb, NAMES, 2, 0), "Kinky", 1, FLOAT)
