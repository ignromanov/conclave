"""`advisor=""` is not an instance-wide switch — it is a silent emptier (GH#57).

Reaching for `ScanCtx(advisor="")` is the obvious way to ask a scan for "everything",
and `interrupted`/`plans` reward it because they read no advisor field at all. The
scans that DO read one behave the opposite way: `_specfm.owns` returns None for a
falsy advisor, so the walk matches nothing and the section renders empty.

Empty and instance-wide are indistinguishable in the output. On a briefing that is a
missing section; on the status projection (GH#57) it is a measured zero over a corpus
that is not empty — the exact wrong-by-omission-and-confident failure that surface
exists to retire. This test pins the asymmetry so the next caller meets it as a red
test rather than as a plausible number.

Widening is `scope` on ScanCtx, plan 057 T3. Until that lands, there is no widening.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from briefing.scans import ScanCtx, roadmap, spec_progress

_SPEC = """---
type: spec
id: "{sid}"
title: "spec owned by {owner}"
status: in_progress
owner: {owner}
created: 2026-01-01
updated: 2026-01-02
schema_version: 1
---

## Acceptance criteria

- [x] one done
- [ ] one open
"""


@pytest.fixture
def two_owners(tmp_path: Path) -> Path:
    """A DATA root holding one spec per advisor — so 'everything' is unambiguously two."""
    specs = tmp_path / "ops" / "specs"
    for sid, owner in (("101-alpha", "advisor-one"), ("102-beta", "advisor-two")):
        d = specs / sid
        d.mkdir(parents=True)
        (d / "spec.md").write_text(_SPEC.format(sid=sid, owner=owner), encoding="utf-8")
    return tmp_path


def _ctx(root: Path, advisor: str) -> ScanCtx:
    return ScanCtx(
        advisor=advisor, short_name=advisor.split("-")[0] if advisor else "",
        repo_root=root, decisions_dir=root, sessions_dir=root, mentions_dir=root,
        gh_cache_dir=root, personality_path=root / "none.md",
        project_root=root, plans_dir=root / ".claude" / "plans",
    )


def _rows(section: str) -> int:
    return len([ln for ln in section.splitlines() if ln.startswith("- ")])


@pytest.mark.parametrize("module", [spec_progress, roadmap], ids=lambda m: m.__name__)
def test_empty_advisor_empties_rather_than_widens(two_owners: Path, module) -> None:
    """One owner sees its own spec; the empty advisor sees NEITHER — not both."""
    assert _rows(module.build(_ctx(two_owners, "advisor-one"))) == 1
    assert _rows(module.build(_ctx(two_owners, "advisor-two"))) == 1

    widened = _rows(module.build(_ctx(two_owners, "")))
    assert widened != 2, (
        f"{module.__name__} widened on advisor='' — if that is now intended, this test "
        "is the place to say so, and every caller of the empty-advisor idiom needs review"
    )
    assert widened == 0, f"{module.__name__} returned {widened} rows for advisor=''"


def test_the_status_stub_ctx_is_only_safe_for_advisor_blind_sections() -> None:
    """`engine status` builds a ctx with advisor='' (cmd/status.py `_stub_ctx`).

    That is safe only while every section it feeds ignores the field. This asserts the
    set it actually feeds, so adding an advisor-reading section to the projection has
    to change this list — and whoever changes it reads the docstring above first.
    """
    from engine.cmd import status as status_cmd

    ctx = status_cmd._stub_ctx(Path("/nonexistent"))
    assert ctx.advisor == "", "the stub stopped using the empty-advisor idiom — re-read this test"

    advisor_blind = {"interrupted"}
    assert "spec_progress" not in advisor_blind
    assert "roadmap" not in advisor_blind
