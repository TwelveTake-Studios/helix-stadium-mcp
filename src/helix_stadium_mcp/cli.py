"""`helix-stadium-mcp` console-script dispatcher.

Subcommands:
  serve     run the MCP server over stdio (what the MCP client invokes)
  doctor    diagnose install + load the catalog + report counts
  detect    print resolved install path as JSON
  explain   [debug] render a .hsp preset as plain text
  version   print version + disclaimer
"""
from __future__ import annotations

import argparse
import json
import sys

from . import DISCLAIMER, __version__


def _cmd_serve(_args) -> int:
    from .server import main as serve_main
    serve_main()
    return 0


def _cmd_detect(args) -> int:
    from .config import detect
    print(json.dumps(detect(args.res), indent=2))
    return 0


def _cmd_doctor(args) -> int:
    from .catalog import Catalog
    from .config import detect
    d = detect(args.res)
    print(json.dumps(d, indent=2))
    if not d.get("found"):
        print("\nPROBLEMS FOUND — set HELIX_STADIUM_RES to your install's res/ folder.",
              file=sys.stderr)
        return 1
    try:
        c = Catalog(args.res)
    except Exception as e:  # noqa: BLE001 - doctor reports any load failure
        print(f"\nCatalog load FAILED: {e}", file=sys.stderr)
        return 1
    print("\ncatalog counts:")
    print(json.dumps(c.counts(), indent=2))
    print("\nOK")
    return 0


def _cmd_explain(args) -> int:
    from .catalog import Catalog
    from .codec import read_hsp
    from .preset import explain_text
    obj = read_hsp(open(args.path, "rb").read())
    print(explain_text(Catalog(args.res), obj))
    return 0


def _cmd_version(_args) -> int:
    print(f"helix-stadium-mcp {__version__}")
    print(DISCLAIMER)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="helix-stadium-mcp",
                                description="MCP server for Line 6 Helix Stadium (.hsp) presets")
    p.add_argument("--res", help="path to the Helix Stadium res/ catalog dir "
                                 "(overrides HELIX_STADIUM_RES + auto-detect)")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("serve", help="run the MCP server over stdio").set_defaults(func=_cmd_serve)
    sub.add_parser("detect", help="print resolved install path as JSON").set_defaults(func=_cmd_detect)
    sub.add_parser("doctor", help="diagnose install + load catalog").set_defaults(func=_cmd_doctor)

    ep = sub.add_parser("explain", help="[debug] render a .hsp preset as text")
    ep.add_argument("path", help="path to a .hsp file")
    ep.set_defaults(func=_cmd_explain)

    sub.add_parser("version", help="print version + disclaimer").set_defaults(func=_cmd_version)
    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help()
        return 0
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
