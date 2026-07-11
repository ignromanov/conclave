"""conftest.py — shared pytest fixtures for the briefing test suite.

Provides the hermetic kai_cto_tmp_root fixture used by test_backfill_cli.py
so briefing_main(["kai-cto"]) never writes to the live agent-memory/ tree.

Path note: scripts/lifecycle/ (Phase-4, spec 085) is added to sys.path so
test_session_init, test_gh_board_query, and test_study_phase can import their
modules directly without installation.

Determinism contract:
  - CODE source (briefing.md template, personality.md) is anchored on
    engine_root() / templates_dir() — __file__-relative, never reads from
    a live instance root (D2: instance-agnostic).
  - Mutable agent-memory inputs (decisions, sessions, mentions, gh-cache,
    hot.md, progress-summary.md) are written as SYNTHETIC inline fixtures —
    no live reads, fully reproducible per-commit regardless of agent-memory state.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make scripts/lifecycle/ importable for Phase-4 test modules.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lifecycle"))

import json
import textwrap

import pytest

from briefing.paths import engine_root, templates_dir


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


@pytest.fixture()
def kai_cto_tmp_root(tmp_path: Path) -> Path:
    """A hermetic .ai-like tmp root for briefing_main(["kai-cto"]) tests.

    CODE source (template, personality) — anchored on engine_root(), no live
    instance root is read (D2: instance-agnostic).

    Mutable agent-memory (decisions, sessions, mentions, gh-cache, hot.md,
    progress-summary.md) — written as synthetic inline fixtures, fully
    deterministic across runs.
    """
    advisor = "kai-cto"

    # --- CODE source: anchored on engine_root() ---

    # briefing.md template (engine/skills/team.forge/templates/briefing.md)
    tpl_dst = tmp_path / ".claude" / "skills" / "team.forge" / "templates"
    tpl_dst.mkdir(parents=True, exist_ok=True)
    tpl_src = templates_dir() / "briefing.md"
    if tpl_src.is_file():
        import shutil
        shutil.copy2(tpl_src, tpl_dst / "briefing.md")

    # personality.md (engine/skills/team.<advisor>/memory/personality.md)
    # Always create the directory so _registry_advisors() finds kai-cto.
    pers_dst = tmp_path / ".claude" / "skills" / f"team.{advisor}" / "memory"
    pers_dst.mkdir(parents=True, exist_ok=True)
    pers_src = engine_root() / "skills" / f"team.{advisor}" / "memory" / "personality.md"
    if pers_src.is_file():
        import shutil
        shutil.copy2(pers_src, pers_dst / "personality.md")

    # --- synthetic agent-memory: deterministic across runs ---

    am = tmp_path / "agent-memory"
    am.mkdir(parents=True, exist_ok=True)

    # progress-summary.md — per-instance DATA, synthesized inline
    _write(tmp_path / "progress-summary.md", """\
        # Progress Summary

        **Phase**: P1 (Post-Launch) | **v1.0 DEPLOYED** Mar 28
    """)

    # hot.md — one-liner synthetic
    _write(am / "hot.md", """\
        ## Now

        Spec 084 Phase 2 integration.

        ## Recent decisions

        - codec-compression-strategy: B-iv confirmed.

        ## Watch

        Brotli WASM headroom ~2.4 KB.
    """)

    # briefings output dir (written by the entrypoint)
    (am / "advisors" / "briefings").mkdir(parents=True, exist_ok=True)

    # decisions — 2 synthetic kai-cto files
    dec_dir = am / "advisors" / "decisions"
    dec_dir.mkdir(parents=True, exist_ok=True)
    _write(dec_dir / "2026-05-20-kai-cto-test-decision-a.md", """\
        ---
        type: decision
        status: approved
        owner: kai-cto
        created: 2026-05-20
        confidence: high
        contested: false
        promoted_to: ""
        schema_version: 1
        ---

        Decided to rewrite briefing-build in Python.
    """)
    _write(dec_dir / "2026-05-19-kai-cto-test-decision-b.md", """\
        ---
        type: decision
        status: approved
        owner: kai-cto
        created: 2026-05-19
        confidence: high
        contested: false
        promoted_to: ""
        schema_version: 1
        ---

        Compression strategy B-iv confirmed.
    """)

    # sessions — 1 synthetic kai-cto file
    sess_dir = am / "advisors" / "sessions"
    sess_dir.mkdir(parents=True, exist_ok=True)
    _write(sess_dir / "2026-05-20-kai-cto-test-session.md", """\
        ---
        type: session
        owner: kai-cto
        created: 2026-05-20T10:00:00
        schema_version: 1
        ---

        Phase 2 enrichment scans wired and green.
    """)

    # mentions open — 1 synthetic file
    ment_dir = am / "advisors" / "mentions" / advisor / "open"
    ment_dir.mkdir(parents=True, exist_ok=True)
    _write(ment_dir / "2026-05-20-quorum-to-kai-cto-test-mention.md", """\
        ---
        type: mention
        priority: p1
        from: quorum
        status: open
        created: 2026-05-20T10:00:00
        source_session: test
        target_advisor: kai-cto
        schema_version: 1
        ---

        Review spec 084 Phase 2 plan.
    """)

    # gh-cache — minimal JSON snapshot with 1 issue
    gc_dir = am / "gh-cache"
    gc_dir.mkdir(parents=True, exist_ok=True)
    items = [
        {
            "number": 140,
            "title": "Spec 084 — briefing modernization",
            "labels": [{"name": "agent-infra"}, {"name": "p1"}, {"name": "advisor:kai"}],
            "repository": {"name": "voidpay-ai"},
            "updated_at": "2026-05-20T10:00:00Z",
        }
    ]
    gc_content = f"---\ntype: gh-snapshot\n---\n\n```json\n{json.dumps(items, indent=2)}\n```\n"
    (gc_dir / f"{advisor}.md").write_text(gc_content, encoding="utf-8")

    # ops/ — instance structure marker
    (tmp_path / "ops").mkdir(parents=True, exist_ok=True)

    return tmp_path
