"""engine/cmd/mention.py — adapter for `engine mention <verb>`.

Per-verb sub-subparser design (matches lifecycle.py). Adapters set args._runlog_verb
for the dispatcher run-log hook.
"""
from __future__ import annotations

import sys


def _create(args) -> int:
    from enginelib.mention import MentionOpts, create

    args._runlog_verb = "mention-create"
    args._runlog_args = f"from={args.frm or ''},to={args.to or ''}"
    opts = MentionOpts(
        frm=args.frm or "",
        to=args.to or "",
        body_file=args.body_file or "",
        priority=args.priority,
        now=args.now or "",
        ref_session=args.ref_session or "",
        ref_decision=args.ref_decision or "",
        ref_issue=args.ref_issue or "",
    )
    try:
        mid = create(opts)
    except (ValueError, FileExistsError) as e:
        print(f"mention: {e}", file=sys.stderr)
        return 1
    print(mid)
    return 0


def _resolve(args) -> int:
    from enginelib.mention import resolve

    args._runlog_verb = "mention-resolve"
    args._runlog_args = f"id={args.id or ''},by={args.by or ''}"
    try:
        mid = resolve(args.id or "", args.by or "", args.note, args.now)
    except ValueError as e:
        print(f"resolve-mention: {e}", file=sys.stderr)
        return 1
    print(mid)
    return 0


def register(sub) -> None:
    p = sub.add_parser("mention", help="Cross-advisor mention commands.")
    vsub = p.add_subparsers(dest="mention_verb", required=True)

    c = vsub.add_parser("create", help="File a cross-advisor mention.")
    c.add_argument("--from", dest="frm", default=None, help="Sending advisor id.")
    c.add_argument("--to", default=None, help="Receiving advisor id.")
    c.add_argument("--body-file", dest="body_file", default=None, help="Path to body .md file.")
    c.add_argument("--priority", default="p2", help="Priority: p0|p1|p2|fyi (default p2).")
    c.add_argument("--now", default=None, help="ISO-8601 timestamp (default: local time).")
    c.add_argument("--ref-session", dest="ref_session", default=None, help="Session reference slug.")
    c.add_argument("--ref-decision", dest="ref_decision", default=None, help="Decision reference slug.")
    c.add_argument("--ref-issue", dest="ref_issue", default=None, help="Issue reference (e.g. AI#N).")
    c.set_defaults(func=_create)

    rp = vsub.add_parser("resolve", help="Resolve an open mention (open→archive).")
    rp.add_argument("--id", dest="id", default=None, help="Mention id.")
    rp.add_argument("--by", dest="by", default=None, help="Resolving advisor.")
    rp.add_argument("--note", dest="note", default="", help="Resolution note.")
    rp.add_argument("--now", dest="now", default="", help="ISO-8601 timestamp (default now).")
    rp.set_defaults(func=_resolve)
