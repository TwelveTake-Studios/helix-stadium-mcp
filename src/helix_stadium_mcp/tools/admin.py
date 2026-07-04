"""Install detection + basic preset validation (v1)."""
from __future__ import annotations

import json
from pathlib import Path

from ..codec import has_magic, read_hsp
from ..config import detect as detect_res
from ..util import envelope as E
from ..validation import validate as validate_obj


def register(mcp, ctx) -> None:

    @mcp.tool(name="detect_install")
    def detect_install() -> dict:
        """Locate the installed Helix Stadium catalog (res/) this server reads from.
        Reports the resolved path and whether the catalog is present."""
        d = detect_res(getattr(ctx, "_res_dir", None))
        if not d.get("found"):
            return E.err(E.INSTALL_NOT_FOUND, d.get("message", "not found"), data=d)
        return E.ok(d, summary=f"Helix Stadium catalog at {d['res_dir']}")

    @mcp.tool(name="validate_preset")
    def validate_preset(path: str) -> dict:
        """Structural validation of a .hsp file: magic header, parseable JSON, expected
        top-level shape, and 8-slot snapshot arrays. (Catalog-level and stage-safety
        validation land in a later phase.)"""
        p = Path(path)
        try:
            data = p.read_bytes()
        except OSError as e:
            return E.err(E.NOT_FOUND, f"Cannot read {path}: {e}")

        if not has_magic(data):
            return E.err(E.VALIDATION_FAILED, "missing 8-byte 'rpshnosj' magic header",
                         data={"valid": False, "errors": ["missing magic header"], "warnings": []})
        try:
            obj = read_hsp(data)
        except (ValueError, json.JSONDecodeError) as e:
            return E.err(E.VALIDATION_FAILED, f"parse failed: {e}")

        catalog = None
        try:
            catalog = ctx.catalog          # enables model-id checks; structural-only without it
        except FileNotFoundError:
            pass

        res = validate_obj(obj, catalog)
        result = {"valid": not res["errors"], "name": obj.get("meta", {}).get("name"), **res}
        if res["errors"]:
            return E.err(E.VALIDATION_FAILED, f"{len(res['errors'])} error(s)", data=result)
        return E.ok(
            result,
            summary="valid .hsp" + (f" ({len(res['warnings'])} warning(s))" if res["warnings"] else ""),
            warnings=res["warnings"],
        )
