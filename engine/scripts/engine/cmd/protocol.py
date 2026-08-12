"""engine/cmd/protocol.py — adapter for `engine protocol <verb>` (spec 108 P0)."""
from __future__ import annotations

TIERS = ("quick", "work")
TASK_TYPES = ("dev", "content", "research", "review", "advisory")


def _registry_root(paths) -> "object":
    """The base the three fixed homes hang off.

    NOT `repo_root()`: that is the DATA root (`.conclave`), which holds no `skills/`
    tree at all — a scanner aimed there finds nothing, and `assemble`'s always-exit-0
    contract makes finding nothing look exactly like success.

    NOT `engine_root()` either: the convention locked in paths.py is
    `CONCLAVE_ENGINE_ROOT = the engine/ dir`, with skills living at
    `engine_root().parent/skills`. That is the same resolution `forge_dir()` and
    `plugin_agents_dir()` already use.
    """
    return paths.engine_root().parent


def _load(args):
    from enginelib import paths
    from enginelib.protocols.registry import homes, scan

    advisor_dir = None
    if getattr(args, "advisor", None):
        # advisor_skill_dir lives in enginelib.paths (NOT enginelib.advisors), and its
        # `artifact` parameter exists for exactly our case: a half-migrated advisor can
        # own BOTH conclave-<id>/ and legacy team.<id>/, and resolving on directory
        # existence alone hands back the one the files are not in.
        try:
            advisor_dir = paths.advisor_skill_dir(args.advisor, artifact="protocols") / "protocols"
        except Exception:
            advisor_dir = None
    return scan(homes(_registry_root(paths), advisor_dir))


def _assemble(args) -> int:
    args._runlog_verb = "protocol-assemble"
    args._runlog_args = f"tier={args.tier} task_type={args.task_type}"

    from enginelib.protocols.assemble import select

    files, errors = _load(args)
    chosen = select(files, args.tier, args.task_type)

    for f in chosen:
        print(f"<!-- protocol: {f.path.name} stages={','.join(f.meta.stages)} -->")
        if f.meta.is_adapter:
            print(f"<!-- adapter → external skill: {f.meta.external_skill} -->")
        print(f.path.read_text(encoding="utf-8"))
        print()

    if errors:
        # Loud in CONTENT, never via exit code: a non-zero exit from a !-block aborts
        # the whole command load (measured on plugin-dev:command-development).
        print("=== ASSEMBLY ERROR — the registry is not clean ===")
        for e in errors:
            print(f"  {e.path}: {e.reason}")
        print("=== these protocols did NOT load; treat the session as ungoverned for them ===")

    return 0


def _list(args) -> int:
    args._runlog_verb = "protocol-list"
    args._runlog_args = ""

    files, errors = _load(args)
    print(f"{'PROTOCOL':<40} {'STAGES':<28} {'TIERS':<12} {'BINDING':<10}")
    print("-" * 92)
    for f in sorted(files, key=lambda p: p.path.name):
        print(
            f"{f.path.name:<40} {','.join(f.meta.stages):<28} "
            f"{','.join(f.meta.tiers):<12} {f.meta.binding:<10}"
        )
    print(f"\n{len(files)} protocol(s), {len(errors)} error(s)")
    for e in errors:
        print(f"  ERROR {e.path}: {e.reason}")
    return 0


def register(sub) -> None:
    p = sub.add_parser("protocol", help="Protocol registry: assemble and inspect.")
    vsub = p.add_subparsers(dest="protocol_verb", required=True)

    a = vsub.add_parser("assemble", help="Emit the protocol set for one session.")
    a.add_argument("--tier", choices=TIERS, required=True)
    a.add_argument("--task-type", choices=TASK_TYPES, required=True, dest="task_type")
    a.add_argument("--advisor", default=None, help="Bound advisor id; adds their own home.")
    a.set_defaults(func=_assemble)

    ls = vsub.add_parser("list", help="One row per registry file.")
    ls.add_argument("--advisor", default=None)
    ls.set_defaults(func=_list)
