# Security Policy

## Trust model

Helix Stadium MCP is designed for a **single-user workstation**. It runs with the
same privileges as the user who launches it, and it gives any attached AI agent the
ability to read — and, unless you disable writes, edit and create — Line 6 Helix
Stadium presets on that machine, using the model catalog from your own install.
**It is not a sandbox and does not attempt to be one.** Treat installing it the same
way you would treat granting a local automation script access to your preset files
and your Helix Stadium install.

If you need a stronger boundary (multi-tenant, untrusted agents, or untrusted
input), run the server inside an OS-level sandbox / container / dedicated user
account. This project does not provide that isolation itself.

## Threat model

### What it protects

- **No arbitrary-code-execution tool.** Unlike some MCP servers, this one exposes
  **no raw exec / eval escape hatch.** The entire tool surface is a fixed set of
  structured, parameter-validated tools; there is no tool that runs attacker-supplied
  code, opens a network connection, or touches files outside the presets and setlists
  you point it at.
- **Writes are bounded and gated.** The write tools only create or modify Helix
  preset (`.hsp`) and setlist files. Every write goes through a single `safe_write`
  path — structural validation → byte-exact round-trip check → atomic replace that
  first writes a `.bak` backup → read-back — so a write either lands as a valid,
  restorable file or is refused. There is no override.
- **Read-only on demand.** Set `HELIX_MCP_READONLY` and every write tool is removed
  at startup, leaving the read-only surface. Use it whenever you point the agent at
  content you do not fully trust.
- **Reads from your own install; transmits nothing.** The catalog and per-model
  definitions are read at runtime from *your own* installed Helix Stadium
  (`HELIX_STADIUM_RES`, or platform auto-detect). The server runs over stdio, opens
  no listening socket, and sends nothing about your install anywhere.

### What it does not protect against

- **Prompt injection into a write tool.** An AI agent can be manipulated by untrusted
  content — for example, instructions hidden in a preset name, a file path, or the
  fields of a `.hsp` you ask it to read — into taking an unintended action. With write
  tools enabled, a compromised agent could be steered into editing or overwriting a
  preset. `safe_write` guarantees the result is structurally valid and keeps a `.bak`
  of what it replaced, but it cannot tell a malicious-but-valid edit from one you
  wanted. When you point the agent at presets you do not trust, set
  `HELIX_MCP_READONLY` to remove the write tools entirely.
- **Local processes / same-user boundary.** The same-user trust boundary means there
  is no privilege barrier between "what the agent was told to do" and "what your
  account can do" with the files it can reach.

## Reducing exposure

- **Attach only trusted agents.** Only register this server with MCP clients / agents
  you control.
- **Set `HELIX_MCP_READONLY` for untrusted content.** Pointing the agent at an
  arbitrary downloaded `.hsp` and letting it act on the contents freely is the main
  prompt-injection path; read-only mode removes the write surface for those sessions.
- **Keep your own backups.** `safe_write` writes a `.bak` beside each file it replaces,
  but that is a single-step backup, not version history — keep your own copies of
  presets you care about.

## Supported versions

This project is pre-1.0; security fixes are applied to the latest release on
`main`. Pin a released version if you need stability.

## Reporting a vulnerability

Please report security issues privately to **contact@twelvetake.com** rather than
opening a public issue. Include a description, reproduction steps, and the impact
you observed. We will acknowledge the report and work with you on a fix and
coordinated disclosure.
