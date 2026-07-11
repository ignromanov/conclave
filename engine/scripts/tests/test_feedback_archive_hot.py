"""tests/test_feedback_archive_hot.py — #49(b) regression.

feedback_archive appended the RESOLVED finding via a raw hot.open("a"), dumping
lines below "## Last updated" and — worse — leaving a skeleton-less hot.md when
none existed. The next section-aware write (`engine file decision` → hot.append)
then crashed "section header not found: ## Recent decisions", breaking a real
First Launch. Archive must route through the section-aware writer + seed a
skeleton, so a subsequent hot.append never crashes.
"""
from __future__ import annotations

import feedback.feedback_archive as fa
from enginelib.memory import hot


def _write_resolved_review(fb_root, fid="fb-test-000000"):
    d = fb_root / "2026-07-06"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{fid}.md").write_text(
        "---\n"
        f"feedback_id: {fid}\n"
        "agent: quorum\n"
        "agent_type: advisor\n"
        "created: 2026-07-06T00:00:00Z\n"
        "summary: test review\n"
        "items:\n"
        "  - id: i1\n"
        "    status: resolved\n"
        "    severity: low\n"
        "    observation: something broke\n"
        "    location:\n"
        "      skill: team.start\n"
        "---\nbody\n",
        encoding="utf-8",
    )


def _hermetic(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.setenv("CONCLAVE_RUN_LOG_DIR", str(tmp_path / "rl"))


def test_archive_seeds_skeleton_and_is_section_aware(tmp_path, monkeypatch):
    _hermetic(tmp_path, monkeypatch)
    # No hot.md exists yet — the crash-prone path.
    _write_resolved_review(tmp_path / "ops" / "feedback")

    rc = fa.main([])
    assert rc == 0

    hot_path = tmp_path / "agent-memory" / "hot.md"
    text = hot_path.read_text(encoding="utf-8")

    # Skeleton seeded: all canonical sections present.
    for header in ("## Now", "## Open threads", "## Recent decisions", "## Watch"):
        assert header in text, f"missing section {header}"

    # Finding landed inside Recent decisions, NOT dumped below Last updated.
    rd_idx = text.index("## Recent decisions")
    lu_idx = text.index("## Last updated")
    finding_idx = text.index("RESOLVED fb-test-000000")
    assert rd_idx < finding_idx < lu_idx, "finding must sit under Recent decisions"

    # The exact crash: a subsequent section-aware append must NOT raise.
    hot.append("recent-decisions", "quorum", "followup line", no_compact=True)
    assert "followup line" in hot_path.read_text(encoding="utf-8")


def test_archive_into_existing_skeleton_is_clean(tmp_path, monkeypatch):
    _hermetic(tmp_path, monkeypatch)
    hot.init()  # pre-seed a well-formed skeleton
    _write_resolved_review(tmp_path / "ops" / "feedback")

    rc = fa.main([])
    assert rc == 0

    text = (tmp_path / "agent-memory" / "hot.md").read_text(encoding="utf-8")
    # Still exactly one of each section (no duplicate skeletons appended).
    assert text.count("## Recent decisions") == 1
    assert "RESOLVED fb-test-000000" in text
