---
contract: advisor-anti-patterns
version: 1.1.0
appliers: [all advisors]
propagation: hire-template
stages: [implement, verify, deliver]
tiers: [quick, work]
task_types: [dev, content, research, review, advisory]
binding: required
last_reviewed: "2026-09-18"
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
| 9 | Asserting absence from a command the harness may have rewritten | The written command is not always the command that ran, so the empty result is evidence about the substitute |

## Enforcement

- Visible via `team.done` checklist (items 1-3, 5).
- Audited by [`protocols/audit.md`](../protocols/audit.md) (items 8 + model-version drift).
- Self-enforced by advisor via quality-loop (items 4, 6, 7).
- Self-enforced by re-running the check unproxied before the claim is written (item 9).

## Item 9 — why an empty result is not a measurement

A `PreToolUse` hook may rewrite a shell command before it runs. Measured on this
harness, the rewrite is **substitution, not filtering**: a different program runs in
place of the one that was written, and it answers a different question.

```
written:  head -5 README.md
ran:      rtk read README.md --max-lines 5

written:  git diff > patch.file
ran:      rtk git diff > patch.file      # a human-readable summary, not a patch
          git apply --check patch.file -> "No valid patches in input"
          ...and the file is 140 bytes, so every "was it written" check passes
```

That last one is the shape to fear. It is not a smaller answer; it is a **confident
wrong one**. A pipeline reading the substitute's output (`git diff … | grep …`) greps a
corpus that never had the lines it is looking for, and reports zero.

Absence is the claim this destroys, because absence has no object to re-read. "No other
caller", "no divergence", "no failing tests", "the work is saved in the patch" — each is
believed precisely because nothing came back.

**The rule.** Anything load-bearing runs unproxied — `/usr/bin/grep`, `/usr/bin/git` —
and an absence claim states which one produced it. A second, independent instrument
(a test, a type-checker, an AST scan) beats a second grep: it fails differently.
