---
contract: quality-loop
version: 1.0.0
appliers: [all advisors via lifecycle skills]
propagation: hire-template
source: c-level-advisor skill (inspiration)
---

# Internal Quality Loop

Every advisor runs this loop internally before delivering a non-trivial answer
(strategic recommendation, plan, written artifact, decision).

## Stages

1. **Self-verify** — does the answer match the question? Any unstated assumptions?
2. **Peer-verify** (internal simulation) — "how would <peer advisor> critique this?"
3. **Critic pre-screen** — list top 2 objections a skeptical reader would raise; address or acknowledge.
4. **Present** — deliver answer with the critical pre-screen output visible or implicit.

## Skip when

- Factual lookup / status / simple clarification.
- Conversational exchange (not producing an artifact).

## Hooks into lifecycle

- `team.processing` selects the loop depth (lite for quick answers, full for artifacts).
- `team.done` records if the loop was skipped and why (`reason: factual lookup`).

## Overlay hooks

- Roles may redefine Stage 2 peer (e.g., Kai peers with Shade on security topics).
- Roles may shorten to 3 stages for specific task types (e.g., Dev skips Stage 2 for trivial edits).
