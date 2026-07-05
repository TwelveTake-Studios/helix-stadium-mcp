# helix-stadium-mcp

Work with your Line 6 Helix Stadium presets in plain language, without knowing the technical details.

Point your AI assistant at a `.hsp` preset and ask what it does, or how two snapshots differ. You
get a plain-English answer with real values (dB, Hz, ms) instead of raw parameter numbers. It's an
[MCP](https://modelcontextprotocol.io) server, so it runs in any MCP client (Claude Desktop, Cursor,
VS Code, and others).

## Example

Ask *"what does this preset do?"* and point it at a `.hsp`. You get the whole signal chain back,
per path:

```
# Dual Rectifier Lead
tempo 120.0 BPM | active snapshot #0
Snapshots: 1. Rhythm (blue), 2. Lead (red)
## Path 1
  [amp] Cali Rectifire — on [per-snapshot] · Drive 7.5 | Bass 5.0 | Master 4.0
  [cab] 4x12 Cali V30 — on · HighCut 9.0 kHz | Distance 2.0 "
  [fx]  Minotaur — on [per-snapshot] · Gain 45 % | Level 60 %
  [fx]  Simple Delay — on [per-snapshot] · Mix 18 % | Time 400 ms | Feedback 25 %
```

Friendly model names, on/off state (and which snapshots switch it), and every parameter in the
units you'd read off the hardware.

Because it understands the whole patch, it also **walks you through changes**: ask how to brighten
the lead or get more gain, and it points you to the exact block and parameter to move, which you
apply in your editor. Making those edits for you is coming in v0.2 (see the roadmap).

## Try asking

- *"What does this preset do?"*
- *"What's different between my Rhythm and Lead snapshots?"*
- *"What amp and cab is this patch using, and how hard is the drive pushing?"*
- *"How do I get more gain out of the Lead tone without it getting louder?"*
- *"Find me a plexi-style amp."*  /  *"List every delay model."*
- *"Is this preset valid?"*

## What it does

- **Reads** `.hsp` presets losslessly (byte-exact round-trip).
- **Explains** a preset in plain English — the full signal chain of each path with friendly model
  names, on/off state, per-snapshot & footswitch tags, and parameters in real units (dB, Hz, ms, %).
- **Diffs snapshots** — exactly what changes between two snapshots (e.g. Rhythm vs Lead), in real units.
- **Browses** the model catalog (list / describe / search models).
- **Validates** a preset's structure (and, with the catalog, its model ids and controller sources).

## Install & configure

```bash
uvx twelvetake-helix-stadium-mcp serve      # or: pipx run twelvetake-helix-stadium-mcp serve
```

Add it to your MCP client's config. Most use an `mcpServers` block:

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

## Tools

| Tool | What you'd ask it |
|---|---|
| `read_preset` | Load a `.hsp` and get its structure (paths, blocks, snapshots) |
| `explain_preset` | The full signal chain in plain English, with real units |
| `diff_snapshots` | What changes between two snapshots |
| `list_models` · `describe_model` · `search_models` | Browse the model catalog |
| `validate_preset` | Check a preset's structure |
| `detect_install` | Find the Helix Stadium catalog this reads from |

## Roadmap

Pre-1.0, following [semantic versioning](https://semver.org) — the tool surface can still change
between minor versions.

- **v0.1 (now)** — read, explain & compare presets; browse the model catalog; validate a preset.
  The assistant understands your patch well enough to **talk you through** changes you make yourself.
- **v0.2** — the assistant makes the changes **for** you: change parameters, toggle/add/remove/reorder
  blocks, rename, and manage snapshots, in plain language.
- **v0.3** — generate presets from a description, and assemble setlists.
- **v1.0** — a stable tool surface.

macOS support is in progress alongside Windows.

## Requirements

- **Helix Stadium** installed (Windows confirmed; macOS support in progress). The server reads the
  model catalog from your own install at runtime.
- Python 3.10+.

## Trademarks

Not affiliated with or endorsed by Line 6 or Yamaha Guitar Group.

All trademarks are the property of their respective owners. "Line 6," "Helix," and "Helix Stadium,"
along with any amp, cab, or effect model names and other brand or product names that appear (for
example through the model catalog or a preset), are used here only to identify compatible gear. This
project claims no ownership of any trademark it references.

## License

MIT © TwelveTake Studios LLC. See [LICENSE](https://github.com/TwelveTake-Studios/helix-stadium-mcp/blob/main/LICENSE).
