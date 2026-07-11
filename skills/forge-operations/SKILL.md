---
name: forge-operations
description: >-
  Forge's operational library — the hire / evolve / audit / audit-skills / compose-roster
  protocols plus the agent-model references (semver, color palette, commit conventions,
  loop discipline, aspects) and templates copied by the engine scripts. Load on demand when
  executing a Forge protocol; the `/conclave:forge` command routes here and the `forge` agent
  references it. Not a standalone advisor — infrastructure for the meta-role.
---

# forge-operations — Forge's protocol & reference library

This skill is the **content library** behind Forge (the agent-model meta-architect). The router
lives in the `/conclave:forge` command and the persona in the `forge` agent; both load the
protocol/reference/template assets bundled here on demand.

## Layout

- `references/protocols/` — the four protocols Forge routes to: `hire.md`, `evolve.md`,
  `audit.md`, `audit-skills.md`, plus `compose-roster.md` (097 roster bootstrap).
- `references/` — agent-model references: `agent-model-version.md` (semver source of truth),
  `color-palette.md`, `commit-conventions.md`, `quality-checks.md`, `loop-discipline.md`,
  `obsidian-vault-setup.md`, and `aspects/*.md` (composable overlays loaded by Evolve).
- `references/templates/` — boilerplate the engine copies (`advisor create`,
  `register advisor`, `briefing build`, …).
- `memory/personality.md` — Forge's voice schema (identity card).
- `ARCHITECTURE.md` · `CHANGELOG.md` — skill-level architecture + release notes.

## Resolution

Reference assets from a command/agent body with `${CLAUDE_PLUGIN_ROOT}/skills/forge-operations/…`.
Engine scripts live at `engine/scripts/`.
