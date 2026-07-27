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

from enginelib.duties.model import Manifest
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
    from enginelib.paths import duty_roster_dir

    base = duty_roster_dir()
    return [_load_manifest(base / "missions.base.yaml"), _load_manifest(base / "norms.base.yaml")]


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
    manifests = _base_manifests() + [_load_manifest(Path(args.manifest) if args.manifest else None)]
    findings = validate(manifests)
    findings += project_agent(manifests[0], manifests[-1], agent_id, duties_dir).findings
    return _emit(findings)


def _project(args: argparse.Namespace) -> int:
    from enginelib.duties.project import project_agent, render_projection
    from enginelib.paths import ensure_dir

    agent_id, duties_dir, out_dir = _agent_paths(args.advisor, args.executor)
    manifests = _base_manifests() + [_load_manifest(Path(args.manifest) if args.manifest else None)]
    projection = project_agent(manifests[0], manifests[-1], agent_id, duties_dir)

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

    v = vsub.add_parser("schema", help="Regenerate the committed JSON-Schemas from the models.")
    v.set_defaults(func=_schema)
