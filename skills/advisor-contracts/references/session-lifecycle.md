---
contract: session-lifecycle
version: 1.0.0
appliers: [team.start, team.processing, team.done, team.handoff]
propagation: hire-template
stages: [clarify, design, implement, verify, deliver]
tiers: [quick, work]
task_types: [dev, content, research, review, advisory]
binding: required
last_reviewed: "2026-08-12"
---

# Session lifecycle (default)

Defines the default flow every advisor session follows. Lifecycle skills
(`team.start`, `team.processing`, `team.done`, `team.handoff`) apply it.
Per-advisor overlays live at `skills/team.<id>/contracts/session-lifecycle.md`.

## Stages

### 1. Start (team.start)
- Load the advisor briefing — `agent-memory/advisors/briefings/<id>.md` (auto-generated,
  read-only) + `hot.md` for cross-agent state. Per spec 051 the briefing is
  script-generated — there is no hand-edited briefing file and no per-topic memory dirs.
- Load product.md, constitution.md references.
- Check GH Issues first (per agent-data-policy + github-issues-protocol).
- Detect resume state / task tier (quick answer / advisory / meeting / execution).

### 2. Processing (team.processing)
- Detect mode.
- Invoke the skill chain already identified at `team.start` (type + tier carried, not redetected).

### 3. During session
- Advisor may edit code and commit **if** user requests AND no overlay forbids it.
- Respect shared quality-loop contract.

### 4. Done (team.done)
- Sync GH Issues (decisions, new actions, closed items).
- File session artifacts via the engine CLI (`python -m engine session close`,
  `python -m engine file decision`, `python -m engine mention create`); the briefing
  regenerates from them on next `/conclave:start` — never hand-edited.
- Two-repo commit where applicable.

### 5. Handoff (team.handoff)
- Only when session is incomplete.
- Structured resume-prompt (never narrative prose).

## Overlay hooks

Overlays may:
- **constrain** a stage ("this advisor never edits code")
- **extend** a stage ("this advisor also scans cross-advisor issues")
- **replace** a stage (rare; marked `type: replacement`)

See `skills/forge-operations/references/aspects/contract-overlays.md` for mechanics.
