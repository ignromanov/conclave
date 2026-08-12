"""registry.py — discover protocol files across the four homes (spec 108 §4).

Discovery is by SCAN, never by manifest. The fourth home is an advisor's own
directory, which grows during a session; a manifest could not track a protocol the
advisor wrote fifteen minutes ago.

A malformed file yields a ScanError rather than an exception or a silent skip. Silent
skipping is the exact defect this spec exists to remove.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from enginelib.protocols.model import ProtocolFile, ProtocolMeta

#: The three fixed homes, relative to the repository root.
FIXED_HOMES: tuple[str, ...] = (
    "skills/advisor-contracts/references",
    "skills/forge-operations/references/protocols",
    "skills/forge-operations/references/aspects",
)


@dataclass(frozen=True)
class ScanError:
    path: Path
    reason: str


def homes(engine_root: Path, advisor_dir: Path | None) -> list[Path]:
    dirs = [engine_root / rel for rel in FIXED_HOMES]
    if advisor_dir is not None:
        dirs.append(advisor_dir)
    return dirs


def scan(dirs: list[Path]) -> tuple[list[ProtocolFile], list[ScanError]]:
    import frontmatter

    found: list[ProtocolFile] = []
    errors: list[ScanError] = []
    for d in dirs:
        if not d.is_dir():
            continue  # an absent home is not an error; an absent FILE is
        for path in sorted(d.glob("*.md")):
            try:
                post = frontmatter.load(path)
            except Exception as exc:
                errors.append(ScanError(path, f"unparseable: {exc}"))
                continue
            if not post.metadata:
                errors.append(ScanError(path, "no frontmatter"))
                continue
            try:
                meta = ProtocolMeta(**post.metadata)
            except ValidationError as exc:
                errors.append(ScanError(path, f"invalid frontmatter: {exc.error_count()} error(s)"))
                continue
            found.append(ProtocolFile(path=path, meta=meta))
    return found, errors
