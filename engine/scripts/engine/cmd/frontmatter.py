"""engine/cmd/frontmatter.py — adapter for `engine frontmatter <verb>`."""
from __future__ import annotations


def _backfill(args) -> int:
    args._runlog_verb = "backfill-frontmatter"
    args._runlog_args = f"apply={args.apply},confirm={args.confirm},dry_run={args.dry_run}"

    argv: list[str] = []
    if args.dry_run:
        argv.append("--dry-run")
    if args.apply:
        argv.append("--apply")
    if args.confirm:
        argv.append("--confirm")

    from briefing.backfill_cli import main as _bf_main
    return _bf_main(argv)


def register(sub) -> None:
    p = sub.add_parser("frontmatter", help="Frontmatter migration operations.")
    vsub = p.add_subparsers(dest="frontmatter_verb", required=True)

    b = vsub.add_parser(
        "backfill",
        help="Migrate legacy frontmatter fields in .ai/ ops files. --dry-run is the default.",
    )
    b.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report migration plan without writing files (default behavior).",
    )
    b.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply migration. Must be combined with --confirm.",
    )
    b.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Required safety gate when using --apply.",
    )
    b.set_defaults(func=_backfill)
