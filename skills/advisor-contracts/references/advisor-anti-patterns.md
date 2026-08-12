---
contract: advisor-anti-patterns
version: 1.0.0
appliers: [all advisors]
propagation: hire-template
stages: [implement, verify, deliver]
tiers: [quick, work]
task_types: [dev, content, research, review, advisory]
binding: required
last_reviewed: "2026-08-12"
---

# Shared advisor anti-patterns

Role-agnostic anti-patterns every advisor avoids. Per-role anti-patterns go in
the advisor's `personality.md` or SKILL.md, not here.

## Anti-patterns

| # | Pattern | Why it's bad |
|---|---------|--------------|
| 1 | Starting work without loading relevant skill | Violates Skill-First Protocol |
| 2 | Skipping `/conclave:done` at session end | GH Issues drift; lost decisions |
| 3 | Narrative handoff ("we discussed ...") | Use `/conclave:handoff` structured format |
| 4 | Inventing facts / metrics | Breaks trust; pollutes BRIEFING |
| 5 | Committing to one repo when both changed | main-repo / ai-repo drift |
| 6 | Editing code without user request | Out of advisory scope |
| 7 | Bypassing quality-loop for artifacts | Lowers output quality; erodes critic pre-screen habit |
| 8 | Cross-advisor editing without /conclave:forge | Creates model drift Audit will flag |

## Enforcement

- Visible via `team.done` checklist (items 1-3, 5).
- Audited by [`protocols/audit.md`](../protocols/audit.md) (items 8 + model-version drift).
- Self-enforced by advisor via quality-loop (items 4, 6, 7).
