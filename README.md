# helix-stadium-mcp

Work with your Line 6 Helix Stadium presets in plain language, without knowing the technical details.

Point your AI assistant at a `.hsp` preset and ask what it does, how two snapshots differ, or to
change it — brighten the lead, add a reverb, set up Rhythm / Lead / Clean snapshots. You get
plain-English answers with real values (dB, Hz, ms) instead of raw parameter numbers, and any edits
are written back safely. It's an [MCP](https://modelcontextprotocol.io) server, so it runs in any MCP
client (Claude Desktop, Cursor, VS Code, and others).

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

Because it understands the whole patch, it can also **change it for you**. Ask for more gain on the
lead or a touch more reverb, and it edits the exact block and parameter — then writes the result back
through a safety check (validate → byte-exact round-trip → atomic write with a backup). It can also
build a preset from scratch, set up snapshots, and assemble a setlist.

## Try asking

- *"What does this preset do?"*
- *"What's different between my Rhythm and Lead snapshots?"*
- *"Add a Plate reverb after the amp and set the mix to 20%."*
- *"Give the Lead snapshot more gain without making it louder."*
- *"Set up Rhythm, Lead, and Clean snapshots on this preset."*
- *"Build me a clean preset with a US Deluxe amp, a 1x12 cab, and a spring reverb."*
- *"Find me a plexi-style amp."*  /  *"List every delay model."*
- *"Turn these presets into a setlist for Friday's gig."*

## What it does

- **Reads** `.hsp` presets losslessly (byte-exact round-trip).
- **Explains** a preset in plain English — the full signal chain of each path with friendly model
  names, on/off state, per-snapshot & footswitch tags, and parameters in real units (dB, Hz, ms, %).
- **Diffs snapshots** — exactly what changes between two snapshots (e.g. Rhythm vs Lead), in real units.
- **Edits** — change parameters in real units, toggle or add / remove / reorder blocks, rename, and
  set up snapshots, in plain language. Any model in your catalog can be added at its factory defaults.
- **Creates** — start a new preset from scratch and build it up block by block.
- **Assembles setlists** — order a batch of presets into a setlist with a pre-gig checklist.
- **Browses** the model catalog (list / describe / search models).
- **Validates** a preset's structure (and, with the catalog, its model ids and controller sources).

Every change is written back through a safety gate — validate → round-trip → atomic write with a
`.bak` backup — and `HELIX_MCP_READONLY` keeps the server read-only whenever you want it.

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

To keep the server read-only — for instance when you point it at presets you don't fully trust — set
`HELIX_MCP_READONLY=1`, and the write tools are left out at startup.

## Tools

**Read**

| Tool | What you'd ask it |
|---|---|
| `read_preset` | Load a `.hsp` and get its structure (paths, blocks, snapshots) |
| `explain_preset` | The full signal chain in plain English, with real units |
| `diff_snapshots` | What changes between two snapshots |
| `list_models` · `describe_model` · `search_models` | Browse the model catalog |
| `validate_preset` | Check a preset's structure |
| `detect_install` | Find the Helix Stadium catalog this reads from |

**Edit & build**

| Tool | What you'd ask it |
|---|---|
| `edit_param` | Set a parameter, by current value or for a specific snapshot |
| `add_block` · `remove_block` · `move_block` | Add, remove, or reorder a block |
| `toggle_block` | Turn a block on/off — globally or per snapshot |
| `configure_snapshots` · `set_active_snapshot` | Name the scenes and pick the active one |
| `rename_preset` · `rename_snapshot` | Rename the preset or a snapshot |
| `create_preset` | Start a new blank preset to build up |
| `build_setlist` | Assemble ordered presets into a setlist + checklist |

Every write tool goes through the safety gate above; set `HELIX_MCP_READONLY` to leave them out.

## Roadmap

Pre-1.0, following [semantic versioning](https://semver.org) — the tool surface can still change
between minor versions.

- **v0.1** — read, explain & compare presets; browse the model catalog; validate a preset.
- **v0.2 (now)** — the assistant makes changes **for** you: edit parameters, toggle / add / remove /
  reorder blocks, rename, and set up snapshots; build a preset from scratch; and assemble setlists —
  in plain language. Every write goes through a safety gate, with `HELIX_MCP_READONLY` to keep it
  read-only on demand.
- **v0.3** — generate a whole preset from a description.
- **v1.0** — a stable tool surface.

macOS support is in progress alongside Windows.

## Requirements

- **Helix Stadium** installed (Windows confirmed; macOS support in progress). The server reads the
  model catalog and per-model definitions from your own install at runtime.
- Python 3.10+.

## Trademarks

Not affiliated with or endorsed by Line 6 or Yamaha Guitar Group.

All trademarks are the property of their respective owners. "Line 6," "Helix," and "Helix Stadium,"
along with any amp, cab, or effect model names and other brand or product names that appear (for
example through the model catalog or a preset), are used here only to identify compatible gear. This
project claims no ownership of any trademark it references.

## License

MIT © TwelveTake Studios LLC. See [LICENSE](https://github.com/TwelveTake-Studios/helix-stadium-mcp/blob/main/LICENSE).
