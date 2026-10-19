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
    L.check_target(drive, "Kinky", 1, FLOAT)                         # a knob
    L.check_target(drive, "Kinky", 2, {"type": "b"})                 # an on/off switch
    L.check_target(L.find(eb, NAMES, 1, 2), "Delay", 1, FLOAT)       # per-snapshot: active one
    L.check_target(L.find(eb, NAMES, 1, 9), "Preamp", 1, FLOAT)      # addressed by position
    L.check_target(L.find(eb, NAMES, 2, 0), "Kinky", 1, FLOAT)       # path 2
    with pytest.raises(ValueError, match="preset changed"):
        L.check_target(drive, "Delay", 1, FLOAT)
    with pytest.raises(ValueError, match="type"):
        L.check_target(drive, "Kinky", 1, {"type": "i"})              # a knob isn't a list


def test_list_param_tag_matches_the_app():
    # Optical Trem note value -> option 7 (capture 3)
    assert L.osc_encode("/ParamValueSet", "iiiiiii", (106, 0, 4, 0, 9, 7, -1)).hex() == (
        "2f506172616d56616c756553657400002c69696969696969000000000000006a"
        "00000000000000040000000000000009" "00000007ffffffff")


def test_bool_tag_and_free_position():
    # the app's own Boost-off frame (capture 2)
    assert L.osc_encode("/ParamValueSet", "iiiiiFi", (106, 0, 1, 0, 2, False, -1)).hex() == (
        "2f506172616d56616c756553657400002c69696969694669000000000000006a"
        "00000000000000010000000000000002ffffffff")
    eb = _eb()
    L.free_position(eb, 1, 3)
    for pos in (1, 13, 0):
        with pytest.raises(ValueError):
            L.free_position(eb, 1, pos)


def test_agenda_matches_the_app():
    # the app's own /doAgenda blobs (capture 4): move, delete, Y split at position 2
    m, c = L.cmd("movb"), L.cmd("clrb")
    assert L.pack([{"cmnd": m, "fl_s": 0, "bl_s": 1, "fl_d": 1, "bl_d": 4}]).hex() == (
        "9185a4626c5f6404a4626c5f7301a4636d6e64ce6d6f7662a4666c5f6401a4666c5f7300")
    assert L.pack([{"cmnd": c, "flow": 1, "bloc": 4}]).hex() == (
        "9183a4626c6f6304a4636d6e64ce636c7262a4666c6f7701")
    s = L.cmd("setm")
    assert L.pack([{"cmnd": s, "flow": 0, "bloc": 27, "slot": 0, "modl": 783, "type": 9},
                   {"cmnd": s, "flow": 0, "bloc": 2, "slot": 0, "modl": 475, "type": 3},
                   {"cmnd": L.cmd("spld"), "flow": 0, "bloc": 2, "bblk": 16}]).hex() == (
        "9386a4626c6f631ba4636d6e64ce7365746da4666c6f7700a46d6f646ccd030fa4736c6f7400a4747970650986"
        "a4626c6f6302a4636d6e64ce7365746da4666c6f7700a46d6f646ccd01dba4736c6f7400a4747970650384a462"
        "626c6b10a4626c6f6302a4636d6e64ce73706c64a4666c6f7700")
    assert L.osc_encode("/doAgenda", "ib", (514, b"\x01\x02\x03\x04\x05")).hex().endswith(
        "0000000501020304" "05000000")


def test_merge_and_unsplit_match_the_app():
    # capture 5, path 2: merge at 8, remove that merge, remove the split at 4
    s, f = L.cmd("setm"), 1
    setm = lambda bloc, modl, typ: {"cmnd": s, "flow": f, "bloc": bloc, "slot": 0, "modl": modl, "type": typ}
    assert L.pack([setm(27, 789, 9), setm(8, 478, 4),
                   {"cmnd": L.cmd("jono"), "flow": f, "bloc": 8, "bblk": 22}]).hex() == (
        "9386a4626c6f631ba4636d6e64ce7365746da4666c6f7701a46d6f646ccd0315a4736c6f7400a4747970650986"
        "a4626c6f6308a4636d6e64ce7365746da4666c6f7701a46d6f646ccd01dea4736c6f7400a4747970650484a462"
        "626c6b16a4626c6f6308a4636d6e64ce6a6f6e6fa4666c6f7701")
    assert L.pack([setm(27, 783, 9), {"cmnd": L.cmd("clrb"), "flow": f, "bloc": 8}]).hex() == (
        "9286a4626c6f631ba4636d6e64ce7365746da4666c6f7701a46d6f646ccd030fa4736c6f7400a4747970650983"
        "a4626c6f6308a4636d6e64ce636c7262a4666c6f7701")
    assert L.pack([setm(14, 771, 8), {"cmnd": L.cmd("clrb"), "flow": f, "bloc": 4}]).hex() == (
        "9286a4626c6f630ea4636d6e64ce7365746da4666c6f7701a46d6f646ccd0303a4736c6f7400a4747970650883"
        "a4626c6f6304a4636d6e64ce636c7262a4666c6f7701")
