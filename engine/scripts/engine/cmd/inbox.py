"""engine/cmd/inbox.py — adapter for `engine inbox <verb>`."""
from __future__ import annotations

import sys


def shq(s: str) -> str:
    """Always single-quote for shell display.

    shq("foo") == "'foo'" — never omits quotes for simple strings.
    Do NOT replace with shlex.quote (which omits quotes for alphanumeric strings).
    """
    return "'" + s.replace("'", "'\\''") + "'"


def _to_issues(args) -> int:
    from pathlib import Path

    import enginelib.gh as gh
    from enginelib.inbox import parse_inbox

    args._runlog_verb = "inbox-to-issues"
    args._runlog_args = (
        f"advisor={args.advisor or ''},"
        f"mode={'execute' if args.execute else 'dry-run'}"
    )

    if not args.advisor:
        print("inbox-to-gh: --advisor is required", file=sys.stderr)
        return 2
    if not args.file:
        print("inbox-to-gh: --file is required", file=sys.stderr)
        return 2
    p = Path(args.file)
    if not p.is_file():
        print(f"inbox-to-gh: file not found: {args.file}", file=sys.stderr)
        return 2

    specs = parse_inbox(p.read_text(encoding="utf-8"), args.advisor)

    for spec in specs:
        if args.skip_stale:
            print(f'keep "{spec.title}"? [y/N] ', end="", file=sys.stderr, flush=True)
            ans = sys.stdin.readline().rstrip("\n")
            if ans not in ("y", "Y", "yes", "YES"):
                continue

        if args.execute:
            gh.create_issue(spec.title, spec.body, spec.labels)
        else:
            parts = (
                ["gh", "issue", "create",
                 "--title", shq(spec.title),
                 "--body", shq(spec.body)]
                + [x for label in spec.labels for x in ("--label", shq(label))]
            )
            print(" ".join(parts))

    return 0


def register(sub) -> None:
    p = sub.add_parser("inbox", help="Inbox migration operations.")
    vsub = p.add_subparsers(dest="inbox_verb", required=True)

    v = vsub.add_parser("to-issues", help="Parse inbox.md into gh issue create commands.")
    v.add_argument("--advisor", default="", help="Advisor label name (required).")
    v.add_argument("--file", dest="file", default="", help="Path to inbox.md (required).")
    mode = v.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run", action="store_false", dest="execute",
        help="Print commands without executing (default).",
    )
    mode.add_argument(
        "--execute", action="store_true", dest="execute",
        help="Invoke gh issue create.",
    )
    v.add_argument("--skip-stale", action="store_true", dest="skip_stale",
                   help="Prompt y/N per item before creating.")
    v.set_defaults(func=_to_issues, execute=False)
