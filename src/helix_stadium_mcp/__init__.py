"""helix-stadium-mcp — an MCP server for Line 6 Helix Stadium (.hsp) presets.

Reads, explains, and (later) edits/generates Helix Stadium presets from natural
language. Ships ZERO Line 6 content: the model catalog is read from the user's
own installed Helix Stadium at runtime. Run the server with ``helix-stadium-mcp serve``.
"""
from __future__ import annotations

__version__ = "0.1.0"

DISCLAIMER = (
    "helix-stadium-mcp is an independent, unofficial tool. It is not affiliated with, "
    "authorized, maintained, sponsored, or endorsed by Line 6 or Yamaha Guitar Group. "
    '"Line 6," "Helix," and "Helix Stadium" are trademarks of their respective owners, '
    "used here only nominatively to describe compatibility."
)
