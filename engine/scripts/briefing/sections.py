"""sections.py — the one list of briefing sections, in render order.

There were two. `render.py:build` built a 17-key dict of `scan.build(ctx)` calls, and
`__main__.py:main` built the same dict again with a timing pair around each call. Adding a
section meant two edits, and nothing failed if you made one — the untimed path would render
the new section and the shipping path would leave the template placeholder unsubstituted.
`test_dispatch_parity.py` held the two literals equal by AST while both existed; this module
is what retires it (plan 057 T5b).

**Not in `scans/__init__.py`, which is where the plan put it.** Every scan module does
`from briefing.scans import ScanCtx`, so a registry importing those modules from inside that
package's `__init__` executes while `briefing.scans` is still partially initialised. It
happens to work as long as `ScanCtx` is defined above the registry, and it fails with an
opaque circular-import error the first time someone reorders the file. A separate module has
no cycle to be careful about: scans import the package, this imports the scans.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from briefing.scans import (
    ScanCtx,
    closeability,
    code_repo,
    current_work,
    decisions,
    drift,
    identity,
    interrupted,
    mentions,
    owed,
    p0,
    plans,
    queue,
    roadmap,
    sessions,
    spec_progress,
)


class Scan(Protocol):
    """What this registry needs of a scan module: `build(ctx) -> str`."""

    def build(self, ctx: ScanCtx) -> str: ...


@dataclass(frozen=True)
class Section:
    """One section of the briefing.

    `key` is the template placeholder, so it is also the join between this list and
    `briefing/templates/`. `step` is the label the timed path emits — kept here rather than
    derived from `key` because the two spellings differ (`my_queue` vs `my-queue`,
    `who_i_am` vs `who-i-am`) and deriving one from the other would silently rename every
    timing line in the session-init output.
    """

    key: str
    scan: Scan
    step: str


# Render order. The template does not care, but the timed path's output does, and a reader
# comparing two session-init logs should not have to.
SECTIONS: tuple[Section, ...] = (
    Section("who_i_am", identity, "who-i-am"),
    Section("recent_decisions", decisions, "decisions"),
    Section("my_queue", queue, "my-queue"),
    Section("p0_blockers", p0, "p0"),
    Section("last_sessions", sessions, "sessions"),
    Section("mentions", mentions, "mentions"),
    Section("current_work", current_work, "current-work"),
    Section("spec_progress", spec_progress, "spec-progress"),
    Section("owed", owed, "owed"),
    Section("roadmap", roadmap, "roadmap"),
    Section("drift", drift, "drift"),
    Section("interrupted", interrupted, "interrupted"),
    Section("plans", plans, "plans"),
    Section("closeability", closeability, "closeability"),
    Section("code_repo", code_repo, "code-repo"),
)

# The two keys every caller adds that are not sections: who the briefing is for, and when it
# was built. Named here so "17 keys, 15 scans" is a stated fact rather than a discrepancy
# someone has to re-derive (it cost this plan a wrong count for its whole first draft).
META_KEYS: tuple[str, ...] = ("advisor", "generated_at")
