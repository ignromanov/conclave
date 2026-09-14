"""A frozen synthetic instance — the only base a briefing golden net can stand on.

Plan 057 §4 rejected the obvious source. A golden captured from the live instance is
unbuildable: the briefing is a function of `hot.md`, the gh-cache and the session
ledger, all of which move between any two runs, so the net reddens on the next session
close and gets deleted within a day for crying wolf. This module builds a tree that
does not move, and every choice in it is made against a measured coupling.

WHAT IS DELIBERATELY IN IT (each line exists to make one extraction error visible):

* **Two advisors.** A FILTER section cannot be seen to filter with one advisor in the
  tree — the net would pass over an extraction that dropped the predicate entirely.
* **A per-advisor gh-cache pair, with the p0 label on the OTHER advisor.** `p0.py` is
  titled "Global p0 blockers" and reads one cache (plan 057 §2, executed). In this
  tree that defect is visible as output: alpha's briefing must not show beta's p0.
* **Four ownership fields across four specs** — `owner`, `advisor`, `owner_suggestion`,
  and the retired `forge` id (GH#253: three predicates answer "does this spec belong
  to advisor X" and disagree on exactly these shapes).
* **One handoff and nothing else in `ops/handoffs/`.** `interrupted.py` reads no
  advisor field at all, so the same handoff must appear in BOTH briefings. A net over
  one advisor cannot tell instance-wide from advisor-scoped.
* **A REGISTRY row that disagrees with its spec.** `drift.py` emits nothing when the
  two agree, so an agreeing fixture silently covers nothing.
* **Two plans in different verify states.** `plans.py` suppresses member rows when one
  state covers the whole corpus, so a single-plan fixture renders a summary and no rows.

WHAT IS DELIBERATELY OUT, and why the alternative was worse:

* **`updatedAt` on gh-cache items.** `queue.py` renders it as "Nd ago" against the
  wall clock, so a fixture carrying it produces a different string every day. Omitted
  rather than frozen, because freezing the clock for one field costs more than the
  field is worth here.
* **Git.** The tree is NOT a git repo, and callers chdir into it. `current_work` and
  `code_repo` both shell out to git and both degrade to a stable no-repo rendering on
  a non-zero exit. Freezing them properly needs deterministic SHAs plus `os.utime` on
  every `docs/` file — real work, and it belongs with those two scans, not here.

TIME: handoff mtimes are pinned with `os.utime` because `interrupted.py` both sorts on
mtime and renders it. Everything else in the tree is clock-independent (measured).
"""
from __future__ import annotations

import json
import os
import textwrap
from pathlib import Path

# The two advisors. Both must satisfy enginelib.advisors' id regex (<word>-<role>).
ALPHA = "alpha-cto"
BETA = "beta-coo"

# Pinned mtimes for the two handoffs — fixed instants, so the rendered stamps are
# constants AND their relative order is observable. `interrupted.py` sorts on mtime
# descending, and a fixture with ONE handoff cannot see a reordering mutation at all:
# the plan asks this net to catch "drop a row, reorder", and half of that needs two rows.
# 2026-01-05T09:30:00Z and 2026-01-04T09:30:00Z as POSIX timestamps.
HANDOFF_MTIME_NEWER = 1767605400.0
HANDOFF_MTIME_OLDER = HANDOFF_MTIME_NEWER - 86400


def _w(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content).lstrip("\n"), encoding="utf-8")


def _gh_cache(path: Path, advisor: str, items: list[dict]) -> None:
    """A gh-fetch-shaped snapshot. `captured_at` is fixed; `updatedAt` is absent by design."""
    _w(
        path,
        f"---\ntype: gh-snapshot\nschema_version: 1\nadvisor: {advisor}\n"
        f'captured_at: "2026-01-05T09:00:00Z"\nttl_seconds: 900\n---\n\n'
        f"# GH Snapshot — {advisor}\n\n```json\n{json.dumps(items, indent=2)}\n```\n",
    )


def build(root: Path) -> Path:
    """Materialise the frozen instance at *root* and return it."""
    root.mkdir(parents=True, exist_ok=True)

    # --- roster: two advisors, plus an executor that must NOT be counted as one ---
    for advisor in (ALPHA, BETA):
        _w(root / ".claude" / "agents" / f"{advisor}.md", f"---\nname: {advisor}\n---\nstub\n")
    _w(root / ".claude" / "agents" / "exec-atlas-dev.md", "---\nname: exec-atlas-dev\n---\nstub\n")

    # --- identity ---
    for advisor, blurb in ((ALPHA, "Alpha owns the core."), (BETA, "Beta owns delivery.")):
        _w(
            root / ".claude" / "skills" / f"team.{advisor}" / "memory" / "personality.md",
            f"---\ntype: personality\n---\n\n# {advisor}\n\n{blurb}\n",
        )

    # --- hot.md ---
    _w(
        root / "agent-memory" / "hot.md",
        """
        ## Now

        Frozen fixture — nothing is in flight.

        ## Recent decisions

        - synthetic-decision: pinned.

        ## Watch

        Nothing.
        """,
    )
    (root / "agent-memory" / "advisors" / "briefings").mkdir(parents=True, exist_ok=True)

    # --- decisions: `by:` is the field files_for_advisor reads for this dir ---
    _w(
        root / "agent-memory" / "advisors" / "decisions" / f"2026-01-02-{ALPHA}-first.md",
        f"---\ntype: decision\nstatus: approved\nby: {ALPHA}\ncreated: 2026-01-02\n"
        "schema_version: 1\n---\n\nThe first decision.\n",
    )
    _w(
        root / "agent-memory" / "advisors" / "decisions" / f"2026-01-01-{BETA}-second.md",
        f"---\ntype: decision\nstatus: approved\nby: {BETA}\ncreated: 2026-01-01\n"
        "schema_version: 1\n---\n\nBeta's decision — must not appear under alpha.\n",
    )
    # ops/decisions is read unfiltered by advisor — it appears for BOTH.
    _w(root / "ops" / "decisions" / "2026-01-01-shared-ruling.md", "---\ntype: decision\n---\n\nShared.\n")

    # --- sessions: this dir's field is `advisor:` ---
    _w(
        root / "agent-memory" / "advisors" / "sessions" / f"2026-01-03-{ALPHA}-work.md",
        f"---\ntype: session\nadvisor: {ALPHA}\ncreated: 2026-01-03T10:00:00\n"
        "schema_version: 1\n---\n\nAlpha worked.\n",
    )

    # --- mentions: the advisor is a PATH SEGMENT, so a wrong value means a missing dir ---
    _w(
        root / "agent-memory" / "advisors" / "mentions" / ALPHA / "open"
        / f"2026-01-04-{BETA}-to-{ALPHA}-review.md",
        f"---\ntype: mention\npriority: p1\nfrom: {BETA}\nstatus: open\n"
        f"created: 2026-01-04T10:00:00\ntarget_advisor: {ALPHA}\nschema_version: 1\n---\n\n"
        "Please review the frozen fixture.\n",
    )

    # --- gh-cache: the KEY pair. beta holds the p0; alpha must not show it. ---
    _gh_cache(
        root / "agent-memory" / "gh-cache" / f"{ALPHA}.md",
        ALPHA,
        [
            {"number": 101, "title": "Alpha core refactor",
             "labels": [{"name": "agent-infra"}, {"name": "p1"}, {"name": f"advisor:{ALPHA}"}],
             "repository": {"name": "synthetic"}},
        ],
    )
    _gh_cache(
        root / "agent-memory" / "gh-cache" / f"{BETA}.md",
        BETA,
        [
            {"number": 202, "title": "Delivery is on fire",
             "labels": [{"name": "bug"}, {"name": "p0"}, {"name": f"advisor:{BETA}"}],
             "repository": {"name": "synthetic"}},
        ],
    )

    # --- specs: one per ownership field, plus the retired id ---
    _spec(root, "010-alpha-core", "010", "Alpha core", "in-progress", "owner", ALPHA)
    _spec(root, "011-beta-delivery", "011", "Beta delivery", "proposed", "advisor", BETA)
    _spec(root, "012-alpha-suggested", "012", "Alpha suggested", "proposed", "owner_suggestion", ALPHA)
    # GH#253: `forge` is a retired id that _specfm maps to forge-chro — which is on
    # neither advisor's roster here, so this spec must appear in NEITHER briefing.
    _spec(root, "013-legacy-owner", "013", "Legacy owner", "proposed", "owner", "forge")

    # 010 carries a plan, which is what current_work's progress line and plans.py read.
    _w(
        root / "ops" / "specs" / "010-alpha-core" / "plan.md",
        """
        ---
        type: plan
        id: 010-alpha-core
        owner: alpha-cto
        verify:
          kind: file-contains
          root: project
          file: marker.txt
          pattern: present
        ---

        # Plan

        - [x] done task
        - [ ] open task — @alpha-cto to finish

        The open line names an advisor on purpose: `owed.py` filters on BODY TEXT, not
        on frontmatter ownership, and it is the only scan that also reads
        `ctx.short_name`. Without a named line it renders its placeholder and the net
        covers nothing there.
        """,
    )
    # The `landed` predicate's target. Its absence is what makes the second plan differ.
    _w(root / "marker.txt", "present\n")
    # A second plan in a DIFFERENT verify state — plans.py suppresses member rows when
    # one state covers the whole corpus, so two states are the minimum useful fixture.
    _w(
        root / ".claude" / "plans" / "harness-plan.md",
        """
        ---
        type: plan
        id: harness-plan
        verify:
          kind: file-contains
          root: project
          file: nowhere.txt
          pattern: missing
        ---

        # Harness plan

        - [ ] nothing yet
        """,
    )

    # --- REGISTRY: 010's row says `proposed`, the spec says `in-progress` -> drift ---
    _w(
        root / "ops" / "specs" / "REGISTRY.md",
        """
        # Spec registry

        | ID | Type | Status | Reason |
        |----|------|--------|--------|
        | 010 | Feature | proposed | registry deliberately disagrees with the spec |
        | 011 | Feature | proposed | agrees — must produce no drift row |
        """,
    )

    # --- handoffs: instance-wide by construction; must appear for BOTH advisors ---
    # Two of them, in opposite mtime order to their filenames, so a sort that silently
    # became filename-order (or reversed) shows up as a diff rather than as nothing.
    for name, sender, recipient, mtime in (
        (f"2026-01-05-{BETA}-to-{ALPHA}-resume.md", BETA, ALPHA, HANDOFF_MTIME_NEWER),
        (f"2026-01-06-{ALPHA}-to-{BETA}-followup.md", ALPHA, BETA, HANDOFF_MTIME_OLDER),
    ):
        handoff = root / "ops" / "handoffs" / name
        _w(
            handoff,
            f"---\ntype: handoff\nstatus: open\nfrom: {sender}\n---\n\n"
            f"**To**: {recipient} | **From**: {sender}\n\nPick up the frozen fixture.\n",
        )
        os.utime(handoff, (mtime, mtime))
    # A terminal handoff that must be EXCLUDED — without it the net cannot tell a
    # status filter from no filter at all.
    done = root / "ops" / "handoffs" / f"2026-01-03-{ALPHA}-to-{BETA}-shipped.md"
    _w(done, f"---\ntype: handoff\nstatus: done\nfrom: {ALPHA}\n---\n\nShipped.\n")
    os.utime(done, (HANDOFF_MTIME_NEWER + 3600, HANDOFF_MTIME_NEWER + 3600))

    return root


def _spec(root: Path, slug: str, spec_id: str, title: str, status: str, field: str, owner: str) -> None:
    """One spec whose ownership is declared through exactly one field.

    The `## Acceptance` checkboxes sit at column 0 on purpose: `spec_progress.py`
    tolerates no leading whitespace there, while `current_work.py` does — a difference
    a fixture written by eye gets wrong in the direction that hides a bug.
    """
    _w(
        root / "ops" / "specs" / slug / "spec.md",
        f"---\ntype: spec\nid: {spec_id}\ntitle: \"{title}\"\nstatus: {status}\n"
        f"{field}: {owner}\nschema_version: 1\nmilestone: M1\n---\n\n"
        f"# {title}\n\n## Acceptance\n\n- [x] first criterion\n- [ ] second criterion\n",
    )
