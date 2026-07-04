"""Model-catalog browsing tools (v1, read-only). Catalog read from the user's install."""
from __future__ import annotations

from ..util import envelope as E


def _catalog(ctx):
    try:
        return ctx.catalog, None
    except FileNotFoundError as e:
        return None, E.err(E.INSTALL_NOT_FOUND, str(e))


def register(mcp, ctx) -> None:

    @mcp.tool(name="list_models")
    def list_models(category: str | None = None) -> dict:
        """List available models, optionally filtered by category (e.g. 'Amp', 'Cab',
        'Distortion', 'Delay', 'Reverb'). Returns id, friendly name, and category."""
        cat, e = _catalog(ctx)
        if e:
            return e
        data = cat.list_models(category)
        return E.ok(data, summary=f"{len(data)} model(s)"
                                  + (f" in {category}" if category else ""))

    @mcp.tool(name="describe_model")
    def describe_model(model_id: str) -> dict:
        """Describe one model by id (resolving Stereo aliases): friendly name, category,
        DSP, and its full parameter list with display tags."""
        cat, e = _catalog(ctx)
        if e:
            return e
        desc = cat.describe(model_id)
        if not desc:
            return E.err(E.NOT_FOUND, f"Unknown model id: {model_id}")
        return E.ok(desc, summary=f"{desc['name']} ({desc['category']}), {len(desc['params'])} params")

    @mcp.tool(name="search_models")
    def search_models(query: str, limit: int = 25) -> dict:
        """Search models by id or friendly name (case-insensitive substring)."""
        cat, e = _catalog(ctx)
        if e:
            return e
        hits = cat.search(query, limit)
        return E.ok(hits, summary=f"{len(hits)} match(es) for {query!r}")
