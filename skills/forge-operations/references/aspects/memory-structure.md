---
aspect: memory-structure
version: 2.0.0
depends_on: []
propagation: hire-template
files:
  - skills/team.<id>/memory/personality.md (hire-time identity)
  - skills/team.<id>/memory/references/*.md (hire-time domain refs)
  - .ai/agent-memory/advisors/briefings/<id>.md (auto-regenerated, spec 051)
  - .ai/agent-memory/advisors/{sessions,decisions,mentions}/ (script-written)
find-pattern: |
  "memory/personality.md" OR "memory/references/" OR "agent-memory/advisors/"
stages: [implement]
tiers: [work]
task_types: [advisory]
binding: advisory
last_reviewed: "2026-08-12"
---

# Aspect: memory-structure

Spec 051 layout: hire-time memory lives under the advisor skill; session memory lives in shared `agent-memory/advisors/`.

## Per-advisor (hire-time, mutated via `team.forge evolve`)
- `memory/personality.md` — identity prose.
- `memory/references/*.md` — domain reference docs.

## Shared (session-time, script-written only)
- `agent-memory/advisors/briefings/<id>.md` — auto-regenerated on `/conclave:start` via `briefing-build.sh`.
- `agent-memory/advisors/sessions/<date>-<id>-<slug>.md` — filed by `close-session.sh`.
- `agent-memory/advisors/decisions/<date>-<id>-<slug>.md` — filed by `file-decision.sh`.
- `agent-memory/advisors/mentions/<recipient>/{open,archive}/` — managed by `mention.sh` / `resolve-mention.sh`.

## Mutations often triggered by
- New reference domain added to an advisor (create new `memory/references/<domain>.md`).
- Per-advisor `personality.md` rewrite via `team.forge evolve aspect=identity`.

## Cross-deps
- `lifecycle` — `team.start` invokes `briefing-build.sh`; `team.done` invokes `close-session.sh`.

## Deprecated (spec 051, removed 2026-04-24)
- `memory/BRIEFING.md` — replaced by shared briefings.
- `memory/topics/*.md` — split into `memory/personality.md` + `memory/references/*.md`.
