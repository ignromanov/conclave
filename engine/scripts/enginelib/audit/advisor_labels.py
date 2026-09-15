"""enginelib/audit/advisor_labels.py — the roster and the board's `advisor:*` labels (#111).

`engine advisor rename` classifies every place an id is written down and reports what it
cannot classify, which is its completeness assertion. The assertion holds over the **file
tree**, and a GitHub label is not a file — so a surface that is 100% missed is reported as
0 unclassified and the rename returns clean.

Measured on this instance: PR #95 renamed `forge` → `forge-chro`; twenty hours later the
board still carried `advisor:forge` with 34 open issues, and `briefing build forge-chro`
rendered `_(no open issues for advisor:forge-chro)_`. The query ran, the query was correct,
and the empty result was indistinguishable from "nothing to do".

Two directions, because the drift has two shapes and only one of them is a rename:

  - a roster advisor with no label — its queue reads empty forever;
  - an `advisor:*` label naming nobody in the roster — a queue nobody reads.

Neither is repaired here and nothing is ever removed. A label carrying issues is the only
record that those issues were ever assigned, so the rule against quiet removal binds
hardest exactly where the thing looks like garbage.

**No pseudo-advisor carve-out.** This board carries `advisor:quorum`, which a previous
session called a pseudo-advisor "by design" — but no registry in CODE says so, and a
literal here listing the ids that are allowed to have no advisor would be a second copy of
the roster, which is the defect class this audit belongs to. `quorum` is reported like any
other orphan; its disposition is an operator decision, and a WARN invites one where a
carve-out forecloses it.

I/O-free: the two sets are handed in. The network lives in the CLI adapter, which is also
the only layer that can tell "no disagreement" from "gh never answered" — collapsing those
two into one clean exit is the false-clean this audit exists to prevent.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

from enginelib.advisors import advisor_label
from enginelib.audit import Findings

#: `advisor:` — derived from the one function that builds these labels, never spelled
#: again. A second literal is how the write side came to say `advisor:kai-cto` while two
#: read sides asked for `advisor:kai`, which is the failure this audit reports.
LABEL_PREFIX = advisor_label("")


def advisor_labels(labels: Iterable[str]) -> set[str]:
    """The `advisor:*` subset of a repo's labels."""
    return {name for name in labels if name.startswith(LABEL_PREFIX)}


def run(
    roster: Iterable[str],
    labels: Iterable[str],
    *,
    issue_counts: Mapping[str, int] | None = None,
    capped: bool = False,
    repo: str = "<repo>",
) -> Findings:
    """Compare the roster against the board's advisor labels, both directions.

    `issue_counts` maps a label to its open-issue count, counted client-side by the
    caller. It is context on the orphan finding, never a condition for it: for ~60s
    after a `gh label edit`, GitHub's search index under-reports and a server-side
    count would call a live label empty. `capped` says the caller's page limit was
    reached, so a count is a floor rather than a number.
    """
    findings = Findings()
    roster = sorted(set(roster))
    present = advisor_labels(labels)

    if not roster:
        # A comparison against an empty roster is satisfied by every label set. Saying so
        # with the denominator is the difference between a measured zero and an instrument
        # that never ran.
        findings.warn.append(
            "scanned 0 advisors — this audit measured nothing")
        return findings

    for advisor in roster:
        label = advisor_label(advisor)
        if label not in present:
            findings.warn.append(
                f"advisor {advisor} has no label on {repo} — its queue reads empty in "
                f"every briefing; `gh label create {label} -R {repo}`"
            )

    expected = {advisor_label(a) for a in roster}
    for label in sorted(present - expected):
        count = (issue_counts or {}).get(label, 0)
        floor = "≥" if capped else ""
        findings.warn.append(
            f"label {label} on {repo} names no advisor in this roster, and carries "
            f"{floor}{count} open issue(s) — nothing reads that queue. Rename it onto a "
            f"live advisor (`gh label edit {label} --name {LABEL_PREFIX}<id> -R {repo}`) "
            f"or decide it deliberately; this audit never deletes a label."
        )

    return findings
