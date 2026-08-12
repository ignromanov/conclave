---
aspect: responsibilities
version: 1.0.0
depends_on: [identity]
propagation: hire-template
files:
  - skills/team.<id>/SKILL.md (## Scope, ## Self-Description)
  - .claude/agents/team.<id>.md (description competencies)
find-pattern: |
  "## Scope" OR "## Self-Description" OR "competencies"
stages: [design, implement]
tiers: [work]
task_types: [advisory]
binding: advisory
last_reviewed: "2026-08-12"
---

# Aspect: responsibilities

Competencies, scope boundaries, "can answer / cannot answer" lists.

## Typical mutations
- "Kai больше не отвечает за infra — передаём DevOps Forge"
- "Shade расширить scope до supply-chain security"

## Cross-deps
- Changes to `toolbox` usually imply `responsibilities` update (new skill → new scope).
