"""scans/ — one module per briefing section.

Each module exposes a single ``build(ctx) -> str`` function.
``ctx`` is a :class:`ScanCtx` dataclass carrying all resolved paths
needed by every scan.  It is constructed once in the caller (render.py
or the CLI) and threaded through all build() calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

# What a ctx is ABOUT. `advisor` is one person's view; `instance` is the whole roster's.
Scope = Literal["advisor", "instance"]


class AdvisorScopeRequired(RuntimeError):
    """An advisor-KEYED scan was handed an instance-wide ctx.

    Not a bug in the caller's data — a category error. There is no file holding the
    union of five per-advisor gh-caches, so "the instance's queue" cannot be read;
    it has to be assembled by iterating the roster and combining the shards
    (`enginelib.status.reduce.combine_shards`, plan 057 §11). This exists as a named
    error because the alternative — `Path / None` — raises a TypeError from inside a
    path join, which reports the symptom three frames from the decision.
    """


@dataclass(frozen=True)
class ScanCtx:
    """Resolved runtime context for a single briefing/projection build.

    All Path fields are absolute and already resolved at construction time.

    `advisor` + `scope` are one fact in two fields, so the invariant is checked rather
    than trusted: an advisor scope names an advisor, an instance scope names none. The
    reason is GH#57's executed defect — `advisor=""` was the idiom for "everything", and
    it does the opposite. `_specfm.owns` returns None for a falsy advisor, so the walk
    matches nothing and the section renders **empty**, while the advisor-blind scans
    reward the same call with real instance-wide data. Empty and instance-wide are
    indistinguishable in the output; on a briefing that is a missing section, on the
    status projection it is a measured zero over a corpus that is not empty.

    So no scan reads `advisor` directly. Each reads the accessor for its class, and the
    class is the classification plan 057 §13 measured over all 20 sites:

    * `advisor_key`    — KEY (5 sites): the advisor selects which file to open. Raises
                         under instance scope, because iterating is the caller's job.
    * `advisor_filter` — FILTER (8 sites): an ownership predicate over a shared source.
                         `None` means "every owner", which is what widening actually is.
    * `audience`       — SHAPE (6 sites): the advisor reaches only labels and diagnostics.

    Attributes:
        advisor:           Canonical advisor name (e.g. "kai-cto"); None under instance scope.
        short_name:        First segment before "-" (e.g. "kai").
        repo_root:         Absolute path to the .ai/ repo root.
        decisions_dir:     agent-memory/advisors/decisions/
        sessions_dir:      agent-memory/advisors/sessions/
        mentions_dir:      agent-memory/advisors/mentions/
        gh_cache_dir:      agent-memory/gh-cache/
        personality_path:  .claude/skills/team.<advisor>/memory/personality.md
        project_root:      CODE checkout root — the tree plan predicates resolve against
        plans_dir:         .claude/plans/ (harness plan convention)
        scope:             "advisor" (default) or "instance"
    """

    advisor: str | None
    short_name: str
    repo_root: Path
    decisions_dir: Path
    sessions_dir: Path
    mentions_dir: Path
    gh_cache_dir: Path
    personality_path: Path
    project_root: Path
    plans_dir: Path
    scope: Scope = "advisor"

    def __post_init__(self) -> None:
        if self.scope == "advisor" and not self.advisor:
            raise ValueError(
                "an advisor scope needs an advisor — `advisor=''` is not a widening "
                'switch, it is a silent emptier; pass scope="instance" to widen (GH#57)'
            )
        if self.scope == "instance" and self.advisor:
            raise ValueError(
                f"instance scope names no advisor, got {self.advisor!r} — an instance-wide "
                "read filtered to one advisor is neither of the two things it looks like"
            )

    @property
    def advisor_key(self) -> str:
        """The advisor whose own file this scan opens. KEY sites only.

        Raises under instance scope rather than returning a fallback: there is no
        per-advisor file that holds the union, so any value returned here would be a
        wrong answer dressed as a right one.

        Keyed on `advisor is None`, not on `scope`, and the two are the same test — the
        invariant above makes them equivalent. Writing both would add a clause that
        cannot be false, which reads as a second check and is not one.
        """
        if self.advisor is None:
            raise AdvisorScopeRequired(
                "this scan is advisor-keyed (it opens one advisor's file); an instance-wide "
                "total is assembled by iterating the roster and combining shards, not by "
                "reading one key — see plan 057 §11"
            )
        return self.advisor

    @property
    def advisor_filter(self) -> str | None:
        """The ownership predicate for FILTER sites — None meaning "every owner".

        Carries no logic on purpose: the invariant already guarantees that None appears
        exactly under instance scope. What it carries is the NAME, so a call site
        declares which of the three classes (§13) it belongs to, and `str | None`
        propagates into the helper signatures where mypy can see it.
        """
        return self.advisor

    @property
    def audience(self) -> str:
        """Who or what this projection is about, in words. SHAPE sites only.

        Never a path segment and never a predicate: this is the string that lands in a
        label, a placeholder line, or the WARN that names which `gh-fetch` to rerun.
        """
        return "the instance" if self.advisor is None else self.advisor
