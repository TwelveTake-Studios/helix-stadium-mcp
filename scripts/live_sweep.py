"""Prove live control of every model: add it, push every parameter to its minimum, maximum
and default, read each back, remove it. Runs on ONE disposable user preset and never saves.

    HELIX_STADIUM_HOST=<ip> python scripts/live_sweep.py <preset id> [log.jsonl]

TURN THE UNIT'S VOLUME DOWN FIRST: gain, level and feedback all go to maximum.
Resumable: models already in the log are skipped. Stops at the first state it can't explain
(preset switched, a block that won't come out); per-value mismatches are logged, not fatal.
At the end the preset is reloaded, which throws every change away.
"""
from __future__ import annotations

import json
import sys
import time

from helix_stadium_mcp import live as L
from helix_stadium_mcp.tools.live import _FIXED, _defs

PATH, POS = 2, 6           # the test spot (path 2 position 6)


def blocks(u, names):
    return {(b["path"], b["position"]): b for b in L.blocks(u.edit_buffer(), names) if b["slot"] == 0}


def clear(u, names, keep):
    """Remove every block that isn't in `keep` (the test block and any cab an amp brought)."""
    for (p, q), b in blocks(u, names).items():
        if (p, q) not in keep and not b["model"].startswith("P35_"):
            u.call("/doAgenda", "b", L.pack([{"cmnd": L.cmd("clrb"), "flow": p - 1, "bloc": q}]))
    extra = set(blocks(u, names)) - set(keep)
    if any(not blocks(u, names)[k]["model"].startswith("P35_") for k in extra):
        raise SystemExit(f"STOP: blocks would not come out: {sorted(extra)}")


def same(a, b, pdef):
    if pdef["type"] == "f":
        return isinstance(a, float) and abs(a - b) <= 1e-4 * max(1.0, abs(pdef["max"] - pdef["min"]))
    return a == b and isinstance(a, bool) == (pdef["type"] == "b")


def send(u, pid, pdef, v):
    t = pdef["type"]
    if t == "b":
        u.call("/ParamValueSet", "iiii" + ("T" if v else "F") + "i", PATH - 1, POS, 0, pid, bool(v), -1)
    else:
        u.call("/ParamValueSet", "iiii" + t + "i", PATH - 1, POS, 0, pid,
               float(v) if t == "f" else int(v), -1)


def sweep_model(u, md, names, model, baseline):
    rec = md[model]
    u.call("/ModelSet", "iiii", PATH - 1, POS, 0, rec["id"])
    now = blocks(u, names)
    got = now.get((PATH, POS))
    if not got or got["model"] != model:
        clear(u, names, baseline)
        return {"model": model, "result": "refused"}
    out = {"model": model, "result": "taken", "params": {}, "brought": sorted(
        f"{p}/{q} {b['model']}" for (p, q), b in now.items() if (p, q) not in baseline and (p, q) != (PATH, POS))}
    params = {n: p for n, p in rec.get("params", {}).items() if p.get("type") in ("f", "i", "b")}
    for label in ("min", "max", "def"):
        for name, p in params.items():
            if p["id"] in got["params"]:
                send(u, p["id"], p, p[label])
        back = blocks(u, names)[(PATH, POS)]["params"]
        for name, p in params.items():
            r = out["params"].setdefault(name, {})
            if p["id"] not in back:
                r["absent"] = True
            else:
                r[label] = "ok" if same(back[p["id"]]["value"], p[label], p) else \
                    f"sent {p[label]!r} got {back[p['id']]['value']!r}"
    clear(u, names, baseline)
    out["bad"] = sorted(n for n, r in out["params"].items()
                        if r.get("absent") or any(v != "ok" for k, v in r.items() if k != "absent"))
    return out


def main():
    preset = int(sys.argv[1])
    log = sys.argv[2] if len(sys.argv) > 2 else "live_sweep.jsonl"
    md, names = _defs()
    try:
        with open(log, encoding="utf-8") as f:
            done = {json.loads(x)["model"] for x in f}
    except FileNotFoundError:
        done = set()
    todo = sorted(k for k, r in md.items() if isinstance(r, dict) and "id" in r
                  and not k.startswith("P35_") and r.get("category") not in _FIXED and k not in done)
    print(f"{len(todo)} models to go ({len(done)} already logged)", flush=True)
    with L.Unit(timeout=10) as u:
        u.call("/LoadPresetWithCID", "i", preset)
        if u.property("server.active.preset.id") != preset:
            raise SystemExit("STOP: could not load the test preset")
        baseline = set(blocks(u, names))
        if (PATH, POS) in baseline:
            raise SystemExit(f"STOP: test spot path {PATH} position {POS} isn't empty")
        with open(log, "a", encoding="utf-8") as f:
            for i, model in enumerate(todo, 1):
                if u.property("server.active.preset.id") != preset:
                    raise SystemExit("STOP: a different preset was loaded on the unit")
                r = sweep_model(u, md, names, model, baseline)
                f.write(json.dumps(r) + "\n"); f.flush()
                print(f"{i}/{len(todo)} {model}: {r['result']} {len(r.get('bad', []))} bad", flush=True)
                time.sleep(0.05)
        u.call("/LoadPresetWithCID", "i", preset)     # throw every change away
    print("done; preset reloaded", flush=True)


if __name__ == "__main__":
    main()
