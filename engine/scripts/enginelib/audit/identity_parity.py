"""enginelib/audit/identity_parity.py — one identity, two surfaces, still equal?

An advisor's `description` is written once and projected onto two files: the
agent-def (`.claude/agents/<id>.md`) and the router (`.claude/skills/conclave-<id>/
SKILL.md`). `router.scaffold_router` does that projection — at mint. Its
refuse-to-clobber guard (#58) then makes the only re-projection path *decline to
run* on an enriched wrapper, which is what every hired advisor has. From the first
hand edit onward the two copies are independent files that agree by habit.

`tests/test_description_standard.py` pins this field for everything CODE ships and
records its own blind spot verbatim: advisor routers are instance DATA, "no engine
test can pin them. They are held by the generator instead ... and by `engine
doctor`." Neither holds them after mint. This is the reader that does.

Scope, stated because it is narrower than it looks: this audit compares the two
copies to each other. It has no opinion on whether the description is *true*. The
defect that commissioned it — an agent-def naming a customer segment the operator
had rejected six days earlier — sat identically in both copies, and this audit is
green on it. What it catches is the half-applied repair: the sweep that hit the
agent-def and missed the router, which is this instance's documented recurring
failure.

I/O-free: no print/argparse/sys.exit. Returns Findings for the adapter to format.
"""
from __future__ import annotations

from pathlib import Path

from enginelib import frontmatter
from enginelib.audit import Findings
from enginelib.paths import iter_advisor_skills


def scanned(agents_dir: Path, skills_base: Path) -> list[str]:
    """The advisors this audit can rule on: a router AND an agent-def both present.

    Discovery goes through `iter_advisor_skills`, which resolves both the canonical
    `conclave-<id>` and the legacy `team.<id>` layouts. A second glob written here
    would call a `team.`-prefixed router a phantom — the exact second-copy drift
    `audit/advisor_naming.py` was rewritten to remove.

    A router with no agent-def is excluded rather than reported: `audit
    phantom-skills` owns that finding, and claiming it here would make every
    instance mid-migration read as an identity failure.
    """
    return [
        advisor_id
        for advisor_id, _skill_md in iter_advisor_skills(skills_base)
        if (agents_dir / f"{advisor_id}.md").is_file()
    ]


def run(agents_dir: Path, skills_base: Path) -> Findings:
    """Report every advisor whose two description copies have drifted apart."""
    findings = Findings()
    pairs = {
        advisor_id: skill_md
        for advisor_id, skill_md in iter_advisor_skills(skills_base)
        if (agents_dir / f"{advisor_id}.md").is_file()
    }

    if not pairs:
        # A glob that matches nothing satisfies every comparison below. Saying so
        # with the denominator is the difference between a measured zero and an
        # instrument that never ran.
        findings.warn.append(
            f"scanned 0 advisors under {skills_base} — this audit measured nothing"
        )
        return findings

    for advisor_id, skill_md in pairs.items():
        agent_def = agents_dir / f"{advisor_id}.md"
        # Normalised to str at the boundary: a key-absent None and an empty block
        # are the same finding below, and carrying the Optional past this line only
        # moves the None-check somewhere less obvious.
        left = frontmatter.fm_get_block(agent_def, "description") or ""
        right = frontmatter.fm_get_block(skill_md, "description") or ""

        missing = [
            str(p) for p, v in ((agent_def, left), (skill_md, right)) if not v.strip()
        ]
        if missing:
            findings.crit.append(
                f"{advisor_id}: no description in {', '.join(missing)} — "
                f"an advisor with no identity string routes on its id alone"
            )
            continue

        # Independent block scalars wrap independently; a re-wrap or a trailing
        # newline is not an identity change, and a gate that cried on one would be
        # switched off before it ever caught a real drift.
        if " ".join(left.split()) == " ".join(right.split()):
            continue

        findings.crit.append(
            f"{advisor_id}: description differs between "
            f"{agent_def.parent.name}/{agent_def.name} and "
            f"{skill_md.parent.name}/{skill_md.name} — one surface was edited and the "
            f"other was not. The agent-def is the source (the router derives from it at "
            f"mint); copy that block into the router's frontmatter. Do NOT run "
            f"`scaffold-router --force` to fix this: on an enriched router it re-renders "
            f"the template and drops the body — measured 74 lines to 22 on a real wrapper."
        )

    return findings
