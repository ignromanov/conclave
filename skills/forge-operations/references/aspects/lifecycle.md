---
aspect: lifecycle
version: 1.0.0
depends_on: [memory-structure]
propagation: hire-template
files:
  - skills/team.start/SKILL.md
  - skills/team.processing/SKILL.md
  - skills/team.done/SKILL.md
  - skills/team.handoff/SKILL.md
  - skills/forge-operations/SKILL.md
  - ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/session-lifecycle.md
find-pattern: |
  "LIFECYCLE_SKILLS" OR "/conclave:start" OR "/conclave:done" OR "/conclave:processing" OR "/conclave:handoff"
stages: [implement]
tiers: [work]
task_types: [advisory]
binding: advisory
last_reviewed: "2026-08-12"
---

# Aspect: lifecycle

Process skills that run at session boundaries.

## Touching this aspect bumps
- protocol version of the edited lifecycle skill
- possibly `references/agent-model-version.md` if the change propagates

## Mutations often
- New stage added (rare).
- Rule inside a stage updated.
- Contract @import added / removed.

## Not an advisor — no identity, no personality.
