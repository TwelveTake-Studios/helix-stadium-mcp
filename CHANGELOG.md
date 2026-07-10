# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.1] - 2026-07-10

A read-clarity and guidance patch. No new tools; the write surface is unchanged.

### Added
- `read_preset` and `explain_preset` now show each block's key (e.g. `b06`) and its footswitch and
  controller assignments — bypass switches (momentary or latching) and per-parameter controllers,
  with their ranges in real units. When you ask for a change, the assistant can point to the exact
  block, and it can tell you how your footswitches and expression controls are wired.

### Changed
- The server now ships built-in guidance for the assistant using it, so it makes edits directly
  through the tools and says plainly when a request isn't supported yet.

## [0.2.0] - 2026-07-09

The server can now **edit, create, and assemble** presets, not just read them — the tool
surface grows from 8 read-only tools to 19. Every write goes through a validate →
round-trip → atomic-write safety gate, and `HELIX_MCP_READONLY` keeps the server read-only
when you want it. Default blocks and parameter ranges are synthesized from your own
install's model definitions, so any model in the catalog can be added at its factory
defaults.

### Added
- **Edit tools (9)** — `edit_param`, `toggle_block`, `add_block`, `remove_block`,
  `move_block`, `rename_preset`, `rename_snapshot`, `configure_snapshots`, and
  `set_active_snapshot`. Change parameters in real display units (e.g. `8000` for 8 kHz),
  toggle or add / remove / reorder blocks, rename, and define / switch snapshots — all in
  plain language.
- **`create_preset`** — start a new blank preset (input → output, empty chain, 8 snapshots)
  and build it up with the edit tools.
- **`build_setlist`** — assemble a setlist from a list of presets. It validates every member
  fail-closed (any invalid preset aborts the whole write) and emits order-numbered `.hsp`
  copies, a `setlist.json`, and a `SETLIST.md` pre-gig checklist.
- **Snapshot generation** — `configure_snapshots` names the scenes; `edit_param` and
  `toggle_block` take a `snapshot` argument to store per-scene parameter and bypass values;
  `set_active_snapshot` sets the scene the preset opens in. Build multi-snapshot presets
  (e.g. Rhythm / Lead / Clean) end to end.
- **Model definitions at runtime** — `add_block` synthesizes each block's full parameter
  structure and factory defaults from your install's model definitions, reaching every model
  in the catalog (amps, cabs, and effects alike). `describe_model` now reports each
  parameter's default and valid range plus the model's DSP cost, and `edit_param` clamps
  values to those ranges.

### Changed
- **The server is no longer read-only.** The package summary, README, and `SECURITY.md` now
  describe the read / edit / build surface. `HELIX_MCP_READONLY` strips the write tools for
  read-only deployments.

### Security
- **Every write is gated.** All writes funnel through a single `safe_write` path: structural
  validation → byte-exact round-trip check → atomic replace with a `.bak` backup →
  read-back. A failure at any step blocks the write; there is no override.
- **`HELIX_MCP_READONLY`** removes all write tools at startup, so you can point the agent at
  untrusted content and keep the server strictly read-only. This resolves the "future write
  tool" caveat noted in 0.1.x — with the toggle set, prompt injection cannot be steered into
  an unwanted write.
- The server still runs over stdio, opens no listening socket, and transmits nothing about
  your install.

## [0.1.1] - 2026-07-04

Documentation and packaging patch. No functional or API changes; the tool surface is
unchanged and remains read-only.

### Changed
- Expanded the README with real usage content: a plain-language lead-in, an example
  `explain` output, a "Try asking" section, a versioned roadmap, and an expanded tool
  reference. Moved trademark/affiliation into a dedicated Trademarks note that also covers
  amp, cab, and effect model names, and reworded `SECURITY.md`, the package docstring, and
  the CLI `version` disclaimer in the same plain, factual voice.
- Rewrote the `pyproject.toml` package summary to match the read-only tool surface
  (dropped the stale "editing" claim); added `helix-stadium`/`hsp` keywords and an
  `Environment :: Console` classifier; added a Changelog project URL.

### Fixed
- Made the README `LICENSE` link absolute so it resolves on the PyPI project page.
- Added the missing `diff_snapshots` entry to the tool list in `SECURITY.md`.
- Included `SECURITY.md` in the source distribution (`sdist`).

## [0.1.0] - 2026-07-04

First release. The Phase-1 core: a read-only MCP server that reads, explains, and
browses Line 6 Helix Stadium `.hsp` presets. The model catalog is read at runtime from
the user's own installed Helix Stadium.

### Added
- **Codec** (`codec/`) — the `.hsp` container: the 8-byte magic header, a
  preservation-first float format, and (de)serialization that round-trips a preset
  **byte-for-byte**, so a read → write cycle is lossless (native int/float JSON values
  are preserved, not reformatted).
- **Catalog** (`catalog/`) — loads `P35ModelCatalog` / `P35ModelUIDefs` / `P35Controls`
  from the user's install `res/` at runtime; model/param counts match spec
  (18 categories / 627 models / 641 UIDefs entries / 5,344 params / 145 stereo aliases),
  and stereo preset ids resolve to their base mono model.
- **Encoding** (`encoding/`) — decodes raw parameter values into real units via the
  UIDefs display domains (A/B/C), band formats, `unitsMultiplier` (kHz), and enum
  labels, so values render cleanly as dB / Hz / kHz / ms / % / pan.
- **Preset** (`preset/`) — reconstructs the signal flow (per path, per block) and the
  plain-English `explain` rendering with friendly model names, on/off state,
  per-snapshot & footswitch tags, and parameters in real units.
- **Tools** over FastMCP (8) — `read_preset`, `explain_preset`, `diff_snapshots`,
  `list_models`, `describe_model`, `search_models`, `validate_preset`, `detect_install`;
  each returns the structured envelope. The server builds and registers all three tool
  groups (read / models / admin).
- **Validation** (`validation/`) — structural + catalog checks: shape, 8-slot snapshot
  arrays, block positions, model-id resolution, and controller source-reference integrity.
- **Install detection** (`config.py`) — resolves the catalog `res/` directory from an
  explicit path, the `HELIX_STADIUM_RES` env var, or platform auto-detect
  (Windows confirmed; macOS candidates staged, unverified).
- **CLI** (`helix-stadium-mcp`): `serve`, `doctor`, `detect`, `explain`, `version`.
- **Test suite** — codec / catalog / encoding tests, with the real-catalog checks
  gated behind `--run-install` (they need a real Helix Stadium install and otherwise
  skip). A GitHub Actions CI workflow runs ruff + pytest on Python 3.10–3.13.
- Packaging as `twelvetake-helix-stadium-mcp` (import package `helix_stadium_mcp`,
  console script `helix-stadium-mcp`); `LICENSE` (MIT) and `SECURITY.md`.

### Security
- The v1 tool surface is **read-only** and exposes **no arbitrary-code-execution
  tool**. Prompt injection into a *future* write tool is the main residual risk; a
  planned `HELIX_MCP_READONLY` toggle will keep the server read-only even after write
  tools land. The threat model is documented in `SECURITY.md`.

[Unreleased]: https://github.com/TwelveTake-Studios/helix-stadium-mcp/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/TwelveTake-Studios/helix-stadium-mcp/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/TwelveTake-Studios/helix-stadium-mcp/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/TwelveTake-Studios/helix-stadium-mcp/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/TwelveTake-Studios/helix-stadium-mcp/releases/tag/v0.1.0
