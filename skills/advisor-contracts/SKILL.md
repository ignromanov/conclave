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
[`references/`](references/) and are imported verbatim at session start by `/conclave:start`
(`${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/*.md`) and read by the engine's
`session_init` overlay scan. This SKILL.md is the discovery entry point; the references are the
authoritative content.

| Reference | Governs |
|-----------|---------|
| `session-lifecycle.md` | the mandatory start → processing → done lifecycle |
| `agent-data-policy.md` | CODE vs DATA boundary, where an advisor may write |
| `github-issues-protocol.md` | GitHub Issues as source of truth |
| `decision-framework.md` | confidence-graduated authority |
| `quality-loop.md` | the per-task quality gate |
| `feedback-protocol.md` | how advisors emit feedback into the notebook |
| `output-formatting.md` | the ▍-framed output instantiation |
| `question-shape.md` | the prose-context + condensed-Ask pattern |
| `advisor-anti-patterns.md` | failure modes to avoid |
| `first-launch-protocol.md` | first-session bootstrap |
| `persona-voice.md` | the 4-axis persona identity |
| `executor-protocol.md` | how advisors dispatch `exec.*` executors |
| `autonomous-pipeline.md` | the 089 oracle/verifier signal flow |
| `spawned-advisor-brief.md` | brief shape for spawned advisor subagents |
| `spec-051-invariants.md` | memory-architecture invariants |

> Not a standalone advisor — infrastructure shared by the roster.
