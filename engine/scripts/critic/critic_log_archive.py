#!/usr/bin/env python3
"""critic_log_archive.py — archive a critic run to agent-memory/executors/socra-critic/runs/.

Appends run metadata + refutation entries to a dated markdown file, structured for
calibration reuse (spec 089 D32). Each run gets its own file: <date>-<slug>.md.
If the file already exists on the same date, the run is appended as a second section.

Reuses 084/086 substrate: pydantic v2 + ruamel.yaml (for reading the refutation file).

Usage:
    python critic_log_archive.py \\
        --refutation <spec-dir>/critic-refutation.yaml \\
        --run-id     <task_slug>-<YYYYMMDD-HHMMSS>     \\
        --repo-root  <path-to-.ai-root>                \\
        [--outcome pass|fail|partial|inconclusive|unknown] \\
        [--judge-verdict <spec-dir>/judge-verdict.yaml]

Exit codes (ADR-0003): 0 ok · 1 error · 2 missing input.
"""
from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

try:
    from critic_refute import _load_yaml
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from critic_refute import _load_yaml


def _runs_dir(repo_root: Path) -> Path:
    return repo_root / "agent-memory" / "executors" / "socra-critic" / "runs"


def _archive_path(runs_dir: Path, run_id: str) -> Path:
    date_str = datetime.now(tz=UTC).strftime("%Y-%m-%d")
    slug = run_id.replace("/", "-").replace(" ", "-")
    return runs_dir / f"{date_str}-{slug}.md"


def _format_entry(entry: dict, idx: int) -> str:
    lines = [
        f"### R-{idx + 1:03d} — `{entry.get('type', 'unknown')}` "
        f"[{entry.get('strength', '?')}]",
        f"- **location**: `{entry.get('location', 'n/a')}`",
        f"- **ac_ref**: {entry.get('ac_ref', 'none')}",
        f"- **description**: {entry.get('description', '')}",
        f"- **evidence**: {entry.get('evidence', '')}",
        f"- **suggested_judge_question**: {entry.get('suggested_judge_question', '')}",
    ]
    return "\n".join(lines)


def archive(
    refutation_path: Path,
    run_id: str,
    repo_root: Path,
    outcome: str = "unknown",
    judge_verdict_path: Path | None = None,
) -> int:
    if not refutation_path.exists():
        print(f"ERROR: refutation file not found: {refutation_path}", file=sys.stderr)
        return 2

    raw = _load_yaml(refutation_path)
    refutations: list[dict] = raw.get("refutations", [])

    high = sum(1 for r in refutations if r.get("strength") == "high")
    medium = sum(1 for r in refutations if r.get("strength") == "medium")
    low = sum(1 for r in refutations if r.get("strength") == "low")

    judge_section = ""
    if judge_verdict_path is not None:
        if not judge_verdict_path.exists():
            print(
                f"WARN: judge-verdict not found at {judge_verdict_path} — skipping cross-ref",
                file=sys.stderr,
            )
        else:
            jraw = _load_yaml(judge_verdict_path)
            judge_section = (
                "\n## Judge verdict (cross-ref)\n\n"
                f"- **verdict**: {jraw.get('verdict', 'unknown')}\n"
                f"- **confidence**: {jraw.get('confidence', 'n/a')}\n"
                f"- **sample_count**: {jraw.get('sample_count', 'n/a')}\n"
            )

    now_iso = datetime.now(tz=UTC).isoformat(timespec="seconds")

    frontmatter = (
        "---\n"
        f"type: critic-run-archive\n"
        f"run_id: {run_id}\n"
        f"artifact_ref: {raw.get('artifact_ref', 'unknown')}\n"
        f"ac_contract_ref: {raw.get('ac_contract_ref', 'unknown')}\n"
        f"outcome: {outcome}\n"
        f"archived_at: {now_iso}\n"
        f"refutation_count: {len(refutations)}\n"
        f"strength_high: {high}\n"
        f"strength_medium: {medium}\n"
        f"strength_low: {low}\n"
        f"schema_version: 1\n"
        "---\n"
    )

    summary_table = (
        "| Metric | Value |\n"
        "|--------|-------|\n"
        f"| Total refutations | {len(refutations)} |\n"
        f"| Unverifiable claims | {raw.get('unverifiable_count', 0)} |\n"
        f"| Assumptions surfaced | {raw.get('assumption_count', 0)} |\n"
        f"| Scope overstepped | {raw.get('scope_overstep_count', 0)} |\n"
        f"| Strength high | {high} |\n"
        f"| Strength medium | {medium} |\n"
        f"| Strength low | {low} |\n"
        f"| Elapsed ms | {raw.get('elapsed_ms', 0)} |\n"
    )

    refutations_body = "\n\n".join(
        _format_entry(e, i) for i, e in enumerate(refutations)
    ) or "_No refutations recorded._"

    body = (
        f"# Critic run — {run_id}\n\n"
        f"**Archived**: {now_iso}  \n"
        f"**Outcome**: {outcome}  \n"
        f"**Artifact**: `{raw.get('artifact_ref', 'unknown')}`  \n"
        f"**Contract**: `{raw.get('ac_contract_ref', 'unknown')}`  \n\n"
        f"## Summary\n\n"
        f"{summary_table}"
        f"{judge_section}\n"
        f"## Refutations\n\n"
        f"{refutations_body}\n"
    )

    runs_dir = _runs_dir(repo_root)
    out_path = _archive_path(runs_dir, run_id)
    runs_dir.mkdir(parents=True, exist_ok=True)

    if out_path.exists():
        with out_path.open("a", encoding="utf-8") as f:
            f.write("\n\n---\n\n")
            f.write(body)
    else:
        with out_path.open("w", encoding="utf-8") as f:
            f.write(frontmatter + "\n")
            f.write(body)

    print(f"OK: archived to {out_path}")
    return 0


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Archive a critic run to agent-memory/executors/socra-critic/runs/ "
            "for calibration reuse (spec 089 D32)."
        )
    )
    p.add_argument("--refutation", required=True, help="Path to critic-refutation.yaml")
    p.add_argument("--run-id", required=True, help="Run identifier (task_slug-YYYYMMDD-HHMMSS)")
    p.add_argument("--repo-root", required=True, help="Repo root (.ai root, agent-memory lives here)")
    p.add_argument(
        "--outcome",
        default="unknown",
        choices=["pass", "fail", "partial", "inconclusive", "unknown"],
        help="Judge outcome for calibration tagging (default: unknown)",
    )
    p.add_argument(
        "--judge-verdict",
        default=None,
        help="Optional path to judge-verdict.yaml for cross-reference",
    )
    return p.parse_args()


def main() -> int:
    args = _parse_args()
    jvp = Path(args.judge_verdict) if args.judge_verdict else None
    return archive(
        refutation_path=Path(args.refutation),
        run_id=args.run_id,
        repo_root=Path(args.repo_root),
        outcome=args.outcome,
        judge_verdict_path=jvp,
    )


if __name__ == "__main__":
    sys.exit(main())
