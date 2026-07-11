"""engine/cmd/model.py — adapter for `engine model <verb>`."""
from __future__ import annotations

import sys


def _bump(args) -> int:
    from enginelib.model import bump, current_standard
    from enginelib.paths import advisor_skill_dir, forge_references_dir, project_skills_dir

    args._runlog_verb = "model-bump"
    args._runlog_args = (
        f"target={args.advisor or 'all'},"
        f"set_all={args.set_all},"
        f"dry_run={args.dry_run}"
    )

    if not args.advisor and not args.all:
        print("usage: engine model bump --advisor <id> | --all", file=sys.stderr)
        return 1

    # Hired advisors live project-side under .claude/skills/conclave-<id> (#55),
    # not in the engine's own skills/ tree — resolve the bump base accordingly.
    sd = project_skills_dir()
    ref = forge_references_dir() / "agent-model-version.md"
    standard = current_standard(ref)
    target = args.advisor if args.advisor else "*"

    results = bump(
        target,
        set_all=args.set_all,
        dry_run=args.dry_run,
        skills_dir=sd,
        standard=standard,
    )

    for r in results:
        a = r["advisor"]
        action = r["action"]
        if action == "missing":
            print(f"missing: {advisor_skill_dir(a, sd) / 'SKILL.md'}", file=sys.stderr)
        elif action == "skip-no-forge":
            print(f"SKIP: {a} has no forge: block in frontmatter", file=sys.stderr)
        elif action == "would-bump":
            print(f"would bump {a} model-version → {standard}")
        elif action == "bumped":
            print(f"bumped: {a} → {standard}")

    return 0


def register(sub) -> None:
    p = sub.add_parser("model", help="Advisor model versioning operations.")
    vsub = p.add_subparsers(dest="model_verb", required=True)

    b = vsub.add_parser(
        "bump",
        help="Stamp forge.model-version in advisor SKILL.md frontmatter to current standard.",
    )
    target = b.add_mutually_exclusive_group()
    target.add_argument(
        "--advisor",
        metavar="id",
        default=None,
        help="Single advisor id (without team. prefix).",
    )
    target.add_argument(
        "--all",
        action="store_true",
        dest="all",
        default=False,
        help="Stamp all non-lifecycle advisors.",
    )
    b.add_argument(
        "--set-all",
        action="store_true",
        dest="set_all",
        default=False,
        help="Also stamp hired-by and last-evolve (use on fresh hire).",
    )
    b.add_argument(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        default=False,
        help="Preview without writing.",
    )
    b.set_defaults(func=_bump)
