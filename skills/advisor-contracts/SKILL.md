---
name: advisor-contracts
description: >-
  Internal contract library — NOT auto-activated. The shared behavioral substrate every advisor
  session loads: session lifecycle, agent-data policy, decision framework, quality loop, feedback
  protocol, output formatting, executor protocol, persona voice, and the spec-051 memory invariants
  (full set in the SKILL.md table). Load by path when authoring or auditing advisor behavior;
  `/conclave:start` imports the references directly. Not a standalone advisor — the common contract
  substrate for the roster.
---

# advisor-contracts

The contract substrate shared by every Conclave advisor. The individual contracts live under
[`references/`](references/), are imported verbatim at session start by `/conclave:start`, and
are read by the engine's `session_init` overlay scan. This SKILL.md is the discovery entry point;
the references are the authoritative content.

⚠️ That import is an **explicit per-file list, not a glob**: eight of the ten commands —
`start`, `processing`, `done`, `handoff`, `retro`, `triage`, `feedback`, `forge` — open with their own
``!`cat …/references/<name>.md` `` lines and load only what they name. A reference added to this
directory reaches no session until it is wired into those lists — and five existing ones
(`persona-voice.md`, `executor-protocol.md`, `autonomous-pipeline.md`, `spawned-advisor-brief.md`,
`spec-051-invariants.md`) are in no command's list at all; they are loaded by path when needed.

## `appliers:` — who loads a contract

Every reference declares its scope in frontmatter, and the suite reads it (#268):

```yaml
appliers: [all advisors]                      # policy — binds wherever it is loaded
appliers: [all executors]                     # exec-*.md agent-defs
appliers: [team.start, team.processing]       # these commands must import it
appliers: [all advisors, team.start]          # universal, and start.md must import it
```

Two gates, both directions, in `tests/test_a_contract_declares_who_loads_it.py`:

- a command may import only contracts whose scope covers it;
- a contract naming `team.<cmd>` must actually be imported by `commands/<cmd>.md`.

The field is not new. It shipped under **three** spellings — `appliers:`, `applies_to:` and
`applies-to:`, the last carrying prose where a list belongs — because nothing read any of them:
a grep for all three across `engine/scripts` returned zero production callers and zero tests. In
that state it accumulated a `team.quorum` applier for a command that does not exist, a free-text
`[all advisors via lifecycle skills]`, and disagreements with the import blocks in both
directions. An unread field is not metadata; it is a comment that looks like metadata.

## Absorbed contracts and branch contracts

Most references are **absorbed**: they bind by sitting in the session's context, and no step
names them. That is correct, not a gap — a ceremonial sentence pointing at
`advisor-anti-patterns.md` adds nothing a reader obeys.

A **branch** contract is different: it states what fires it and carries `## Steps` to run, so some
command must evaluate its trigger. Exactly one reference is a branch today —
`first-launch-protocol.md` — and the suite derives that from the document rather than from a
declared field. A branch a command imports and never names is dead prose: that was GH#169, where
every hire between #75 and f56315d skipped First Launch in silence.

| Reference | Governs |
|-----------|---------|
| `session-lifecycle.md` | the mandatory start → processing → done lifecycle |
| `agent-data-policy.md` | CODE vs DATA boundary, where an advisor may write |
| `github-issues-protocol.md` | GitHub Issues as source of truth |
| `decision-framework.md` | confidence-graduated authority |
| `quality-loop.md` | the per-task quality gate |
| `feedback-protocol.md` | how advisors emit feedback into the notebook |
| `output-discipline.md` | when an advisor may speak, and with what authority |
| `output-formatting.md` | the ▍-framed output instantiation |
| `state-report.md` | the inventory surface — what a state answer shows, and in what order |
| `question-shape.md` | the prose-context + condensed-Ask pattern |
| `advisor-anti-patterns.md` | failure modes to avoid |
| `first-launch-protocol.md` | first-session bootstrap |
| `persona-voice.md` | the 4-axis persona identity |
| `executor-protocol.md` | how advisors dispatch `exec.*` executors |
| `autonomous-pipeline.md` | the 089 oracle/verifier signal flow |
| `spawned-advisor-brief.md` | brief shape for spawned advisor subagents |
| `spec-051-invariants.md` | memory-architecture invariants |

> Not a standalone advisor — infrastructure shared by the roster.
