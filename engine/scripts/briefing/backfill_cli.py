"""backfill_cli.py — CLI entrypoint for `python3 -m briefing.backfill_cli`.

Invoked by backfill-frontmatter.sh. Parses --dry-run / --apply --confirm flags
and calls backfill.backfill_tree(). --dry-run is the default.
"""
from __future__ import annotations

import argparse
import sys

from briefing.backfill import BackfillPlan, backfill_tree
from briefing.paths import repo_root


def _print_plan(plans: list[BackfillPlan], dry_run: bool) -> None:
    mode = "DRY RUN" if dry_run else "APPLIED"
    total_migrate = sum(len(p.to_migrate) for p in plans)
    total_skipped = sum(p.skipped for p in plans)
    total_files = sum(p.total_files for p in plans)

    print(f"[backfill-frontmatter] mode={mode}")
    print(f"  total files scanned : {total_files}")
    print(f"  to migrate          : {total_migrate}")
    print(f"  already migrated    : {total_skipped}")
    print()

    for plan in plans:
        if not plan.to_migrate:
            continue
        print(f"  [{plan.page_type}] {len(plan.to_migrate)} file(s):")
        for path in plan.to_migrate:
            print(f"    {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="backfill-frontmatter",
        description=(
            "Migrate legacy frontmatter fields in .ai/ ops files. "
            "--dry-run is the default and safe to run any time."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Report migration plan without writing any files (default behavior).",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply the migration. Must be combined with --confirm.",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        default=False,
        help="Required safety gate when using --apply.",
    )
    args = parser.parse_args(argv)

    # Safety gate: --apply without --confirm is an error.
    if args.apply and not args.confirm:
        print(
            "backfill-frontmatter: --apply requires --confirm.\n"
            "Run with --dry-run first to review the plan, then:\n"
            "  python -m engine frontmatter backfill --apply --confirm",
            file=sys.stderr,
        )
        return 1

    # Determine mode: dry_run unless --apply --confirm both set.
    dry_run = not (args.apply and args.confirm)

    try:
        root = repo_root()
    except RuntimeError:
        if dry_run:
            print("[backfill-frontmatter] no instance root configured — nothing to scan")
            return 0
        raise

    plans = backfill_tree(root, dry_run=dry_run)
    _print_plan(plans, dry_run=dry_run)

    return 0


if __name__ == "__main__":
    sys.exit(main())
