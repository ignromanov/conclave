---
id: d_example_duty
description: >-
  Records the decision behind a non-obvious change. Use when a decision is made, an
  alternative is rejected, or rationale is requested.
goal: Leave a record of why, not only of what.
# mission: m_record_decisions   # what this duty covers; defaults to `id` when omitted
# condition: the change is non-obvious   # prose, evaluated in context — omit for unconditional
context:
  triggers: [decision-made, alternative-rejected, rationale-requested]
---

<!-- KAD scaffold (spec 091 §3). Copy this file to your own duties/ dir and rewrite it.

     `description` is the ONLY part injected at startup, for every agent holding this duty.
     Everything below the frontmatter lazy-loads when a trigger fires. Keep the description
     at 30-80 tokens and shaped as:

         [capabilities]. Use when [trigger A], [trigger B] mentioned.

     The validator flags a description sharing no content words with this body — that check
     exists because the body is what gets edited and the description is what gets forgotten.

     A duty says what it covers. It does NOT say how much force it carries: `type:` is
     rejected here. A self-written duty is advice; only an operator norm in
     `.conclave/roster/norms.yaml` makes one binding. -->

When a decision is made that a later reader could not reconstruct from the diff alone,
record it: what was chosen, what was rejected, and the constraint that decided between
them. A rejected alternative with its reason is worth more than the chosen one, because
the chosen one is already visible in the result.

Keep the record where the decision applies — beside the spec for a design decision, in the
commit body for an implementation one. A record filed somewhere no one reads is not a record.
