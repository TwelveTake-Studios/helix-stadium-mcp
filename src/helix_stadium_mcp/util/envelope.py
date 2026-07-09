"""The structured result envelope every MCP tool returns.

Shape: ``{ok, data, summary, warnings, error}``. Tools never raise across the
transport — failures come back as ``err(code, message)`` so the client sees a
clean, typed result.
"""
from __future__ import annotations

from typing import Any

# Stable, typed error codes.
INSTALL_NOT_FOUND = "INSTALL_NOT_FOUND"
PARSE_ERROR = "PARSE_ERROR"
NOT_FOUND = "NOT_FOUND"
VALUE_OUT_OF_RANGE = "VALUE_OUT_OF_RANGE"
VALIDATION_FAILED = "VALIDATION_FAILED"
IO_ERROR = "IO_ERROR"


def ok(data: Any = None, summary: str = "", warnings: list[str] | None = None) -> dict:
    return {"ok": True, "data": data, "summary": summary,
            "warnings": warnings or [], "error": None}


def err(code: str, message: str, data: Any = None) -> dict:
    return {"ok": False, "data": data, "summary": "",
            "warnings": [], "error": {"code": code, "message": message}}
