"""Talk to a Helix Stadium on the network, the way the Helix Stadium app does.

Reverse-engineered from a capture of the app editing a Stadium XL on firmware 1.4.0
(2026-10-18). The app opens a ZeroMQ DEALER socket to TCP 2002 (ZMTP 3.0, NULL security:
no login, no encryption). Each message is one OSC packet whose first int argument is a
request id; the unit answers with zero or more OSC replies carrying that id, then
``/status``. Large replies carry a blob holding a MessagePack document whose map keys are
four-character codes packed into uint32s.

PROVEN from the capture:
  /BlockEnableSet    ,iiii   [rid, flow, block, 0|1]
  /ParamValueSet     ,iiiiifi [rid, flow, block, model slot, param id, value, -1]
  /activateSnapshot  ,ii     [rid, snapshot index]
  /EditBufferStateGet ,i     -> /getEditBufferState [rid, ?, blob]  (the live preset)
Values are the same stored units as an .hsp file (Kinky Boost Drive 7 = 0.70).

Not proven, so refused rather than guessed (see ``check_target``): blocks whose position
and id differ (the capture can't tell which one a message uses), non-float params,
snapshot-controlled params, and the second path. Saving and loading presets were not
captured and are not implemented.
"""
from __future__ import annotations

import os
import socket
import struct

from ..modeldefs import _unpack

PORT = 2002
TIMEOUT = 4.0


def host() -> str:
    h = os.environ.get("HELIX_STADIUM_HOST", "").strip()
    if not h:
        raise ConnectionError("set HELIX_STADIUM_HOST to the unit's network address")
    return h


# --- OSC ---------------------------------------------------------------------------------

def _pad(b: bytes) -> bytes:
    return b + b"\0" * (4 - len(b) % 4)


def osc_encode(addr: str, tags: str, args) -> bytes:
    out = _pad(addr.encode()) + _pad(("," + tags).encode())
    for t, a in zip(tags, args, strict=True):
        if t == "i":
            out += struct.pack(">i", a)
        elif t == "f":
            out += struct.pack(">f", a)
        elif t == "s":
            out += _pad(a.encode())
        else:
            raise ValueError(f"unsupported OSC type {t!r}")
    return out


def _ostr(b: bytes, i: int):
    j = b.index(b"\0", i)
    return b[i:j].decode("latin1"), (j + 4) & ~3


def osc_decode(b: bytes):
    addr, i = _ostr(b, 0)
    if i >= len(b) or b[i:i + 1] != b",":
        return addr, []
    tags, i = _ostr(b, i)
    args = []
    for t in tags[1:]:
        if t == "i":
            args.append(struct.unpack_from(">i", b, i)[0]); i += 4
        elif t == "h":
            args.append(struct.unpack_from(">q", b, i)[0]); i += 8
        elif t == "f":
            args.append(struct.unpack_from(">f", b, i)[0]); i += 4
        elif t == "d":
            args.append(struct.unpack_from(">d", b, i)[0]); i += 8
        elif t == "s":
            s, i = _ostr(b, i); args.append(s)
        elif t == "b":
            n = struct.unpack_from(">i", b, i)[0]
            args.append(bytes(b[i + 4:i + 4 + n])); i += (4 + n + 3) & ~3
        elif t in "TF":
            args.append(t == "T")
        else:
            raise ValueError(f"unsupported OSC type {t!r}")
    return addr, args


def _fourcc(o):
    """MessagePack keys are uint32 four-character codes: 0x73666700 -> 'sfg_'."""
    if isinstance(o, dict):
        return {(struct.pack(">I", k).decode("latin1") if isinstance(k, int) and k > 0xFFFFFF
                 else k): _fourcc(v) for k, v in o.items()}
    if isinstance(o, list):
        return [_fourcc(x) for x in o]
    return o


def decode_blob(blob: bytes):
    """8-byte tag (e.g. '_sbepgsm') then one MessagePack document."""
    return _fourcc(_unpack(blob, 8)[0])


# --- ZMTP 3.0, NULL mechanism, DEALER ----------------------------------------------------

_GREETING = b"\xff" + b"\0" * 7 + b"\x01\x7f\x03\x00" + b"NULL".ljust(20, b"\0") + b"\0" * 32


class Unit:
    """One connection per use: ``with Unit() as u: u.call(...)``."""

    def __init__(self, addr: str | None = None, timeout: float = TIMEOUT):
        self.addr, self.timeout, self.rid = addr or host(), timeout, 1000

    def __enter__(self):
        self.s = socket.create_connection((self.addr, PORT), timeout=self.timeout)
        self.s.sendall(_GREETING)
        peer = self._read(64)
        if peer[12:16] != b"NULL":
            raise ConnectionError("unit asked for a security mechanism this client doesn't speak")
        ready = b"\x05READY" + self._prop("Socket-Type", b"DEALER") + self._prop("Identity", b"")
        self._send(ready, command=True)
        self._frame()                                      # the unit's READY
        return self

    def __exit__(self, *exc):
        self.s.close()

    @staticmethod
    def _prop(name: str, value: bytes) -> bytes:
        return bytes([len(name)]) + name.encode() + struct.pack(">I", len(value)) + value

    def _read(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.s.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("unit closed the connection")
            buf += chunk
        return buf

    def _send(self, body: bytes, command: bool = False):
        flag = 0x04 if command else 0
        if len(body) > 255:
            self.s.sendall(bytes([flag | 0x02]) + struct.pack(">Q", len(body)) + body)
        else:
            self.s.sendall(bytes([flag, len(body)]) + body)

    def _frame(self):
        flag = self._read(1)[0]
        n = struct.unpack(">Q", self._read(8))[0] if flag & 0x02 else self._read(1)[0]
        return flag, self._read(n)

    def call(self, addr: str, tags: str = "", *args):
        """Send one request; return ``(replies, status)`` for this request id."""
        self.rid += 1
        rid = self.rid
        self._send(osc_encode(addr, "i" + tags, (rid, *args)))
        replies = []
        while True:
            flag, body = self._frame()
            if flag & 0x04:
                continue                                   # ZMTP command (e.g. ping)
            a, args_ = osc_decode(body)
            if not args_ or args_[0] != rid:
                continue
            if a == "/status":
                return replies, args_[1:]
            replies.append((a, args_[1:]))

    # --- reads ----------------------------------------------------------------------------

    def edit_buffer(self) -> dict:
        replies, _ = self.call("/EditBufferStateGet")
        for a, args in replies:
            if a == "/getEditBufferState":
                return decode_blob(next(x for x in args if isinstance(x, bytes)))
        raise ConnectionError("unit did not return the current preset")

    def property(self, key: str):
        replies, _ = self.call("/PropertyValueGet", "s", key)
        for a, args in replies:
            if a == "/getPropertyValue":
                blob = next((x for x in args if isinstance(x, bytes)), None)
                return decode_blob(blob).get("val_") if blob else None
        return None


# --- the live preset ---------------------------------------------------------------------

def blocks(eb: dict, names: dict) -> list[dict]:
    """Flatten the edit buffer's signal flow: one entry per block, path numbers from 1."""
    out = []
    for fi, flow in enumerate(eb["sfg_"]["flow"]):
        b = flow["blks"]
        for pos, blk in zip(b[0::2], b[1::2], strict=True):
            for slot, m in enumerate(blk["mdls"]):
                out.append({"path": fi + 1, "position": pos, "id": blk["id__"], "slot": slot,
                            "type": blk["type"], "enabled": bool(blk["enbl"]),
                            "model": names.get(m["id__"], f"#{m['id__']}"),
                            "params": {p["pid_"]: {"value": p["valu"], "snap": p["snap"]}
                                       for p in m["parm"]}})
    return out


def find(eb: dict, names: dict, path: int, position: int, slot: int = 0) -> dict:
    for b in blocks(eb, names):
        if (b["path"], b["position"], b["slot"]) == (path, position, slot):
            return b
    raise KeyError(f"no block at path {path} position {position}")


def check_target(blk: dict, expect_model: str, pid: int | None = None, pdef: dict | None = None):
    """Refuse anything the capture didn't prove. Raises ValueError with the reason."""
    if blk["model"] != expect_model:
        raise ValueError(f"block is now {blk['model']}, not {expect_model}: the preset changed "
                         "on the unit; read it again")
    if blk["path"] != 1:
        raise ValueError("live edits on path 2 aren't proven yet")
    if blk["position"] != blk["id"]:
        raise ValueError("live edits on this block aren't proven yet (its position and id differ)")
    if pid is None:
        return
    p = blk["params"].get(pid)
    if p is None:
        raise KeyError("that parameter isn't on this block")
    if p["snap"]:
        raise ValueError("this parameter is snapshot-controlled; live snapshot values "
                         "aren't proven yet")
    if not pdef or pdef.get("type") != "f" or not isinstance(p["value"], float):
        raise ValueError("only continuous (knob) parameters can be changed live so far")
