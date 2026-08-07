"""An advisor id is `<name>-<role>`, and `<role>` comes from a closed C-suite vocabulary.

Executors have carried `exec-<name>-<role>` with a hard gate since #61/#63
(`tests/test_executor_defs.py::test_executor_naming_standard`, exactly 3 segments).
Advisors had no rule at all: three independent call sites each validated against
`^[a-z0-9-]+$`, which accepts `engineering-data` and `growth-monetization` — ids
that look like a name and a role but are two domains with no persona at all. That
is what produced `advisor:engineering` as a GH label and the confusion this rule
exists to end.

A shape-only rule (two segments) would NOT have caught those: `engineering-data`
has two segments. Only a closed role vocabulary separates `vera-cto` from
`engineering-data`, which is why the vocabulary is the load-bearing half.

The boundary between an advisor role and an executor role: an advisor role names a
SEAT ACCOUNTABLE FOR AN OUTCOME the product is judged on; an executor role names a
FUNCTION THAT PRODUCES AN ARTIFACT when dispatched. `eng` fails — nobody holds the
job title "Eng", and its accountability sentence collapses to "produces code",
which is `dev`.
"""
from __future__ import annotations

import pytest

from enginelib.advisors import ADVISOR_ROLES, is_valid_advisor_id, validate_advisor_id

# Reserved by the executor gate; an overlap would make the `exec-` prefix the only
# thing telling the two tiers apart.
EXECUTOR_ROLES = frozenset({"dev", "test", "rank", "research", "critic", "judge"})


# ---------------------------------------------------------------------------
# The vocabulary
# ---------------------------------------------------------------------------

def test_every_role_is_a_bare_lowercase_token():
    """No hyphens: the id is exactly two segments, so a hyphenated role would make
    the split between name and role ambiguous."""
    for role in ADVISOR_ROLES:
        assert role.isascii() and role.islower() and role.isalnum(), role


def test_no_role_collides_with_an_executor_role():
    assert ADVISOR_ROLES & EXECUTOR_ROLES == frozenset()


def test_the_ambiguous_acronyms_are_absent():
    """`cdo` is Data vs Digital with no dominant reading, `cco` has four readings,
    `cso` three. Each is excluded in favour of an unambiguous longer form."""
    for ambiguous in ("cdo", "cco", "cso", "cxo"):
        assert ambiguous not in ADVISOR_ROLES, ambiguous
    assert "cdao" in ADVISOR_ROLES, "the data seat must exist under its unambiguous form"
    assert "ciso" in ADVISOR_ROLES, "the security seat must exist under its unambiguous form"


def test_privacy_and_product_do_not_share_a_slug():
    """`cpo` is triple-booked in the wild (Product / Privacy / People). Product keeps
    the short slug; privacy takes `cdpo`, people takes `chro`."""
    assert "cpo" in ADVISOR_ROLES
    assert "cdpo" in ADVISOR_ROLES
    assert "chro" in ADVISOR_ROLES


# ---------------------------------------------------------------------------
# The validator
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("good", ["sage-cto", "vera-cto", "forge-chro", "nexus-ceo", "spark-cmo"])
def test_accepts_a_persona_name_plus_a_vocabulary_role(good):
    validate_advisor_id(good)
    assert is_valid_advisor_id(good)


def test_rejects_an_executor_role_in_the_advisor_slot():
    """`vera-eng` was the operator's drafted target and is REJECTED: `eng` names an
    execution function, not an executive seat."""
    with pytest.raises(ValueError) as exc:
        validate_advisor_id("vera-eng")
    assert "eng" in str(exc.value)


@pytest.mark.parametrize("bad", ["forge", "testx", "advisor", "quorum"])
def test_rejects_a_single_segment_id(bad):
    with pytest.raises(ValueError):
        validate_advisor_id(bad)


@pytest.mark.parametrize("bad", ["engineering-data", "growth-monetization", "privacy-trust"])
def test_rejects_two_domains_masquerading_as_name_and_role(bad):
    """The whole point: these PASS a shape-only two-segment check and must still fail."""
    with pytest.raises(ValueError):
        validate_advisor_id(bad)


def test_rejects_a_hyphenated_persona_name():
    """Exactly two segments, mirroring the executor gate's exactly-three. Allowing
    `mary-jane-cto` here while the executor gate rejects `exec-mary-jane-dev` would
    make two rules that are supposed to mirror each other disagree."""
    with pytest.raises(ValueError):
        validate_advisor_id("mary-jane-cto")


@pytest.mark.parametrize("bad", ["Vera-cto", "vera cto", "vera/cto", "-cto", "vera-", ""])
def test_rejects_malformed_input(bad):
    with pytest.raises(ValueError):
        validate_advisor_id(bad)
    assert not is_valid_advisor_id(bad)


def test_the_error_names_the_allowed_roles():
    """A validator that refuses without saying what would be accepted forces the
    reader into the source."""
    with pytest.raises(ValueError) as exc:
        validate_advisor_id("vera-engineering")
    message = str(exc.value)
    for role in ("cto", "cmo", "ciso"):
        assert role in message, message


# ---------------------------------------------------------------------------
# Enforcement points — the rule holds wherever an id ENTERS the system
# ---------------------------------------------------------------------------

def test_create_refuses_a_non_conforming_id(tmp_path):
    from tests.cmd.helpers import run_engine

    r = run_engine(
        "advisor", "create", "--id", "vera-eng", "--role", "Engineering", "--color", "blue",
        env={"CONCLAVE_AI_ROOT": str(tmp_path), "CONCLAVE_RUN_LOG_DIR": f"{tmp_path}-rl"},
    )
    assert r.returncode == 1, r.stdout
    assert "cto" in r.stderr, r.stderr
    assert not (tmp_path / ".claude" / "agents" / "vera-eng.md").exists()


def test_create_accepts_a_conforming_id(tmp_path):
    from tests.cmd.helpers import run_engine

    r = run_engine(
        "advisor", "create", "--id", "vera-cto", "--role", "Engineering", "--color", "blue",
        env={"CONCLAVE_AI_ROOT": str(tmp_path), "CONCLAVE_RUN_LOG_DIR": f"{tmp_path}-rl"},
    )
    assert r.returncode == 0, r.stderr
    assert (tmp_path / ".claude" / "agents" / "vera-cto.md").is_file()


def test_rename_refuses_a_non_conforming_target(tmp_path):
    """The rename command is the other door an id walks through."""
    from tests.cmd.helpers import run_engine

    agents = tmp_path / ".claude" / "agents"
    agents.mkdir(parents=True)
    (agents / "sage-cto.md").write_text("---\nname: sage-cto\n---\n", encoding="utf-8")

    r = run_engine(
        "advisor", "rename", "--from", "sage-cto", "--to", "vera-eng",
        env={"CONCLAVE_AI_ROOT": str(tmp_path), "CONCLAVE_RUN_LOG_DIR": f"{tmp_path}-rl"},
    )
    assert r.returncode == 1, r.stdout
    assert "cto" in r.stderr, r.stderr


def test_scaffold_router_refuses_a_non_conforming_id(tmp_path):
    from enginelib import router

    with pytest.raises(ValueError):
        router.scaffold_router("forge", skills_root=tmp_path)


def test_every_shipped_advisor_agent_def_conforms():
    """The twin of tests/test_executor_defs.py::test_executor_naming_standard.

    Executors have had this gate since #61/#63; advisors had none, which is how
    single-segment and two-domain ids reached the shipped plugin at all.
    """
    from pathlib import Path

    # engine/scripts/tests/test_advisor_naming_standard.py → parents[3] = repo root
    agents = Path(__file__).resolve().parents[3] / "agents"
    assert agents.is_dir(), agents
    offenders = [
        md.stem
        for md in sorted(agents.glob("*.md"))
        if not md.stem.startswith("exec-") and not is_valid_advisor_id(md.stem)
    ]
    assert not offenders, (
        f"shipped agent-defs violate <name>-<role>: {offenders}. "
        f"Allowed roles: {', '.join(sorted(ADVISOR_ROLES))}"
    )
