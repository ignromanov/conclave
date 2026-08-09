"""engine/cmd/skill.py — adapter for `engine skill <verb>`."""
from __future__ import annotations


def _verify(args) -> int:
    from enginelib.skill import verify

    names = args.names
    args._runlog_verb = "skill-verify"
    args._runlog_args = f"names={','.join(names)}"

    # Single-name mode is unchanged (backward-compatible): print the bare resolved
    # path (or nothing) and exit 0 — callers capture $(engine skill verify X).
    if len(names) == 1:
        result = verify(names[0])
        if result is not None:
            print(result)
        return 0

    # Batch mode (G1 gate): one status line per name; exit 1 if ANY name is a phantom.
    # Passing the whole candidate list as argv removes the shell word-splitting that
    # made a hand-rolled per-name loop mangle every entry after the first.
    missing = 0
    for name in names:
        result = verify(name)
        if result is None:
            print(f"PHANTOM\t{name}")
            missing += 1
        else:
            print(f"OK\t{name}\t{result}")
    return 1 if missing else 0


def _stocktake(args) -> int:
    import json
    import sys
    import time
    from collections import Counter
    from datetime import date

    from enginelib import paths
    from enginelib.skill import stocktake_rows

    args._runlog_verb = "skill-stocktake"
    args._runlog_args = f"mode={'full' if args.full else 'quick'}"

    skills_dir = paths.repo_root() / ".claude" / "skills"
    if not skills_dir.is_dir():
        print(f"no skills dir: {skills_dir}", file=sys.stderr)
        return 1

    now_epoch = int(time.time())
    today = date.today().isoformat()
    sessions_dir = paths.repo_root() / "agent-memory" / "advisors" / "sessions"
    rows = stocktake_rows(skills_dir, sessions_dir, now_epoch)

    if args.full:
        output_dir = paths.repo_root() / "agent-memory" / "skill-stocktake"
        out_file = output_dir / f"{today}-results.json"

        print(f"Skill Stocktake — full mode → {out_file}")

        output_dir.mkdir(parents=True, exist_ok=True)
        # missing_skillmd rows are excluded from --full (matches bash: scan_full skips
        # dirs without SKILL.md before calling evaluate_skill).
        skills_json = [
            {
                "name": row["name"],
                "verdict": row["verdict"],
                "age_days": row["age_days"],
                "lines": row["lines"],
                "bytes": row["bytes"],
                "invocations_30d": row["invocations"],
                "mtime_epoch": row["mtime"],
            }
            for row in rows
            if isinstance(row["age_days"], int)
        ]
        data = {"date": today, "mode": "full", "skills": skills_json}
        out_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

        print(f"Wrote {out_file}")
        print("Verdict summary:")
        counter = Counter(
            row["verdict"] for row in rows if isinstance(row["age_days"], int)
        )
        for verdict, count in counter.most_common():
            print(f"{count:>7} {verdict}")
    else:
        # --quick: only skills changed in last 7 days (age_days <= 7).
        # missing_skillmd rows have age_days="N/A" (not int) → naturally excluded.
        print("Skill Stocktake — quick mode (changed last 7 days)")
        print("")
        print(
            f"{'SKILL':<40} {'VERDICT':<25} {'AGE-DAYS':<10} "
            f"{'LINES':<8} {'BYTES':<8} {'INVOCATIONS':<15}"
        )
        print("-" * 100)

        recent = [
            r for r in rows
            if isinstance(r["age_days"], int) and r["age_days"] <= 7
        ]
        for row in recent:
            print(
                f"{row['name']:<40} {row['verdict']:<25} {row['age_days']:<10} "
                f"{row['lines']:<8} {row['bytes']:<8} {row['invocations']:<15}"
            )

        print("")
        print(f"Total skills changed in last 7d: {len(recent)}")

    return 0


def _install(args) -> int:
    """Install a skill package, but only from an allow-listed source (spec 112 §2.2).

    Exit codes follow the house convention: 2 = malformed request, 3 = refused by policy
    (the same code an emoji collision returns — blocked, not broken), 0 = installed or
    dry-run, 1 = the installer itself failed.
    """
    import shutil
    import subprocess
    import sys

    from enginelib import paths
    from enginelib.skill_install import (
        install_command,
        is_allowed,
        package_source,
        parse_allowlist,
        refusal_message,
    )

    pkg = args.package
    args._runlog_verb = "skill-install"
    args._runlog_args = f"package={pkg}"

    if package_source(pkg) is None:
        print(
            f"malformed package: {pkg!r} (expected owner/repo or owner/repo@skill)",
            file=sys.stderr,
        )
        return 2

    allowlist_file = paths.forge_references_dir() / "skill-sources.md"
    if not allowlist_file.is_file():
        print(f"no allowlist at {allowlist_file} — refusing everything", file=sys.stderr)
        return 3

    allowlist = parse_allowlist(allowlist_file.read_text(encoding="utf-8"))
    if not is_allowed(pkg, allowlist):
        print(refusal_message(pkg, str(allowlist_file)), file=sys.stderr)
        return 3

    cmd = install_command(pkg)
    if args.dry_run:
        print(f"would install: {' '.join(cmd)}")
        return 0

    if shutil.which(cmd[0]) is None:
        print(
            f"{cmd[0]} CLI not found on PATH — install it, or run: {' '.join(cmd)}",
            file=sys.stderr,
        )
        return 1

    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"installer failed ({result.returncode}): {' '.join(cmd)}", file=sys.stderr)
        return 1
    print(f"installed: {pkg}")
    return 0


def _bind(args) -> int:
    """Write a verified skill into an agent-def's `skills:` list (spec 112 T3).

    Exit codes: 2 = no such agent, 3 = the skill does not resolve (binding a phantom is the
    defect this codebase keeps re-shipping), 0 = bound, already bound, or dry-run.
    """
    import sys

    from enginelib import paths
    from enginelib.skill import verify
    from enginelib.skill_bind import BlockSequenceUnsupported, bind_skill

    agent, skill = args.agent, args.skill
    args._runlog_verb = "skill-bind"
    args._runlog_args = f"agent={agent} skill={skill}"

    # Two homes, both resolved — executor defs are CODE, hired advisor defs are project-side.
    # Never concatenate a path here; the two repos move independently.
    candidates = [
        paths.plugin_agents_dir() / f"{agent}.md",
        paths.project_agents_dir() / f"{agent}.md",
    ]
    target = next((p for p in candidates if p.is_file()), None)
    if target is None:
        print(f"no agent-def named {agent!r}; looked in:", file=sys.stderr)
        for p in candidates:
            print(f"  {p}", file=sys.stderr)
        return 2

    if verify(skill) is None:
        print(
            f"phantom skill: {skill!r} does not resolve — not bound.\n"
            f"  install it first: engine skill install <owner/repo@{skill}>",
            file=sys.stderr,
        )
        return 3

    before = target.read_text(encoding="utf-8")
    try:
        after, changed = bind_skill(before, skill)
    except BlockSequenceUnsupported as e:
        print(f"{target}: {e}", file=sys.stderr)
        return 2

    if not changed:
        print(f"already bound: {skill} → {agent}")
        return 0

    line = next(ln for ln in after.splitlines() if ln.startswith("skills:"))
    if args.dry_run:
        print(f"would write {target}\n  {line}")
        return 0

    target.write_text(after, encoding="utf-8")
    print(f"bound: {skill} → {agent} ({target})\n  {line}")
    return 0


def register(sub) -> None:
    p = sub.add_parser("skill", help="Skill resolution and related operations.")
    vsub = p.add_subparsers(dest="skill_verb", required=True)

    v = vsub.add_parser("verify", help="Print resolved path to a skill's SKILL.md, or nothing if not found.")
    v.add_argument(
        "names",
        nargs="+",
        metavar="name",
        help="Skill name(s) (plain / plugin:skill / team.<advisor>). One name → bare "
             "path or empty, exit 0. Multiple → batch mode: exit 1 if any is a phantom.",
    )
    v.set_defaults(func=_verify)

    i = vsub.add_parser(
        "install",
        help="Install a skill package from an allow-listed source (skills/forge-operations/references/skill-sources.md).",
    )
    i.add_argument("package", help="Package spec: owner/repo or owner/repo@skill.")
    i.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the install command and exit 0 without running it.",
    )
    i.set_defaults(func=_install)

    b = vsub.add_parser(
        "bind",
        help="Add a verified skill to an agent-def's skills: list (preloaded at dispatch).",
    )
    b.add_argument("--agent", required=True, help="Agent-def stem, e.g. exec-techne-skills.")
    b.add_argument("--skill", required=True, help="Skill id; must resolve via `engine skill verify`.")
    b.add_argument("--dry-run", action="store_true", help="Print the resulting line; write nothing.")
    b.set_defaults(func=_bind)

    s = vsub.add_parser("stocktake", help="Quarterly audit of .claude/skills/.")
    mode = s.add_mutually_exclusive_group()
    mode.add_argument(
        "--quick",
        action="store_false",
        dest="full",
        help="Show only skills changed in last 7 days (default).",
    )
    mode.add_argument(
        "--full",
        action="store_true",
        dest="full",
        help="Audit all skills; write JSON to agent-memory/skill-stocktake/<date>-results.json.",
    )
    s.set_defaults(func=_stocktake, full=False)
