---
aspect: toolbox
version: 1.0.0
depends_on: [responsibilities]
propagation: hire-template
files:
  - skills/team.<id>/SKILL.md (Required Skills, Chains)
find-pattern: |
  "Required Skills" OR "Chains" OR "Toolbox"
external-skill: find-skills
stages: [design, implement]
tiers: [work]
task_types: [advisory]
binding: required
last_reviewed: "2026-08-12"
---

# Aspect: toolbox

Which skills the advisor uses, daily vs occasional, chain shapes.

## How to mutate
1. Invoke `find-skills` with domain keywords.
2. `engine skill verify <name-1> <name-2> ...` — reject phantoms. One call for the whole
   list: it prints `OK`/`PHANTOM` per name and exits non-zero if any is missing. Called once
   per name instead, the answer is a bare path or nothing — and a call that never ran prints
   nothing too, which is how eleven present skills were reported PHANTOM (#88).
3. Update SKILL.md Required Skills + Chains.
4. Shared briefing (`.ai/agent-memory/advisors/briefings/<id>.md`) regenerates on next `/conclave:start` — no manual edit.

## Sanity
- Toolbox total entries target: 6-12 core + ≤ 6 reference.
- Daily core must include at least one lifecycle skill and one chain entry.
