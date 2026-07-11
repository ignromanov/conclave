"""test_regen.py — unit tests for briefing.regen helpers."""
from __future__ import annotations

from briefing.regen import advisors_from_commit_diff

# Local match fixture — the roster is registry-driven in production and injected
# by the caller, so tests pass an explicit set instead of a module constant.
_ADVISORS = ("nexus-ceo", "kai-cto", "shade-ciso", "spark-cmo", "quorum")


def test_advisors_from_commit_diff_decisions() -> None:
    diff = "agent-memory/advisors/decisions/2026-05-21-kai-cto-move-to-base.md"
    result = advisors_from_commit_diff(diff, _ADVISORS)
    assert result == ["kai-cto"]


def test_advisors_from_commit_diff_sessions() -> None:
    diff = "agent-memory/advisors/sessions/2026-05-21-nexus-ceo-sprint.md"
    result = advisors_from_commit_diff(diff, _ADVISORS)
    assert result == ["nexus-ceo"]


def test_advisors_from_commit_diff_mentions() -> None:
    diff = "agent-memory/advisors/mentions/shade-ciso/open/2026-05-21-foo.md"
    result = advisors_from_commit_diff(diff, _ADVISORS)
    assert result == ["shade-ciso"]


def test_advisors_from_commit_diff_hot_md_returns_all() -> None:
    diff = "agent-memory/hot.md"
    result = advisors_from_commit_diff(diff, _ADVISORS)
    assert sorted(result) == sorted(list(_ADVISORS))


def test_advisors_from_commit_diff_multiple_advisors() -> None:
    diff = "\n".join([
        "agent-memory/advisors/decisions/2026-05-21-kai-cto-foo.md",
        "agent-memory/advisors/sessions/2026-05-21-nexus-ceo-bar.md",
    ])
    result = advisors_from_commit_diff(diff, _ADVISORS)
    assert sorted(result) == ["kai-cto", "nexus-ceo"]


def test_advisors_from_commit_diff_deduplicates() -> None:
    diff = "\n".join([
        "agent-memory/advisors/decisions/2026-05-21-kai-cto-foo.md",
        "agent-memory/advisors/decisions/2026-05-21-kai-cto-bar.md",
    ])
    result = advisors_from_commit_diff(diff, _ADVISORS)
    assert result == ["kai-cto"]


def test_advisors_from_commit_diff_unrelated_files() -> None:
    diff = "\n".join([
        "ops/specs/084-briefing-enrichment/plan.md",
        "architecture/fsd-registry.md",
        "src/features/invoice-codec/lib/encode.ts",
    ])
    result = advisors_from_commit_diff(diff, _ADVISORS)
    assert result == []


def test_advisors_from_commit_diff_empty() -> None:
    assert advisors_from_commit_diff("", _ADVISORS) == []
    assert advisors_from_commit_diff("   \n  ", _ADVISORS) == []


def test_advisors_from_commit_diff_all_canonical_advisors() -> None:
    lines = [
        f"agent-memory/advisors/decisions/2026-05-21-{adv}-test.md"
        for adv in _ADVISORS
    ]
    result = advisors_from_commit_diff("\n".join(lines), _ADVISORS)
    assert sorted(result) == sorted(list(_ADVISORS))


def test_advisors_from_commit_diff_honors_injected_set() -> None:
    """#47: the match set is injected (registry-driven), not a hardcoded roster."""
    diff = "\n".join([
        "agent-memory/advisors/decisions/2026-05-21-alpha-foo.md",
        "agent-memory/advisors/decisions/2026-05-21-kai-cto-bar.md",
    ])
    result = advisors_from_commit_diff(diff, ("alpha", "beta"))
    assert result == ["alpha"]  # kai-cto not in the injected roster → ignored
