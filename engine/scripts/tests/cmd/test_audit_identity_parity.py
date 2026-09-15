"""`engine audit identity-parity` — the CLI contract over the parity check.

The library test (`tests/enginelib/test_audit_identity_parity.py`) pins what counts
as drift. This one pins what the operator sees: the exit code, and the denominator
line printed before the verdict. A clean run over five advisors and a clean run over
an empty skills dir differ by that line alone, and only one of them is evidence.
"""
from __future__ import annotations

from pathlib import Path

from tests.cmd.helpers import run_engine

DESC = "🧭 CEO of one web product. Use when asking whether something should be built."


def _instance(tmp: Path, advisors: dict[str, tuple[str | None, str | None]]) -> Path:
    agents = tmp / ".claude" / "agents"
    skills = tmp / ".claude" / "skills"
    agents.mkdir(parents=True, exist_ok=True)
    skills.mkdir(parents=True, exist_ok=True)
    for advisor_id, (agent_desc, skill_desc) in advisors.items():
        if agent_desc is not None:
            (agents / f"{advisor_id}.md").write_text(
                f"---\nname: {advisor_id}\ndescription: |\n  {agent_desc}\n---\n",
                encoding="utf-8",
            )
        if skill_desc is not None:
            d = skills / f"conclave-{advisor_id}"
            d.mkdir(parents=True, exist_ok=True)
            (d / "SKILL.md").write_text(
                f"---\nname: conclave-{advisor_id}\ndescription: |\n  {skill_desc}\n---\n",
                encoding="utf-8",
            )
    return tmp


def _audit(tmp: Path):
    return run_engine(
        "audit", "identity-parity",
        env={"CONCLAVE_AI_ROOT": str(tmp), "CONCLAVE_RUN_LOG_DIR": f"{tmp}-rl"},
    )


def test_a_roster_in_parity_exits_zero(tmp_path):
    _instance(tmp_path, {"sage-cto": (DESC, DESC), "helm-ceo": (DESC, DESC)})
    r = _audit(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "2 advisor(s): helm-ceo, sage-cto" in r.stdout, r.stdout


def test_drift_exits_one_and_names_the_advisor(tmp_path):
    _instance(tmp_path, {"sage-cto": (DESC, DESC), "helm-ceo": (DESC, DESC + " drifted")})
    r = _audit(tmp_path)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "CRIT: helm-ceo" in r.stdout, r.stdout
    assert "sage-cto:" not in r.stdout.replace("advisor(s): helm-ceo, sage-cto", ""), r.stdout


def test_an_empty_instance_does_not_read_as_a_pass(tmp_path):
    """Exit 2, not 0: nothing was compared. The CLI's 0 is reserved for a roster
    that was actually measured, or a reader cannot tell a clean audit from an
    audit pointed at the wrong directory."""
    _instance(tmp_path, {})
    r = _audit(tmp_path)
    assert r.returncode == 2, r.stdout + r.stderr
    assert "0 advisor(s)" in r.stdout, r.stdout
    assert "measured nothing" in r.stdout, r.stdout
