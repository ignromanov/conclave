"""engine/cmd/status.py — adapter for `engine status` (GH#57).

The projection's I/O lives here, in the adapter, so `enginelib/status/` stays pure and
the sanctioned layering (briefing -> enginelib, never back) is not bent to reach a
data source. What this command PRINTS is fixed by `state-report.md` v1.0; this module
gathers and hands off, it does not decide the display.

**Scope defaults to the instance.** The question the issue was filed against — "what is
going on" — is an instance question, and an advisor default would reproduce at the CLI
the exact defect this projection exists to retire: `p0.py` is titled "Global p0
blockers" and reads one advisor's cache, so a p0 on another advisor renders as none.
`--advisor <id>` narrows; nothing widens by accident.

Unwired sources are declared `Absent` with a reason rather than counted as zero
(rule 6), which is what lets this ship incrementally without lying: a slot that is not
yet connected says so in words, and the operator can tell it from a real zero.
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta


def _handoffs_section(repo_root):
    """Open handoffs, instance-wide, with staleness from the newest MOVEMENT."""
    from briefing.scans import interrupted
    from enginelib.status.model import Absent, Count, SectionResult, Staleness

    handoffs_dir = repo_root / "ops" / "handoffs"
    if not handoffs_dir.is_dir():
        return SectionResult(
            name="хендофы",
            measurement=Absent(reason=f"каталога нет: {handoffs_dir.name}/"),
            verdict="unknown",
        )

    ctx = _stub_ctx(repo_root)
    rows = interrupted.collect(ctx)
    newest = None
    if rows:
        newest = max(
            datetime.strptime(mtime, "%Y-%m-%d %H:%M UTC").replace(tzinfo=UTC)
            for _, mtime, _ in rows
        )
    policy = Staleness(warn_after=timedelta(days=7), error_after=timedelta(days=30))
    return SectionResult(
        name="хендофы",
        measurement=Count(
            value=len(rows),
            noun="хендофов открыто",
            proof="ops/handoffs/*.md — frontmatter status не в терминальном наборе",
        ),
        verdict=policy.assess(newest, datetime.now(UTC)),
        rows=tuple(rows),
    )


def _feedback_section(repo_root):
    """Feedback notebook: how much of it is resolved, and how much is reachable."""
    from enginelib.status.model import Absent, Count, SectionResult

    index = repo_root / "ops" / "feedback" / "_index" / "index.jsonl"
    if not index.is_file():
        return SectionResult(
            name="фидбек",
            measurement=Absent(reason="индекс не собран (ops/feedback/_index/index.jsonl нет)"),
            verdict="unknown",
        )

    total = resolved = 0
    for line in index.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            # A malformed row is not a zero. Counting it as absent-from-total would
            # understate the denominator silently, which is the failure this whole
            # surface is written against; so it counts toward total and nothing else.
            total += 1
            continue
        total += 1
        if row.get("status") == "resolved":
            resolved += 1

    return SectionResult(
        name="фидбек",
        measurement=Count(
            value=resolved, of=total,
            noun="фидбек-записей resolved",
            proof="ops/feedback/_index/index.jsonl",
        ),
        verdict="stale_warn" if total and resolved == 0 else "fresh",
    )


def _stub_ctx(repo_root):
    """A ScanCtx for an instance-scoped read.

    `advisor` is typed `str` with no instance-wide path anywhere in the scan layer
    (measured: zero occurrences of a scope or advisor-is-None branch across all 17
    modules), so an instance-scoped caller must still supply one. The sections used
    here read no advisor field, which is why the value is inert — and that is a
    property of these two sections, not of the layer. Widening this to the sections
    that DO read it is the explicit `scope` on ScanCtx, plan 057 T3.
    """
    from pathlib import Path

    from briefing.scans import ScanCtx

    return ScanCtx(
        advisor="", short_name="", repo_root=repo_root,
        decisions_dir=repo_root / "agent-memory" / "advisors" / "decisions",
        sessions_dir=repo_root / "agent-memory" / "advisors" / "sessions",
        mentions_dir=repo_root / "agent-memory" / "advisors" / "mentions",
        gh_cache_dir=repo_root / "agent-memory" / "gh-cache",
        personality_path=Path("/dev/null"),
        project_root=repo_root, plans_dir=repo_root / ".claude" / "plans",
    )


# Slots the projection owes and does not yet gather. Named, with the reason a human
# can act on — an unwired slot that renders `0` is the lie rule 6 forbids, and one
# that renders nothing at all is worse.
_NOT_YET_WIRED = {
    "спеки": "не подключено (plan 057 T10)",
    "очередь": "не подключено — per-advisor кэш, нужен scope (plan 057 T7)",
    "ветки": "не подключено — нужен join git cherry × gh pr (plan 057 T9)",
    "CI": "не подключено — statusCheckRollup, ничего его не проецирует (plan 057 T11)",
}


def _status(args) -> int:
    from enginelib.paths import repo_root as data_root
    from enginelib.status.model import Absent, SectionResult
    from enginelib.status.render_terminal import glance, glance_overflows, work

    args._runlog_verb = "status"
    args._runlog_args = f"scope={'advisor' if args.advisor else 'instance'}"

    root = data_root()
    sections = [_handoffs_section(root), _feedback_section(root)]
    sections += [
        SectionResult(name=n, measurement=Absent(reason=r), verdict="unknown")
        for n, r in _NOT_YET_WIRED.items()
    ]

    today = datetime.now().strftime("%d.%m")
    print(glance("engine", "🦉", "состояние", today, sections))
    if glance_overflows(sections):
        print(
            f"[status] WARNING: {len(sections)} секций при потолке в 12 строк — "
            "их надо группировать, а не резать",
            file=sys.stderr,
        )
    if not args.glance:
        print()
        print(work(sections))
    return 0


def register(sub) -> None:
    p = sub.add_parser("status", help="Aggregate projection of the work pool (GH#57).")
    p.add_argument(
        "--advisor", default="",
        help="Narrow to one advisor. Default is instance-wide — see module docstring.",
    )
    p.add_argument(
        "--glance", action="store_true",
        help="Print only the glance block, without the work layer.",
    )
    p.set_defaults(func=_status)
