"""engine/cmd/register.py — adapter for `engine register <verb>`.

Per-verb sub-subparser design (matches mention.py). Adapters set args._runlog_verb
for the dispatcher run-log hook.
"""
from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path


def _advisor(args) -> int:
    from enginelib import register as reg
    from enginelib.paths import (
        forge_dir,
        project_agents_dir,
        project_claude_dir,
        project_skills_dir,
    )

    args._runlog_verb = "register-advisor"
    args._runlog_args = f"dry_run={1 if args.dry_run else 0}"
    roster_env = os.environ.get("CONCLAVE_ROSTER_DIR")
    # Project-side .claude (sibling of the .conclave DATA root), NOT repo_root()/.claude:
    # in the plugin layout repo_root() is <project>/.conclave, so repo_root()/.claude
    # would be <project>/.conclave/.claude (nonexistent) and discover nothing. The
    # project_* helpers collapse to repo_root()/.claude in the in-repo/test layout.
    roster_dir = Path(roster_env) if roster_env else project_skills_dir()
    agents_dir = project_agents_dir()
    advisors = reg.discover_advisors(roster_dir)
    table = reg.agents_table(advisors, agents_dir)
    if args.dry_run:
        print("=== CLAUDE.md Custom Agents (preview) ===")
        print(table)
        print()
        print("=== Quorum Advisor Registry (preview) ===")
        for a in advisors:
            print(f"- {a}")
        return 0
    print("<!-- forge:registry:begin -->")
    print(table)
    print("<!-- forge:registry:end -->")
    claude_md = project_claude_dir() / "CLAUDE.md"
    forge_skill = forge_dir() / "SKILL.md"
    print(
        f"NOTE: apply the output above between markers in {claude_md} and {forge_skill} via Edit.",
        file=sys.stderr,
    )
    return 0


def _executor(args) -> int:
    from enginelib import register as reg

    args._runlog_verb = "register-executor"
    opts = reg.ExecutorOpts(
        chosen_name=args.chosen_name or "",
        role=args.role or "",
        emoji=args.emoji or "",
        color=args.color or "",
        tools=args.tools or "",
    )
    today = datetime.now(UTC).strftime("%Y-%m-%d")
    try:
        agent_def, mem_dir = reg.create_executor(opts, today, dry_run=args.dry_run)
    except reg.EmojiCollisionError as e:
        print(str(e), file=sys.stderr)
        return 3
    except ValueError as e:
        print(str(e), file=sys.stderr)
        return 2
    if args.dry_run:
        print(f"[dry-run] would create: {agent_def} + {mem_dir}", file=sys.stderr)
    else:
        print(f"[register-executor] scaffolded: {agent_def}", file=sys.stderr)
        print(f"[register-executor] memory: {mem_dir}/MEMORY.md", file=sys.stderr)
        print(
            "[register-executor] next: dispatch executor to fill inline-voice + contract "
            "placeholders via self-introduction",
            file=sys.stderr,
        )
    return 0


def register(sub) -> None:
    p = sub.add_parser("register", help="Registration commands.")
    vsub = p.add_subparsers(dest="register_verb", required=True)

    a = vsub.add_parser("advisor", help="Discover advisors and emit the CLAUDE.md Custom-Agents table.")
    a.add_argument("--dry-run", dest="dry_run", action="store_true", help="Preview mode (no marker output).")
    a.add_argument("--rebuild", action="store_true", help="Accepted for parity with register-advisor.sh (no-op).")
    a.set_defaults(func=_advisor)

    e = vsub.add_parser("executor", help="Scaffold a new Executor agent.")
    e.add_argument("--chosen-name", dest="chosen_name", help="Self-chosen identifier (alphanumeric, hyphen, underscore).")
    e.add_argument("--role", help="Executor role (dev|test).")
    e.add_argument("--emoji", help="Single emoji glyph (must not collide with reserved).")
    e.add_argument("--color", help="Color name from color-palette.md pool.")
    e.add_argument("--tools", default="", help="Comma-separated tool scope (default: the role's set — dev writes, test reads).")
    e.add_argument("--dry-run", dest="dry_run", action="store_true", help="Validate inputs and exit without writing files.")
    e.set_defaults(func=_executor)
