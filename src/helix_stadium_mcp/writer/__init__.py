"""The write gate — the single door every authored `.hsp` write passes through.

Policy: **never silently write an invalid preset.** Errors block
unconditionally; the round-trip harness runs on the ACTUAL bytes; writes are atomic
with a `.bak` backup; and the file on disk is re-read and verified before we return.
"""
from __future__ import annotations

import os
import tempfile

from ..codec import read_hsp, write_hsp
from ..validation import validate


class WriteBlocked(Exception):
    """A write was refused by the gate. ``report`` explains where and why."""

    def __init__(self, report: dict):
        self.report = report
        super().__init__(report.get("message", "write blocked"))


def round_trip_check(obj: dict, catalog=None) -> dict:
    """Serialize → reparse → verify. Returns ``{ok, bytes, issues}``.

    The idempotence (byte) check is what catches int-vs-float / framing drift that a
    Python ``==`` comparison misses (``1 == 1.0`` is True).
    """
    issues: list[str] = []
    data = write_hsp(obj)
    obj2 = read_hsp(data)
    if obj2 != obj:
        issues.append("RT-001: a value changed during round-trip")
    if write_hsp(obj2) != data:
        issues.append("RT-002/003: serialization not idempotent (framing or int/float drift)")
    rv = validate(obj2, catalog)
    if rv["errors"]:
        issues.append("RT-005: reparse failed validation: " + "; ".join(rv["errors"]))
    return {"ok": not issues, "bytes": data, "issues": issues}


def atomic_write(target: str, data: bytes) -> str | None:
    """Write ``data`` to ``target`` atomically, backing up any existing file to ``.bak``.

    Returns the backup path (or None if the target was new). Never partially overwrites.
    """
    backup = None
    if os.path.exists(target):
        backup = target + ".bak"
        with open(target, "rb") as f:
            prev = f.read()
        with open(backup, "wb") as f:
            f.write(prev)
    directory = os.path.dirname(os.path.abspath(target))
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".hsp.tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, target)  # atomic on the same filesystem
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return backup


def safe_write(obj: dict, target: str, catalog=None) -> dict:
    """Validate → round-trip → atomic write + backup → read-back verify.

    Raises :class:`WriteBlocked` (no override) on any error. Returns
    ``{ok, target, backup, warnings}`` on success.
    """
    pre = validate(obj, catalog)
    if pre["errors"]:
        raise WriteBlocked({"phase": "validate", "message": f"{len(pre['errors'])} validation error(s)",
                            "errors": pre["errors"]})

    rt = round_trip_check(obj, catalog)
    if not rt["ok"]:
        raise WriteBlocked({"phase": "round-trip", "message": "round-trip verification failed",
                            "errors": rt["issues"]})

    backup = atomic_write(target, rt["bytes"])

    readback = read_hsp(open(target, "rb").read())
    if readback != obj:
        raise WriteBlocked({"phase": "read-back", "message": "file on disk does not match the intended preset",
                            "errors": ["read-back mismatch (possible disk/OS corruption)"]})

    return {"ok": True, "target": target, "backup": backup, "warnings": pre["warnings"]}
