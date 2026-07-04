"""MCP server entry point.

Wires the tool groups onto a FastMCP server. A shared :class:`HelixContext`
lazily loads the model catalog from the user's install the first time a tool
needs it, so `serve`/`detect` start instantly and catalog errors surface as clean
tool results rather than crashes.
"""
from __future__ import annotations


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
    mcp = FastMCP("helix-stadium-mcp")
    from . import tools
    report = tools.register_all(mcp, ctx)
    return mcp, ctx, report


def main() -> None:
    """Console entry point (`helix-stadium-mcp serve`). Runs over stdio."""
    mcp, _ctx, _report = build_server()
    mcp.run()


if __name__ == "__main__":
    main()
