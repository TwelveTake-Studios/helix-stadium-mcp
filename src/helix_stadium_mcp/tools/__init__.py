"""Tool groups.

``register_all`` wires every implemented group onto the MCP server. Read groups
(read / models / admin) always register. The write group (edit) registers unless
``HELIX_MCP_READONLY`` is set, giving a hard read-only mode. Groups whose ``register``
raises ``NotImplementedError`` are scaffold stubs and are skipped (incremental build).
"""
from __future__ import annotations

import os

from . import admin, edit, models, read, setlist

_READ_GROUPS = (read, models, admin)
_WRITE_GROUPS = (edit, setlist)


def readonly() -> bool:
    return os.environ.get("HELIX_MCP_READONLY", "").strip().lower() in ("1", "true", "yes", "on")


def register_all(mcp, ctx) -> dict:
    groups = list(_READ_GROUPS) + ([] if readonly() else list(_WRITE_GROUPS))
    registered, skipped = [], []
    for group in groups:
        name = group.__name__.rsplit(".", 1)[-1]
        try:
            group.register(mcp, ctx)
            registered.append(name)
        except NotImplementedError:
            skipped.append(name)
    return {"registered": registered, "skipped": skipped, "readonly": readonly()}
