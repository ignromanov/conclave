"""enginelib/audit/overlays.py — port of audit-overlays.sh.

I/O-free: no print / argparse / sys.exit. Returns OverlayReport(warn, info).

For each team.*/contracts/*.md in skills_dir (excluding team.forge paths):
  - base must exist at base_dir/<contract>.md (WARN if missing; skip remaining checks)
  - overrides-base-version must match version in base (WARN on mismatch)
  - advisor SKILL.md must mention contract name as substring (INFO if absent)
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class OverlayReport:
    warn: list[str] = field(default_factory=list)
    info: list[str] = field(default_factory=list)


def _field2(text: str, prefix: str) -> str:
    """Return whitespace-split field index 1 from the first line starting with prefix, else ''."""
    for line in text.splitlines():
        if line.startswith(prefix):
            parts = line.split()
            return parts[1] if len(parts) > 1 else ""
    return ""


_ADVISOR_PREFIXES = ("conclave-", "team.")


def _bare_dir(dirname: str) -> str:
    for prefix in _ADVISOR_PREFIXES:
        if dirname.startswith(prefix):
            return dirname[len(prefix):]
    return dirname


def run(skills_dir: Path, base_dir: Path) -> OverlayReport:
    """Check overlay health for all advisor contracts/*.md under both the current
    conclave-<id> and legacy team.<id> layouts (#54), excluding the forge meta-dir."""
    rpt = OverlayReport()

    candidates = [
        p
        for prefix in _ADVISOR_PREFIXES
        for p in skills_dir.glob(f"{prefix}*/contracts/*.md")
    ]
    # No advisor is exempt. This used to skip the `forge` directory, which left the
    # one advisor shipped in every instance as the only one whose contract drift
    # nothing could detect — while spec 100 §3.3 records forge's overlays as RUN,
    # "its self-mutation contracts". The forge → forge-chro rename already made the
    # literal stop matching; removing it stops the exemption coming back by accident.
    overlays = sorted(candidates)

    for overlay in overlays:
        advisor = overlay.parent.parent.name
        contract = overlay.stem
        base = base_dir / f"{contract}.md"

        if not base.exists():
            rpt.warn.append(
                f"{advisor} overlay {contract} has no base in team.forge/contracts/"
            )
            continue

        base_ver = _field2(base.read_text(encoding="utf-8"), "version:")
        over_ver = _field2(overlay.read_text(encoding="utf-8"), "overrides-base-version:")

        if base_ver != over_ver:
            rpt.warn.append(
                f"{advisor} overlay {contract} base-version {over_ver} ≠ current {base_ver}"
            )

        skill = skills_dir / advisor / "SKILL.md"
        if skill.exists() and contract not in skill.read_text(encoding="utf-8"):
            rpt.info.append(
                f"{advisor} overlay {contract} not declared in SKILL.md ## Contract Overrides"
            )

    return rpt
