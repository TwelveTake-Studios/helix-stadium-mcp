"""Tool groups.

``register_all`` wires every implemented group onto the MCP server. Groups whose
``register`` raises ``NotImplementedError`` are still scaffold stubs and are
skipped, so the server runs with whatever is implemented (incremental build,
mirroring the reaper/gimp pattern).
"""
from __future__ import annotations

from . import admin, models, read

_GROUPS = (read, models, admin)


def register_all(mcp, ctx) -> dict:
    registered, skipped = [], []
    for group in _GROUPS:
        name = group.__name__.rsplit(".", 1)[-1]
        try:
            group.register(mcp, ctx)
            registered.append(name)
        except NotImplementedError:
            skipped.append(name)
    return {"registered": registered, "skipped": skipped}
