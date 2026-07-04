"""Locate the user's Helix Stadium ``res/`` catalog directory.

Resolution order: explicit path -> ``HELIX_STADIUM_RES`` env var -> platform
auto-detect. We NEVER bundle the catalog; it is read from the user's own install.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Confirmed on a real Windows install.
_WINDOWS = [
    r"C:\Program Files (x86)\Line6\Helix Stadium\res",
    r"C:\Program Files\Line6\Helix Stadium\res",
]
# UNVERIFIED — needs confirmation on a real Mac (see docs/DECISIONS-NEEDED.md #4).
_MACOS = [
    "/Applications/Helix Stadium.app/Contents/Resources/res",
    "/Applications/Line 6/Helix Stadium.app/Contents/Resources/res",
]


def candidate_res_dirs() -> list[Path]:
    plat = _WINDOWS if sys.platform.startswith("win") else _MACOS if sys.platform == "darwin" else []
    return [Path(p) for p in plat]


def resolve_res_dir(explicit: str | os.PathLike | None = None) -> Path:
    """Return a valid res/ dir or raise FileNotFoundError with the probed paths."""
    tried: list[str] = []
    for cand in (explicit, os.environ.get("HELIX_STADIUM_RES")):
        if cand:
            p = Path(cand)
            tried.append(str(p))
            if p.is_dir():
                return p
    for p in candidate_res_dirs():
        tried.append(str(p))
        if p.is_dir():
            return p
    raise FileNotFoundError(
        "Helix Stadium res/ catalog not found. Set HELIX_STADIUM_RES to your install's "
        "res folder (the one containing P35ModelCatalog.json). Probed:\n  " + "\n  ".join(tried)
    )


def detect(explicit: str | None = None) -> dict:
    """Structured detection result for the `detect`/`doctor` commands."""
    try:
        res = resolve_res_dir(explicit)
        return {"found": True, "res_dir": str(res),
                "has_catalog": (res / "P35ModelCatalog.json").is_file()}
    except FileNotFoundError as e:
        return {"found": False, "res_dir": None, "message": str(e),
                "candidates": [str(p) for p in candidate_res_dirs()]}
