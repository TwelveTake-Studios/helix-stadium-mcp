"""MCP server entry point.

Wires the tool groups onto a FastMCP server. A shared :class:`HelixContext`
lazily loads the model catalog from the user's install the first time a tool
needs it, so `serve`/`detect` start instantly and catalog errors surface as clean
tool results rather than crashes.
"""
from __future__ import annotations


# Guidance handed to any MCP client/assistant using this server. Keeps an assistant from
# misdescribing the tool (these are Helix Stadium presets, not the older Helix line / HX Edit)
# and from offloading edits to manual work when a tool doesn't cover something.
INSTRUCTIONS = """\
Helix Stadium MCP reads, edits, creates, and assembles Line 6 Helix Stadium presets
(.hsp files). A preset is a JSON document; every change is written through a safety gate
(validate -> byte-exact round-trip -> atomic write with a .bak backup). The model catalog
and per-model definitions are read from the user's own Helix Stadium installation.

Guidance for assistants using this server:
- These presets are for the Line 6 Helix Stadium. They are NOT edited with "HX Edit" -- that
  is the editor for the older Helix Floor / Rack / LT / Stomp / HX Effects line and does not
  work with the Stadium.
- Make edits with these tools. Do not tell the user to edit a preset by hand in a separate
  application; performing the edit here is the point.
- If a request is not covered by a tool, say plainly that the server does not support it yet
  and offer the closest thing it can do. Do not invent a manual workaround and do not claim it
  is impossible.
- Block references (e.g. b04) and any footswitch/controller assignments come from read_preset;
  parameter values are in real display units (dB, Hz, ms, %, or enum labels).
- Every write keeps a .bak next to the file, so edits are recoverable.
"""


class HelixContext:
    """Lazily-loaded catalog access shared by all tools."""

    def __init__(self, res_dir: str | None = None):
        self._res_dir = res_dir
        self._catalog = None

    @property
    def catalog(self):
        """The loaded Catalog. Raises FileNotFoundError if no install is found."""
        if self._catalog is None:
            from .catalog import Catalog
            self._catalog = Catalog(self._res_dir)
        return self._catalog


def build_server(ctx: HelixContext | None = None):
    """Create the FastMCP server and register the implemented tool groups."""
    from mcp.server.fastmcp import FastMCP

    if ctx is None:
        ctx = HelixContext()
    mcp = FastMCP("helix-stadium-mcp", instructions=INSTRUCTIONS)
    from . import tools
    report = tools.register_all(mcp, ctx)
    return mcp, ctx, report


def main() -> None:
    """Console entry point (`helix-stadium-mcp serve`). Runs over stdio."""
    mcp, _ctx, _report = build_server()
    mcp.run()


if __name__ == "__main__":
    main()
