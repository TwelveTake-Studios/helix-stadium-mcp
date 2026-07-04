# Changelog

All notable changes to this project are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-07-04

First release. The Phase-1 core: a read-only MCP server that reads, explains, and
browses Line 6 Helix Stadium `.hsp` presets. Ships **zero Line 6 content** — the model
catalog is read at runtime from the user's own installed Helix Stadium.

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

[Unreleased]: https://github.com/TwelveTake-Studios/helix-stadium-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/TwelveTake-Studios/helix-stadium-mcp/releases/tag/v0.1.0
