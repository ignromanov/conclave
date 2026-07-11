"""frontmatter_io.py — read + ruamel.yaml round-trip write for markdown frontmatter.

Two separate paths for read vs write:

READ  — uses python-frontmatter (handles YAML edge-cases + encoding well).
        Returns a plain dict for validate/schema consumers.

WRITE — bypasses python-frontmatter entirely and uses ruamel.yaml directly.
        python-frontmatter internally converts the CommentedMap returned by the
        handler back to a plain dict, stripping all comment annotations (confirmed
        by inspection of the library source). The direct path parses the raw YAML
        block, applies mutations on the CommentedMap, and dumps it back — so
        comments and key order survive.

Research: research/frontmatter-source-of-truth.md §R3.
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from typing import Any

import frontmatter
import ruamel.yaml
from ruamel.yaml.comments import CommentedMap

from enginelib.snapshot import snapshot_write

# Shared ruamel.yaml instance for all I/O in this module.
_yaml = ruamel.yaml.YAML()
_yaml.preserve_quotes = True
_yaml.width = 4096  # type: ignore[assignment]
# Strip non-standard constructors; keep only tag:yaml.org,2002:* builtins to
# prevent !!python/object/apply: style code execution from agent-authored files.
_yaml.constructor.yaml_constructors = {
    k: v for k, v in _yaml.constructor.yaml_constructors.items()
    if k is None or k.startswith("tag:yaml.org,2002:")
}

# Pattern matching the opening --- and closing --- of YAML frontmatter.
_FM_RE = re.compile(r"^---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL)

# Pattern matching one or more leading HTML comments (e.g. DATA CLASSIFICATION block).
_LEADING_COMMENT_RE = re.compile(r"^(<!--.*?-->[ \t]*\n?)+", re.DOTALL)


def _split_raw(text: str) -> tuple[str | None, str]:
    """Split raw file text into (yaml_block_or_None, body).

    Strips leading HTML comment blocks before attempting frontmatter extraction.
    """
    text = _LEADING_COMMENT_RE.sub("", text)
    m = _FM_RE.match(text)
    if not m:
        return None, text
    return m.group(1), text[m.end():]


def read(path: Path) -> tuple[dict[str, Any], str]:
    """Parse a markdown file into (frontmatter_dict, body_string).

    Returns a plain dict suitable for pydantic validation.
    Returns ({}, raw_text) for files without frontmatter.
    Strips leading HTML comment blocks (e.g. DATA CLASSIFICATION header) before parsing.
    """
    raw = path.read_text(encoding="utf-8")
    stripped = _LEADING_COMMENT_RE.sub("", raw)
    post = frontmatter.loads(stripped)
    return dict(post.metadata), post.content


def read_commented(path: Path) -> tuple[CommentedMap, str]:
    """Parse a markdown file into (CommentedMap, body_string).

    Returns the ruamel.yaml CommentedMap so write() can preserve comments.
    Use this path when you need to mutate and write back with comment retention.
    """
    text = path.read_text(encoding="utf-8")
    raw_yaml, body = _split_raw(text)
    if raw_yaml is None:
        return CommentedMap(), text
    result = _yaml.load(raw_yaml)
    if result is None:
        result = CommentedMap()
    return result, body.lstrip("\n")


def write(path: Path, meta: Any, body: str, header: str = "") -> None:
    """Write frontmatter + body back to path.

    meta may be a CommentedMap (from read_commented — comments preserved) or a
    plain dict (for new files — no comments to preserve).
    Atomic: writes via a tmp sibling + os.replace (enginelib.snapshot.snapshot_write) so a
    crash mid-write cannot truncate the durable feedback notebook this also round-trips.
    """
    stream = io.StringIO()
    _yaml.dump(meta, stream)
    fm_block = stream.getvalue().rstrip("\n")

    body_text = body.strip("\n")
    content = f"---\n{fm_block}\n---\n"
    if body_text:
        content += f"\n{body_text}\n"
    if header:
        content = header + content

    snapshot_write(path, content)
