"""Preset validation (structural + catalog).

v1 scope: structural integrity (shape, snapshot-array lengths, block positions)
plus catalog checks (model ids resolve) when a catalog is supplied. Deeper
stage-safety checks (value-in-range, source-reference integrity, routing) land in
a later phase — see docs/spec/07-safety-validation.md.
"""
from __future__ import annotations


def validate(obj: dict, catalog=None) -> dict:
    """Return ``{"errors": [...], "warnings": [...]}`` for a parsed .hsp object."""
    errors: list[str] = []
    warnings: list[str] = []

    if not isinstance(obj, dict):
        return {"errors": ["preset is not a JSON object"], "warnings": []}
    if not isinstance(obj.get("meta"), dict):
        errors.append("missing 'meta' object")

    preset = obj.get("preset")
    if not isinstance(preset, dict):
        errors.append("missing 'preset' object")
        return {"errors": errors, "warnings": warnings}

    snaps = preset.get("snapshots")
    if isinstance(snaps, list) and len(snaps) != 8:
        warnings.append(f"expected 8 snapshot slots, found {len(snaps)}")

    sources = set((preset.get("sources") or {}).keys())  # numeric-string keys

    flow = preset.get("flow")
    if not isinstance(flow, list):
        errors.append("'preset.flow' is not a list")
        flow = []

    for pi, path_obj in enumerate(flow, start=1):
        if not isinstance(path_obj, dict):
            errors.append(f"path {pi} is not an object")
            continue
        for bkey, blk in path_obj.items():
            if not (bkey.startswith("b") and isinstance(blk, dict)):
                continue
            _check_block(pi, bkey, blk, catalog, sources, errors, warnings)

    return {"errors": errors, "warnings": warnings}


def _check_snap8(label: str, arr, warnings: list[str]) -> None:
    if isinstance(arr, list) and len(arr) != 8:
        warnings.append(f"{label}: snapshot array length {len(arr)} (expected 8)")


def _check_source(label: str, ctrl, sources: set, warnings: list[str]) -> None:
    """A controller must reference a source id that exists in preset.sources."""
    if isinstance(ctrl, dict) and "source" in ctrl and sources:
        if str(ctrl["source"]) not in sources:
            warnings.append(f"{label}: controller source {ctrl['source']} not in preset.sources")


def _check_block(pi, bkey, blk, catalog, sources, errors, warnings) -> None:
    where = f"path{pi}.{bkey}"

    pos = blk.get("position")
    if isinstance(pos, int) and bkey[1:].isdigit() and pos != int(bkey[1:]):
        warnings.append(f"{where}: position {pos} != key index {int(bkey[1:])}")

    en = blk.get("@enabled")
    if isinstance(en, dict):
        _check_snap8(f"{where} @enabled", en.get("snapshots"), warnings)
        _check_source(f"{where} @enabled", en.get("controller"), sources, warnings)

    for slot in blk.get("slot") or []:
        if not isinstance(slot, dict):
            continue
        model = slot.get("model")
        if catalog is not None and model and catalog.resolve(model) is None:
            warnings.append(f"{where}: model '{model}' not found in the installed catalog")
        params = slot.get("params")
        if isinstance(params, dict):
            for pid, pv in params.items():
                if isinstance(pv, dict):
                    _check_snap8(f"{where}.{pid}", pv.get("snapshots"), warnings)
                    _check_source(f"{where}.{pid}", pv.get("controller"), sources, warnings)
