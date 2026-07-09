"""Setlist assembly (Mode B — loose `.hsp` files + a manifest).

The north-star finish: a natural-language setlist → one preset per song → assembled in
gig order. Until we have a real `.hss` sample to decode, a setlist is
a folder of order-numbered, individually-validated `.hsp` files plus a manifest + a
verify-before-the-show checklist. Every preset must validate before it's included — a setlist
is only as safe as its weakest member.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..codec import read_hsp
from ..preset import summarize
from ..validation import validate

_CHECKLIST = """## Verify before the show (per song)
1. **Load it cold** — import the `.hsp`, confirm it loads with no error dialog.
2. **Walk all snapshots** — step through each, confirm none is silent and none jumps volume.
3. **Levels at gig volume** — consistent FOH feed across snapshots.
4. **Footswitches** — press each assigned switch; confirm it does what its name says.
5. **Tempo** — tap-tempo if the song's tempo differs from the preset.
6. **Firmware match** — the unit runs the firmware these were built against; don't update day-of.
7. **Keep a fallback** in an adjacent slot. Do the verify at soundcheck, never the downbeat.
"""


def _safe(s: str) -> str:
    out = "".join(c if (c.isalnum() or c in " -_") else "_" for c in (s or "")).strip()
    return out or "preset"


def build_setlist(name: str, preset_paths: list[str], out_dir: str, catalog=None) -> dict:
    """Validate each preset, copy it into ``<out_dir>/<name>/`` order-numbered, and write a
    manifest + checklist. Returns ``{ok, folder?, songs?, errors?}``. Any invalid preset aborts
    the whole setlist (nothing is written)."""
    if not preset_paths:
        return {"ok": False, "errors": ["no presets given"]}

    parsed, errors = [], []
    for i, pp in enumerate(preset_paths, start=1):
        p = Path(pp)
        try:
            data = p.read_bytes()
            obj = read_hsp(data)
        except (OSError, ValueError) as e:
            errors.append(f"{pp}: cannot read/parse ({e})")
            continue
        song = obj.get("meta", {}).get("name") or p.stem
        rv = validate(obj, catalog)
        if rv["errors"]:
            errors.append(f"{song}: {len(rv['errors'])} validation error(s) — {rv['errors'][0]}")
        parsed.append((i, song, obj, data))

    if errors:
        return {"ok": False, "errors": errors}

    folder = Path(out_dir) / _safe(name)
    folder.mkdir(parents=True, exist_ok=True)

    songs = []
    for order, song, obj, data in parsed:
        fn = f"{order:02d} - {_safe(song)}.hsp"
        (folder / fn).write_bytes(data)
        entry = {"order": order, "song": song, "file": fn,
                 "snapshots": [s.get("name") for s in obj.get("preset", {}).get("snapshots", [])
                               if s.get("valid")]}
        if catalog is not None:
            s = summarize(catalog, obj)
            entry["chain"] = [[b["name"] for b in path] for path in s["paths"]]
            entry["tempo"] = s["tempo"]
        songs.append(entry)

    manifest = {"name": name, "mode": "loose-hsp+manifest", "songs": songs}
    (folder / "setlist.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (folder / "SETLIST.md").write_text(_render_md(name, songs), encoding="utf-8")
    return {"ok": True, "folder": str(folder), "songs": songs}


def _render_md(name: str, songs: list[dict]) -> str:
    lines = [f"# Setlist — {name}", "", f"{len(songs)} song(s), in gig order. "
             "Import each `.hsp` into Helix Stadium.", ""]
    for s in songs:
        lines.append(f"## {s['order']}. {s['song']}  (`{s['file']}`)")
        if s.get("chain"):
            for pi, chain in enumerate(s["chain"], start=1):
                if chain:
                    lines.append(f"- Path {pi}: " + " → ".join(chain))
        if s.get("snapshots"):
            lines.append(f"- Snapshots: {', '.join(s['snapshots'])}")
        lines.append("")
    lines.append(_CHECKLIST)
    return "\n".join(lines)
