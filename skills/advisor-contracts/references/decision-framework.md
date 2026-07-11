---
contract: decision-framework
version: 1.0.0
appliers: [team.processing]
propagation: hire-template
---

# Decision Framework

Default flow for any advisory decision an advisor helps the user reach.

## Five beats

1. **Context** — what is the situation? Constraints? Stakeholders?
2. **Options** — enumerate 2-4 viable approaches. No straw-men.
3. **Trade-offs** — for each option: pros / cons / cost / reversibility.
4. **Recommendation** — pick one; justify in ≤ 3 sentences.
5. **Next step** — smallest concrete action user can take in ≤ 24h.

## Use when

- User asks "what should we do about X?"
- Advisory session (tier: 1:1) with an open question.
- Before writing a roadmap, plan, or strategy doc.

## Skip when

- User asks a factual lookup ("what is …?").
- User executes a decided plan (use lifecycle, not this framework).

## Overlay hooks

- `replacement` — role may redefine the 5 beats (e.g., CFO uses 4 beats with explicit $ impact).
- `extension` — role may add a beat (e.g., Shade adds "Threat model" between Trade-offs and Recommendation).
