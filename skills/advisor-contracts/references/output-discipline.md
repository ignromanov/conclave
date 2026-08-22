---
type: contract
name: output-discipline
schema_version: 1.0
applies_to: [all advisor SKILL.md, team.start, team.processing, team.done, team.handoff, team.retro]
stages: [clarify, design, spec, plan, implement, verify, deliver]
tiers: [quick, work]
task_types: [dev, content, research, review, advisory]
binding: required
last_reviewed: "2026-08-21"
---

# Output discipline — one terminal object per run

> **Purpose**: governs *when an advisor may speak and with what authority*.
> `output-formatting.md` governs *how the result renders*. The two are required together and
> must not contradict; if they appear to, this file governs emission and that one governs glyphs.

**The rule.** The channel that proves an agent is alive, the channel that reports what is
happening, and the channel that says what it means are three different channels, and none may
answer another's question.

## R1 — one terminal object per run

A run is bounded by the operator's message. Every run ends in exactly one of:

| Outcome | Carries | State token |
|---|---|---|
| completed | the report | `done` or `done-with-caveats` |
| awaiting_input | a typed question, never prose | `blocked` |
| blocked | a reason and what is needed | `blocked` |
| failed | the report, with failure as its verdict | `failed` |

## R2 — the anti-swallow invariant

`completed` with no report is a violation, not a quiet success. `awaiting_input` with no question
is a violation. **No ending is permitted that carries neither a report nor a question.** This is
what makes silence safe: a run that ends quietly ended in *some* outcome, and two of them are
questions.

## R3 — verbs, not conclusions

Between actions you may emit activity: what you read, ran, wrote, how far along you are.
You may not emit conclusions.

| Permitted | Forbidden |
|---|---|
| `read 4 files · ran tests · 12/40` | `I think the cause is the resolver` |
| `phase 3/7 · scanning the registry` | `this looks like the same bug as #129` |

The distinction is not stylistic. An intermediate conclusion you later abandon still shapes what
the reader believes, and the reader cannot tell a live conclusion from a discarded one.

In the CLI the activity lane is the tool-call chrome the harness already draws. You do not need to
narrate it. Writing it out in prose is duplication, not transparency.

## R4 — the deletion test

Any short thought you emit between actions must survive this: delete every one of them; the final
report must still be complete. If a fact disappears, that note was carrying it — put the fact in
the report.

## R5 — declare micro-notes non-load-bearing

Mark them as skippable. This is not modesty. A summarised reasoning trace is accuracy-neutral but
still inflates the reader's trust with nothing behind it; the declaration is the counterweight.

## R6 — length bound

No human-readable field except the report body exceeds 200 characters. Without this the narration
does not disappear — it migrates into the justification of a decision, and nothing has changed.

## R7 — seven things that may never wait for the report

Emit these the moment they occur. The list is closed; everything else waits.

1. A decision you are not authorised to make.
2. A destructive or irreversible action — **before** it happens.
3. A scope departure — the work is a materially different task than the one asked for.
4. A false premise — the bug does not reproduce, the file does not exist, the requirement
   contradicts itself.
5. A blocking failure you cannot resolve.
6. A long silence — emit activity, never narration.
7. Anything the operator explicitly asked to be told about. A standing instruction outranks this
   contract.

Cases 1-5 end the run under R1. They are not chat messages.

## R8 — a question is a typed action

Interrupt with `AskUserQuestion`. A question in prose is a violation even when it is a good
question: prose cannot be rendered as a question by a UI, and it is indistinguishable from the
narration this contract removes.

## See also

- `output-formatting.md` — the ▍-render grammar and the report's slots
- `.conclave/ops/specs/113-output-discipline-protocol/spec.md` — the measurements behind each rule
