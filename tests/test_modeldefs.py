"""Model-defs decoder + block synthesis.

The decoder tests are self-contained (hand-built MessagePack bytes, no install). The
synthesis/range tests are install-gated (`pytest --run-install`): they read the real
``res/modeldefs/*.bin`` and assert a synthesized block matches a real block's shape and
survives the codec round-trip.
"""
import struct

import pytest

from helix_stadium_mcp import modeldefs as M


# -- decoder (no install needed) ------------------------------------------
def test_msgpack_scalars():
    assert M._unpack(b"\x05", 0)[0] == 5             # positive fixint
    assert M._unpack(b"\xff", 0)[0] == -1            # negative fixint
    assert M._unpack(b"\xc0", 0)[0] is None
    assert M._unpack(b"\xc2", 0)[0] is False
    assert M._unpack(b"\xc3", 0)[0] is True
    assert M._unpack(b"\xa2id", 0)[0] == "id"        # fixstr
    assert M._unpack(b"\xcd\x01\x00", 0)[0] == 256   # uint16
    assert M._unpack(b"\xd0\xfb", 0)[0] == -5        # int8
    assert M._unpack(b"\xcb" + struct.pack(">d", 0.742), 0)[0] == 0.742      # float64
    assert abs(M._unpack(b"\xca" + struct.pack(">f", 0.5), 0)[0] - 0.5) < 1e-9  # float32


def test_msgpack_containers():
    assert M._unpack(b"\x92\x01\x02", 0)[0] == [1, 2]            # fixarray
    assert M._unpack(b"\x81\xa1a\x05", 0)[0] == {"a": 5}         # fixmap
    # a param-record shape: {"def": 0.55, "type": "f"}
    payload = b"\x82\xa3def\xcb" + struct.pack(">d", 0.55) + b"\xa4type\xa1f"
    assert M._unpack(payload, 0)[0] == {"def": 0.55, "type": "f"}


def test_decode_bin_skips_header_and_magic():
    body = b"\x81\xa2id\x2a"  # {"id": 42}
    raw = b'{"ver":"x"}\x00' + M._MAGIC + body
    assert M._decode_bin(raw) == {"id": 42}


def test_decode_bin_requires_magic():
    with pytest.raises(ValueError):
        M._decode_bin(b"no magic here")


def test_coerce_default_float32_quantizes():
    # a float64 default becomes its float32 image (device-native), matching real blocks
    v = M._coerce_default(0.742)
    assert v == struct.unpack("<f", struct.pack("<f", 0.742))[0]
    assert M._coerce_default(True) is True
    assert M._coerce_default(2) == 2
    # a continuous (type "f") param is a float even when the def is a whole number
    assert isinstance(M._coerce_default(1, "f"), float) and M._coerce_default(1, "f") == 1.0
    assert M._coerce_default(-48, "f") == -48.0


def test_block_type_mapping():
    assert M.block_type("amp") == "amp"
    assert M.block_type("preamp") == "amp"
    assert M.block_type("cab_ir_interp") == "cab"
    assert M.block_type("delay") == "fx"
    assert M.block_type("reverb") == "fx"
    assert M.block_type("anything-else") == "fx"


# -- synthesis against the real install -----------------------------------
install = pytest.mark.install


@pytest.fixture(scope="module")
def defs():
    md = M.load_modeldefs()
    if not md:
        pytest.skip("no Helix Stadium model-defs found")
    return md


@install
def test_modeldefs_load(defs):
    assert len(defs) > 500
    rec = defs["Agoura_AmpBritPlexi"]
    assert rec["category"] == "amp"
    assert isinstance(rec["usage"], (int, float))
    assert "def" in rec["params"]["Bass"]


@install
@pytest.mark.parametrize("mid,btype", [
    ("Agoura_AmpBritPlexi", "amp"),
    ("HD2_CabMicIr_4x12BritV30WithPan", "cab"),
    ("HD2_ReverbGanymedeMono", "fx"),
    ("HD2_DelaySimpleDelayMono", "fx"),
])
def test_synth_template_shape(defs, mid, btype):
    t = M.synth_template(mid)
    assert t is not None
    assert t["type"] == btype
    assert t["favorite"] == 0 and t["path"] == 0
    assert t["@enabled"] == {"value": True}
    assert t["harness"]["params"] == {
        "EvtIdx": {"value": -1}, "bypass": {"value": False}, "upper": {"value": True}}
    slot = t["slot"][0]
    assert slot["model"] == mid and slot["version"] == 0
    assert slot["params"], "params must be non-empty"
    for pv in slot["params"].values():
        assert set(pv) == {"value"}


@install
def test_synth_unknown_model_is_none(defs):
    assert M.synth_template("NotARealModelId") is None


@install
def test_synth_roundtrips_through_codec(defs):
    from helix_stadium_mcp.codec import read_hsp, write_hsp
    from helix_stadium_mcp.defaults import load_empty
    from helix_stadium_mcp.preset import add_block

    base = load_empty()
    if base is None:
        pytest.skip("no empty-preset template available")
    for mid in ("HD2_CabMicIr_4x12BritV30WithPan", "HD2_ReverbGanymedeMono"):
        add_block(base, 1, M.synth_template(mid))
    b1 = write_hsp(base)
    assert write_hsp(read_hsp(b1)) == b1     # byte-stable round-trip


@install
def test_clamp_range_continuous_only(defs):
    # a normalized 0..1 knob clamps; a boolean/enum does not
    rng = M.clamp_range("HD2_DistKinkyBoostMono", "Drive")
    assert rng == (0, 1)
    assert M.clamp_range("HD2_DistKinkyBoostMono", "Boost") is None   # boolean param


@install
def test_device_defaults_to_regular_stadium(defs):
    # default reads p37md = the regular Stadium (safe subset). device_id from the header.
    assert M.device_id() == 0x00260001
    assert len(defs) == 786
    # XL-only I/O models (extra FX loops / sends / inputs) are absent and un-synthesizable
    assert "HD2_FXLoopMono3" not in defs
    assert M.synth_template("HD2_FXLoopMono3") is None


@install
def test_synth_empty_shape(defs):
    obj = M.synth_empty("My Preset")
    assert obj is not None
    assert obj["meta"]["name"] == "My Preset"
    assert obj["meta"]["device_id"] == M.device_id()   # sourced from the install
    flow = obj["preset"]["flow"]
    assert len(flow) == 2
    for path in flow:
        assert path["b00"]["type"] == "input" and path["b00"]["endpoint"] == "b13"
        assert path["b13"]["type"] == "output" and path["b13"]["endpoint"] == "b00"
    snaps = obj["preset"]["snapshots"]
    assert len(snaps) == 8 and [s["valid"] for s in snaps] == [True] + [False] * 7
    assert set(obj["preset"]) >= {"flow", "params", "snapshots", "sources", "xyctrl", "clip", "cursor"}
    assert len(obj["preset"]["sources"]) == 24


@install
def test_generate_preset_from_scratch_roundtrips(defs):
    """Full generation: synth blank -> add synth blocks -> scenes -> automate -> write."""
    from helix_stadium_mcp.codec import read_hsp, write_hsp
    from helix_stadium_mcp.preset import (add_block, configure_snapshots, edit_param,
                                          resolve_snapshot_index, set_active_snapshot)
    obj = M.synth_empty("Gen")
    add_block(obj, 1, M.synth_template("Agoura_AmpBritPlexi"))
    add_block(obj, 1, M.synth_template("HD2_CabMicIr_4x12BritV30WithPan"))
    configure_snapshots(obj, ["Rhythm", "Lead"])
    edit_param(obj, 1, "b01", "NormDrv", 0.9, snapshot=resolve_snapshot_index(obj, "Lead"))
    set_active_snapshot(obj, 0)
    b1 = write_hsp(obj)
    assert write_hsp(read_hsp(b1)) == b1              # byte-stable round-trip
