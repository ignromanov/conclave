"""engine/cmd/audit.py — adapter for `engine audit <name>`.

Owns argparse, print, sys.exit contract (Q5). Delegates to per-audit adapter closures.

Extension contract (post-3A.2): each `_AUDITS[name]` closure is `(args: Namespace) -> int`
and owns its own output + exit code. Findings audits call `return _emit(module.run(...))` to
get the shared CRIT/WARN format and 0/1/2 exit codes. Non-Findings audits (scope-collision,
agent-configs) format and return their own exit codes (e.g. agent-configs 0/2, scope-collision 0/3).
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from enginelib.audit import Findings


def _emit(findings: Findings) -> int:
    """Print CRIT/WARN lines + summary; return 0 (clean) / 1 (crit) / 2 (warn)."""
    for msg in findings.crit:
        print(f"CRIT: {msg}")
    for msg in findings.warn:
        print(f"WARN: {msg}")
    print(f"=== Summary: {len(findings.crit)} CRIT, {len(findings.warn)} WARN ===")
    if findings.crit:
        return 1
    if findings.warn:
        return 2
    return 0


def _specs_registry(args: argparse.Namespace) -> int:
    from enginelib.audit import specs_registry
    from enginelib.paths import repo_root

    root = repo_root()
    specs = root / "ops" / "specs"
    return _emit(specs_registry.run(specs, specs / "REGISTRY.md"))


def _architecture_doc(args: argparse.Namespace) -> int:
    from enginelib.audit import architecture_doc
    from enginelib.paths import engine_root

    arch = (
        Path(args.arch)
        if args.arch
        else engine_root().parent / "skills" / "forge-operations" / "ARCHITECTURE.md"
    )
    scripts_dir = Path(args.scripts_dir) if args.scripts_dir else engine_root() / "scripts"
    contracts_dir = (
        Path(args.contracts_dir) if args.contracts_dir else engine_root() / "contracts"
    )
    return _emit(architecture_doc.run(arch, scripts_dir, contracts_dir))


def _phantom_skills(args: argparse.Namespace) -> int:
    from enginelib import paths
    from enginelib.audit import phantom_skills

    # Advisors live project-side (.claude/skills), not in engine/skills — default there
    # so the scan isn't silently empty (#3 D2). Agent defs are the sibling agents/ dir.
    skills_dir = Path(args.skills_dir) if args.skills_dir else paths.project_skills_dir()
    agents_dir = skills_dir.parent / "agents"
    findings = phantom_skills.run(skills_dir, agents_dir)
    for msg in findings.warn:
        print(f"WARN: {msg}")
    return 0


def _advisor_naming(args: argparse.Namespace) -> int:
    from enginelib.audit import advisor_naming
    from enginelib.paths import project_agents_dir

    return _emit(advisor_naming.run(project_agents_dir()))


def _registry_consistency(args: argparse.Namespace) -> int:
    from enginelib.audit import registry_consistency
    from enginelib.paths import project_claude_dir

    claude = project_claude_dir()
    return _emit(registry_consistency.run(
        claude / "skills",
        claude / "agents",
        claude / "CLAUDE.md",
    ))


def _overlays(args: argparse.Namespace) -> int:
    from enginelib.audit import overlays
    from enginelib.paths import contracts_dir, project_skills_dir

    rpt = overlays.run(project_skills_dir(), contracts_dir())
    for w in rpt.warn:
        print(f"WARN: {w}")
    for i in rpt.info:
        print(f"INFO: {i}")
    return 0


def _scope_collision(args: argparse.Namespace) -> int:
    from enginelib.audit import scope_collision
    from enginelib.paths import engine_root, project_agents_dir

    if args.agents_dir:
        dirs = [Path(d) for d in args.agents_dir]
    else:
        dirs = [
            project_agents_dir(),
            engine_root() / ".claude" / "agents",
        ]

    if not any(d.is_dir() for d in dirs):
        print("ERROR: no agents dirs found", file=sys.stderr)
        return 1

    collisions = scope_collision.run(dirs)

    if not collisions:
        print("Cat11 scope-collision: OK (no overlapping owns: across agents)")
        return 0

    print("Cat11 scope-collision: CRIT — overlapping owns: detected")
    for tok, agents in sorted(collisions.items()):
        print(f"  owns:{tok} claimed by: {', '.join(agents)}")
    return 3


def _agent_configs(args: argparse.Namespace) -> int:
    from enginelib.audit import agent_configs
    from enginelib.paths import project_claude_dir

    scan_dir = project_claude_dir()
    rpt = agent_configs.run(scan_dir)
    print(f"=== audit agent-configs — scanning {scan_dir} ===")
    for cat in rpt.categories:
        print("")
        print(f"[{cat.severity}] {cat.label}")
        for m in cat.matches[:5]:
            print(m)
    print("")
    print(f"=== Summary: {rpt.crit} CRIT, {rpt.warn} WARN ===")
    return 2 if rpt.crit > 0 else 0


def _bloat(args: argparse.Namespace) -> int:
    from enginelib.audit import bloat
    from enginelib.paths import briefings_dir, skills_dir

    skills = Path(args.skills_dir) if args.skills_dir else skills_dir()
    if args.forge_dir:
        forge_root = Path(args.forge_dir)
        forge_refs = forge_root / "references"
        forge_skill = forge_root / "SKILL.md"
    else:
        forge_refs = None
        forge_skill = None
    return _emit(bloat.run(skills, briefings_dir(), forge_refs, forge_skill))


def _versions(args: argparse.Namespace) -> int:
    from enginelib.audit import versions
    from enginelib.paths import forge_references_dir, skills_dir

    skills = Path(args.skills_dir) if args.skills_dir else skills_dir()
    if args.skills_dir:
        standard_file = skills / "team.forge" / "references" / "agent-model-version.md"
    else:
        standard_file = forge_references_dir() / "agent-model-version.md"
    rpt = versions.run(skills, standard_file)
    print(f"standard: {rpt.standard}")
    for line in rpt.entries:
        print(line)
    return 1 if rpt.crit > 0 else (2 if rpt.warn > 0 else 0)


def _routing_targets(args: argparse.Namespace) -> int:
    from enginelib.audit import routing_targets
    from enginelib.paths import engine_root

    repo = engine_root().parent
    agents = repo / "agents"
    surfaces: list[Path] = []
    for d in (repo / "commands", agents):
        surfaces.extend(sorted(d.rglob("*.md")))
    roster = frozenset(
        p.stem.removeprefix("conclave-").removeprefix("exec-") for p in agents.glob("*.md")
    )
    roots = [repo / "skills", repo / "engine" / "skills"]
    return _emit(routing_targets.run(surfaces, roots, roster))


def _skills(args: argparse.Namespace) -> int:
    from datetime import date

    from enginelib.audit import skills as skills_audit
    from enginelib.paths import repo_root

    today = date.today().isoformat()
    rpt = skills_audit.run(
        skills_audit.user_skills_dir(),
        repo_root() / ".claude" / "skills",
        skills_audit.plugins_json(),
        skills_audit.settings_json(),
        today,
    )
    audit_dir = repo_root() / "agent-memory" / "advisors" / "audits"
    audit_dir.mkdir(parents=True, exist_ok=True)
    out = audit_dir / f"{today}-skills.md"
    out.write_text(rpt.markdown, encoding="utf-8")
    if not args.quiet:
        print(f"[audit-skills] wrote={out}")
        print(f"[audit-skills] user-skills={rpt.user_count} project-skills={rpt.project_count} plugins={rpt.plugin_count}")
    return 0


# Maps CLI audit name → adapter callable `(args: Namespace) -> int`.
# Findings audits: call `_emit(module.run(...))`. Non-Findings: own their format + exit code.
_AUDITS: dict[str, Callable[[argparse.Namespace], int]] = {
    "specs-registry": _specs_registry,
    "scope-collision": _scope_collision,
    "bloat": _bloat,
    "architecture-doc": _architecture_doc,
    "phantom-skills": _phantom_skills,
    "registry-consistency": _registry_consistency,
    "advisor-naming": _advisor_naming,
    "overlays": _overlays,
    "agent-configs": _agent_configs,
    "skills": _skills,
    "versions": _versions,
    "routing-targets": _routing_targets,
}


def register(subparsers: argparse._SubParsersAction) -> None:  # type: ignore[type-arg]
    p = subparsers.add_parser("audit", help="Run a named audit check.")
    p.add_argument("name", choices=list(_AUDITS), help="Audit to run.")
    p.add_argument(
        "--agents-dir",
        dest="agents_dir",
        action="append",
        metavar="DIR",
        help="Override agents dir (repeatable; used by scope-collision).",
    )
    p.add_argument(
        "--arch",
        dest="arch",
        default=None,
        metavar="FILE",
        help="Override ARCHITECTURE.md path (used by architecture-doc).",
    )
    p.add_argument(
        "--scripts-dir",
        dest="scripts_dir",
        default=None,
        metavar="DIR",
        help="Override scripts dir (used by architecture-doc).",
    )
    p.add_argument(
        "--contracts-dir",
        dest="contracts_dir",
        default=None,
        metavar="DIR",
        help="Override contracts dir (used by architecture-doc).",
    )
    p.add_argument(
        "--skills-dir",
        dest="skills_dir",
        default=None,
        metavar="DIR",
        help="Override skills dir (used by phantom-skills).",
    )
    p.add_argument(
        "--forge-dir",
        dest="forge_dir",
        default=None,
        metavar="DIR",
        help="Override forge-operations root (SKILL.md + references/; used by bloat).",
    )
    p.add_argument(
        "--quiet",
        action="store_true",
        dest="quiet",
        default=False,
        help="Suppress stdout (used by skills).",
    )
    p.set_defaults(func=_run)


def _run(args: argparse.Namespace) -> int:
    return _AUDITS[args.name](args)
