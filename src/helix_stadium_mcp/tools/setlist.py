"""Setlist assembly tool. Writes files, so it lives in the write group."""
from __future__ import annotations

import os

from ..setlist import build_setlist
from ..util import envelope as E


def register(mcp, ctx) -> None:

    @mcp.tool(name="build_setlist")
    def build_setlist_tool(name: str, presets: list[str], out_dir: str | None = None) -> dict:
        """Assemble an ordered setlist from per-song `.hsp` presets. `presets` is the list of
        `.hsp` file paths in gig order. Each is validated first (a setlist is only as safe as its
        weakest member); the result is a folder of order-numbered `.hsp` files plus a manifest and
        a verify-before-the-show checklist. `out_dir` defaults to the first preset's folder."""
        if not presets:
            return E.err(E.NOT_FOUND, "no presets given")
        catalog = None
        try:
            catalog = ctx.catalog
        except FileNotFoundError:
            pass
        outd = out_dir or os.path.dirname(os.path.abspath(presets[0]))
        res = build_setlist(name, presets, outd, catalog)
        if not res["ok"]:
            return E.err(E.VALIDATION_FAILED, "setlist not built — some presets are invalid",
                         data={"errors": res["errors"]})
        return E.ok({"folder": res["folder"], "songs": res["songs"]},
                    summary=f"setlist {name!r}: {len(res['songs'])} song(s) -> {res['folder']}")
