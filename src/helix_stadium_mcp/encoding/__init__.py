"""Raw <-> display value encoding.

A param's ``display_tag`` (from UIDefs) points to a P35Controls control-type OR is
an inline enum list. Three stored-value domains, chosen by the control-type,
never guessed:
  A  normalized x scale  (``dspToDisplayScale``)
  B  bipolar normalized  (``min + stored*(max-min)`` via minDisplayValue/maxDisplayValue)
  C  real units          (identity)
Then ``format``/``formatUnits`` (a printf string or a list of display-value bands)
produces the human readout.

NOTE (v1 scope): band-format + the common domains are handled; a few exotic
control-types still fall back to a plain rounded number. Full coverage is tracked
in docs/OPEN-QUESTIONS.md.
"""
from __future__ import annotations


def _num(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        r = round(v, 4)
        return str(int(r)) if r == int(r) else str(r)
    return str(v)


def _pick_band(bands: list, num: float) -> dict | None:
    for b in bands:
        lo = b.get("lowerBound", float("-inf"))
        hi = b.get("upperBound", float("inf"))
        if lo <= num < hi:
            return b
    return bands[-1] if bands else None


def _apply_format(fmt, num) -> str | None:
    """Apply a printf format or a display-value band. Bands may carry a
    ``unitsMultiplier`` (e.g. x0.001 for kHz, x-1 for pan-Left) and some are
    literal labels (``Off``, ``Center``) with no format specifier."""
    mult = 1
    if isinstance(fmt, list):
        if not fmt:
            return None
        if isinstance(fmt[0], str):
            # enum: a list of labels indexed by the (int) value
            try:
                return fmt[int(num)]
            except (ValueError, IndexError, TypeError):
                return None
        band = _pick_band(fmt, num)
        if not band:
            return None
        mult = band.get("unitsMultiplier", 1)
        fmt = band.get("formatUnits") or band.get("format")
    if isinstance(fmt, str):
        try:
            return fmt % (num * mult)
        except (TypeError, ValueError):
            return fmt  # literal label with no % specifier (e.g. "Off", "Center")
    return None


def sync_note_label(catalog, index) -> str | None:
    """Map a tempo-sync note index to its division label (e.g. 7 -> '1/8 Dotted')."""
    sn = catalog.controls.get("sync_note") if hasattr(catalog, "controls") else None
    fmt = sn.get("format") if isinstance(sn, dict) else None
    if isinstance(fmt, list) and isinstance(index, (int, float)) and 0 <= int(index) < len(fmt):
        return fmt[int(index)]
    return None


def display_string(catalog, model_id: str, param_id: str, stored):
    """Return ``(human_string, display_tag)`` for a stored param value."""
    pdef = catalog.param_def(model_id, param_id)
    tag = pdef.get("display_tag") if pdef else None

    # inline enum: stored int indexes the list
    if isinstance(tag, list):
        try:
            return tag[int(stored)], tag
        except (ValueError, IndexError, TypeError):
            return _num(stored), tag

    ctrl = catalog.controls.get(tag) if isinstance(tag, str) else None
    if not ctrl:
        return _num(stored), tag

    # A single odd control shape must never crash a read-only render.
    try:
        scale = ctrl.get("dspToDisplayScale")
        if scale is not None:                                # domain A
            num = stored * scale
        elif "minDisplayValue" in ctrl and "maxDisplayValue" in ctrl:   # domain B
            num = ctrl["minDisplayValue"] + stored * (ctrl["maxDisplayValue"] - ctrl["minDisplayValue"])
        else:                                                # domain C
            num = stored
        formatted = _apply_format(ctrl.get("formatUnits") or ctrl.get("format"), num)
        return (formatted if formatted is not None else _num(num)), tag
    except Exception:  # noqa: BLE001 - display fallback, never raise from a render
        return _num(stored), tag
