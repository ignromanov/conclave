"""engine/cmd/find.py — adapter for `engine find <verb>`."""
from __future__ import annotations


def _references(args) -> int:
    from enginelib.find import find_references
    from enginelib.paths import engine_root

    args._runlog_verb = "find-references"
    args._runlog_args = f"pattern={args.pattern}"

    for line in find_references(args.pattern, engine_root()):
        print(line)
    return 0


def register(sub) -> None:
    p = sub.add_parser("find", help="Search engine root for patterns.")
    vsub = p.add_subparsers(dest="find_verb", required=True)

    r = vsub.add_parser(
        "references",
        help="Grep engine_root/.claude + CLAUDE.md for an extended-regex pattern.",
    )
    r.add_argument("pattern", help="Extended regex pattern to search for.")
    r.set_defaults(func=_references)
