"""Model catalog loaded from the user's own Helix Stadium install.

Reads P35ModelCatalog / P35ModelUIDefs / P35Controls from ``res/`` at runtime.
Resolves ``*Stereo`` model ids via their base model's
``stereo_model`` field, and joins each param to its ``display_tag`` control-type.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import resolve_res_dir


def _load(res: Path, name: str):
    return json.loads((res / name).read_text(encoding="utf-8"))


class Catalog:
    def __init__(self, res_dir=None):
        self.res = resolve_res_dir(res_dir) if not isinstance(res_dir, Path) else res_dir
        self.catalog = _load(self.res, "P35ModelCatalog.json")
        self.uidefs = _load(self.res, "P35ModelUIDefs.json")
        self.controls = _load(self.res, "P35Controls.json")

        self.model_category: dict[str, str] = {}
        self.populated_categories: list[str] = []
        for cat in self.catalog["categories"]:
            models = [m for m in cat.get("models", []) if m]
            if models:
                self.populated_categories.append(cat["name"])
            for m in models:
                self.model_category[m] = cat["name"]

        # stereo_model value -> base model id (for resolving *Stereo ids)
        self.stereo_base: dict[str, str] = {
            d["stereo_model"]: base
            for base, d in self.uidefs.items()
            if isinstance(d, dict) and d.get("stereo_model")
        }

    # -- resolution --------------------------------------------------------
    def resolve(self, model_id: str) -> dict | None:
        """UIDefs entry for a model id, resolving *Stereo aliases to their base."""
        if model_id in self.uidefs:
            return self.uidefs[model_id]
        base = self.stereo_base.get(model_id)
        return self.uidefs[base] if base else None

    def friendly_name(self, model_id: str) -> str:
        entry = self.resolve(model_id)
        return entry.get("name", model_id) if entry else model_id

    def category_of(self, model_id: str) -> str:
        if model_id in self.model_category:
            return self.model_category[model_id]
        base = self.stereo_base.get(model_id)
        return self.model_category.get(base, "?") if base else "?"

    def param_def(self, model_id: str, param_id: str) -> dict | None:
        entry = self.resolve(model_id)
        if not entry:
            return None
        for p in entry.get("params", []):
            if p.get("id") == param_id:
                return p
        return None

    # -- browsing ----------------------------------------------------------
    def counts(self) -> dict:
        n_params = sum(len(v.get("params", [])) for v in self.uidefs.values()
                       if isinstance(v, dict))
        return {
            "populated_categories": len(self.populated_categories),
            "models": len(self.model_category),
            "uidefs_entries": len(self.uidefs),
            "params": n_params,
            "control_tags": len(self.controls),
            "stereo_aliases": len(self.stereo_base),
        }

    def list_models(self, category: str | None = None) -> list[dict]:
        out = []
        for mid, cat in sorted(self.model_category.items()):
            if category and cat.lower() != category.lower():
                continue
            out.append({"id": mid, "name": self.friendly_name(mid), "category": cat})
        return out

    def describe(self, model_id: str) -> dict | None:
        entry = self.resolve(model_id)
        if not entry:
            return None
        return {
            "id": model_id,
            "name": entry.get("name", model_id),
            "category": self.category_of(model_id),
            "dsp": entry.get("dsp"),
            "class": entry.get("class"),
            "params": [
                {"id": p.get("id"), "name": p.get("name"), "display_tag": p.get("display_tag")}
                for p in entry.get("params", [])
            ],
        }

    def search(self, query: str, limit: int = 25) -> list[dict]:
        q = query.lower()
        hits = []
        for mid in self.model_category:
            name = self.friendly_name(mid)
            if q in mid.lower() or q in name.lower():
                hits.append({"id": mid, "name": name, "category": self.category_of(mid)})
            if len(hits) >= limit:
                break
        return hits
