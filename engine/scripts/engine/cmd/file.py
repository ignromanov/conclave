"""engine/cmd/file.py — adapter for `engine file <verb>`.

Per-verb sub-subparser design (matches mention.py). Adapters set args._runlog_verb
for the dispatcher run-log hook. The `decision` verb exits 0/1; no stdout on success.
"""
from __future__ import annotations

import sys


def _decision(args) -> int:
    from enginelib.filing import DecisionOpts, file_decision

    args._runlog_verb = "file-decision"
    args._runlog_args = f"slug={args.slug or ''},by={args.by or ''}"
    opts = DecisionOpts(
        slug=args.slug or "",
        by=args.by or "",
        date=args.date or "",
        body_file=args.body_file or "",
        meeting=args.meeting or "",
        session=args.session or "",
        supersedes=args.supersedes or "",
        tags=args.tags or "",
        status=args.status,
        cross_cutting=args.cross_cutting,
    )
    try:
        file_decision(opts)
    except ValueError as e:
        print(f"file-decision: {e}", file=sys.stderr)
        return 1
    return 0


def _handoff(args) -> int:
    from enginelib.filing import HandoffOpts, file_handoff

    args._runlog_verb = "file-handoff"
    args._runlog_args = f"from={args.frm or ''},to={args.to or ''},slug={args.slug or ''}"
    opts = HandoffOpts(
        frm=args.frm or "",
        to=args.to or "",
        date=args.date or "",
        priority=args.priority or "",
        title=args.title or "",
        slug=args.slug or "",
        body_file=args.body_file or "",
        policy=args.policy,
        gh_issue=args.gh_issue,
        no_issue=args.no_issue,
    )
    try:
        file_handoff(opts)
    except ValueError as e:
        print(f"file-handoff: {e}", file=sys.stderr)
        return 1
    return 0


def register(sub) -> None:
    p = sub.add_parser("file", help="File advisor documents (decision, handoff).")
    vsub = p.add_subparsers(dest="file_verb", required=True)

    d = vsub.add_parser("decision", help="File an advisor decision document.")
    d.add_argument("--slug", default=None, help="Decision slug (short identifier).")
    d.add_argument("--by", default=None, help="Advisor id filing the decision.")
    d.add_argument("--date", default=None, help="Decision date (YYYY-MM-DD).")
    d.add_argument("--body-file", dest="body_file", default=None, help="Path to body .md file.")
    d.add_argument("--meeting", default=None, help="Meeting slug for cross-ref append.")
    d.add_argument("--session", default=None, help="Session slug for cross-ref append.")
    d.add_argument("--supersedes", default=None, help="Slug of superseded decision.")
    d.add_argument("--tags", default=None, help="Comma-separated tags.")
    d.add_argument("--status", default="active", help="Status: active|superseded|reverted (default active).")
    d.add_argument("--cross-cutting", dest="cross_cutting", action="store_true",
                   help="Also copy to ops/decisions/{date}-{slug}.md.")
    d.set_defaults(func=_decision)

    hp = vsub.add_parser("handoff", help="File a narrative handoff document (Pattern A).")
    hp.add_argument("--from", dest="frm")
    hp.add_argument("--to")
    hp.add_argument("--date")
    hp.add_argument("--priority")
    hp.add_argument("--title")
    hp.add_argument("--slug")
    hp.add_argument("--body-file", dest="body_file")
    hp.add_argument("--policy", default="")
    hp.add_argument("--gh-issue", dest="gh_issue", default="",
                    help="Resolvable reference: #12, AI#12, owner/repo#12, or a github.com "
                         "issue/pull URL. Required unless --no-issue is given (#55).")
    hp.add_argument("--no-issue", dest="no_issue", default="",
                    help="Why this handoff has no issue to resolve against. Recorded in the "
                         "document, so the gap is a decision rather than an omission.")
    hp.set_defaults(func=_handoff)
