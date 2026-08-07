"""tests/cmd/test_advisor_rename.py — integration tests for `engine advisor rename`.

Hermetic: BARE tmp_path with CONCLAVE_AI_ROOT pinned at it, so repo_root() and
project_root() coincide (tmp is not named `.conclave`) and the whole instance —
DATA tree plus `.claude/` config — lives under one root.

The fixture below is a scale model of the real `safe-unfollow` instance measured
in the originating handoff: one file per artifact CLASS, not per artifact, so a
class that the planner forgets fails a test rather than surviving as a count.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.cmd.helpers import run_engine

OLD = "engineering-data"
NEW = "vera-cto"
OTHER = "atlas-cro"


def _w(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _instance(tmp: Path) -> dict[str, Path]:
    """Build a scale model of a real instance. Returns a name → path map."""
    p: dict[str, Path] = {}

    # ---- config: live, rewritten by whole-token replacement -----------------
    p["agent_def"] = _w(
        tmp / ".claude" / "agents" / f"{OLD}.md",
        f"---\nname: {OLD}\ndescription: Engineering advisor.\n---\n\n# {OLD}\n",
    )
    p["other_agent_def"] = _w(
        tmp / ".claude" / "agents" / f"{OTHER}.md",
        f"---\nname: {OTHER}\n---\n",
    )
    p["router"] = _w(
        tmp / ".claude" / "skills" / f"conclave-{OLD}" / "SKILL.md",
        f"---\nname: conclave-{OLD}\n---\n\nSession with {OLD}.\n",
    )
    p["personality"] = _w(
        tmp / ".claude" / "skills" / f"conclave-{OLD}" / "memory" / "personality.md",
        f"# Personality\n\nThe {OLD} advisor speaks forensically.\n",
    )
    p["cross_ref"] = _w(
        tmp / ".claude" / "skills" / f"conclave-{OTHER}" / "SKILL.md",
        f"---\nname: conclave-{OTHER}\n---\n\nEscalate perf questions to {OLD}.\n",
    )
    # Two things inside config that LOOK like the id and are not: the router's
    # provenance block is keyed `<meta-advisor>:` (a schema key), and a slash
    # command is a CODE-side name this rename does not own.
    p["router_meta"] = _w(
        tmp / ".claude" / "skills" / f"conclave-{OTHER}" / "memory" / "personality.md",
        f"---\n{OLD}:\n  model-version: 1.4.0\n  hired-by: {OLD}\n---\n\n"
        f"> Self-chosen identity. Mutated only via `/conclave:{OLD} evolve`.\n",
    )
    p["claude_md"] = _w(
        tmp / ".claude" / "CLAUDE.md",
        f"| `team.{OLD}` | Engineering advisor |\n| `team.{OTHER}` | Growth advisor |\n",
    )
    p["manifest"] = _w(
        tmp / "role-manifest.yaml",
        f"roles:\n  - id: {OLD}\n    seat: engineering\n  - id: {OTHER}\n",
    )
    p["hot"] = _w(
        tmp / "agent-memory" / "hot.md",
        f"- [2026-08-06T21:45-0300] {OLD}: closed session promo-stack-unblock\n",
    )

    # ---- history: path renamed, structural fields rewritten, prose kept -----
    p["session"] = _w(
        tmp / "agent-memory" / "advisors" / "sessions" / f"2026-08-06-{OLD}-neon.md",
        f"---\nadvisor: {OLD}\ndate: 2026-08-06\nslug: neon\n---\n\n"
        f"Back then I was called {OLD} and that is what the record says.\n",
    )
    p["decision"] = _w(
        tmp / "agent-memory" / "advisors" / "decisions" / f"2026-08-06-{OLD}-no-merge.md",
        f"---\nslug: no-merge\ndate: 2026-08-06\nby: {OLD}\nstatus: active\n---\n\nBody.\n",
    )
    p["mention_in"] = _w(
        tmp / "agent-memory" / "advisors" / "mentions" / OLD / "open"
        / f"2026-08-06-1200-{OTHER}-to-{OLD}-hi.md",
        f"---\nid: 2026-08-06-1200-{OTHER}-to-{OLD}-hi\nfrom: {OTHER}\nto: {OLD}\n"
        f"status: open\n---\n\nBody.\n",
    )
    p["mention_out"] = _w(
        tmp / "agent-memory" / "advisors" / "mentions" / OTHER / "open"
        / f"2026-08-06-1200-{OLD}-to-{OTHER}-hi.md",
        f"---\nid: 2026-08-06-1200-{OLD}-to-{OTHER}-hi\nfrom: {OLD}\nto: {OTHER}\n"
        f"status: open\n---\n\nBody.\n",
    )
    p["feedback"] = _w(
        tmp / "ops" / "feedback" / "2026-08-07" / f"{OLD}-2026-08-06-neon.md",
        f"---\nfeedback_id: fb-1\nagent: {OLD}\nagent_type: advisor\n_draft: false\n---\n\nBody.\n",
    )
    p["index"] = _w(
        tmp / "ops" / "feedback" / "_index" / "index.jsonl",
        json.dumps({"feedback_id": "fb-1", "agent": OLD, "item_id": "i1"}) + "\n"
        + json.dumps({"feedback_id": "fb-2", "agent": OTHER, "item_id": "i1"}) + "\n",
    )
    p["ops_decision"] = _w(
        tmp / "ops" / "decisions" / f"2026-08-06-{OLD}-topology.md",
        f"---\nslug: topology\ndate: 2026-08-06\nby: {OLD}\nstatus: active\n---\n\nBody.\n",
    )
    p["handoff"] = _w(
        tmp / "ops" / "handoffs" / f"2026-08-07-{OLD}-rename-command.md",
        f"# Handoff\n\n> **From**: {OLD} | **To**: forge\n",
    )

    # ---- regen: deleted, never rewritten -----------------------------------
    p["briefing"] = _w(
        tmp / "agent-memory" / "advisors" / "briefings" / f"{OLD}.md",
        f"# Briefing for {OLD}\n\nGenerated.\n",
    )
    p["gh_cache"] = _w(
        tmp / "agent-memory" / "gh-cache" / f"{OLD}.md",
        f"advisor: {OLD}\nissues: []\n",
    )

    # ---- protected: dated evidence, never touched --------------------------
    p["archive"] = _w(
        tmp / "ops" / "archive" / "legacy-2026-06-16" / f"team.{OLD}.md",
        f"---\nname: team.{OLD}\n---\n",
    )
    p["proof"] = _w(
        tmp / "ops" / "proof" / f"opening-{OLD}.md",
        f"Opening proof for {OLD}.\n",
    )

    # ---- unclassified: matches the id but belongs to no known class --------
    p["wiki"] = _w(
        tmp / "wiki" / "notes" / f"{OLD}-thoughts.md",
        f"Notes about {OLD}.\n",
    )
    return p


def _rename(*args: str, tmp: Path) -> object:
    # CONCLAVE_RUN_LOG_DIR is pinned OUTSIDE the instance (#53 seam): the run-log
    # otherwise lands in agent-memory/run-log inside the very tree these tests
    # snapshot, and every "nothing was written" assertion would fail on the
    # command's own observability record rather than on a real mutation.
    return run_engine(
        "advisor", "rename", *args,
        env={"CONCLAVE_AI_ROOT": str(tmp), "CONCLAVE_RUN_LOG_DIR": f"{tmp}-runlog"},
    )


def _snapshot(tmp: Path) -> dict[str, str]:
    """Every file under tmp as path → content, for proving nothing moved."""
    return {
        str(f.relative_to(tmp)): f.read_text(encoding="utf-8")
        for f in sorted(tmp.rglob("*"))
        if f.is_file()
    }


# ---------------------------------------------------------------------------
# Guard rails — each refuses BEFORE any mutation (handoff step 3)
# ---------------------------------------------------------------------------

def test_refuses_when_from_is_not_canonical(tmp_path):
    _instance(tmp_path)
    before = _snapshot(tmp_path)
    r = _rename("--from", "nobody-here", "--to", NEW, "--apply", "--confirm", tmp=tmp_path)
    assert r.returncode == 1, r.stdout
    assert "not a canonical advisor" in r.stderr
    assert _snapshot(tmp_path) == before


def test_refuses_when_to_already_exists(tmp_path):
    _instance(tmp_path)
    before = _snapshot(tmp_path)
    r = _rename("--from", OLD, "--to", OTHER, "--apply", "--confirm", tmp=tmp_path)
    assert r.returncode == 2, r.stdout
    assert "already exists" in r.stderr
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("bad", ["Vera", "vera cto", "vera/cto", "", "vera-eng", "forge"])
def test_refuses_invalid_target_slug(tmp_path, bad):
    _instance(tmp_path)
    before = _snapshot(tmp_path)
    r = _rename("--from", OLD, "--to", bad, "--apply", "--confirm", tmp=tmp_path)
    assert r.returncode == 1, r.stdout
    assert "invalid --to" in r.stderr and "cto" in r.stderr
    assert _snapshot(tmp_path) == before


def test_refuses_when_a_planned_move_would_collide(tmp_path):
    """A destination that already holds a file aborts the WHOLE run, mutating nothing."""
    _instance(tmp_path)
    _w(
        tmp_path / ".claude" / "skills" / f"conclave-{NEW}" / "SKILL.md",
        f"---\nname: conclave-{NEW}\n---\n",
    )
    before = _snapshot(tmp_path)
    r = _rename("--from", OLD, "--to", NEW, "--apply", "--confirm", tmp=tmp_path)
    assert r.returncode == 2, r.stdout
    assert "collision" in r.stderr
    assert _snapshot(tmp_path) == before


def test_refuses_when_the_retired_id_is_ambiguous_against_another_roster_id(tmp_path):
    """A token-overlapping pair cannot be told apart inside a dated filename.

    The naming standard makes this unreachable from the `--to` side — every
    conforming id is exactly two segments, so one can only match inside another if
    they are equal. It stays reachable from `--from`, which is exactly where it
    matters: the legacy ids awaiting migration are the ones that never conformed.
    """
    _instance(tmp_path)
    _w(tmp_path / ".claude" / "agents" / "growth.md", "---\nname: growth\n---\n")
    _w(
        tmp_path / ".claude" / "agents" / "growth-monetization.md",
        "---\nname: growth-monetization\n---\n",
    )
    before = _snapshot(tmp_path)
    r = _rename("--from", "growth", "--to", "gala-cro", "--apply", "--confirm", tmp=tmp_path)
    assert r.returncode == 1, r.stdout
    assert "ambiguous" in r.stderr
    assert _snapshot(tmp_path) == before


# ---------------------------------------------------------------------------
# Dry-run — the default, and the only rollback this system has (handoff step 2)
# ---------------------------------------------------------------------------

def test_dry_run_is_the_default_and_writes_nothing(tmp_path):
    _instance(tmp_path)
    before = _snapshot(tmp_path)
    r = _rename("--from", OLD, "--to", NEW, tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    assert _snapshot(tmp_path) == before, "default invocation mutated the tree"


def test_apply_without_confirm_writes_nothing(tmp_path):
    _instance(tmp_path)
    before = _snapshot(tmp_path)
    r = _rename("--from", OLD, "--to", NEW, "--apply", tmp=tmp_path)
    assert r.returncode == 1
    assert "--confirm" in r.stderr
    assert _snapshot(tmp_path) == before


def test_dry_run_plan_names_every_moved_path(tmp_path):
    p = _instance(tmp_path)
    r = _rename("--from", OLD, "--to", NEW, tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    for key in ("agent_def", "router", "session", "decision", "mention_in",
                "mention_out", "feedback", "handoff"):
        rel = str(p[key].relative_to(tmp_path))
        assert rel in r.stdout, f"{key} ({rel}) missing from dry-run plan"


def test_dry_run_plan_names_every_in_file_field_edit(tmp_path):
    _instance(tmp_path)
    r = _rename("--from", OLD, "--to", NEW, tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    for field in ("advisor:", "by:", "from:", "to:", "agent:"):
        assert field in r.stdout, f"field edit {field!r} not itemised in plan"


def test_dry_run_plan_separates_protected_and_unclassified(tmp_path):
    p = _instance(tmp_path)
    r = _rename("--from", OLD, "--to", NEW, tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    assert str(p["archive"].relative_to(tmp_path)) in r.stdout
    assert str(p["proof"].relative_to(tmp_path)) in r.stdout
    assert str(p["wiki"].relative_to(tmp_path)) in r.stdout
    assert "protected" in r.stdout
    assert "unclassified" in r.stdout


# ---------------------------------------------------------------------------
# The four artifact classes (handoff step 4)
# ---------------------------------------------------------------------------

@pytest.fixture
def applied(tmp_path):
    paths = _instance(tmp_path)
    r = _rename("--from", OLD, "--to", NEW, "--apply", "--confirm", tmp=tmp_path)
    assert r.returncode == 0, r.stderr + r.stdout
    return tmp_path, paths, r


def test_config_agent_def_moves_and_rewrites(applied):
    tmp, p, _ = applied
    assert not p["agent_def"].exists()
    moved = tmp / ".claude" / "agents" / f"{NEW}.md"
    assert moved.is_file()
    assert f"name: {NEW}" in moved.read_text()
    assert OLD not in moved.read_text()


def test_config_router_dir_moves_with_its_contents(applied):
    tmp, p, _ = applied
    old_dir = tmp / ".claude" / "skills" / f"conclave-{OLD}"
    new_dir = tmp / ".claude" / "skills" / f"conclave-{NEW}"
    assert not old_dir.exists()
    assert (new_dir / "SKILL.md").is_file()
    assert (new_dir / "memory" / "personality.md").is_file()
    assert f"name: conclave-{NEW}" in (new_dir / "SKILL.md").read_text()
    assert OLD not in (new_dir / "memory" / "personality.md").read_text()


def test_config_cross_references_in_other_advisors_are_rewritten(applied):
    _, p, _ = applied
    body = p["cross_ref"].read_text()
    assert NEW in body
    assert OLD not in body


def test_config_yaml_key_named_like_the_advisor_is_a_schema_key(applied):
    """Every router carries a `forge:` provenance block. `forge` is also an
    advisor id, so the whole-token replace renamed the KEY as well — and
    `engine model bump`, which reads that block by name, would stop finding it.

    A key is a schema word; only the value beside it is an identity."""
    _, p, _ = applied
    body = p["router_meta"].read_text()
    assert f"\n{OLD}:\n" in body, "the provenance key was rewritten"
    assert f"hired-by: {NEW}" in body, "the value beside it was not"


def test_config_slash_command_is_a_code_name(applied):
    """`/conclave:forge` is the shipped meta-skill's command. It lives in CODE
    and keeps its name when the advisor's id moves; rewriting the reference
    points the operator at a command that does not exist."""
    _, p, _ = applied
    assert f"/conclave:{OLD} evolve" in p["router_meta"].read_text()


def test_config_roster_surfaces_are_rewritten(applied):
    _, p, _ = applied
    for key in ("claude_md", "manifest", "hot"):
        body = p[key].read_text()
        assert NEW in body, f"{key} not rewritten"
        assert OLD not in body, f"{key} still names the old id"
    assert OTHER in p["manifest"].read_text(), "unrelated roster id was damaged"


def test_history_session_moves_and_rewrites_only_the_field(applied):
    tmp, p, _ = applied
    assert not p["session"].exists()
    moved = tmp / "agent-memory" / "advisors" / "sessions" / f"2026-08-06-{NEW}-neon.md"
    assert moved.is_file()
    body = moved.read_text()
    assert f"advisor: {NEW}" in body
    assert f"Back then I was called {OLD}" in body, "prose was rewritten — history must stay true"


def test_history_decision_by_field_is_rewritten(applied):
    tmp, p, _ = applied
    moved = tmp / "agent-memory" / "advisors" / "decisions" / f"2026-08-06-{NEW}-no-merge.md"
    assert moved.is_file()
    assert f"by: {NEW}" in moved.read_text()


def test_history_mention_recipient_directory_is_renamed(applied):
    tmp, p, _ = applied
    assert not (tmp / "agent-memory" / "advisors" / "mentions" / OLD).exists()
    moved = (
        tmp / "agent-memory" / "advisors" / "mentions" / NEW / "open"
        / f"2026-08-06-1200-{OTHER}-to-{NEW}-hi.md"
    )
    assert moved.is_file(), "recipient-keyed mention directory not renamed"
    assert f"to: {NEW}" in moved.read_text()
    assert f"from: {OTHER}" in moved.read_text()


def test_history_mention_sender_segment_is_renamed(applied):
    tmp, _, _ = applied
    moved = (
        tmp / "agent-memory" / "advisors" / "mentions" / OTHER / "open"
        / f"2026-08-06-1200-{NEW}-to-{OTHER}-hi.md"
    )
    assert moved.is_file()
    assert f"from: {NEW}" in moved.read_text()


def test_history_feedback_markdown_agent_field_is_rewritten(applied):
    tmp, _, _ = applied
    moved = tmp / "ops" / "feedback" / "2026-08-07" / f"{NEW}-2026-08-06-neon.md"
    assert moved.is_file()
    assert f"agent: {NEW}" in moved.read_text()


def test_history_feedback_jsonl_index_is_rewritten(applied):
    _, p, _ = applied
    rows = [json.loads(ln) for ln in p["index"].read_text().splitlines() if ln.strip()]
    assert [r["agent"] for r in rows] == [NEW, OTHER]


def test_regenerated_artifacts_are_deleted_not_rewritten(applied):
    tmp, p, _ = applied
    assert not p["briefing"].exists()
    assert not p["gh_cache"].exists()
    assert not (tmp / "agent-memory" / "advisors" / "briefings" / f"{NEW}.md").exists(), (
        "a stale briefing was renamed forward instead of being dropped for regeneration"
    )
    assert not (tmp / "agent-memory" / "gh-cache" / f"{NEW}.md").exists()


def test_protected_evidence_is_untouched(applied):
    _, p, _ = applied
    assert p["archive"].is_file()
    assert f"team.{OLD}" in p["archive"].read_text()
    assert p["proof"].is_file()
    assert OLD in p["proof"].read_text()


def test_unclassified_matches_are_reported_but_untouched(applied):
    _, p, _ = applied
    assert p["wiki"].is_file()
    assert OLD in p["wiki"].read_text()


# ---------------------------------------------------------------------------
# Regressions found by running the plan against the real safe-unfollow instance
# ---------------------------------------------------------------------------

def test_the_data_roots_own_claude_md_is_config_not_unclassified(tmp_path):
    """The DATA root carries its OWN `.claude/CLAUDE.md` — the roster table that
    tells the harness which agent to route to. Probing only the consumer
    project's `.claude/` left that table reported as unclassified."""
    data, project = tmp_path / "data", tmp_path / "project"
    _instance(data)
    _w(project / ".claude" / "agents" / f"{OLD}.md", f"---\nname: {OLD}\n---\n")
    _w(project / ".claude" / "agents" / f"{OTHER}.md", f"---\nname: {OTHER}\n---\n")

    r = run_engine(
        "advisor", "rename", "--from", OLD, "--to", NEW,
        env={
            "CONCLAVE_AI_ROOT": str(data),
            "CLAUDE_PROJECT_DIR": str(project),
            "CONCLAVE_RUN_LOG_DIR": f"{tmp_path}-runlog",
        },
    )
    assert r.returncode == 0, r.stderr
    config_block = r.stdout.split("config", 1)[1].split("\n\n", 1)[0]
    assert ".claude/CLAUDE.md" in config_block, r.stdout


def test_only_the_top_level_claude_md_is_config(tmp_path):
    """`.claude/CLAUDE.md` carries the roster table. A `CLAUDE.md` nested deeper
    is someone else's project seed.

    This instance keeps a git worktree of the ENGINE repo at
    `.claude/worktrees/104-p0-efficacy-gate/`, and matching `CLAUDE.md` at any
    depth made the planner offer to edit that checkout's own seed file — a
    different repo, from a rename whose rollback story covers neither."""
    _instance(tmp_path)
    nested = _w(
        tmp_path / ".claude" / "worktrees" / "some-branch" / "CLAUDE.md",
        f"A checkout that happens to mention {OLD}.\n",
    )
    before = nested.read_text(encoding="utf-8")
    r = _rename("--from", OLD, "--to", NEW, "--apply", "--confirm", tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    assert nested.read_text(encoding="utf-8") == before
    assert (tmp_path / ".claude" / "CLAUDE.md").read_text(encoding="utf-8").count(NEW) == 1


def test_the_run_log_is_excluded_even_when_its_location_is_overridden(tmp_path):
    """The exclusion is on BOTH the canonical run-log and the env override.

    Pinning only `run_log_dir()` is how the guard disabled itself: with
    CONCLAVE_RUN_LOG_DIR set elsewhere, the instance's real run-log went
    unguarded and turned up in the plan as unclassified.
    """
    _instance(tmp_path)
    _w(
        tmp_path / "agent-memory" / "run-log" / "2026-08-07.jsonl",
        json.dumps({"script": "engine advisor", "args_hash": f"from={OLD}"}) + "\n",
    )
    r = _rename("--from", OLD, "--to", NEW, tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "run-log" not in r.stdout, r.stdout


def test_a_prose_only_match_is_reported_rather_than_vanishing(tmp_path):
    """A history record naming the advisor only in body text earns no move and no
    edit. Reporting it is the difference between 'deliberately left alone' and
    'never seen' — which the plan alone could not otherwise distinguish."""
    _instance(tmp_path)
    audit = _w(
        tmp_path / "agent-memory" / "advisors" / "audits" / "2026-06-17-skills.md",
        f"---\ndate: 2026-06-17\n---\n\nThe {OLD} advisor had 4 phantom skills.\n",
    )
    r = _rename("--from", OLD, "--to", NEW, tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "prose-only" in r.stdout
    assert str(audit.relative_to(tmp_path)) in r.stdout


def test_apply_reports_the_same_counts_the_dry_run_promised(tmp_path):
    _instance(tmp_path)
    dry = _rename("--from", OLD, "--to", NEW, tmp=tmp_path)
    wet = _rename("--from", OLD, "--to", NEW, "--apply", "--confirm", tmp=tmp_path)
    assert dry.returncode == 0 and wet.returncode == 0, dry.stderr + wet.stderr
    dry_counts = json.loads(dry.stdout.split("SUMMARY ", 1)[1].splitlines()[0])
    wet_counts = json.loads(wet.stdout.split("SUMMARY ", 1)[1].splitlines()[0])
    assert dry_counts == wet_counts, "dry-run promised a different plan than apply performed"


def test_migrates_an_id_already_retired_from_the_roster(tmp_path):
    """A CODE-side identity change retires the old id BEFORE its data catches up.

    `forge` → `forge-chro` renamed the shipped agent-def, so `forge` stopped being
    canonical while 130 artifacts still named it. A `--from` guard that asks "is
    this in the current roster" then refuses exactly the migration it exists to
    enable. The guard's real question is "does this id exist at all" — and an id
    owning artifacts on disk is not a typo.
    """
    _instance(tmp_path)
    (tmp_path / ".claude" / "agents" / f"{OLD}.md").unlink()   # retired from the roster

    r = _rename("--from", OLD, "--to", NEW, tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "MOVE" in r.stdout

    wet = _rename("--from", OLD, "--to", NEW, "--apply", "--confirm", tmp=tmp_path)
    assert wet.returncode == 0, wet.stderr
    moved = tmp_path / "agent-memory" / "advisors" / "sessions" / f"2026-08-06-{NEW}-neon.md"
    assert moved.is_file()
    assert f"advisor: {NEW}" in moved.read_text()


def test_a_typo_owning_nothing_is_still_refused(tmp_path):
    """The relaxation must not swallow the guard: an id with no artifacts anywhere
    is a typo, and it is refused whether or not it is in the roster."""
    _instance(tmp_path)
    before = _snapshot(tmp_path)
    r = _rename("--from", "nobdy-cto", "--to", NEW, "--apply", "--confirm", tmp=tmp_path)
    assert r.returncode == 1, r.stdout
    assert "not a canonical advisor" in r.stderr
    assert _snapshot(tmp_path) == before


def test_adopts_a_target_that_exists_but_owns_no_memory(tmp_path):
    """The mirror of the retired-`--from` case, and the other half of the same
    ordering problem.

    A CODE-side rename creates the NEW agent-def before the data moves, so `--to`
    is already in the roster while owning nothing. Refusing on roster membership
    blocks the completion of the very rename that created it. Occupancy is judged
    by MEMORY: config clashes are caught precisely by the path-collision check,
    which names the two paths instead of the id.
    """
    p = _instance(tmp_path)
    p["agent_def"].unlink()                                    # retired by the CODE rename
    _w(tmp_path / ".claude" / "agents" / f"{NEW}.md", f"---\nname: {NEW}\n---\n")

    r = _rename("--from", OLD, "--to", NEW, "--apply", "--confirm", tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    moved = tmp_path / "agent-memory" / "advisors" / "sessions" / f"2026-08-06-{NEW}-neon.md"
    assert moved.is_file()
    assert f"advisor: {NEW}" in moved.read_text()


def test_still_refuses_a_target_that_owns_memory(tmp_path):
    """Adoption must not become a silent merge: a target with history of its own is
    a different advisor, and folding two identities together is unrecoverable."""
    _instance(tmp_path)
    before = _snapshot(tmp_path)
    r = _rename("--from", OLD, "--to", OTHER, "--apply", "--confirm", tmp=tmp_path)
    assert r.returncode == 2, r.stdout
    assert _snapshot(tmp_path) == before


def test_cross_cutting_decisions_are_history_too(tmp_path):
    """`ops/decisions/` holds cross-cutting Y-statements keyed by `by:`, and the
    briefing reads them alongside the advisor's own decisions
    (briefing/scans/decisions.py:39). The classifier knew only
    `agent-memory/advisors/decisions/`, so a renamed advisor's cross-cutting
    record kept pointing at the retired id. Surfaced by the `unclassified`
    bucket on a real instance, which is what that bucket is for."""
    _instance(tmp_path)
    r = _rename("--from", OLD, "--to", NEW, "--apply", "--confirm", tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    moved = tmp_path / "ops" / "decisions" / f"2026-08-06-{NEW}-topology.md"
    assert moved.is_file(), "cross-cutting decision not renamed"
    assert f"by: {NEW}" in moved.read_text()


# ---------------------------------------------------------------------------
# A filename has positions (measured on conclave-self, forge → forge-chro)
#
# The fixture above uses a LONG id that never occurs inside a slug, so a blanket
# token replace looked correct for the whole first round. A short id that is also
# a vocabulary word of the repo — `forge`, `sage`, `iris` — appears in topics,
# event descriptions and sender segments, and a blanket replace corrupts every
# one of them. These four shapes are real paths from this instance.
# ---------------------------------------------------------------------------

SHORT = "nova"
SHORT_NEW = "nova-cto"


def _short_instance(tmp: Path) -> None:
    """A minimal instance whose id also occurs INSIDE slugs."""
    _w(tmp / ".claude" / "agents" / f"{SHORT}.md", f"---\nname: {SHORT}\n---\n")
    _w(tmp / ".claude" / "agents" / f"{OTHER}.md", f"---\nname: {OTHER}\n---\n")
    _w(
        tmp / ".claude" / "skills" / f"conclave-{SHORT}" / "SKILL.md",
        f"---\nname: conclave-{SHORT}\n---\n",
    )
    # owner is the id → the owner segment moves
    _w(
        tmp / "agent-memory" / "advisors" / "sessions" / f"2026-08-06-{SHORT}-{SHORT}-rename.md",
        f"---\nadvisor: {SHORT}\n---\n\nBody.\n",
    )
    # owner is somebody else; the id is the TOPIC
    _w(
        tmp / "ops" / "decisions" / f"2026-07-06-{OTHER}-{SHORT}-discovery-split.md",
        f"---\nby: {OTHER}\n---\n\nBody.\n",
    )
    # no date prefix at all; the id is part of an event description
    _w(
        tmp / "ops" / "feedback" / "nominations" / f"study-phase-py-advisor-{SHORT}-printed.md",
        "---\nfeedback_id: fb-1\n---\n\nBody.\n",
    )
    # recipient segment AND slug text in one name
    _w(
        tmp / "agent-memory" / "advisors" / "mentions" / SHORT / "open"
        / f"2026-07-03-0311-{OTHER}-to-{SHORT}-{SHORT}-it-3-hardcode.md",
        f"---\nfrom: {OTHER}\nto: {SHORT}\nstatus: open\n---\n\nBody.\n",
    )
    # a topic DIRECTORY that merely starts with the id
    _w(
        tmp / "ops" / "feedback" / f"{SHORT}-audit" / "2026-08-06-notes.md",
        f"---\nfeedback_id: fb-2\n---\n\nRaised with {SHORT} during the audit.\n",
    )
    # ANOTHER advisor whose id merely starts with ours, named in the `<owner>-<slug>` shape
    _w(
        tmp / "ops" / "feedback" / "2026-08-07" / f"{SHORT}chain-2026-08-06-x.md",
        f"---\nfeedback_id: fb-3\nagent: {SHORT}chain\n---\n\nEscalated to {SHORT}.\n",
    )


@pytest.fixture
def short_applied(tmp_path):
    _short_instance(tmp_path)
    r = _rename("--from", SHORT, "--to", SHORT_NEW, "--apply", "--confirm", tmp=tmp_path)
    assert r.returncode == 0, r.stderr
    return tmp_path


def test_history_owner_segment_moves_but_the_slug_does_not(short_applied):
    """`<date>-<owner>-<slug>.md`: only the owner segment names the advisor."""
    d = short_applied / "agent-memory" / "advisors" / "sessions"
    assert (d / f"2026-08-06-{SHORT_NEW}-{SHORT}-rename.md").is_file(), sorted(p.name for p in d.iterdir())


def test_history_topic_is_not_an_owner(short_applied):
    """The owner here is someone else; the id sits in the topic and must not move."""
    d = short_applied / "ops" / "decisions"
    assert (d / f"2026-07-06-{OTHER}-{SHORT}-discovery-split.md").is_file(), sorted(
        p.name for p in d.iterdir()
    )


def test_history_undated_name_moves_only_when_the_id_leads_it(short_applied):
    """A feedback nomination is `<event-description>.md` — no owner position at all."""
    d = short_applied / "ops" / "feedback" / "nominations"
    assert (d / f"study-phase-py-advisor-{SHORT}-printed.md").is_file(), sorted(
        p.name for p in d.iterdir()
    )


def test_history_mention_moves_the_recipient_not_the_slug(short_applied):
    """`<date>-<time>-<from>-to-<to>-<slug>.md` — the recipient moves, the slug stays.

    A blanket replace produced `...-to-nova-cto-nova-cto-it-3-...`, silently
    rewriting words that were never an identity.
    """
    d = short_applied / "agent-memory" / "advisors" / "mentions" / SHORT_NEW / "open"
    assert d.is_dir(), "recipient directory not renamed"
    assert (d / f"2026-07-03-0311-{OTHER}-to-{SHORT_NEW}-{SHORT}-it-3-hardcode.md").is_file(), sorted(
        p.name for p in d.iterdir()
    )


def test_history_directory_is_an_identity_only_when_it_is_the_id(short_applied):
    """`mentions/<id>/` names an owner; `feedback/<id>-audit/` names a topic.

    Treating a directory like a filename would move both, because the filename
    rule accepts the id at offset 0 followed by a hyphen — which is exactly what
    a topic directory looks like."""
    d = short_applied / "ops" / "feedback"
    assert (d / f"{SHORT}-audit").is_dir(), sorted(p.name for p in d.iterdir())


def test_history_owner_position_still_requires_a_token_boundary(short_applied):
    """`novachain-<slug>.md` belongs to `novachain`, not to `nova`.

    It enters the scan on a PROSE mention of the shorter id, so nothing else
    stops it: without the boundary check the offset-0 rule splices our new id
    into another advisor's record."""
    d = short_applied / "ops" / "feedback" / "2026-08-07"
    assert (d / f"{SHORT}chain-2026-08-06-x.md").is_file(), sorted(p.name for p in d.iterdir())


def test_config_paths_still_use_whole_token_replacement(short_applied):
    """Config names the advisor mid-token by design (`conclave-<id>`), and there
    the blanket rewrite is the correct one. The position rule is HISTORY-only."""
    assert (short_applied / ".claude" / "skills" / f"conclave-{SHORT_NEW}" / "SKILL.md").is_file()
    assert (short_applied / ".claude" / "agents" / f"{SHORT_NEW}.md").is_file()
