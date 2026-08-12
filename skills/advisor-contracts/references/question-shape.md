---
contract: question-shape
version: 1.0.0
appliers: [team.start, team.processing]
propagation: hire-template
stages: [clarify, design]
tiers: [quick, work]
task_types: [dev, content, research, review, advisory]
binding: required
last_reviewed: "2026-08-12"
---

# Question shape — prose-context + condensed-Ask

Whenever a lifecycle skill surfaces a choice to the user (resume-vs-fresh, tier
override, skill-chain pick, mode/scale ambiguity, briefing-conflict resolution),
follow this two-part split:

1. **In chat (prose, before the call)** — describe the full question, *why* it is
   being asked, and what each option means. One short paragraph per option covering:
   what gets locked in, blast radius, reversibility, and any defaults. The user must
   be able to compare options side-by-side without scrolling.
2. **In `AskUserQuestion` (condensed)** — `label` ≤ 5 words, `description` ≤ 1 short
   sentence. The Ask widget shows the *choice*, not the briefing — context lives in
   the prose above.

## Anti-patterns

- Cramming all rationale into option `description` so the user can't compare options
  without expanding each one.
- Calling `AskUserQuestion` with no preceding prose context ("Resume or start new?"
  with nothing to base the pick on).
- Inline-prose option dumps with no `AskUserQuestion` call — the decision becomes
  unstructured chat with no captured selection.

See memory: `feedback_choices_via_ask.md`.
