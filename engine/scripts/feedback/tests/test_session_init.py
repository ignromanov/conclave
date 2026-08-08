"""test_session_init.py — TDD tests for P5 additions to lifecycle/session_init.py (audit G2/G6)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from briefing.frontmatter_io import write

SCRIPTS_DIR = Path(__file__).parent.parent.parent  # .../scripts/
LIFECYCLE_SCRIPT = SCRIPTS_DIR / "lifecycle" / "session_init.py"


def _run_init(root: Path, advisor: str = "kai-cto") -> subprocess.CompletedProcess:
    # Seed advisor agent file so the registry gate passes (plugin layout: .claude/agents/<slug>.md)
    agent_file = root / ".claude" / "agents" / f"{advisor}.md"
    agent_file.parent.mkdir(parents=True, exist_ok=True)
    agent_file.write_text(f"# {advisor} stub\n", encoding="utf-8")

    return subprocess.run(
        [sys.executable, str(LIFECYCLE_SCRIPT), "--advisor", advisor],
        capture_output=True,
        text=True,
        env={
            "PYTHONPATH": str(SCRIPTS_DIR),
            "CONCLAVE_AI_ROOT": str(root),
            "CLAUDE_PROJECT_DIR": str(root),
            "PATH": "/usr/bin:/bin",
        },
    )


def _make_hot_md(root: Path, lines: list[str]) -> Path:
    hot = root / "agent-memory" / "hot.md"
    hot.parent.mkdir(parents=True, exist_ok=True)
    hot.write_text("\n".join(lines) + "\n")
    return hot


def _make_feedback_reviews(root: Path, items: list[dict]) -> Path:
    """Seed review files so G6 counts the index the engine builds, not one written behind it.

    session_init runs the cadence guard before the G6 count, and that guard calls
    `feedback_triage.py --check`, whose documented first step is a defensive
    `feedback_index --rebuild`. A hand-written _index/index.jsonl is therefore
    overwritten before G6 ever reads it, so seeding the index directly only worked
    while the guard's subprocess was failing to run at all. Seed the reviews the
    rebuild reads instead — then the test exercises G6 rather than the absence of
    a working subprocess.

    Each dict is one item: {"id", "severity", "status"}.
    """
    review_dir = root / "ops" / "feedback" / "2026-05-22"
    review_dir.mkdir(parents=True, exist_ok=True)
    path = review_dir / "fb-111-aaaaaa.md"
    meta = {
        "feedback_id": "fb-111-aaaaaa",
        "agent": "atlas",
        "agent_type": "executor",
        "session_ref": "test-session",
        "skill_version": "sha256:aabbcc",
        "created": "2026-05-22T10:00:00Z",
        "updated_at": "2026-05-22T10:00:00Z",
        "_draft": False,
        "summary": "test review",
        "below_threshold_count": 0,
        "items": [
            {
                "id": item["id"],
                "category": "script-defect",
                "layer": "skill",
                "location": {"file": f"{item['id']}.sh", "line": 4},
                "observation": "exits with 1 unexpectedly",
                "suggested_fix": "add null guard",
                "severity": item["severity"],
                "frequency": "first-time",
                "evidence": "tool_call:abc123",
                "status": item["status"],
            }
            for item in items
        ],
    }
    write(path, meta, "")
    return path


def _stub_briefing(root: Path, advisor: str) -> None:
    """Create stub files so session_init.py doesn't fail on missing infra."""
    briefing = root / "agent-memory" / "advisors" / "briefings" / f"{advisor}.md"
    briefing.parent.mkdir(parents=True, exist_ok=True)
    briefing.write_text("---\n---\n")


# ---------------------------------------------------------------------------
# P5 tests
# ---------------------------------------------------------------------------

def test_session_init_surfaces_top_3_resolved_findings_for_advisor_domain(tmp_path):
    """session_init prints reflexion-resolved: N + indented lines from hot.md for the advisor."""
    _stub_briefing(tmp_path, "kai-cto")
    _make_hot_md(tmp_path, [
        "[RESOLVED fb-111-aaa] team.kai-cto: missing lock file (was medium)",
        "[RESOLVED fb-222-bbb] team.kai-cto: wrong exit code documented (was low)",
        "[RESOLVED fb-333-ccc] team.kai-cto: SKILL.md path stale (was high)",
        "[RESOLVED fb-444-ddd] team.nexus-ceo: unrelated finding (was low)",
        "some other hot.md line not matching pattern",
    ])

    result = _run_init(tmp_path, advisor="kai-cto")
    # session_init may fail on gh-fetch/briefing-build (infra missing in tmp),
    # but it must still print the resolved findings block before bailing
    combined = result.stdout + result.stderr

    assert "reflexion-resolved:" in combined, (
        f"reflexion-resolved: line not found in output:\n{combined}"
    )
    assert "team.kai-cto" in combined, (
        f"advisor domain lines not surfaced:\n{combined}"
    )
    # Should NOT surface unrelated advisor's finding
    assert "team.nexus-ceo" not in combined, (
        f"unrelated advisor finding must not appear:\n{combined}"
    )


def test_session_init_surfaces_critical_pending_line_every_session(tmp_path):
    """session_init prints feedback_critical: N when critical open items exist in index."""
    _stub_briefing(tmp_path, "kai-cto")
    _make_feedback_reviews(tmp_path, [
        {"id": "it-crit-1", "severity": "critical", "status": "open"},
        {"id": "it-crit-2", "severity": "critical", "status": "open"},
        {"id": "it-low-1", "severity": "low", "status": "open"},
        {"id": "it-crit-3", "severity": "critical", "status": "resolved"},
    ])

    result = _run_init(tmp_path, advisor="kai-cto")
    combined = result.stdout + result.stderr

    assert "feedback_critical:" in combined, (
        f"feedback_critical: line not found in output:\n{combined}"
    )
    assert "2" in combined, (
        f"critical count (2) not shown in output:\n{combined}"
    )
