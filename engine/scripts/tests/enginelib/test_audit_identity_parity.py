"""An advisor's identity is one string on two surfaces, and nothing checked it stayed one.

`router.scaffold_router` projects a single `description` onto the agent-def and the
router SKILL.md — at mint, and only at mint. Its refuse-to-clobber guard (#58) then
makes the re-projection path *refuse to run* on exactly the files that can have
drifted: an enriched wrapper is skipped unless `force=True`. So after hire the two
copies are independent, hand-edited, and equal only by luck.

`test_description_standard.py` pins the same field in CODE and says so in its own
scope note: "Advisor routers live in DATA and are instance data; no engine test can
pin them. They are held by the generator instead ... and by `engine doctor`." The
generator half is the half that stops running. This audit is the missing reader.

What it does NOT catch, stated because the distinction cost a session: it does not
know whether a description is *true*. The defect that commissioned it — an agent-def
naming a customer segment an operator decision had rejected — was carried by BOTH
copies identically, and this gate is green on it. It catches the half-applied
repair, which is this project's recurring failure mode (`rename misses off-tree
surfaces`), not the stale claim.
"""
from __future__ import annotations

from pathlib import Path

from enginelib.audit import identity_parity

DESC = (
    "🧭 CEO of one web product — what the engine is for and who it is for. Use when "
    "asking whether something should be built at all."
)


def _instance(tmp_path: Path, advisors: dict[str, tuple[str | None, str | None]]) -> tuple[Path, Path]:
    """Build a throwaway instance: {id: (agent_def_description, skill_description)}.

    `None` on either side means that surface is absent entirely.
    """
    agents = tmp_path / ".claude" / "agents"
    skills = tmp_path / ".claude" / "skills"
    agents.mkdir(parents=True)
    skills.mkdir(parents=True)
    for advisor_id, (agent_desc, skill_desc) in advisors.items():
        if agent_desc is not None:
            (agents / f"{advisor_id}.md").write_text(
                f"---\nname: {advisor_id}\ndescription: |\n  {agent_desc}\ncolor: blue\n---\n\nbody\n",
                encoding="utf-8",
            )
        if skill_desc is not None:
            d = skills / f"conclave-{advisor_id}"
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(
                f"---\nname: conclave-{advisor_id}\ndescription: |\n  {skill_desc}\n---\n\nbody\n",
                encoding="utf-8",
            )
    return agents, skills


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------

def test_matching_descriptions_are_clean(tmp_path: Path):
    agents, skills = _instance(tmp_path, {"helm-ceo": (DESC, DESC)})
    findings = identity_parity.run(agents, skills)
    assert findings.crit == []
    assert findings.warn == []


def test_a_one_sided_edit_is_a_crit(tmp_path: Path):
    """The mutation this gate exists to redden under: the agent-def is repaired and
    the router copy is not. Both files parse, both read plausibly, and every other
    check in the tree stays green."""
    agents, skills = _instance(
        tmp_path, {"helm-ceo": (DESC.replace("one web product", "a solo web product"), DESC)}
    )
    findings = identity_parity.run(agents, skills)
    assert len(findings.crit) == 1, findings
    assert "helm-ceo" in findings.crit[0]
    # The message must name BOTH surfaces — a finding that names one is a finding
    # the reader has to go looking for the other half of.
    assert "agents/helm-ceo.md" in findings.crit[0]
    assert "conclave-helm-ceo/SKILL.md" in findings.crit[0]


def test_the_finding_does_not_prescribe_a_destructive_remedy(tmp_path: Path):
    """`engine advisor scaffold-router --force` is the only engine verb that
    re-projects the description onto the router — and on an enriched wrapper it
    re-renders the template instead, measured at 74 lines down to 22 (§Scope,
    Toolbox and Domain Chains gone). Every hired advisor's router is enriched, so
    the one command that sounds like the fix is data loss in every real case.

    This test exists because the first draft of the message shipped exactly that
    command, and only executing it on a copy caught it."""
    agents, skills = _instance(tmp_path, {"helm-ceo": (DESC, DESC + " drifted")})
    message = identity_parity.run(agents, skills).crit[0]
    assert "--force" not in message.split("Do NOT run")[0], message
    assert "Do NOT run" in message


def test_only_the_drifted_advisor_is_reported(tmp_path: Path):
    agents, skills = _instance(
        tmp_path,
        {
            "helm-ceo": (DESC, DESC + " drifted"),
            "sage-cto": (DESC, DESC),
            "keel-coo": (DESC, DESC),
        },
    )
    findings = identity_parity.run(agents, skills)
    assert len(findings.crit) == 1, findings
    assert "helm-ceo" in findings.crit[0]


def test_whitespace_is_not_drift(tmp_path: Path):
    """The two surfaces wrap their block scalars independently; a trailing newline
    or a re-wrap is not an identity change, and a gate that cried on it would be
    turned off within a week."""
    agents, skills = _instance(tmp_path, {"helm-ceo": (DESC, DESC + "   ")})
    findings = identity_parity.run(agents, skills)
    assert findings.crit == [], findings


# ---------------------------------------------------------------------------
# The two absences, which are different findings
# ---------------------------------------------------------------------------

def test_a_router_without_an_agent_def_is_not_this_audits_finding(tmp_path: Path):
    """`audit phantom-skills` owns that. Reporting it here would make every
    instance mid-migration read as an identity failure."""
    agents, skills = _instance(tmp_path, {"helm-ceo": (None, DESC)})
    findings = identity_parity.run(agents, skills)
    assert findings.crit == []


def test_a_missing_description_is_a_crit(tmp_path: Path):
    """An empty side is not parity — it is the plumbing stub the description
    standard exists to kill, arriving on the surface no CODE test can reach."""
    agents = tmp_path / ".claude" / "agents"
    skills = tmp_path / ".claude" / "skills"
    agents.mkdir(parents=True)
    (agents / "helm-ceo.md").write_text("---\nname: helm-ceo\ncolor: blue\n---\n", encoding="utf-8")
    d = skills / "conclave-helm-ceo"
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(
        f"---\nname: conclave-helm-ceo\ndescription: |\n  {DESC}\n---\n", encoding="utf-8"
    )
    findings = identity_parity.run(agents, skills)
    assert len(findings.crit) == 1, findings
    assert "no description" in findings.crit[0]


# ---------------------------------------------------------------------------
# Vacuity — the failure this file is likeliest to die of
# ---------------------------------------------------------------------------

def test_an_empty_roster_is_a_warning_not_a_pass(tmp_path: Path):
    """A glob that matches nothing satisfies every assertion above. An audit that
    scanned zero advisors reports that it measured nothing, with its denominator —
    it does not print OK."""
    agents, skills = _instance(tmp_path, {})
    findings = identity_parity.run(agents, skills)
    assert findings.crit == []
    assert len(findings.warn) == 1, findings
    assert "0 advisor" in findings.warn[0]


def test_scanned_is_the_discovered_roster_not_a_list(tmp_path: Path):
    agents, skills = _instance(
        tmp_path, {"helm-ceo": (DESC, DESC), "sage-cto": (DESC, DESC)}
    )
    assert identity_parity.scanned(agents, skills) == ["helm-ceo", "sage-cto"]


def test_a_legacy_team_prefixed_router_is_discovered(tmp_path: Path):
    """Resolution goes through `iter_advisor_skills`, which knows both layouts.
    A second glob written here would judge `team.<id>` a phantom — the exact
    second-copy drift `audit/advisor_naming.py` documents."""
    agents, skills = _instance(tmp_path, {"helm-ceo": (DESC, None)})
    legacy = skills / "team.helm-ceo"
    legacy.mkdir(parents=True)
    (legacy / "SKILL.md").write_text(
        f"---\nname: team.helm-ceo\ndescription: |\n  {DESC} drifted\n---\n", encoding="utf-8"
    )
    findings = identity_parity.run(agents, skills)
    assert len(findings.crit) == 1, findings
    assert "helm-ceo" in findings.crit[0]
