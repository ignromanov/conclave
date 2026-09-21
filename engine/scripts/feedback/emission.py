"""The mandatory emission check for `/conclave:done` (spec 086 AC12/G1, GH#310).

Lives in `feedback/` rather than in `enginelib/filing.py`, where it sat as a port of
`emission-gate.sh`. The question it asks — "is there a finished, well-formed review for
this session" — is a feedback-domain question, and answering it needs the `Review` schema.
`feedback/` already imports `enginelib/` in nine places, so the reverse edge would have
closed a cycle; the adapter layer is where cross-package reaching belongs, and
`engine/cmd/{audit,status}.py` already import from `feedback/` exactly that way.

WHAT THIS CANNOT TELL YOU: whether the file it looked for is the file the author wrote.
The path is rebuilt here from `advisor` and `session_id`, while `feedback_emit.py` derives
it by slugifying the session-ref (`/` and `_` become `-`) and appends a six-hex suffix on
collision. A session-ref carrying either shape, or a second emission on one day, produces
a review this gate cannot see — it would then block a correctly finalized session rather
than pass a bad one, so the failure is safe but opaque. Measured on this instance
2026-09-21: 0 of 120 reviews carry a collision suffix and 0 carry an underscore, so the
divergence is latent, not live. Filed separately rather than fixed here, because unifying
the two constructions changes which file the gate reads and that deserves its own change.
"""
from __future__ import annotations

from pathlib import Path

DRAFT_BLOCKER = "still a draft (_draft is not false) — it has not been validated"


def blockers(ai_root, advisor: str, session_id: str, today: str) -> list[str]:
    """Why this session's mandatory emission does not satisfy AC12. Empty list == it does.

    Three conditions, and all three are needed:

    1. the file exists,
    2. `_draft` is false — the flag `--finalize` flips, and
    3. the frontmatter validates against `Review`.

    (2) and (3) are separate on purpose. The issue's own suggested fix reads "make
    `emission_gate()` run `Review.model_validate` rather than `re.search`", and taken
    literally that is a regression: `draft` is an ordinary optional field with a default,
    so an unfinished review validates clean and would close its session. Conversely (2)
    alone is what shipped, and it is why a hand-edited review with two items missing
    `location` closed green and hard-aborted triage for three advisors two days later.

    Returns reasons rather than a bool so the caller can print them. A refusal that does
    not name the field sends the author back to guess, which is the same silence the
    incident produced downstream, moved earlier.
    """
    from briefing.frontmatter_io import read as fm_read
    from feedback.schema import schema_errors

    path = Path(ai_root) / "ops" / "feedback" / today / f"{advisor}-{session_id}.md"
    if not path.is_file():
        return [f"no emission file: {path}"]

    try:
        meta, _body = fm_read(path)
    except Exception as exc:  # noqa: BLE001 — any parse failure is one blocker, reported
        # Unparseable is not "absent" and not "invalid": the indexer records it as SKIP
        # rather than REJECT, and conflating the three is how a reader loses the one
        # distinction that says whether the file can be repaired or must be rewritten.
        return [f"{path.name}: unreadable frontmatter: {exc}"]

    reasons: list[str] = []
    if meta.get("_draft", False) is not False:
        reasons.append(f"{path.name}: {DRAFT_BLOCKER}")
    reasons.extend(f"{path.name}: {err}" for err in schema_errors(meta))
    return reasons
