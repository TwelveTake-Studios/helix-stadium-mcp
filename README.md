# helix-stadium-mcp

An [MCP](https://modelcontextprotocol.io) server that lets an AI assistant **read, explain, and
(soon) edit** Line 6 Helix Stadium `.hsp` guitar presets from natural language.

> **Disclaimer:** `helix-stadium-mcp` is an independent, unofficial tool. It is **not affiliated
> with, authorized, maintained, sponsored, or endorsed by Line 6 or Yamaha Guitar Group.** "Line 6,"
> "Helix," and "Helix Stadium" are trademarks of their respective owners, used here only nominatively
> to describe compatibility.

## What it does

- **Reads** `.hsp` presets losslessly (byte-exact round-trip).
- **Explains** a preset in plain English — the full signal chain of each path with friendly model
  names, on/off state, per-snapshot & footswitch tags, and parameters in real units (dB, Hz, ms, %).
- **Diffs snapshots** — exactly what changes between two snapshots (e.g. Rhythm vs Lead), in real units.
- **Browses** the model catalog (list / describe / search models).
- **Validates** a preset's structure (and, with the catalog, its model ids and controller sources).

Editing, generation, and setlist tooling are on the roadmap.

## Requirements

- **Helix Stadium** installed (Windows confirmed; macOS support in progress). The server reads the
  model catalog from your own install at runtime — **no Line 6 content is bundled or redistributed.**
- Python 3.10+.

## Install & configure

```bash
uvx twelvetake-helix-stadium-mcp serve      # or: pipx run twelvetake-helix-stadium-mcp serve
```

Add to your MCP client (e.g. Claude Desktop `mcpServers`):

```json
{
  "mcpServers": {
    "helix-stadium": {
      "command": "uvx",
      "args": ["twelvetake-helix-stadium-mcp", "serve"]
    }
  }
}
```

If the catalog isn't auto-detected, set `HELIX_STADIUM_RES` to your install's `res/` folder (the one
containing `P35ModelCatalog.json`). Check detection with `helix-stadium-mcp doctor`.

## Tools (v1)

`read_preset` · `explain_preset` · `diff_snapshots` · `list_models` · `describe_model` ·
`search_models` · `validate_preset` · `detect_install`

## License

MIT © TwelveTake Studios LLC. See [LICENSE](./LICENSE).
