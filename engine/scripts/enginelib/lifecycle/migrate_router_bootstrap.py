"""enginelib/lifecycle/migrate_router_bootstrap.py — I/O-free core for migrate-router-bootstrap.

Why this exists: `render_router` refuses to overwrite an enriched wrapper (#58), so the bash
fence a router carries freezes at mint time. A template fix therefore reaches new instances and
no existing one — which is how the `${CLAUDE_PLUGIN_ROOT:-.}` bootstrap survived eleven reports
across two triage windows while the template that produced it was one edit away.

The wrapper has two owners. The identity, the description and the `forge:` block are the
instance's, written at hire time and never regenerable. The bootstrap fence is the engine's: it
is a copy of the template and carries no instance decision beyond the advisor id. This migration
refreshes the second and does not read the first.

Contract (matches migrate_add_type / migrate_add_tags):
  - No stdout/argparse/sys.exit. File read+write OK.
  - run(skills_root, dry_run) -> MigrateResult
  - Idempotent: a router whose fence already equals the template's is skipped.
  - A router with no bootstrap fence is skipped, never given one — this refreshes, it does
    not install.
  - dry_run: populates would_update; updated stays 0; no writes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from enginelib import paths
from enginelib.snapshot import snapshot_write

_BASH_FENCE = re.compile(r"```bash\n.*?```", re.DOTALL)
_MARKER = "session_init.py"


@dataclass
class MigrateResult:
    updated: int
    skipped: int
    would_update: list[str] = field(default_factory=list)   # dry-run only: router paths


def _bootstrap_fences(text: str) -> list[str]:
    """Every bash fence in text that launches session-init."""
    return [f for f in _BASH_FENCE.findall(text) if _MARKER in f]


def canonical_bootstrap(advisor_id: str, template_path: Path | None = None) -> str:
    """The bootstrap fence the CURRENT template prescribes, rendered for one advisor.

    Read from the template rather than hard-coded here, so this migration cannot drift from
    what a fresh mint produces — the drift it exists to repair.
    """
    path = template_path or (paths.templates_dir() / "advisor-router.md")
    fences = _bootstrap_fences(path.read_text(encoding="utf-8"))
    if len(fences) != 1:
        raise RuntimeError(
            f"advisor-router.md must carry exactly one bash fence invoking {_MARKER}; "
            f"found {len(fences)} in {path}"
        )
    return fences[0].replace("${ID}", advisor_id)


def run(skills_root: Path, dry_run: bool = False) -> MigrateResult:
    """Refresh the bootstrap fence of every minted router under skills_root."""
    updated = 0
    skipped = 0
    would: list[str] = []

    for skill_file in sorted(Path(skills_root).glob("conclave-*/SKILL.md")):
        advisor_id = skill_file.parent.name[len("conclave-"):]
        text = skill_file.read_text(encoding="utf-8")
        fences = _bootstrap_fences(text)
        if not fences:
            skipped += 1
            continue

        want = canonical_bootstrap(advisor_id)
        if all(f == want for f in fences):
            skipped += 1
            continue

        if dry_run:
            would.append(str(skill_file))
            continue

        for fence in fences:
            text = text.replace(fence, want)
        snapshot_write(skill_file, text)
        updated += 1

    return MigrateResult(updated=updated, skipped=skipped, would_update=would)
