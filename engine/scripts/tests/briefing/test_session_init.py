"""Tests for lifecycle/session-init.py — session initialization helper."""
from __future__ import annotations

import subprocess
import textwrap
import time
from pathlib import Path

import pytest
import session_init

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def _make_root(tmp_path: Path) -> Path:
    """Scaffold a minimal .ai-like tmp root."""
    (tmp_path / "ops").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    (tmp_path / "agent-memory" / "advisors" / "briefings").mkdir(parents=True, exist_ok=True)
    (tmp_path / "agent-memory" / "advisors" / "sessions").mkdir(parents=True, exist_ok=True)
    (tmp_path / "agent-memory" / "advisors" / "decisions").mkdir(parents=True, exist_ok=True)
    return tmp_path


# ---------------------------------------------------------------------------
# repo_root resolution
# ---------------------------------------------------------------------------

class TestRepoRoot:
    def test_env_override(self, tmp_path, monkeypatch):
        _make_root(tmp_path)
        monkeypatch.setenv("VOIDPAY_AI_ROOT", str(tmp_path))
        result = session_init._repo_root()
        assert result == tmp_path.resolve()

    def test_missing_raises(self, tmp_path, monkeypatch):
        monkeypatch.delenv("VOIDPAY_AI_ROOT", raising=False)
        monkeypatch.setattr(session_init, "__file__", str(tmp_path / "x.py"))
        with pytest.raises(RuntimeError, match="cannot locate .ai root"):
            session_init._repo_root()


# ---------------------------------------------------------------------------
# Step 1b — resume scan
# ---------------------------------------------------------------------------

class TestResumeScan:
    def test_empty_dirs(self, tmp_path):
        root = _make_root(tmp_path)
        items = session_init._step1b_resume_scan("kai-cto", root)
        assert items == []

    def test_finds_spec_resume(self, tmp_path):
        root = _make_root(tmp_path)
        prompt = root / "ops" / "specs" / "085-test" / "resume-prompt.md"
        _write(prompt, "# resume\n")
        items = session_init._step1b_resume_scan("kai-cto", root)
        assert any("spec-resume" in i and "085-test" in i for i in items)

    def test_finds_handoff_for_advisor(self, tmp_path):
        root = _make_root(tmp_path)
        handoffs = root / "ops" / "handoffs"
        handoffs.mkdir(parents=True, exist_ok=True)
        _write(handoffs / "2026-05-22-kai-cto-session.md", "# handoff\n")
        items = session_init._step1b_resume_scan("kai-cto", root)
        assert any("handoff" in i and "kai-cto" in i for i in items)

    def test_skips_other_advisor_handoff(self, tmp_path):
        root = _make_root(tmp_path)
        handoffs = root / "ops" / "handoffs"
        handoffs.mkdir(parents=True, exist_ok=True)
        _write(handoffs / "2026-05-22-nexus-ceo-session.md", "# handoff\n")
        items = session_init._step1b_resume_scan("kai-cto", root)
        assert not any("nexus-ceo" in i for i in items)


# ---------------------------------------------------------------------------
# Step 1c — reflexion extract
# ---------------------------------------------------------------------------

class TestReflexionExtract:
    def test_extracts_reflexion(self, tmp_path):
        f = tmp_path / "session.md"
        _write(f, textwrap.dedent("""\
            ---
            type: session
            owner: kai-cto
            reflexion: "always read briefing before diving into code"
            ---
            body text
        """))
        val = session_init._extract_reflexion(f)
        assert val == "always read briefing before diving into code"

    def test_empty_reflexion_returns_empty(self, tmp_path):
        f = tmp_path / "session.md"
        _write(f, textwrap.dedent("""\
            ---
            type: session
            reflexion: ""
            ---
        """))
        val = session_init._extract_reflexion(f)
        assert val == ""

    def test_dash_reflexion_ignored(self, tmp_path):
        root = _make_root(tmp_path)
        sess = root / "agent-memory" / "advisors" / "sessions"
        _write(sess / "2026-05-22-kai-cto-test.md", textwrap.dedent("""\
            ---
            reflexion: "—"
            ---
        """))
        items = session_init._step1c_reflexion("kai-cto", root)
        assert items == []

    def test_surfaces_non_empty_reflexion(self, tmp_path):
        root = _make_root(tmp_path)
        sess = root / "agent-memory" / "advisors" / "sessions"
        _write(sess / "2026-05-22-kai-cto-test.md", textwrap.dedent("""\
            ---
            reflexion: "check GH cache freshness before gh queries"
            ---
        """))
        items = session_init._step1c_reflexion("kai-cto", root)
        assert len(items) == 1
        assert "check GH cache" in items[0]

    def test_returns_at_most_three(self, tmp_path):
        root = _make_root(tmp_path)
        sess = root / "agent-memory" / "advisors" / "sessions"
        for i in range(5):
            _write(
                sess / f"2026-05-2{i}-kai-cto-sess{i}.md",
                f"---\nreflexion: \"tip {i}\"\n---\n",
            )
        items = session_init._step1c_reflexion("kai-cto", root)
        assert len(items) <= 3


# ---------------------------------------------------------------------------
# Overlay scan
# ---------------------------------------------------------------------------

class TestScanOverlays:
    def test_no_advisor_dir(self, tmp_path):
        root = _make_root(tmp_path)
        overlays = session_init._scan_overlays("kai-cto", root)
        assert overlays == []

    def test_detects_overlay(self, tmp_path, monkeypatch):
        root = _make_root(tmp_path)
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        # D-4 paths: base under skills/advisor-contracts/references/, overlay under agent-memory/
        forge_contracts = root / "skills" / "advisor-contracts" / "references"
        advisor_contracts = root / "agent-memory" / "advisors" / "kai-cto" / "contracts"
        _write(forge_contracts / "session-lifecycle.md", "# base\n")
        _write(advisor_contracts / "session-lifecycle.md", "# overlay\n")
        overlays = session_init._scan_overlays("kai-cto", root)
        assert any("session-lifecycle.md" in o for o in overlays)

    def test_no_overlay_when_file_absent(self, tmp_path, monkeypatch):
        root = _make_root(tmp_path)
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        forge_contracts = root / "skills" / "advisor-contracts" / "references"
        _write(forge_contracts / "session-lifecycle.md", "# base\n")
        # advisor contracts dir exists but doesn't contain the file
        (root / "agent-memory" / "advisors" / "kai-cto" / "contracts").mkdir(parents=True, exist_ok=True)
        overlays = session_init._scan_overlays("kai-cto", root)
        assert overlays == []


# ---------------------------------------------------------------------------
# Advisor discovery (registry-derived, not hardcoded — Forge invariant #7)
# ---------------------------------------------------------------------------

class TestKnownAdvisors:
    def test_discovers_registry_advisors(self, tmp_path):
        root = _make_root(tmp_path)
        # Advisors are now CC-discoverable agents at .claude/agents/<slug>.md (plugin layout)
        for slug in ("privacy-trust", "growth-monetization"):
            _write(root / ".claude" / "agents" / f"{slug}.md", "# advisor\n")
        assert session_init._known_advisors(root) == {"privacy-trust", "growth-monetization"}

    def test_excludes_non_advisor_agents(self, tmp_path):
        """forge and exec-* stems are meta/executor agents — never hired advisors."""
        root = _make_root(tmp_path)
        _write(root / ".claude" / "agents" / "privacy-trust.md", "# advisor\n")
        _write(root / ".claude" / "agents" / "forge.md", "# meta\n")
        _write(root / ".claude" / "agents" / "exec-coder.md", "# exec\n")
        assert session_init._known_advisors(root) == {"privacy-trust"}

    def test_empty_registry_returns_empty(self, tmp_path):
        root = _make_root(tmp_path)
        assert session_init._known_advisors(root) == set()

    def test_conclave_data_root_uses_sibling_agents(self, tmp_path, monkeypatch):
        """Regression (start-firstrun it-2): when root is a `.conclave` DATA root and
        CLAUDE_PROJECT_DIR is unset, minted advisors live in the SIBLING
        root.parent/.claude/agents — not inside .conclave/."""
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        data_root = tmp_path / ".conclave"
        data_root.mkdir()
        _write(tmp_path / ".claude" / "agents" / "privacy-trust.md", "# advisor\n")
        assert session_init._known_advisors(data_root) == {"privacy-trust"}


# ---------------------------------------------------------------------------
# CLI arg validation
# ---------------------------------------------------------------------------

class TestMainArgValidation:
    def test_unknown_advisor_exits_1(self, monkeypatch):
        monkeypatch.setenv("VOIDPAY_AI_ROOT", "/nonexistent")
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", "/nonexistent")
        rc = session_init.main(["--advisor", "unknown-xyz"])
        assert rc == 1

    def test_registry_advisor_not_rejected(self, tmp_path, monkeypatch, capsys):
        """A hired advisor present in the instance registry must pass validation —
        regression for the hardcoded CANONICAL_ADVISORS VoidPay roster."""
        root = _make_root(tmp_path)
        # Plugin layout: advisors are now at .claude/agents/<slug>.md
        _write(root / ".claude" / "agents" / "privacy-trust.md", "# advisor\n")
        monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root))
        # stub heavy post-validation steps — we only assert validation accepts the advisor
        monkeypatch.setattr(session_init, "_step1_load_briefing", lambda a, r: (0, []))
        monkeypatch.setattr(session_init, "_step1b_resume_scan", lambda a, r: [])
        monkeypatch.setattr(session_init, "_step1c_reflexion", lambda a, r: [])
        monkeypatch.setattr(session_init, "_scan_overlays", lambda a, r: [])
        monkeypatch.setattr(session_init, "_step_cadence_guard", lambda: [])
        rc = session_init.main(["--advisor", "privacy-trust"])
        assert rc != 1
        assert "not in instance registry" not in capsys.readouterr().err

    def test_missing_advisor_flag(self):
        with pytest.raises(SystemExit):
            session_init.main([])

    def test_seeds_hot_skeleton_when_missing(self, tmp_path, monkeypatch, capsys):
        """#49b: main() seeds a well-formed hot.md if absent, so the first
        `engine file decision` this session can't crash on a missing section."""
        root = _make_root(tmp_path)
        _write(root / ".claude" / "agents" / "privacy-trust.md", "# advisor\n")
        monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root))
        monkeypatch.setattr(session_init, "_step1_load_briefing", lambda a, r: (0, []))
        monkeypatch.setattr(session_init, "_step1b_resume_scan", lambda a, r: [])
        monkeypatch.setattr(session_init, "_step1c_reflexion", lambda a, r: [])
        monkeypatch.setattr(session_init, "_scan_overlays", lambda a, r: [])
        monkeypatch.setattr(session_init, "_step_cadence_guard", lambda: [])

        hot = root / "agent-memory" / "hot.md"
        assert not hot.is_file()
        session_init.main(["--advisor", "privacy-trust"])
        assert hot.is_file()
        text = hot.read_text(encoding="utf-8")
        for header in ("## Now", "## Recent decisions", "## Watch"):
            assert header in text


# ---------------------------------------------------------------------------
# Resolved-findings surfacing (G2) — must track the #49b bullet format
# ---------------------------------------------------------------------------

class TestLoadResolvedFindings:
    def test_matches_section_aware_bullet_format(self, tmp_path):
        """#49b: archive writes findings as '- [ts] agent: [RESOLVED …] team.<adv>: …'
        bullets — the surfacing reader must match by substring, not startswith."""
        root = _make_root(tmp_path)
        _write(
            root / "agent-memory" / "hot.md",
            "## Recent decisions\n\n"
            "- [2026-07-06T00:00+0000] quorum: [RESOLVED fb-1] team.kai-cto: fixed X (was low)\n"
            "- [2026-07-06T00:00+0000] quorum: [RESOLVED fb-2] team.other: y (was low)\n",
        )
        found = session_init._load_resolved_findings("kai-cto", root)
        assert len(found) == 1
        assert "team.kai-cto" in found[0]

    def test_matches_bare_agent_slug_format(self, tmp_path):
        """feedback_archive writes '] <slug>:' where <slug> is location.skill OR,
        when absent, the bare agent slug. Real hot.md lines are bare ('] forge:'),
        so the surfacing reader must match the bare form too — not only 'team.<adv>'."""
        root = _make_root(tmp_path)
        _write(
            root / "agent-memory" / "hot.md",
            "## Recent decisions\n\n"
            "- [2026-07-06T00:00+0000] forge: [RESOLVED fb-1] forge: fixed X (was low)\n"
            "- [2026-07-06T00:00+0000] quorum: [RESOLVED fb-2] quorum: y (was low)\n",
        )
        found = session_init._load_resolved_findings("forge", root)
        assert len(found) == 1
        assert "] forge:" in found[0]

    def test_absent_hot_returns_empty(self, tmp_path):
        root = _make_root(tmp_path)
        assert session_init._load_resolved_findings("kai-cto", root) == []


# ---------------------------------------------------------------------------
# Step 1 — load_briefing (mocked subprocess)
# ---------------------------------------------------------------------------


def _patch_engine_run(monkeypatch, *, gh_code=0, briefing_code=0, briefing_stdout="", calls=None):
    """Intercept the `python -m engine …` subprocess calls _step1_load_briefing makes.

    gh-fetch → gh_code, briefing build → briefing_code, git-fetch → 0 (hermetic);
    anything else falls through to the real subprocess.run. Replaces the old
    fake-`gh-fetch.sh` mocking after gh-fetch was ported to the engine module.

    briefing_stdout simulates the build's `wrote=`/`unchanged=` line — the build-and-
    compare result _step1_load_briefing branches on (#14).

    Pass a dict as `calls` to also record the kwargs each intercepted call was given,
    keyed by verb — the command-matching predicates then live in exactly one place.
    """
    _real_run = subprocess.run
    codes = {"gh-fetch": gh_code, "git-fetch": 0, "briefing": briefing_code}
    stdouts = {"gh-fetch": "", "git-fetch": "", "briefing": briefing_stdout}

    def _verb(cmd):
        if cmd[1:5] == ["-m", "engine", "lifecycle", "gh-fetch"]:
            return "gh-fetch"
        if cmd[1:5] == ["-m", "engine", "lifecycle", "git-fetch"]:
            return "git-fetch"
        if cmd[1:4] == ["-m", "engine", "briefing"]:
            return "briefing"
        return None

    def _mock_run(cmd, **kwargs):
        verb = _verb(cmd) if isinstance(cmd, list) else None
        if verb is None:
            return _real_run(cmd, **kwargs)
        if calls is not None:
            calls[verb] = kwargs
        return subprocess.CompletedProcess(
            args=cmd, returncode=codes[verb], stdout=stdouts[verb], stderr=""
        )

    monkeypatch.setattr(session_init.subprocess, "run", _mock_run)


class TestGhFetchRemoteCwd:
    """H6 — gh-fetch must never fall back to the ENGINE's own git origin.

    `gh_fetch.resolve_repos()` layers roster → local git remote → refuse. The middle layer runs
    `git remote get-url origin` in `CONCLAVE_GIT_REMOTE_CWD`, defaulting to the child's cwd. That
    cwd was `engine/scripts`, so an instance with a null roster resolved the engine's own repo and
    fetched a stranger's issue board into the advisor briefing. Pin it to the consumer project.
    """

    def _briefing(self, root: Path) -> None:
        path = root / "agent-memory" / "advisors" / "briefings" / "kai-cto.md"
        path.write_text("# briefing\n", encoding="utf-8")

    def test_pins_remote_cwd_to_claude_project_dir(self, tmp_path, monkeypatch):
        root = _make_root(tmp_path / "data")
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
        self._briefing(root)

        calls: dict[str, dict] = {}
        _patch_engine_run(monkeypatch, calls=calls)
        session_init._step1_load_briefing("kai-cto", root)

        env = calls["gh-fetch"].get("env")
        assert env is not None, "gh-fetch spawned with inherited env — remote cwd left unpinned"
        assert env.get("CONCLAVE_GIT_REMOTE_CWD") == str(project)

        git_env = calls["git-fetch"].get("env")
        assert git_env is not None, "git-fetch spawned with inherited env — remote cwd left unpinned"
        assert git_env.get("CONCLAVE_GIT_REMOTE_CWD") == str(project)

    def test_falls_back_to_data_root_parent(self, tmp_path, monkeypatch):
        """No CLAUDE_PROJECT_DIR: a `.conclave` DATA root's project is its parent."""
        project = tmp_path / "project"
        root = _make_root(project / ".conclave")
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
        self._briefing(root)

        calls: dict[str, dict] = {}
        _patch_engine_run(monkeypatch, calls=calls)
        session_init._step1_load_briefing("kai-cto", root)

        assert calls["gh-fetch"]["env"].get("CONCLAVE_GIT_REMOTE_CWD") == str(project)
        assert calls["git-fetch"]["env"].get("CONCLAVE_GIT_REMOTE_CWD") == str(project)

    def test_never_points_at_the_engine_checkout(self, tmp_path, monkeypatch):
        """The regression itself: the pinned dir must not be the engine's own tree."""
        root = _make_root(tmp_path / "data")
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
        self._briefing(root)

        calls: dict[str, dict] = {}
        _patch_engine_run(monkeypatch, calls=calls)
        session_init._step1_load_briefing("kai-cto", root)

        pinned = calls["gh-fetch"]["env"]["CONCLAVE_GIT_REMOTE_CWD"]
        assert pinned != calls["gh-fetch"].get("cwd")

        git_pinned = calls["git-fetch"]["env"]["CONCLAVE_GIT_REMOTE_CWD"]
        assert git_pinned != calls["git-fetch"].get("cwd")

    def test_caller_supplied_value_is_not_overridden(self, tmp_path, monkeypatch):
        """The env var is an existing test/ops seam — pinning must not clobber a deliberate one."""
        root = _make_root(tmp_path / "data")
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "project"))
        monkeypatch.setenv("CONCLAVE_GIT_REMOTE_CWD", str(tmp_path / "explicit"))
        self._briefing(root)

        calls: dict[str, dict] = {}
        _patch_engine_run(monkeypatch, calls=calls)
        session_init._step1_load_briefing("kai-cto", root)

        assert calls["gh-fetch"]["env"]["CONCLAVE_GIT_REMOTE_CWD"] == str(tmp_path / "explicit")
        assert calls["git-fetch"]["env"]["CONCLAVE_GIT_REMOTE_CWD"] == str(tmp_path / "explicit")

    def test_empty_value_is_treated_as_unset(self, tmp_path, monkeypatch):
        """`setdefault` kept an empty string, and `_git_remote_slug` reads empty as unset —
        so `export CONCLAVE_GIT_REMOTE_CWD=` silently restored the leak this pin closes."""
        root = _make_root(tmp_path / "data")
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
        monkeypatch.setenv("CONCLAVE_GIT_REMOTE_CWD", "")
        self._briefing(root)

        calls: dict[str, dict] = {}
        _patch_engine_run(monkeypatch, calls=calls)
        session_init._step1_load_briefing("kai-cto", root)

        assert calls["gh-fetch"]["env"]["CONCLAVE_GIT_REMOTE_CWD"] == str(project)
        assert calls["git-fetch"]["env"]["CONCLAVE_GIT_REMOTE_CWD"] == str(project)

    def test_relative_project_dir_is_resolved_before_the_child_changes_cwd(
        self, tmp_path, monkeypatch
    ):
        """The child runs in engine/scripts, so a relative CLAUDE_PROJECT_DIR must be made
        absolute here — `.` handed over verbatim resolves to the engine checkout."""
        root = _make_root(tmp_path / "data")
        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        monkeypatch.chdir(project)
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", ".")
        monkeypatch.delenv("CONCLAVE_GIT_REMOTE_CWD", raising=False)
        self._briefing(root)

        calls: dict[str, dict] = {}
        _patch_engine_run(monkeypatch, calls=calls)
        session_init._step1_load_briefing("kai-cto", root)

        assert calls["gh-fetch"]["env"]["CONCLAVE_GIT_REMOTE_CWD"] == str(project)
        assert calls["git-fetch"]["env"]["CONCLAVE_GIT_REMOTE_CWD"] == str(project)


class TestStep1LoadBriefing:
    def test_build_unchanged_returns_0(self, tmp_path, monkeypatch):
        """#14: build-and-compare, not mtime — an `unchanged=` build result returns 0
        regardless of how old the briefing file is."""
        root = _make_root(tmp_path)
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        briefing = root / "agent-memory" / "advisors" / "briefings" / "kai-cto.md"
        briefing.write_text("# briefing\n", encoding="utf-8")

        _patch_engine_run(
            monkeypatch, gh_code=0, briefing_stdout=f"[briefing-build] unchanged={briefing}\n"
        )

        code, lines = session_init._step1_load_briefing("kai-cto", root)
        assert code == 0
        assert any("unchanged" in ln for ln in lines)

    def test_gh_refresh_unchanged_briefing_returns_0(self, tmp_path, monkeypatch):
        """Regression (fb-1780512267-6f009e/it-1): a gh cache-refresh (exit 2) on an
        UNCHANGED briefing must still return 0. Exit 2 is reserved for an actual briefing
        regen; leaking gh_code==2 here falsely signals 'briefing regenerated'.
        """
        root = _make_root(tmp_path)
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        briefing = root / "agent-memory" / "advisors" / "briefings" / "kai-cto.md"
        briefing.write_text("# briefing\n", encoding="utf-8")

        _patch_engine_run(
            monkeypatch, gh_code=2, briefing_stdout=f"[briefing-build] unchanged={briefing}\n"
        )

        code, lines = session_init._step1_load_briefing("kai-cto", root)
        assert code == 0, f"unchanged briefing + gh-refresh must return 0, got {code}"
        assert any("unchanged" in ln for ln in lines)
        assert any("briefing-path" in ln for ln in lines)

    def test_content_change_triggers_regen(self, tmp_path, monkeypatch):
        """#14: a `wrote=` build result (real content change) returns 2 — independent
        of the briefing file's age, since mtime is no longer consulted at all."""
        root = _make_root(tmp_path)
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        briefing = root / "agent-memory" / "advisors" / "briefings" / "kai-cto.md"
        briefing.write_text("# old\n", encoding="utf-8")

        _patch_engine_run(
            monkeypatch, gh_code=0, briefing_code=0,
            briefing_stdout=f"[briefing-build] wrote={briefing}\n",
        )

        code, lines = session_init._step1_load_briefing("kai-cto", root)
        assert code == 2
        assert any("regenerated" in ln for ln in lines)

    def test_gh_fetch_failure_returns_3(self, tmp_path, monkeypatch):
        root = _make_root(tmp_path)
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))

        _patch_engine_run(monkeypatch, gh_code=1)

        code, lines = session_init._step1_load_briefing("kai-cto", root)
        assert code == 3
        assert any("FAILED" in ln for ln in lines)


# ---------------------------------------------------------------------------
# Cadence guard (feedback triage check)
# ---------------------------------------------------------------------------

class TestCadenceGuard:
    """Tests for _step_cadence_guard — prints feedback: line when triage is due."""

    def _make_triage_marker(self, root: Path, age_days: float) -> Path:
        """Create last-triage marker with given age in days."""
        import os
        marker = root / "ops" / "feedback" / "_index" / "last-triage"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.touch()
        old_time = time.time() - age_days * 86400
        os.utime(marker, (old_time, old_time))
        return marker

    def _make_feedback_script(self, root: Path, *, triage_due: bool, open_items: int = 5) -> Path:
        """Scaffold a fake feedback_triage.py that prints the expected --check output."""
        scripts = root / "engine" / "scripts"
        feedback_dir = scripts / "feedback"
        feedback_dir.mkdir(parents=True, exist_ok=True)
        due_str = "true" if triage_due else "false"
        script = feedback_dir / "feedback_triage.py"
        script.write_text(
            f"import sys\n"
            f"if '--check' in sys.argv:\n"
            f"    print('triage_due={due_str}')\n"
            f"    print('open_items={open_items}')\n"
            f"    sys.exit(0)\n"
            f"sys.exit(0)\n",
            encoding="utf-8",
        )
        return script

    def test_cadence_due_when_marker_stale(self, tmp_path, monkeypatch):
        """mtime > 7 days → feedback: line printed."""
        root = _make_root(tmp_path)
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        self._make_triage_marker(root, age_days=8)
        self._make_feedback_script(root, triage_due=True, open_items=3)
        lines = session_init._step_cadence_guard()
        assert any("feedback:" in ln for ln in lines)
        assert any("triage due" in ln.lower() for ln in lines)

    def test_cadence_due_when_15_or_more_reviews(self, tmp_path, monkeypatch):
        """≥15 new reviews → feedback: line printed."""
        root = _make_root(tmp_path)
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        self._make_triage_marker(root, age_days=1)  # fresh marker, not stale by time
        self._make_feedback_script(root, triage_due=True, open_items=15)
        lines = session_init._step_cadence_guard()
        assert any("feedback:" in ln for ln in lines)

    def test_no_cadence_line_when_not_due(self, tmp_path, monkeypatch):
        """Fresh marker + few reviews → no feedback: line."""
        root = _make_root(tmp_path)
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        self._make_triage_marker(root, age_days=1)
        self._make_feedback_script(root, triage_due=False, open_items=2)
        lines = session_init._step_cadence_guard()
        assert not any("feedback:" in ln for ln in lines)

    def test_no_marker_means_due(self, tmp_path, monkeypatch):
        """No last-triage marker → triage due."""
        root = _make_root(tmp_path)
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        self._make_feedback_script(root, triage_due=True, open_items=0)
        lines = session_init._step_cadence_guard()
        assert any("feedback:" in ln for ln in lines)

    def test_missing_triage_script_returns_warning(self, tmp_path, monkeypatch):
        """If feedback_triage.py doesn't exist → returns a warning line, does not crash."""
        root = _make_root(tmp_path)
        monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(root / "engine"))
        lines = session_init._step_cadence_guard()
        # Either no feedback: line (silently skipped) OR a warning — must not raise
        assert isinstance(lines, list)


# ---------------------------------------------------------------------------
# render_dashboard — advisor-agnostic string entrypoint
# ---------------------------------------------------------------------------

class TestRenderDashboard:
    def test_empty_data_root_returns_non_crashing_string(self, tmp_path):
        """Empty/uninitialized data root (no advisors) → non-empty, non-crashing string."""
        root = _make_root(tmp_path)
        result = session_init.render_dashboard(root)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_seeded_advisor_appears_in_dashboard(self, tmp_path, monkeypatch):
        """When ≥1 advisor is seeded, their slug appears in the rendered string."""
        root = _make_root(tmp_path)
        _write(root / ".claude" / "agents" / "privacy-trust.md", "# advisor\n")
        monkeypatch.setattr(session_init, "_step1_load_briefing", lambda a, r: (0, []))
        monkeypatch.setattr(session_init, "_step1b_resume_scan", lambda a, r: [])
        monkeypatch.setattr(session_init, "_step1c_reflexion", lambda a, r: [])
        monkeypatch.setattr(session_init, "_scan_overlays", lambda a, r: [])
        monkeypatch.setattr(session_init, "_step_cadence_guard", lambda: [])
        result = session_init.render_dashboard(root)
        assert "privacy-trust" in result

    def test_resolved_findings_and_critical_feedback_appear(self, tmp_path, monkeypatch):
        """_load_resolved_findings and _check_critical_feedback_pending surface in dashboard."""
        root = _make_root(tmp_path)
        _write(root / ".claude" / "agents" / "privacy-trust.md", "# advisor\n")
        monkeypatch.setattr(session_init, "_step1_load_briefing", lambda a, r: (0, []))
        monkeypatch.setattr(session_init, "_step1b_resume_scan", lambda a, r: [])
        monkeypatch.setattr(session_init, "_step1c_reflexion", lambda a, r: [])
        monkeypatch.setattr(session_init, "_scan_overlays", lambda a, r: [])
        monkeypatch.setattr(session_init, "_step_cadence_guard", lambda: [])
        monkeypatch.setattr(
            session_init, "_load_resolved_findings",
            lambda a, r, top_n=3: ["[RESOLVED 2026-01-01] team.privacy-trust: example fix"],
        )
        monkeypatch.setattr(session_init, "_check_critical_feedback_pending", lambda r: 2)
        result = session_init.render_dashboard(root)
        assert "reflexion-resolved: 1" in result
        assert "feedback_critical: 2" in result


# ---------------------------------------------------------------------------
# Forge as META-advisor (spec 099 Task 8 — AC9/AC10/AC11)
# ---------------------------------------------------------------------------

class TestForgeMetaAdvisor:
    def test_meta_advisors_is_forge(self):
        """AC11 anchor: the meta set names forge explicitly."""
        assert "forge" in session_init.META_ADVISORS

    def test_forge_absent_from_dashboard(self, tmp_path):
        """AC10: forge is not auto-enumerated among hired advisors."""
        agents = tmp_path / ".claude" / "agents"
        agents.mkdir(parents=True)
        (agents / "forge.md").write_text("---\nname: forge\n---\n")
        (agents / "iris.md").write_text("---\nname: iris\n---\n")
        assert session_init._known_advisors(tmp_path) == {"iris"}

    def test_forge_admitted_by_main(self, monkeypatch, tmp_path, capsys):
        """AC9: session_init --advisor forge is not rejected by main()."""
        monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
        (tmp_path / "ops").mkdir()
        (tmp_path / ".claude").mkdir()
        monkeypatch.setattr(
            session_init, "_advisor_summary",
            lambda a, r: (0, [f"[session-init] advisor={a}"]),
        )
        rc = session_init.main(["--advisor", "forge"])
        assert rc == 0
        assert "advisor=forge" in capsys.readouterr().out

    def test_gh_fetch_skipped_for_meta(self, monkeypatch, tmp_path):
        """AC9: gh-fetch is skipped for meta-advisors (forge has no domain GH board)."""
        called = {"gh": False}

        def _fake_run(cmd, *a, **k):
            if "gh-fetch.sh" in " ".join(str(c) for c in cmd):
                called["gh"] = True
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
        monkeypatch.setattr(session_init.subprocess, "run", _fake_run)
        code, lines = session_init._step1_load_briefing("forge", tmp_path)
        assert called["gh"] is False
        assert any("gh-fetch: skipped (meta-advisor)" in ln for ln in lines)
