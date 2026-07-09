"""Model-catalog browsing tools (v1, read-only). Catalog read from the user's install."""
from __future__ import annotations

from ..encoding import display_string
from ..modeldefs import param_meta, usage
from ..util import envelope as E


def _enrich_ranges(cat, model_id: str, desc: dict) -> None:
    """Attach factory default, range, and DSP usage from the model-defs (best-effort).

    Ranges/defaults are shown in the same display units ``edit_param`` accepts, so the
    AI can tune within bounds. No-ops if the model-defs can't be read.
    """
    meta = param_meta(model_id)
    if meta:
        for p in desc.get("params", []):
            pm = meta.get(p["id"])
            if not isinstance(pm, dict):
                continue
            if pm.get("def") is not None:
                p["default"] = display_string(cat, model_id, p["id"], pm["def"])[0]
            if pm.get("type") == "f" and isinstance(pm.get("min"), (int, float)) \
                    and isinstance(pm.get("max"), (int, float)):
                p["range"] = [display_string(cat, model_id, p["id"], pm["min"])[0],
                              display_string(cat, model_id, p["id"], pm["max"])[0]]
    u = usage(model_id)
    if u is not None:
        desc["dsp_usage"] = u


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
        DSP cost, and its full parameter list with display tags, factory default, and range."""
        cat, e = _catalog(ctx)
        if e:
            return e
        desc = cat.describe(model_id)
        if not desc:
            return E.err(E.NOT_FOUND, f"Unknown model id: {model_id}")
        _enrich_ranges(cat, model_id, desc)
        return E.ok(desc, summary=f"{desc['name']} ({desc['category']}), {len(desc['params'])} params")

    @mcp.tool(name="search_models")
    def search_models(query: str, limit: int = 25) -> dict:
        """Search models by id or friendly name (case-insensitive substring)."""
        cat, e = _catalog(ctx)
        if e:
            return e
        hits = cat.search(query, limit)
        return E.ok(hits, summary=f"{len(hits)} match(es) for {query!r}")
