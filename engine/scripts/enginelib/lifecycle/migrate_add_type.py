"""enginelib/lifecycle/migrate_add_type.py — I/O-free core for migrate-add-type.

Contract:
  - No stdout/argparse/sys.exit. File read+write OK.
  - run(root, dry_run) -> MigrateResult: sweeps *.md under root,
    injecting type: frontmatter by path mapping (ordered glob rules).
  - Idempotent: files already containing ^type: are skipped.
  - Unknown paths: counted as skipped; adapter prints stderr warning in both modes.
  - dry_run: populates would_inject; injected stays 0; no writes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from enginelib.snapshot import snapshot_write


@dataclass
class MigrateResult:
    injected: int
    skipped: int
    would_inject: list[str] = field(default_factory=list)   # dry-run only: "type=<t> into <path>"
    skipped_paths: list[str] = field(default_factory=list)  # unknown-mapping paths


def infer_type(path: Path) -> str | None:
    """Return the type string for path, or None if no mapping matches.

    Rules are ORDERED — first match wins, faithful to the bash glob order.
    """
    s = str(path)
    if "/decisions/" in s:
        return "decision"
    if "/sessions/" in s:
        return "session"
    if re.search(r"/mentions/[^/]+/[^/]+", s):
        return "mention"
    if "/audit/" in s:
        return "audit-finding"
    if "/reconcile/" in s:
        return "reconcile-mismatch"
    if re.search(r"/plans/[^/]+/steps/[^/]+", s):
        return "plan-step"
    return None


def _inject(text: str, inferred: str) -> str:
    """Insert type: into text. Faithful to the bash awk/cat branches.

    Has frontmatter (first line exactly '---'): insert `type: <inferred>` after
    the first ---. Mirrors awk which strips the trailing newline — join without
    re-adding one.

    No frontmatter: prepend a new block; original text keeps its trailing newline.
    """
    lines = text.splitlines()
    if lines and lines[0] == "---":
        new_lines: list[str] = []
        inserted = False
        for line in lines:
            new_lines.append(line)
            if line == "---" and not inserted:
                new_lines.append(f"type: {inferred}")
                inserted = True
        return "\n".join(new_lines)
    else:
        return f"---\ntype: {inferred}\n---\n\n" + text


def run(root: Path, dry_run: bool = False) -> MigrateResult:
    """Sweep all *.md under root, injecting type: frontmatter by path mapping."""
    injected = 0
    skipped = 0
    would_inject: list[str] = []
    skipped_paths: list[str] = []

    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")

        if re.search(r"^type:", text, re.M):
            continue  # already typed — idempotent skip

        t = infer_type(path)
        if t is None:
            # Unknown path mapping; adapter emits stderr warning in both modes
            skipped_paths.append(str(path))
            skipped += 1
            continue

        if dry_run:
            would_inject.append(f"type={t} into {path}")
            continue  # injected stays 0 in dry-run

        snapshot_write(path, _inject(text, t))
        injected += 1

    return MigrateResult(injected, skipped, would_inject, skipped_paths)
