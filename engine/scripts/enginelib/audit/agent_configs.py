"""enginelib/audit/agent_configs — static security scan of .claude/ for secrets,
dangerous flags, and injection patterns.

Spec 071 Aspect 4. I/O-free: no print/argparse/sys.exit in code.
Adapter (engine/cmd/audit.py::_agent_configs) owns output + exit code.

Exit semantics (adapter): exit 2 on any CRIT findings, else 0.
Counting: crit += category.count for CRIT; warn += category.count for WARN.
INFO categories do NOT count toward either total (matching bash behaviour).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Directories excluded from scan (--exclude-dir equivalent).
_EXCLUDE_DIRS = frozenset({".venv", "node_modules", "__pycache__", ".git"})

SECRET_EXCLUDES = r"settings\.local\.json"
DANGER_EXCLUDES = (
    r"spec\.md|plan\.md|references/|worktrees/|node_modules/|/tests/|/protocols/"
    r"|audit-agent-configs\.sh|team\.forge/SKILL\.md|wiki/promote-decision\.sh"
    r"|hot-md-init\.sh|migrate-foundations-to-wiki\.sh"
)

# Ordered scan definitions: (pattern, severity, label, excludes).
# Order matches bash output order exactly.
_SCANS: list[tuple[str, str, str, str]] = [
    (r"sk-[a-zA-Z0-9]{32,}",              "CRIT", "Anthropic-style API key leak",        SECRET_EXCLUDES),
    (r"ghp_[a-zA-Z0-9]{36,}",             "CRIT", "GitHub personal access token leak",   SECRET_EXCLUDES),
    (r"AKIA[A-Z0-9]{16}",                 "CRIT", "AWS access key ID leak",               SECRET_EXCLUDES),
    (r"xox[bp]-[a-zA-Z0-9-]+",            "CRIT", "Slack token leak",                    SECRET_EXCLUDES),
    (r"--no-verify",                      "WARN", "--no-verify flag",                    DANGER_EXCLUDES),
    (r"--force",                          "WARN", "--force flag",                        DANGER_EXCLUDES),
    (r"git reset --hard",                 "WARN", "git reset --hard",                   DANGER_EXCLUDES),
    (r"bypassPermissions",                "WARN", "bypassPermissions used",             DANGER_EXCLUDES),
    (r'"command":[^"]*\$[A-Z_]+[^"]*"',   "CRIT", "Unquoted shell var in hook command", ""),
    (r'"mcpServers":[^}]*"[*]"',          "INFO", "MCP server with wildcard scope",     ""),
]


@dataclass
class Category:
    severity: str
    label: str
    matches: list[str]
    count: int


@dataclass
class AgentConfigReport:
    categories: list[Category]
    crit: int
    warn: int


def _walk(scan_dir: Path) -> list[Path]:
    """Return sorted list of scannable files, excluding dirs in _EXCLUDE_DIRS.

    Descends through directory symlinks. `Path.rglob` lists a symlinked directory but never
    recurses into it, and under the two-repo layout `.claude/skills/<name>` is exactly such a
    symlink into the DATA repo (spec 103 §3.2) — so the scanner went blind over most of its own
    surface while still exiting 0.

    The resolved-path visited set is a de-duplicator, not a termination guard: a cycle
    (`x/loop -> x`) already stops itself when the kernel raises ELOOP ~32 levels down, but not
    before yielding every file below it once per level (measured: 16x for a one-file dir). Two
    distinct links onto the same real directory are collapsed the same way.
    """
    files: list[Path] = []
    if not scan_dir.is_dir():
        return files
    seen: set[Path] = set()
    stack = [scan_dir]
    while stack:
        current = stack.pop()
        try:
            resolved = current.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        try:
            entries = list(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if entry.is_dir():
                if entry.name not in _EXCLUDE_DIRS:
                    stack.append(entry)
            elif entry.is_file():
                files.append(entry)
    return sorted(files)


def _grep_file(path: Path, pattern_re: re.Pattern[str]) -> list[str]:
    """Return grep -EnI style matches: 'path:lineno:line' for each matching line.

    Skips binary files (grep -I): a file is binary if its bytes contain NUL (b'\\x00').
    """
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    if b"\x00" in raw:
        return []
    text = raw.decode("utf-8", errors="replace")
    results: list[str] = []
    for lineno, line in enumerate(text.splitlines(), 1):
        if pattern_re.search(line):
            results.append(f"{path}:{lineno}:{line}")
    return results


def run(scan_dir: Path) -> AgentConfigReport:
    """Scan scan_dir and return an AgentConfigReport.

    Faithfully replicates: grep -rEnI --exclude-dir=.venv --exclude-dir=node_modules
    --exclude-dir=__pycache__ --exclude-dir=.git, with per-category excludes applied
    as grep -v -E '$excludes' over the whole 'path:lineno:content' match string.
    """
    files = _walk(scan_dir)
    categories: list[Category] = []
    crit = 0
    warn = 0

    for pattern, severity, label, excludes in _SCANS:
        pattern_re = re.compile(pattern)
        all_matches: list[str] = []
        for path in files:
            all_matches.extend(_grep_file(path, pattern_re))

        if excludes:
            excludes_re = re.compile(excludes)
            all_matches = [m for m in all_matches if not excludes_re.search(m)]

        if not all_matches:
            continue

        cat = Category(severity, label, all_matches, len(all_matches))
        categories.append(cat)
        if severity == "CRIT":
            crit += len(all_matches)
        elif severity == "WARN":
            warn += len(all_matches)
        # INFO does not count toward crit or warn totals.

    return AgentConfigReport(categories, crit, warn)
