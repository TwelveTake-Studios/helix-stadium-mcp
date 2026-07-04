# Security Policy

## Trust model

Helix Stadium MCP is designed for a **single-user workstation**. It runs with the
same privileges as the user who launches it, and it gives any attached AI agent
the ability to read Line 6 Helix Stadium presets and the model catalog on that
machine. **It is not a sandbox and does not attempt to be one.** Treat installing
it the same way you would treat granting a local automation script access to your
preset files and your Helix Stadium install.

If you need a stronger boundary (multi-tenant, untrusted agents, or untrusted
input), run the server inside an OS-level sandbox / container / dedicated user
account. This project does not provide that isolation itself.

## Threat model

### What it protects

- **No arbitrary-code-execution tool.** Unlike some MCP servers, this one exposes
  **no raw exec / eval escape hatch.** The entire tool surface is a fixed set of
  structured, parameter-validated tools (`read_preset`, `explain_preset`,
  `list_models`, `describe_model`, `search_models`, `validate_preset`,
  `detect_install`). There is no tool that runs attacker-supplied code.
- **Read-only, today.** The v1 surface only *reads*: it parses `.hsp` presets and
  reads the model catalog from your own install. It does not write files, does not
  modify presets, and does not reach the network. It runs over stdio and does not
  open a listening socket.
- **Ships zero Line 6 content.** No catalog, preset, or editor data is bundled or
  redistributed. The catalog is read at runtime from *your own* installed Helix
  Stadium (`HELIX_STADIUM_RES`, or platform auto-detect). Nothing about your
  install is transmitted anywhere.

### What it does not protect against

- **Prompt injection (into a future write tool).** An AI agent can be manipulated
  by untrusted content — for example, instructions hidden in a preset name, a
  file path, or the fields of a `.hsp` you ask it to read — into taking an
  unintended action. Today the blast radius is limited because every tool is
  read-only, so the worst case is disclosing the contents of a preset the agent
  is pointed at. **This changes when preset editing / generation lands** (on the
  roadmap): a compromised agent could then be steered into writing an unwanted
  preset. A planned `HELIX_MCP_READONLY` environment toggle will let you keep the
  server strictly read-only even after write tools exist; use it whenever you
  point the agent at content you do not fully trust.
- **Local processes / same-user boundary.** The same-user trust boundary means
  there is no privilege barrier between "what the agent was told to do" and "what
  your account can do" with the files it can reach.

## Reducing exposure

- **Attach only trusted agents.** Only register this server with MCP clients /
  agents you control.
- **Be deliberate with untrusted presets.** Pointing the agent at an arbitrary
  downloaded `.hsp` and letting it act on the contents freely is the main
  prompt-injection path.
- **Keep write tools gated.** When preset editing lands, set `HELIX_MCP_READONLY`
  (planned) to keep the server read-only unless you explicitly intend to write.

## Supported versions

This project is pre-1.0; security fixes are applied to the latest release on
`main`. Pin a released version if you need stability.

## Reporting a vulnerability

Please report security issues privately to **contact@twelvetake.com** rather than
opening a public issue. Include a description, reproduction steps, and the impact
you observed. We will acknowledge the report and work with you on a fix and
coordinated disclosure.
