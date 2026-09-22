---
type: contract
appliers: [all advisors, team.start, team.processing, team.done, team.handoff, team.retro]
name: output-discipline
schema_version: 1.0
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

**"One object" counts reports, not blocks, and never outcomes.** A run that merged, closed and
reopened three separate things still ends in one report; its verdict slot rules on the run, and
the separable outcomes are rows inside slot 3. The count that matters is how many times the
reader is told "this is the answer" — once. A report whose evidence forces a continuation
section is still one object; two attributed blocks each claiming to conclude the run are two.
(Ruled 2026-09-19 by kosmos-cxo on forge-chro's item 6 — he chose one block and was right.)

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

**Scope**: R3 governs the activity lane *between* actions. The terminal report — and a state
report in particular (`state-report.md`), which is conclusions by design — is R1's terminal
object and outside R3 entirely. R3 never licenses suppressing a conclusion from the report the
operator asked for.

In the CLI the activity lane is the tool-call chrome the harness already draws. You do not need to
narrate it. Writing it out in prose is duplication, not transparency.

**Exposition is not a conclusion.** R3 bars a claim about *this run's outcome* — a finding that
could later be retracted, which the reader cannot tell from a live one. It does not bar a claim
about the *material*: how this codebase is structured, what a primitive does, why an approach has
the shape it has. Such a statement is true independently of how the run ends, so abandoning the
run abandons nothing the reader was told. The test is one question: **could this be retracted by
what the run finds?** Yes → hold it for the report. No → it is exposition, and R3 is silent.

This settles R3 against a harness output style that mandates mid-work explanation (the
`★ Insight` block and its equivalents). The two do not collide: such a block is didactic, about
the code, and carries no verdict on the work. It must still pass R4 — delete every one of them
and the report stays complete — which it does *because* it carries no run-facts. R5 applies
unchanged; a visually distinct frame is how the declaration is made. An advisor that smuggles a
run-conclusion inside such a block has violated R3, not found an exemption from it.
(Ruled 2026-09-19 by kosmos-cxo on forge-chro's item 5 — a standing non-compliance with one of
the two rules in every session, in both directions, for 18 days.)

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
- `state-report.md` — the inventory-surface contract; R1/R7/R8 bind there too, R3 does not
- `.conclave/ops/specs/113-output-discipline-protocol/spec.md` — the measurements behind each rule
