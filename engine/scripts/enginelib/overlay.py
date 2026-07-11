"""enginelib/overlay.py — core logic for per-advisor contract overlays.

Port of apply-overlay.sh. I/O-free: no stdout, no argparse, no sys.exit.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from enginelib.paths import advisor_skill_dir
from enginelib.snapshot import snapshot_write


@dataclass
class OverlayResult:
    status: str   # created|exists|removed|no-remove|modify|no-modify|base-missing
    base_path: Path
    overlay_path: Path


def apply_overlay(
    advisor: str,
    contract: str,
    type_: str,
    action: str,
    *,
    contracts_dir: Path,
    repo_root: Path,
) -> OverlayResult:
    """Apply an overlay action for a per-advisor contract.

    Returns OverlayResult; never prints or exits.
    """
    base = contracts_dir / f"{contract}.md"
    # #54: resolve the advisor's SKILL dir (current conclave-<id>, or an existing
    # legacy team.<id> via dual-read); fresh advisors land on the canonical prefix.
    skill_dir = advisor_skill_dir(advisor, repo_root / ".claude" / "skills")
    overlay_dir = skill_dir / "contracts"
    overlay = overlay_dir / f"{contract}.md"
    dir_name = skill_dir.name

    if not base.is_file():
        return OverlayResult(status="base-missing", base_path=base, overlay_path=overlay)

    # Read base version: first line matching ^version:, second field.
    base_ver = ""
    for line in base.read_text(encoding="utf-8").splitlines():
        if line.startswith("version:"):
            parts = line.split()
            if len(parts) >= 2:
                base_ver = parts[1]
            break

    # Title-case type_: first char upper + rest unchanged.
    type_title = (type_[0].upper() + type_[1:]) if type_ else ""

    if action == "add":
        if overlay.exists():
            return OverlayResult(status="exists", base_path=base, overlay_path=overlay)
        body = (
            f"---\n"
            f"contract: {contract}\n"
            f"advisor: {advisor}\n"
            f"overrides-base-version: {base_ver}\n"
            f"type: {type_}\n"
            f"---\n"
            f"\n"
            f"# {dir_name} overlay: {contract}\n"
            f"\n"
            f"## {type_title}: <short title>\n"
            f"\n"
            f"Default: _(describe default behavior from base)_\n"
            f"Override: _(describe what changes for {dir_name})_\n"
            f"\n"
            f"## Rationale\n"
            f"_(link to personality.md non-negotiable or project constraint)_\n"
            f"\n"
            f"## How it applies\n"
            f"- _(stage or hook this overlay modifies)_\n"
        )
        snapshot_write(overlay, body)
        return OverlayResult(status="created", base_path=base, overlay_path=overlay)

    if action == "remove":
        if not overlay.is_file():
            return OverlayResult(status="no-remove", base_path=base, overlay_path=overlay)
        overlay.unlink()
        return OverlayResult(status="removed", base_path=base, overlay_path=overlay)

    if action == "modify":
        if not overlay.is_file():
            return OverlayResult(status="no-modify", base_path=base, overlay_path=overlay)
        return OverlayResult(status="modify", base_path=base, overlay_path=overlay)

    # Unknown action — caller (adapter) should validate before calling; guard here.
    raise ValueError(f"apply_overlay: unknown action {action!r}")
