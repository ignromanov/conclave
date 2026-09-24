"""Which project files the harness loads into every session, and how big they are.

The rotation slice of spec 110 (GH#369, GH#191): a size ceiling is only meaningful against the
set that actually costs context, so this module reproduces the harness's load rules rather than
trusting a hand-kept list. Reads files; prints nothing.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

#: Claude Code memory docs: imports nest at most five hops deep.
MAX_IMPORT_DEPTH = 5
ENTRY_POINTS = ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md")

_FENCE = re.compile(r"^```.*?^```[^\n]*$", re.S | re.M)
_INLINE = re.compile(r"`[^`\n]*`")
_IMPORT = re.compile(r"(?:^|(?<=\s))@([^\s`]+)")


@dataclass(frozen=True)
class Loaded:
    path: Path  # resolved, for identity
    rel: str    # as reached from the project root, symlinks preserved, for display and config
    size: int   # bytes
    via: str    # "entry", "rule", or "@import from <rel>"


def imports_in(text: str) -> list[str]:
    """Candidate import targets. Code is stripped first: an `@` in a fence is an example."""
    return _IMPORT.findall(_INLINE.sub("", _FENCE.sub("", text)))


def has_paths_frontmatter(text: str) -> bool:
    if not text.startswith("---\n"):
        return False
    end = text.find("\n---", 4)
    return end != -1 and any(ln.startswith("paths:") for ln in text[4:end].splitlines())


def autoload_set(project_root: Path) -> list[Loaded]:
    seen: set[Path] = set()
    out: list[Loaded] = []

    def visit(p: Path, via: str, depth: int) -> None:
        try:
            real = p.resolve()
        except OSError:
            return
        # A name that is not a file is not an import: `@vera-cto` in prose resolves to nothing.
        if real in seen or not real.is_file():
            return
        seen.add(real)
        data = real.read_bytes()
        rel = os.path.relpath(p, project_root)
        out.append(Loaded(real, rel, len(data), via))
        if depth >= MAX_IMPORT_DEPTH:
            return
        for target in imports_in(data.decode("utf-8", errors="replace")):
            tp = Path(target).expanduser()
            visit(tp if tp.is_absolute() else p.parent / tp, f"@import from {rel}", depth + 1)

    for entry in ENTRY_POINTS:
        visit(project_root / entry, "entry", 0)
    rules = project_root / ".claude" / "rules"
    if rules.is_dir():
        for rule in sorted(rules.rglob("*.md")):
            if not has_paths_frontmatter(rule.read_text(encoding="utf-8", errors="replace")):
                visit(rule, "rule", 0)
    return out
