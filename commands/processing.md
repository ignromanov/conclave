---
description: >-
  Decides how the current request should be handled — a quick answer, a working session, a
  meeting, or executing an existing plan — binds it to a matching open GitHub issue, and hands
  off to the workflow that fits. Use right after /conclave:start, once the request is known.
---

!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/github-issues-protocol.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/session-lifecycle.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/decision-framework.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/quality-loop.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/advisor-anti-patterns.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/feedback-protocol.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/output-formatting.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/question-shape.md`

# /conclave:processing — Work Routing

> **MANDATORY** for every advisor session after `/conclave:start`. Works independently — no Quorum required.

## Question shape

This skill mostly auto-routes silently. When it CAN'T (ambiguous mode, borderline tier,
multiple plausible workflows, compaction-vs-continue judgment) it follows the
**prose-context + condensed-Ask** pattern — see `question-shape.md` (auto-imported).
Applies here at Step 0.5, Step 0.7, Mode Detection, and Tier Detection.

## Step 0.5 — Compaction check

Before mode detection, check whether any of these apply to the current state:

- Just completed a research/exploration phase, about to start implementation
- Mode is about to transition (e.g., Quick Answer → Working Session)
- Last task was a failed approach the user explicitly abandoned

→ Announce: "Compacting — <trigger reason>" and invoke `/compact` before proceeding.

If mid-implementation, mid-debug, or mid-edit, SKIP compaction.

## Step 0.7 — Iteration discipline check

After Step 0.5 (compaction) and before GH issue matching, check if the session needs `workflow.iterative-loop` (controller-discipline wrapper for multi-iteration work).

Invoke `workflow.iterative-loop` BEFORE the lifecycle workflow if ANY of:

- Spec file has `## Acceptance criteria` / `## DoD` / explicit AC list
- `plan.md` has ≥2 unchecked tasks
- User message mentions DoD / AC / validation / "make sure all tests pass"
- Subagent dispatch (Atlas/Iris/Shade) expected this session
- Mid-session resume where previous iteration left findings open
- User pressure phrase ("just ship it", "good enough", "user is waiting") detected — invoke DEFENSIVELY

Skip iteration discipline when:
- Quick Answer mode (no DoD)
- Meeting / brainstorming (use those workflows)
- Single Read / grep / one-liner (no validation cycle)

The loop WRAPS the lifecycle workflow — see `workflow.iterative-loop/protocols/08-session-router.md`.

## GH Issue Matching (before mode detection)

Before routing, check if the user's request maps to an existing open GH issue (loaded by `/conclave:start` Step 3).

- **If matched** → bind session to that issue. Reference AI#N / GH#N in all outputs. Set Project Board status → `In Progress`:
  ```bash
  # Set status to In Progress via project item-edit (see github-issues-protocol.md for field IDs)
  gh project item-edit --project-id ${PROJECT_ID} --id ITEM_ID \
    --field-id ${STATUS_FIELD_ID} --single-select-option-id ${IN_PROGRESS_OPTION_ID}
  ```
- **If not matched** → proceed normally. If work produces a new actionable task, recommend creating a GH issue at `/conclave:done`.

## Mode Detection

Analyze user request to determine session mode:

| Mode | Signal | Action |
|------|--------|--------|
| Quick Answer | "what do you think?", opinion question | Answer directly, no workflow |
| Working Session | "let's work on X", task description | Detect type + tier, load skills |
| Meeting | "team meeting", "let's discuss" | Invoke team.quorum |
| Execution | "execute plan", plan.md exists | Load plan, invoke subagent-driven-development |

**Ambiguity escape hatch** — if two modes are equally plausible (e.g., "посмотри спеку и скажи что думаешь" reads as both Quick Answer and Working Session), do NOT silently pick. Invoke **Question shape** (above): prose the signals you saw + cost of misroute, then `AskUserQuestion` with condensed labels. Same rule for borderline Tier (Quick-vs-Feature on a 2-hour task) and ambiguous Task Type (Content-vs-Advisory on copywriting strategy questions).

### Quick Answer Mode

Answer directly. No ceremony. Skip type/tier detection.
If a decision is made during the answer → record in BRIEFING.md.

### Meeting Mode

Invoke `team.quorum`. It handles its own Phase 1-7 protocol.

### Execution Mode

Check for `plan.md` in the relevant spec directory.
- Has unchecked tasks? → invoke `subagent-driven-development`
- All complete? → invoke `workflow.dev-lifecycle` (review + PR phase)

### Working Session Mode

#### Task Type Detection

| Task Type | Signals | Workflow Skill |
|-----------|---------|----------------|
| Development | code, feature, bug, test, refactor | workflow.dev-lifecycle |
| Content | blog, tweet, copy, announcement, docs | workflow.content-pipeline |
| Grant | application, proposal, funding, grant | workflow.grant-pipeline |
| Advisory | strategy, decision, architecture, planning | workflow.advisory-session |
| Review | PR, code review, audit | workflow.pr-review |

#### Tier (carried from team.start)

Tier (Quick / Feature / Epic) was classified by `/conclave:start` Step 2 — **read it, do not
reclassify**. It drives execution depth:

| Tier | Consequence |
|------|-------------|
| Quick | No spec, minimal review |
| Feature | spec.md, standard review |
| Epic | Full spec + plan.md, parallel agents |

If the request visibly outgrew the tier `/conclave:start` picked, surface it via the
Question-shape pattern — don't silently re-tier.

## Skill-Driven Execution

```
Task type detected → workflow skill identified
  └→ Skill installed?
     ├→ YES → Invoke via Skill tool, follow its protocol
     ├→ MAYBE → Search with find-skills
     │   ├→ Found installed → invoke
     │   ├→ Found remote → recommend install to user
     │   └→ Not found → log gap
     └→ NO → work best-effort
        └→ /conclave:done → report gap, recommend writing-skills
```

## Loop Discipline

Producer scripts and consumer scripts compose via cached snapshots; the LLM is the controller.

- **Exit codes**: 0 (cache-hit) · 2 (refreshed) · 3 (stale, refresh failed) · 1 (error).
- **Exit-3 retry**: re-fetch with `--no-cache`; on second 3, defer or escalate per consumer policy.
- **p0 blocking**: any `audit-finding` tagged `priority/p0` blocks progress past the next mutation step. Pass `--ack-finding <id>` to override, or resolve the finding first.

Full grammar + Mermaid flowchart: see `${CLAUDE_PLUGIN_ROOT}/skills/forge-operations/references/loop-discipline.md`.

## Decision Log

When a routing decision is non-obvious, log it:
"Routed to [workflow] because [reason]. Tier: [tier]."
This helps /conclave:done understand what was attempted.

## Routing Result (chat output)

After mode + type + tier detected and skill chain identified, render the routing summary as the ▍-block per `output-formatting.md` (auto-imported). This makes the routing visible and reviewable — not a silent decision.

▍ **{persona-emoji} {advisor} · routing · {date}**
▍
▍ **gh-bind**    AI#{N} · {title-fragment}              ← `none` if unmatched
▍ **mode**       {Quick | Working | Meeting | Execution}
▍ ⚠ **compact**  triggered ({reason})                  ← OMIT if not compacted
▍ ⚠ **iterate**  invoked workflow.iterative-loop ({reason}) ← OMIT if not invoked
▍ **type**       {Development | Content | Grant | Advisory | Review} ← Working only
▍ **tier**       {Quick | Feature | Epic}              ← Working only
▍ **skills**     {chain → comma-separated}
▍
▍ **next →** {first action from chosen workflow}

Quick Answer mode skips `type`/`tier` (no workflow). Meeting / Execution modes render only `mode` + the routing target.
