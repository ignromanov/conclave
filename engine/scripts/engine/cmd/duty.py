"""engine/cmd/duty.py — adapter for `engine duty <verb>` (spec 091).

Owns argparse, print, and the exit-code contract (Q5). All logic lives in enginelib.duties,
which is I/O-free. Exit codes follow the house convention set by cmd/audit.py:

    0 = clean · 1 = error-severity findings · 2 = warning-severity findings

Verbs:
    validate  — compose the base + an agent manifest and report findings
    project   — write COMPUTED-DUTIES.md for an agent
    scaffold  — copy the KAD template into an agent's duties/ dir
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from enginelib.duties.ledger import OUTCOMES
from enginelib.duties.model import AgentKind, Manifest
from enginelib.duties.validate import Finding


def _emit(findings: list[Finding]) -> int:
    """Print findings; return 0 (clean) / 1 (error) / 2 (warning). Mirrors cmd/audit.py."""
    for f in findings:
        print(f"{f.severity.upper()}: {f.code} — {f.message}")
    errors = sum(1 for f in findings if f.severity == "error")
    warnings = len(findings) - errors
    print(f"=== Summary: {errors} error, {warnings} warning ===")
    if errors:
        return 1
    if warnings:
        return 2
    return 0


def _load_manifest(path: Path | None) -> Manifest:
    """Read a roster yaml into a Manifest. An absent path is the empty manifest — a fresh
    instance has no agent-written norms, and that is a clean state, not a failure."""
    if path is None or not path.is_file():
        return Manifest(version=1)
    import yaml

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return Manifest(
        version=int(data.get("version", 1)),
        roles=data.get("roles") or [],
        missions=data.get("missions") or [],
        norms=data.get("norms") or [],
    )


def _base_manifests() -> list[Manifest]:
    """The engine base, plus the instance's operator-owned norms.

    The instance file is loaded by DEFAULT, not behind `--manifest`: `commands/done.md`
    invokes `duty discharge` with no flags, so a norms file reachable only by flag would be
    unreachable from the one place the check actually runs.
    """
    from enginelib.paths import duty_roster_dir, instance_norms_path

    base = duty_roster_dir()
    return [
        _load_manifest(base / "missions.base.yaml"),
        _load_manifest(base / "norms.base.yaml"),
        _load_manifest(instance_norms_path()),
    ]


def _merged_base() -> Manifest:
    """The base manifests as ONE manifest.

    The core takes (base, agent_manifest) — two slots. The adapter has three base files, so
    passing them by index (`manifests[0]`, `manifests[-1]`) silently drops everything in
    between. That was harmless while both engine bases shipped empty; it stops being harmless
    the moment the instance norms file joins them, since that file is the entire point of P2.
    """
    merged = Manifest(version=1)
    for m in _base_manifests():
        merged.roles.extend(m.roles)
        merged.missions.extend(m.missions)
        merged.norms.extend(m.norms)
    return merged


def _kind(args: argparse.Namespace) -> AgentKind:
    """Which abstract tier the derived role inherits. `kind:advisor` and `kind:executor` are
    a partition (validate.py), so getting this wrong makes base norms miss the agent."""
    return "executor" if args.executor else "advisor"


def _agent_paths(advisor: str, executor: str | None) -> tuple[str, Path, Path]:
    """Resolve (agent_id, duties_dir, projection_dir) for an advisor or an executor.

    Advisors resolve through advisor_skill_dir() — never string-concatenated, and always the
    canonical `conclave-<id>` prefix (operator decision 2026-07-27). Executors have no skill
    dir; per executor-protocol.md their home is the bare-slug memory dir.
    """
    from enginelib.paths import advisor_skill_dir, advisors_memory_dir, executor_memory_dir

    if executor:
        home = executor_memory_dir(executor)
        return executor, home / "duties", home
    skill_dir = advisor_skill_dir(advisor, artifact="duties")
    return advisor, skill_dir / "duties", advisors_memory_dir() / advisor


def _validate(args: argparse.Namespace) -> int:
    from enginelib.duties.project import project_agent
    from enginelib.duties.validate import validate

    agent_id, duties_dir, _ = _agent_paths(args.advisor, args.executor)
    base = _merged_base()
    agent_manifest = _load_manifest(Path(args.manifest) if args.manifest else None)
    projection = project_agent(base, agent_manifest, agent_id, duties_dir, _kind(args))
    # Validate against the projection's OWN derivation. An operator norm naming a duty is a
    # reference to a mission the duty file declares — validating without it would report
    # `unknown-mission` for the one-line norm P2 exists to make possible.
    findings = validate([base, agent_manifest, projection.derived])
    findings += projection.findings
    return _emit(findings)


def _project(args: argparse.Namespace) -> int:
    from enginelib.duties.project import project_agent, render_projection
    from enginelib.paths import ensure_dir

    agent_id, duties_dir, out_dir = _agent_paths(args.advisor, args.executor)
    agent_manifest = _load_manifest(Path(args.manifest) if args.manifest else None)
    projection = project_agent(_merged_base(), agent_manifest, agent_id, duties_dir, _kind(args))

    out = ensure_dir(out_dir) / "COMPUTED-DUTIES.md"
    out.write_text(render_projection(agent_id, projection), encoding="utf-8")
    print(f"wrote {out} ({len(projection.duties)} duties, {len(projection.norms)} norms)")
    return _emit(projection.findings)


def _scaffold(args: argparse.Namespace) -> int:
    from enginelib.paths import duty_template_path, ensure_dir

    _, duties_dir, _ = _agent_paths(args.advisor, args.executor)
    dest = ensure_dir(duties_dir) / f"{args.id}.md"
    if dest.exists():
        print(f"engine duty scaffold: {dest} already exists — refusing to overwrite",
              file=sys.stderr)
        return 1
    shutil.copyfile(duty_template_path(), dest)
    print(f"scaffolded {dest} — rewrite the frontmatter and body, then `engine duty validate`")
    return 0


def _record(args: argparse.Namespace) -> int:
    """Append one ledger entry — how a session says what became of a duty."""
    from enginelib.duties.ledger import append_entry

    _, _, home = _agent_paths(args.advisor, args.executor)
    entry = append_entry(home, duty_id=args.duty, session_id=args.session,
                         outcome=args.outcome, note=args.note)
    print(f"recorded {entry.duty_id} {entry.outcome} @ {entry.ts}")
    return 0


def _discharge(args: argparse.Namespace) -> int:
    """Report which obligations in force were addressed this session.

    Exit 2 (warning) when something is owed — deferred or unevaluated. Not exit 1: an
    unmet obligation is a state to surface at session end, not a broken tool. `/conclave:done`
    shows it; the operator decides.
    """
    from enginelib.duties.discharge import check_discharge

    agent_id, duties_dir, home = _agent_paths(args.advisor, args.executor)
    agent_manifest = _load_manifest(Path(args.manifest) if args.manifest else None)
    r = check_discharge(_merged_base(), agent_manifest, agent_id, home, session_id=args.session,
                        duties_dir=duties_dir, kind=_kind(args))

    for mission in r.discharged:
        print(f"discharged: {mission}")
    for mission in r.condition_unmet:
        print(f"condition-unmet: {mission}")
    for mission in r.deferred:
        print(f"DEFERRED: {mission}")
    for mission in r.unevaluated:
        print(f"UNEVALUATED: {mission} — condition not answered this session")
    print(f"=== Summary: {len(r.discharged)} discharged, {len(r.deferred)} deferred, "
          f"{len(r.unevaluated)} unevaluated (of {r.norms_in_force} obligations) ===")
    if not r.norms_in_force:
        # An empty registry is a state, not a failure — but it must be a *stated* state.
        # Without this line the run is textually identical to one that owed two things and
        # discharged both, and "clean" would mean "nothing was ever checked".
        print("no norms in force — nothing is owed to check against")
    return 0 if r.is_clean else 2


def _schema(args: argparse.Namespace) -> int:
    """Regenerate the committed JSON-Schemas from the models (single owner of the fact)."""
    import json

    from enginelib.duties.model import SCHEMA_FILES, schema_dir

    out = schema_dir()
    for name, model in SCHEMA_FILES.items():
        (out / f"{name}.schema.json").write_text(
            json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8")
    print(f"regenerated {len(SCHEMA_FILES)} schemas in {out}")
    return 0


def _add_target_args(v: argparse.ArgumentParser) -> None:
    v.add_argument("--advisor", default=None, help="Advisor id (e.g. sage-cto).")
    v.add_argument("--executor", default=None, help="Executor slug (e.g. iris-test).")
    v.add_argument("--manifest", default=None, help="Agent manifest yaml (roles/missions/norms).")


def register(sub) -> None:
    p = sub.add_parser("duty", help="Deontic duty registry (spec 091).")
    vsub = p.add_subparsers(dest="duty_verb", required=True)

    v = vsub.add_parser("validate", help="Validate the composed registry for an agent.")
    _add_target_args(v)
    v.set_defaults(func=_validate)

    v = vsub.add_parser("project", help="Write COMPUTED-DUTIES.md for an agent.")
    _add_target_args(v)
    v.set_defaults(func=_project)

    v = vsub.add_parser("scaffold", help="Copy the KAD duty template into an agent's duties/.")
    _add_target_args(v)
    v.add_argument("--id", required=True, help="Duty id (filename stem, e.g. d_close_session).")
    v.set_defaults(func=_scaffold)

    v = vsub.add_parser("record", help="Append a ledger entry for one duty (spec 091 §4).")
    _add_target_args(v)
    v.add_argument("--duty", required=True, help="Duty or mission id.")
    v.add_argument("--session", required=True, help="Session id this outcome belongs to.")
    v.add_argument("--outcome", required=True,
                   choices=sorted(OUTCOMES), help="What became of the duty.")
    v.add_argument("--note", default=None, help="Optional one-line context.")
    v.set_defaults(func=_record)

    v = vsub.add_parser("discharge",
                        help="Report obligations addressed vs owed for a session.")
    _add_target_args(v)
    v.add_argument("--session", required=True, help="Session id to check.")
    v.set_defaults(func=_discharge)

    v = vsub.add_parser("schema", help="Regenerate the committed JSON-Schemas from the models.")
    v.set_defaults(func=_schema)
