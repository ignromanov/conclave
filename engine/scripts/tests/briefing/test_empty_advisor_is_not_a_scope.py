"""Scope is a field, not an empty string (GH#57, plan 057 T3).

`advisor=""` was the obvious way to ask a scan for "everything", and it was measured to
do **six different things** across fifteen modules:

* `interrupted`, `plans` — genuinely instance-wide; they read no advisor field at all.
* `roadmap`, `drift`, `spec_progress` — empty. `_specfm.owns` returned None for a falsy
  advisor, so the walk matched nothing.
* `sessions`, `decisions`, `code_repo` — empty. `files_for_advisor` compared each
  record's owner against `""`.
* `current_work` — correctly instance-wide, by accident of writing `if advisor and ...`.
* `owed` — instance-wide **noise**: it builds `rf"\b{re.escape(advisor)}\b"`, and for the
  empty advisor that is `\b\b`, which matches every line carrying a word.
* `spec_progress`'s ★ flag — universal, for the same reason: `"" in line` is always True.

One call, six answers, and no error anywhere distinguishes them. On a briefing that is a
missing section; on the status projection it is a measured zero over a corpus that is not
empty — the wrong-by-omission-and-confident failure that surface exists to retire.

So `scope` is explicit, the two contradictory constructions are refused, and each of the
20 `ctx.advisor` read sites reads the accessor for its class (§13): `advisor_key` (KEY),
`advisor_filter` (FILTER), `audience` (SHAPE).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from briefing.scans import (
    AdvisorScopeRequired,
    ScanCtx,
    closeability,
    current_work,
    mentions,
    owed,
    p0,
    queue,
    roadmap,
    spec_progress,
)

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
- [ ] one open — @{owner} to finish
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


def _ctx(root: Path, advisor: str | None) -> ScanCtx:
    instance = advisor is None
    return ScanCtx(
        advisor=advisor,
        short_name="" if instance else advisor.split("-")[0],
        scope="instance" if instance else "advisor",
        repo_root=root, decisions_dir=root, sessions_dir=root, mentions_dir=root,
        gh_cache_dir=root, personality_path=root / "none.md",
        project_root=root, plans_dir=root / ".claude" / "plans",
    )


def _specs_seen(section: str) -> int:
    """How many of the fixture's two specs this render names.

    Not a line count: `current_work` renders `**101-alpha** — ...` with no list bullet,
    so a `- ` counter measures its FORMAT and reports zero for a section that is working.
    The question every one of these scans answers is "whose specs", so count the specs.
    """
    return sum(sid in section for sid in ("101-alpha", "102-beta"))


# --------------------------------------------------------------------------
# The two constructions that cannot mean anything
# --------------------------------------------------------------------------


def test_an_advisor_scope_with_no_advisor_is_refused(tmp_path: Path) -> None:
    """The dead idiom fails at construction, not four frames deeper in a walk."""
    with pytest.raises(ValueError, match="silent emptier"):
        _ctx(tmp_path, "")


def test_an_instance_scope_naming_one_advisor_is_refused(tmp_path: Path) -> None:
    """Neither of the two things it looks like, so it is not constructible."""
    base = _ctx(tmp_path, "advisor-one")
    with pytest.raises(ValueError, match="instance scope names no advisor"):
        ScanCtx(**{**base.__dict__, "scope": "instance"})


# --------------------------------------------------------------------------
# FILTER — instance scope drops the predicate, and that means MORE rows
# --------------------------------------------------------------------------


@pytest.mark.parametrize("module", [spec_progress, roadmap, current_work],
                         ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_instance_scope_widens_a_filter_scan(two_owners: Path, module) -> None:
    """One owner sees one spec; the instance sees BOTH — not zero, which is what
    `advisor=""` returned from two of these three."""
    assert _specs_seen(module.build(_ctx(two_owners, "advisor-one"))) == 1
    assert _specs_seen(module.build(_ctx(two_owners, "advisor-two"))) == 1
    assert _specs_seen(module.build(_ctx(two_owners, None))) == 2


def test_the_star_flag_is_not_universal_under_instance_scope(two_owners: Path) -> None:
    """`"" in line` starred every open item. Instance scope has no name to mention."""
    rendered = spec_progress.build(_ctx(two_owners, None))
    assert "★" not in rendered, f"instance scope flagged ownership hints:\n{rendered}"
    assert "★" in spec_progress.build(_ctx(two_owners, "advisor-one"))


# --------------------------------------------------------------------------
# KEY — instance scope is a category error, and says so
# --------------------------------------------------------------------------


@pytest.mark.parametrize("module", [queue, p0, closeability, mentions, owed],
                         ids=lambda m: m.__name__.rsplit(".", 1)[-1])
def test_an_advisor_keyed_scan_refuses_instance_scope(two_owners: Path, module) -> None:
    """No file holds the union of five per-advisor caches, so there is nothing to read.

    `owed` is in this list and looks like a FILTER: it greps active specs for an advisor's
    name. But "owed to anyone" needs the roster to enumerate names, not the absence of a
    predicate — and the absence of a predicate is precisely what produced `\\b\\b`.
    """
    with pytest.raises(AdvisorScopeRequired):
        module.build(_ctx(two_owners, None))


def test_the_named_error_says_what_to_do_instead() -> None:
    """A TypeError from inside a Path join reports the symptom, not the decision."""
    with pytest.raises(AdvisorScopeRequired, match="iterating the roster"):
        assert _ctx(Path("/nonexistent"), None).advisor_key


# --------------------------------------------------------------------------
# The projection's own ctx
# --------------------------------------------------------------------------


def test_the_status_stub_ctx_declares_its_scope() -> None:
    """`engine status` reads instance-wide once, then per-advisor for the mosaics.

    This replaces an assertion that the stub used `advisor == ""`. That test could only
    ever check that the idiom was still in place; it could not check that the idiom meant
    anything, and it did not.
    """
    from engine.cmd import status as status_cmd

    instance = status_cmd._stub_ctx(Path("/nonexistent"))
    assert instance.scope == "instance"
    assert instance.advisor is None
    assert instance.advisor_filter is None
    assert instance.audience == "the instance"

    per_advisor = status_cmd._stub_ctx(Path("/nonexistent"), advisor="advisor-one")
    assert per_advisor.scope == "advisor"
    assert per_advisor.advisor_key == "advisor-one"
