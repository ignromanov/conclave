---
description: |
  DEPRECATED redirect. Superseded by team.forge (spec 049) at the cutover.
  Triggers for "hire", "create advisor", "нанять" route to team.forge / `/conclave:forge`.
---

# team.hire — DEPRECATED

This skill has been replaced by `team.forge`, which unifies Hire / Evolve / Audit.

## Redirect

- **Create advisor** → `team.forge` (routes to `protocols/hire.md`)
- **Upgrade advisor** → `team.forge` (Audit finds gaps, Evolve fixes)
- **Anything else** → `team.forge`

See `${CLAUDE_PLUGIN_ROOT}/skills/forge-operations/SKILL.md`.

## Status

Retained as a redirect tombstone (never-silent-delete). Routes callers to Forge; add no code here.
