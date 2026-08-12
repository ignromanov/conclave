---
stages: [implement, verify]
tiers: [work]
task_types: [advisory]
binding: required
last_reviewed: "2026-08-12"
---

# Aspect: Lifecycle Skill

Modify `team.start/`, `team.done/`, `team.handoff/`, or `team.processing/` skills.

## Blast radius

These skills define the **contract** every advisor session depends on. Changes propagate to all 7 advisors immediately.

## Required checks

Before committing:
1. Read the current skill file end-to-end
2. Run one advisor's `/conclave:start → session → /conclave:done` cycle as smoke test in a scratch branch
3. Confirm the session produces expected artifacts in `.ai/agent-memory/advisors/`
4. Confirm no regressions in `register-advisor.sh` output

## Commit convention

`feat(lifecycle): <skill> <change>` or `fix(lifecycle): <skill> <bugfix>`
