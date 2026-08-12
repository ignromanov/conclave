---
stages: [implement]
tiers: [work]
task_types: [advisory]
binding: required
last_reviewed: "2026-08-12"
---

# Aspect: References

Modify `memory/references/<domain>.md` for an advisor.

## When

- New domain expertise added (e.g., a new grant protocol Nexus should know)
- Existing reference superseded by new info
- Reorganizing reference files

## How

1. Load `templates/reference.md` if creating new
2. Edit file under approval gate (`.claude/` path — security)
3. Verify no facts duplicate `.ai/product.md` / `.ai/architecture/*` / `.ai/progress.md` — if they do, refactor to pointer
4. Commit in `.ai` repo: `docs(advisor-references): <advisor> <domain>`

## Don't

- Don't place dynamic state here (use shared `.ai/agent-memory/advisors/`)
- Don't duplicate product/architecture facts
