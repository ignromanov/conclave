"""enginelib/lifecycle/migrate_add_tags.py — I/O-free core for migrate-add-tags.

Contract:
  - No stdout/argparse/sys.exit. File read+write OK.
  - run(root, dry_run) -> TagsResult: sweeps *.md under root,
    injecting tags: [op/<type>] after the first type: line.
  - Idempotent: files already containing ^tags: are skipped.
  - No type: found: counted as skipped; adapter prints stderr warning in both modes.
  - dry_run: populates would_inject; injected stays 0; no writes.
  - Order dependency: migrate-add-type must run before this script.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from enginelib.snapshot import snapshot_write


@dataclass
class TagsResult:
    injected: int = 0
    skipped: int = 0
    would_inject: list[str] = field(default_factory=list)
    skipped_paths: list[str] = field(default_factory=list)


def _extract_type(text: str) -> str:
    """Return the value of type: from frontmatter, or '' if not found.

    Frontmatter-gated: only matches type: lines between the opening --- pair.
    Mirrors bash awk with in_fm toggle on ^---$.
    """
    in_fm = False
    for line in text.splitlines():
        if line == "---":
            in_fm = not in_fm
            continue
        if in_fm and line.startswith("type:"):
            return line[len("type:"):].strip()
    return ""


def _inject_tags(text: str, tags_value: str) -> str:
    """Insert tags: <tags_value> immediately after the first line starting with type:.

    Mirrors bash awk which strips the trailing newline — join without re-adding one.
    """
    out: list[str] = []
    inserted = False
    for line in text.splitlines():
        out.append(line)
        if not inserted and line.startswith("type:"):
            out.append(f"tags: {tags_value}")
            inserted = True
    return "\n".join(out)


def run(root: Path, dry_run: bool = False) -> TagsResult:
    """Sweep all *.md under root, injecting tags: [op/<type>] after the type: line."""
    result = TagsResult()

    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")

        if re.search(r"^tags:", text, re.M):
            continue  # already tagged — idempotent skip

        t = _extract_type(text)
        if not t:
            # No type: present — skip with warning (both modes)
            result.skipped_paths.append(str(path))
            result.skipped += 1
            continue

        tags_value = f"[op/{t}]"

        if dry_run:
            result.would_inject.append(f"tags={tags_value} into {path}")
            continue  # injected stays 0 in dry-run

        snapshot_write(path, _inject_tags(text, tags_value))
        result.injected += 1

    return result
