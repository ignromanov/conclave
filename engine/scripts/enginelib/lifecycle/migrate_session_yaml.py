"""enginelib/lifecycle/migrate_session_yaml.py — I/O-free core for migrate-session-yaml.

Why this exists: 38 of 77 session records on the authoring instance do not parse with
`yaml.safe_load` (#255). Two independent causes, both from writers that interpolated a
value into frontmatter raw:

  reflexion: The gate passed: the mutation did not.   -> ": " reads as a nested mapping
  issues: [#17,#18]                                   -> "#" opens a comment; the flow
                                                         sequence never closes

Both writers are fixed (#256 for the first, as_flow_list for the second). This repairs
what is already on disk, and only that.

Why it is not a sed. A session record is written once and never revised, and the
reflexion is what session-init hands the next session as a prior -- it exists nowhere
else. A field-only
migration through an audited write path is exactly the shape of the 2026-08-31 incident
that erased 58 days of item age, so the discipline here is:

  - Per FIELD, not per file. A chunk that parses on its own is copied verbatim, bytes
    included. A `>-` folded reflexion is left folded: re-emitting it as `|-` would change
    the parsed value from space-joined to newline-joined, which is corruption wearing the
    costume of a fix.
  - The gate is equality, not a count. Every field readable before the write must read
    back identical after it, through the same reader. `run()` refuses to write a file
    that fails its own check and reports it.
  - The body is never touched.

Contract (matches migrate_router_bootstrap):
  - No stdout/argparse/sys.exit. File read+write OK.
  - run(sessions_root, dry_run) -> MigrateResult
  - Idempotent: a record whose frontmatter already parses is skipped.
  - dry_run: populates would_update; updated stays 0; no writes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from enginelib import frontmatter
from enginelib.snapshot import snapshot_write

_KEY = re.compile(r"^([A-Za-z_][\w-]*):(.*)$")
_BLOCK_INDICATORS = ("|", "|-", "|+", ">", ">-", ">+")


@dataclass
class MigrateResult:
    updated: int
    skipped: int
    would_update: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)   # (path, why)


def split_frontmatter(text: str) -> tuple[str, list[str], str] | None:
    """(opening, frontmatter_lines, remainder) or None when there is no frontmatter."""
    if not text.startswith("---\n"):
        return None
    rest = text[4:]
    end = rest.find("\n---")
    if end == -1:
        return None
    return "---\n", rest[:end].splitlines(), rest[end:]


def chunk_fields(lines: list[str]) -> list[list[str]]:
    """Group frontmatter lines into one chunk per top-level key.

    A key's chunk carries the lines that belong to it -- the indented body of a block
    scalar, or the items of a block sequence -- so a chunk can be parsed, and judged,
    on its own.
    """
    chunks: list[list[str]] = []
    for line in lines:
        if _KEY.match(line) and chunks:
            chunks.append([line])
        elif _KEY.match(line):
            chunks.append([line])
        elif chunks:
            chunks[-1].append(line)
        else:
            chunks.append([line])
    return chunks


def chunk_parses(chunk: list[str]) -> bool:
    try:
        return isinstance(yaml.safe_load("\n".join(chunk)), dict)
    except yaml.YAMLError:
        return False


def repair_chunk(chunk: list[str]) -> list[str] | None:
    """A parseable rewrite of one broken chunk, or None when the shape is unhandled.

    Returning None is the honest outcome for anything this does not understand: the
    record stays broken and is reported, which is strictly better than a rewrite whose
    correctness nobody established.
    """
    m = _KEY.match(chunk[0])
    if not m:
        return None
    key, head = m.group(1), m.group(2).strip()

    if head.startswith("[") and len(chunk) == 1:
        inner = head[1:].rsplit("]", 1)[0] if head.endswith("]") else head[1:]
        return [f"{key}: {frontmatter.as_flow_list(inner.strip())}"]

    if head in _BLOCK_INDICATORS:
        return None            # already a block scalar; if it fails, this is not the cause

    value = "\n".join([head] + [ln.strip() for ln in chunk[1:]]).strip()
    rendered = frontmatter.as_block(value, chomp=True)
    if not rendered:
        return [f"{key}:"]
    return (f"{key}: {rendered}").splitlines()


def field_values(lines: list[str]) -> dict[str, str]:
    """Every field's raw text, read the way the engine reads it: by line.

    Used on both sides of the write as the equality gate. Deliberately not
    `yaml.safe_load` -- the input side does not parse, which is the whole point.
    """
    out: dict[str, str] = {}
    for chunk in chunk_fields(lines):
        m = _KEY.match(chunk[0])
        if not m:
            continue
        key, head = m.group(1), m.group(2).strip()
        if head in _BLOCK_INDICATORS:
            body = [ln.strip() for ln in chunk[1:] if ln.strip()]
            out[key] = "\n".join(body)
        elif head.startswith("["):
            inner = head[1:].rsplit("]", 1)[0] if head.endswith("]") else head[1:]
            out[key] = ",".join(p.strip().strip("'\"") for p in inner.split(",") if p.strip())
        else:
            out[key] = head.strip("'\"")
    return out


def migrate_text(text: str) -> tuple[str | None, str]:
    """(new_text, reason). new_text is None when nothing was done."""
    parts = split_frontmatter(text)
    if parts is None:
        return None, "no frontmatter"
    opening, fm_lines, remainder = parts
    try:
        if isinstance(yaml.safe_load("\n".join(fm_lines)), dict):
            return None, "already parses"
    except yaml.YAMLError:
        pass

    before = field_values(fm_lines)
    out: list[str] = []
    repaired: list[str] = []
    for chunk in chunk_fields(fm_lines):
        if chunk_parses(chunk):
            out.extend(chunk)
            continue
        fixed = repair_chunk(chunk)
        if fixed is None:
            out.extend(chunk)
            continue
        out.extend(fixed)
        m = _KEY.match(chunk[0])
        if m:
            repaired.append(m.group(1))

    if not repaired:
        return None, "no repairable field found"

    # Gate the BYTES that will be written, never the intermediate. Assembling the
    # frontmatter and checking the line list instead let a reassembly bug -- the closing
    # fence glued onto the last value -- pass a green check and reach disk.
    candidate = opening + "\n".join(out) + remainder
    reparsed = split_frontmatter(candidate)
    if reparsed is None:
        return None, "repair destroyed the frontmatter fences"
    try:
        parsed = yaml.safe_load("\n".join(reparsed[1]))
    except yaml.YAMLError as exc:
        return None, f"still invalid after repair: {str(exc).splitlines()[0]}"
    if not isinstance(parsed, dict):
        return None, "repair did not yield a mapping"

    after = field_values(reparsed[1])
    for key, was in before.items():
        if after.get(key) != was:
            return None, f"field {key!r} changed: {was!r} -> {after.get(key)!r}"
    if reparsed[2] != remainder:
        return None, "the body changed"

    return candidate, "repaired: " + ",".join(repaired)


def run(sessions_root: Path, dry_run: bool = False) -> MigrateResult:
    res = MigrateResult(updated=0, skipped=0)
    for path in sorted(Path(sessions_root).glob("*.md")):
        text = path.read_text(encoding="utf-8")
        new_text, reason = migrate_text(text)
        if new_text is None:
            if reason in ("already parses", "no frontmatter"):
                res.skipped += 1
            else:
                res.failed.append((str(path), reason))
            continue
        if dry_run:
            res.would_update.append(f"{path} ({reason})")
            continue
        snapshot_write(path, new_text)
        res.updated += 1
    return res
