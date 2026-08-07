"""tests/cmd/test_cmd_duty.py — integration tests for `engine duty <verb>` (spec 091).

Hermetic: BARE tmp_path as CONCLAVE_AI_ROOT, so projections land in the tmp DATA tree and
never touch the live instance.

The exit-code contract is the house one from cmd/audit.py: 0 clean / 1 error / 2 warning.
"""
from __future__ import annotations

from pathlib import Path

from tests.cmd.helpers import run_engine

# run_engine inherits os.environ, and the SessionStart hook exports CONCLAVE_ENGINE_ROOT —
# which inside a git worktree names the MAIN checkout. These tests exercise THIS branch's
# CLI against THIS branch's shipped roster assets, so the CODE root is pinned explicitly
# rather than inherited. (Same production-follows-config / test-follows-source split the
# enginelib duty tests make.)
_CODE_ROOT = Path(__file__).resolve().parents[4]
_ENGINE_ROOT = str(_CODE_ROOT / "engine")

CLEAN_DUTY = """---
id: d_close_session
description: Files session artifacts before exit. Use when the session ends or handoff is mentioned.
goal: Leave no session unrecorded.
---

At session end, file the decision and session records through the engine CLI before committing.
"""

BROKEN_DUTY = """---
id: d_broken
description: ""
goal: nothing
---

A body with no description to match it.
"""


def _run(*args: str, tmp: Path):
    return run_engine("duty", *args,
                      env={"CONCLAVE_AI_ROOT": str(tmp), "CONCLAVE_ENGINE_ROOT": _ENGINE_ROOT})


def _advisor_duties(tmp: Path, advisor: str = "sage-cto") -> Path:
    """The canonical advisor duties dir. `conclave-` prefix, never `team.` — operator
    decision 2026-07-27; asserted by test_advisor_home_uses_the_conclave_prefix below."""
    d = tmp / ".claude" / "skills" / f"conclave-{advisor}" / "duties"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_validate_is_clean_on_an_empty_instance(tmp_path):
    """A fresh instance has no agent-written norms. Clean, not an error — otherwise every
    consumer's first run reports a problem it did not cause."""
    r = _run("validate", "--advisor", "sage-cto", tmp=tmp_path)
    assert r.returncode == 0, r.stderr


def test_project_writes_computed_duties_for_an_advisor(tmp_path):
    (_advisor_duties(tmp_path) / "d_close_session.md").write_text(CLEAN_DUTY, encoding="utf-8")
    r = _run("project", "--advisor", "sage-cto", tmp=tmp_path)
    assert r.returncode == 0, r.stderr

    out = tmp_path / "agent-memory" / "advisors" / "sage-cto" / "COMPUTED-DUTIES.md"
    assert out.exists(), r.stdout
    text = out.read_text()
    assert "d_close_session: Files session artifacts before exit." in text
    assert "file the decision and session records" not in text, "body leaked into projection"


def test_project_writes_computed_duties_for_an_executor(tmp_path):
    """Executors are the tier 091 exists for — they had no declarable duties at all before
    this. Their home is the bare-slug memory dir (executor-protocol.md), not a skill dir."""
    d = tmp_path / "agent-memory" / "executors" / "iris-test" / "duties"
    d.mkdir(parents=True)
    (d / "d_close_session.md").write_text(CLEAN_DUTY, encoding="utf-8")

    r = _run("project", "--executor", "iris-test", tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    out = tmp_path / "agent-memory" / "executors" / "iris-test" / "COMPUTED-DUTIES.md"
    assert out.exists(), r.stdout
    assert "d_close_session:" in out.read_text()


def test_advisor_home_uses_the_conclave_prefix(tmp_path):
    """Operator decision 2026-07-27: conclave-<id> always, team.<id> never. Pinned here so
    a future resolver change cannot silently reintroduce the second prefix."""
    (_advisor_duties(tmp_path) / "d_close_session.md").write_text(CLEAN_DUTY, encoding="utf-8")
    r = _run("project", "--advisor", "sage-cto", tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    out = tmp_path / "agent-memory" / "advisors" / "sage-cto" / "COMPUTED-DUTIES.md"
    assert "d_close_session:" in out.read_text(), "duties under conclave- were not found"


def test_broken_duty_surfaces_as_a_nonzero_exit(tmp_path):
    (_advisor_duties(tmp_path) / "d_broken.md").write_text(BROKEN_DUTY, encoding="utf-8")
    r = _run("validate", "--advisor", "sage-cto", tmp=tmp_path)
    assert r.returncode == 1, f"expected error exit, got {r.returncode}: {r.stdout}{r.stderr}"
    assert "empty-description" in r.stdout


def test_scaffold_creates_a_duty_that_passes_validation(tmp_path):
    r = _run("scaffold", "--advisor", "sage-cto", "--id", "d_new", tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / ".claude" / "skills" / "conclave-sage-cto" / "duties" / "d_new.md").exists()

    r = _run("validate", "--advisor", "sage-cto", tmp=tmp_path)
    assert r.returncode == 0, f"scaffolded duty does not validate: {r.stdout}"


def test_scaffold_refuses_to_overwrite(tmp_path):
    """A second scaffold must not erase what the agent wrote into the first one — it
    refuses rather than clobbers."""
    _run("scaffold", "--advisor", "sage-cto", "--id", "d_new", tmp=tmp_path)
    target = tmp_path / ".claude" / "skills" / "conclave-sage-cto" / "duties" / "d_new.md"
    target.write_text(CLEAN_DUTY, encoding="utf-8")

    r = _run("scaffold", "--advisor", "sage-cto", "--id", "d_new", tmp=tmp_path)
    assert r.returncode == 1
    assert target.read_text() == CLEAN_DUTY, "existing duty was overwritten"


def test_projection_is_byte_identical_across_runs(tmp_path):
    (_advisor_duties(tmp_path) / "d_close_session.md").write_text(CLEAN_DUTY, encoding="utf-8")
    out = tmp_path / "agent-memory" / "advisors" / "sage-cto" / "COMPUTED-DUTIES.md"
    _run("project", "--advisor", "sage-cto", tmp=tmp_path)
    first = out.read_text()
    _run("project", "--advisor", "sage-cto", tmp=tmp_path)
    assert out.read_text() == first


def test_unknown_verb_is_a_usage_error(tmp_path):
    r = _run("nonesuch", tmp=tmp_path)
    assert r.returncode == 2, "argparse usage errors exit 2 by design (__main__ B4 note)"


# --- §4 ledger + discharge ------------------------------------------------------------

def test_record_appends_a_ledger_entry(tmp_path):
    r = _run("record", "--advisor", "sage-cto", "--duty", "d_x",
             "--session", "s1", "--outcome", "discharged", tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    ledger = tmp_path / "agent-memory" / "advisors" / "sage-cto" / "duty-ledger.yaml"
    assert ledger.exists(), r.stdout
    assert "d_x" in ledger.read_text()


def test_record_rejects_an_outcome_outside_the_vocabulary(tmp_path):
    r = _run("record", "--advisor", "sage-cto", "--duty", "d_x",
             "--session", "s1", "--outcome", "probably-fine", tmp=tmp_path)
    assert r.returncode == 2, "argparse choices rejection is a usage error"


def test_discharge_is_clean_when_nothing_is_owed(tmp_path):
    """Empty base = no obligations in force. A fresh consumer must not be told it is
    delinquent on its first session close."""
    r = _run("discharge", "--advisor", "sage-cto", "--session", "s1", tmp=tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "0 deferred" in r.stdout


def test_discharge_exit_code_is_warning_not_error_when_owed(tmp_path):
    """Exit 2, not 1. An unmet obligation is a state to surface at session end, not a
    broken tool — /conclave:done shows it and the operator decides."""
    import textwrap
    manifest = tmp_path / "m.yaml"
    manifest.write_text(textwrap.dedent("""
        version: 1
        roles:
          - {id: sage-cto, kind: advisor, inherits: ["kind:advisor"]}
        missions:
          - {id: m_session_close, goal: Close the session.}
        norms:
          - {type: obligation, role: sage-cto, mission: m_session_close}
    """).strip(), encoding="utf-8")

    r = _run("discharge", "--advisor", "sage-cto", "--session", "s1",
             "--manifest", str(manifest), tmp=tmp_path)
    assert r.returncode == 2, f"expected warning exit, got {r.returncode}: {r.stdout}"
    assert "DEFERRED: m_session_close" in r.stdout

    _run("record", "--advisor", "sage-cto", "--duty", "m_session_close",
         "--session", "s1", "--outcome", "discharged", tmp=tmp_path)
    r = _run("discharge", "--advisor", "sage-cto", "--session", "s1",
             "--manifest", str(manifest), tmp=tmp_path)
    assert r.returncode == 0, f"recorded discharge did not clear the obligation: {r.stdout}"
