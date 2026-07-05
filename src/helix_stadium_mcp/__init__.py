"""helix-stadium-mcp — an MCP server for Line 6 Helix Stadium (.hsp) presets.

Reads and explains Helix Stadium presets in plain language. The model catalog is
read from the user's own installed Helix Stadium at runtime. Run the server with
``helix-stadium-mcp serve``.
"""
from __future__ import annotations

__version__ = "0.1.1"

DISCLAIMER = (
    "Not affiliated with or endorsed by Line 6 or Yamaha Guitar Group. "
    '"Line 6," "Helix," and "Helix Stadium," along with any amp, cab, or effect '
    "model names and other brand names that appear, are used only to identify "
    "compatible gear. This project owns no trademarks."
)
