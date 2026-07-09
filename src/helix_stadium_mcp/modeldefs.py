"""Decode the Stadium editor's compiled model definitions and synthesize default blocks.

``res/modeldefs/p35md-*.bin`` is the editor's own model-definition file: a short ASCII
JSON header, an 8-byte magic ``ldompgsm`` (reverse of "msgpmodl"), then a single
MessagePack map ``{model_id -> record}``. Each record carries the model's COMPLETE
parameter set — including the hidden ``AmpCab*`` voicing params — with every param's
factory default (``def``), range (``min``/``max``), and ``type``, plus a DSP ``usage``
cost and, for amps, the default paired cab (``cablink``).

That is everything needed to build a valid default block for any of the ~800 models
from the definitions alone: the param structure matches a real block
exactly (verified against 40 exported blocks across every category, 0 differences), and
the block wrapper is constant (``harness``/``type``/``version``). ``add_block`` uses this
to reach every model; ``edit_param``/``describe`` use the ranges for hard-clamping.

Decoded with a minimal, stdlib-only MessagePack reader (the file uses only the map/array/
str/int/float/bool/nil subset) so the package stays dependency-light — the codec and
catalog are likewise stdlib-only. The model definitions are read from the user's own install at runtime.
"""
from __future__ import annotations

import glob
import json
import os
import struct
from pathlib import Path

from .config import resolve_res_dir

_MAGIC = b"ldompgsm"

# .bin ``category`` -> .hsp block ``type`` (verified against real presets). Everything
# not listed is an effect and serializes as "fx".
_BLOCK_TYPE = {"amp": "amp", "preamp": "amp", "cab_ir_interp": "cab"}

_cache: dict | None = None
_cache_key: str | None = None
_device_id: int | None = None


# -- minimal MessagePack reader -------------------------------------------
def _unpack(buf: bytes, i: int):
    """Return ``(value, next_index)`` for the MessagePack value at ``buf[i]``."""
    b = buf[i]
    i += 1
    if b <= 0x7F:                      # positive fixint
        return b, i
    if b >= 0xE0:                      # negative fixint
        return b - 0x100, i
    if 0x80 <= b <= 0x8F:              # fixmap
        return _unpack_map(buf, i, b & 0x0F)
    if 0x90 <= b <= 0x9F:              # fixarray
        return _unpack_array(buf, i, b & 0x0F)
    if 0xA0 <= b <= 0xBF:              # fixstr
        return _unpack_str(buf, i, b & 0x1F)
    if b == 0xC0:
        return None, i
    if b == 0xC2:
        return False, i
    if b == 0xC3:
        return True, i
    if b == 0xCA:                      # float32
        return struct.unpack_from(">f", buf, i)[0], i + 4
    if b == 0xCB:                      # float64
        return struct.unpack_from(">d", buf, i)[0], i + 8
    if b in (0xCC, 0xCD, 0xCE, 0xCF):  # uint 8/16/32/64
        n = 1 << (b - 0xCC)
        return int.from_bytes(buf[i:i + n], "big"), i + n
    if b in (0xD0, 0xD1, 0xD2, 0xD3):  # int 8/16/32/64
        n = 1 << (b - 0xD0)
        return int.from_bytes(buf[i:i + n], "big", signed=True), i + n
    if b in (0xD9, 0xDA, 0xDB):        # str 8/16/32
        n, i = _read_len(buf, i, 1 << (b - 0xD9))
        return _unpack_str(buf, i, n)
    if b in (0xC4, 0xC5, 0xC6):        # bin 8/16/32
        n, i = _read_len(buf, i, 1 << (b - 0xC4))
        return bytes(buf[i:i + n]), i + n
    if b in (0xDC, 0xDD):              # array 16/32
        n, i = _read_len(buf, i, 2 << (b - 0xDC))
        return _unpack_array(buf, i, n)
    if b in (0xDE, 0xDF):              # map 16/32
        n, i = _read_len(buf, i, 2 << (b - 0xDE))
        return _unpack_map(buf, i, n)
    raise ValueError(f"unsupported MessagePack byte 0x{b:02x} at offset {i - 1}")


def _read_len(buf: bytes, i: int, nbytes: int):
    return int.from_bytes(buf[i:i + nbytes], "big"), i + nbytes


def _unpack_str(buf: bytes, i: int, n: int):
    return buf[i:i + n].decode("utf-8"), i + n


def _unpack_array(buf: bytes, i: int, n: int):
    out = []
    for _ in range(n):
        v, i = _unpack(buf, i)
        out.append(v)
    return out, i


def _unpack_map(buf: bytes, i: int, n: int):
    out = {}
    for _ in range(n):
        k, i = _unpack(buf, i)
        v, i = _unpack(buf, i)
        out[k] = v
    return out, i


def _decode_bin(raw: bytes) -> dict:
    """Decode a modeldefs .bin's MessagePack payload into ``{model_id: record}``."""
    pos = raw.find(_MAGIC)
    if pos < 0:
        raise ValueError("modeldefs .bin missing 'ldompgsm' magic")
    obj, _ = _unpack(raw, pos + len(_MAGIC))
    if not isinstance(obj, dict):
        raise ValueError("modeldefs payload is not a model map")
    return obj


# -- loading ---------------------------------------------------------------
def _ver_key(fp: str):
    stem = Path(fp).stem  # e.g. p37md-1_3_0_0
    try:
        return tuple(int(x) for x in stem.split("-", 1)[1].split("_"))
    except (IndexError, ValueError):
        return (0,)


def _preferred_prefix() -> str:
    """Which Stadium the model-defs describe. Default ``p37md`` = the regular Stadium, a safe
    SUBSET whose blocks load on any Stadium. The XL (``p35md``) adds 15 I/O-only models (FX
    Loop 3/4, Send/Return 3/4, Input 2, ...) for its extra jacks; select it with
    ``HELIX_STADIUM_DEVICE=xl``. p37 and p35 are byte-identical for all 786 shared models."""
    dev = os.environ.get("HELIX_STADIUM_DEVICE", "").strip().lower()
    return "p35md" if dev in ("xl", "p35", "stadium-xl") else "p37md"


def _latest_bin(res: Path) -> Path | None:
    """Newest model-defs ``.bin`` for the selected device, falling back to the other family."""
    md = res / "modeldefs"
    pref = _preferred_prefix()
    for prefix in (pref, "p35md" if pref == "p37md" else "p37md"):
        files = glob.glob(str(md / f"{prefix}-*.bin"))
        if files:
            return Path(max(files, key=_ver_key))
    return None


def _parse_device_id(raw: bytes) -> int | None:
    """The device id from the .bin's ASCII JSON header (``{"id":["0x00260001"],...}``)."""
    try:
        hdr = json.loads(raw[:raw.index(b"}") + 1].decode("utf-8"))
        ids = hdr.get("id")
        if isinstance(ids, list) and ids:
            return int(str(ids[0]), 16)
    except (ValueError, KeyError):
        pass
    return None


def load_modeldefs(res_dir=None) -> dict:
    """Return ``{model_id: record}`` from the install's model-defs; ``{}`` if unavailable.

    Degrades gracefully: any missing install / file / decode error yields an empty map,
    so callers fall back to the optional default templates and nothing new can break a read or write.
    """
    global _cache, _cache_key, _device_id
    try:
        res = res_dir if isinstance(res_dir, Path) else resolve_res_dir(res_dir)
    except FileNotFoundError:
        return {}
    key = str(res)
    if _cache is not None and _cache_key == key:
        return _cache
    result: dict = {}
    did = None
    binf = _latest_bin(res)
    if binf is not None:
        try:
            raw = binf.read_bytes()
            result = _decode_bin(raw)
            did = _parse_device_id(raw)
        except (OSError, ValueError):
            result = {}
    _cache, _cache_key, _device_id = result, key, did
    return result


def device_id(res_dir=None) -> int | None:
    """The user's device id (from the selected model-defs header), or ``None`` if unavailable."""
    load_modeldefs(res_dir)
    return _device_id


def record(model_id: str, res_dir=None) -> dict | None:
    """The raw model-defs record for a model id (exact id; mono/stereo are separate)."""
    return load_modeldefs(res_dir).get(model_id)


def param_meta(model_id: str, res_dir=None) -> dict:
    """``{param_id: {def, min, max, type, id}}`` for a model (empty if unknown)."""
    rec = load_modeldefs(res_dir).get(model_id)
    return rec.get("params", {}) if isinstance(rec, dict) else {}


def usage(model_id: str, res_dir=None):
    """The model's DSP cost, or ``None`` if unknown."""
    rec = load_modeldefs(res_dir).get(model_id)
    return rec.get("usage") if isinstance(rec, dict) else None


def clamp_range(model_id: str, param_id: str, res_dir=None):
    """``(min, max)`` for a continuous param, or ``None`` if not clampable.

    Only continuous (``type == "f"``) params with numeric bounds are returned; booleans
    and enums validate elsewhere and must not be range-clamped.
    """
    pm = param_meta(model_id, res_dir).get(param_id)
    if not isinstance(pm, dict) or pm.get("type") != "f":
        return None
    lo, hi = pm.get("min"), pm.get("max")
    if isinstance(lo, (int, float)) and not isinstance(lo, bool) and \
       isinstance(hi, (int, float)) and not isinstance(hi, bool):
        return (lo, hi) if lo <= hi else (hi, lo)
    return None


# -- synthesis -------------------------------------------------------------
def _coerce_default(d, ptype=None):
    """A ``def`` value as it should sit in a block. Continuous params (``type == "f"``) are
    float32-quantized floats (device-native) even when the def is a whole number; enums keep
    their int kind and switches their bool kind."""
    if ptype == "f":
        try:
            return struct.unpack("<f", struct.pack("<f", float(d)))[0]
        except (TypeError, ValueError):
            return d
    if isinstance(d, (bool, int)):
        return d
    if isinstance(d, float):
        return struct.unpack("<f", struct.pack("<f", d))[0]
    return d


def block_type(category: str) -> str:
    return _BLOCK_TYPE.get(category, "fx")


def _synth_params(params_meta: dict) -> dict:
    """``{pid: {"value": default}}`` from a record's params, at type-correct factory defaults."""
    out = {}
    for pid, pdef in params_meta.items():
        pdef = pdef if isinstance(pdef, dict) else {}
        d = pdef.get("def")
        if d is None:
            d = pdef.get("min", 0)
        out[pid] = {"value": _coerce_default(d, pdef.get("type"))}
    return out


def synth_template(model_id: str, res_dir=None) -> dict | None:
    """Build a complete default block for ``model_id`` from the model-defs, or ``None``.

    The result matches a real block's structure exactly, at the model's true
    factory defaults — ready for :func:`helix_stadium_mcp.preset.add_block` (which assigns
    ``position`` on insert).
    """
    rec = load_modeldefs(res_dir).get(model_id)
    if not isinstance(rec, dict) or not isinstance(rec.get("params"), dict):
        return None
    slot_params = _synth_params(rec["params"])
    return {
        "@enabled": {"value": True},
        "favorite": 0,
        "harness": {
            "@enabled": {"value": True},
            "params": {
                "EvtIdx": {"value": -1},
                "bypass": {"value": False},
                "upper": {"value": True},
            },
        },
        "path": 0,
        "type": block_type(rec.get("category", "")),
        "slot": [{
            "@enabled": {"value": True},
            "model": model_id,
            "version": 0,
            "params": slot_params,
        }],
    }


# -- blank preset synthesis ------------------------------------------------
# Save metadata. device_id is sourced from the model-defs header at runtime (so it matches the
# user's actual device); these are the regular-Stadium fallbacks. device_version is the saving
# firmware and isn't in the .bin header, so it stays a known-good constant (fw metadata, not
# tone data, cross-firmware portable).
_DEVICE_ID_FALLBACK = 2490369   # 0x00260001 (regular Stadium)
_DEVICE_VERSION = 318899516     # 0x1302053C
# Footswitch source ids present in every preset (two contiguous banks of 12).
_FS_SOURCE_IDS = [*range(16843008, 16843020), *range(16843264, 16843276)]
# The blank canvas: two paths, input+output only. Path 1 takes the instrument input.
_EMPTY_PATHS = (
    ("P35_InputInst1", "P35_OutputMatrix"),
    ("P35_InputNone", "P35_OutputMatrix"),
)


def _io_block(model_id: str, position: int, endpoint: str, btype: str, res_dir=None) -> dict | None:
    """A structural input/output block (simpler harness, an ``endpoint``) at factory defaults."""
    rec = load_modeldefs(res_dir).get(model_id)
    if not isinstance(rec, dict) or not isinstance(rec.get("params"), dict):
        return None
    return {
        "@enabled": {"value": True},
        "endpoint": endpoint,
        "favorite": 0,
        "harness": {"@enabled": {"value": True}},
        "path": 0,
        "position": position,
        "type": btype,
        "slot": [{"@enabled": {"value": True}, "model": model_id, "version": 0,
                  "params": _synth_params(rec["params"])}],
    }


def synth_empty(name: str = "New Preset", res_dir=None) -> dict | None:
    """Build a blank preset from the install's model-defs.

    Two paths (input+output only, empty processing chains), 8 snapshots (1 valid), and the
    standard preset container. Returns ``None`` if the input/output models can't be read.
    """
    flow = []
    for in_model, out_model in _EMPTY_PATHS:
        b00 = _io_block(in_model, 0, "b13", "input", res_dir)
        b13 = _io_block(out_model, 13, "b00", "output", res_dir)
        if b00 is None or b13 is None:
            return None
        flow.append({"@enabled": {"value": True}, "b00": b00, "b13": b13})
    snapshots = [{"name": f"SNAPSHOT {i + 1}", "expsw": 1 if i == 0 else -1,
                  "source": 0, "tempo": 120.0, "valid": i == 0} for i in range(8)]
    snapshots[0]["color"] = "auto"
    return {
        "meta": {"color": "auto", "device_id": device_id(res_dir) or _DEVICE_ID_FALLBACK,
                 "device_version": _DEVICE_VERSION, "info": "", "name": name},
        "preset": {
            "clip": {"end": 10.0, "filename": "<EMPTY>", "path": "USER CLIPS", "start": 0.0},
            "cursor": {"flow": 0, "path": 0, "position": 8},
            "flow": flow,
            "params": {"activeexpsw": 1, "activesnapshot": 0, "inst1Z": "FirstEnabled",
                       "inst2Z": "FirstEnabled", "tempo": 120.0},
            "snapshots": snapshots,
            "sources": {str(sid): {"fs_color": "auto", "fs_label": "", "fs_topidx": 0}
                        for sid in _FS_SOURCE_IDS},
            "xyctrl": {"rbtime": 0.5, "rubberband": 1, "x": 0, "y": 0},
        },
    }
