"""enginelib/audit/scope_collision — Forge audit Cat 11 (spec 089, D8/R6).

Detects scope collisions between agents: any owns: token claimed by ≥2 distinct agents.
I/O-free: no print/argparse/sys.exit.
"""
from __future__ import annotations

import re
from pathlib import Path


def _extract_frontmatter(text: str) -> str:
    """Return text between the first two --- delimiters, or empty string."""
    lines = text.splitlines()
    count = 0
    fm: list[str] = []
    for line in lines:
        if re.match(r"^---\s*$", line):
            count += 1
            if count == 1:
                continue
            if count == 2:
                break
        if count == 1:
            fm.append(line)
    return "\n".join(fm)


def _parse_owns(fm_text: str) -> list[str]:
    """Parse owns: tokens from frontmatter text.

    Supports:
    - Inline: owns: [a, b, c]
    - Block list: owns:\\n  - token
    """
    tokens: list[str] = []
    lines = fm_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        # Inline form: owns: [a, b, c]
        m = re.match(r"^owns:\s*\[([^\]]*)\]", line)
        if m:
            for tok in m.group(1).split(","):
                tok = tok.strip().strip("\"'")
                if tok:
                    tokens.append(tok)
            break
        # Block form opener: owns:
        if re.match(r"^owns:\s*$", line):
            i += 1
            while i < len(lines):
                item = lines[i]
                m2 = re.match(r"^\s+-\s+(.*)", item)
                if m2:
                    tok = m2.group(1).strip().strip("\"'")
                    if tok:
                        tokens.append(tok)
                    i += 1
                elif re.match(r"^[^\s-]", item):
                    break  # top-level key ends the block
                else:
                    i += 1
            break
        i += 1
    return tokens


def run(agents_dirs: list[Path]) -> dict[str, list[str]]:
    """Scan all agents_dirs for owns: collisions.

    Skips dirs that do not exist. A collision is a token claimed by ≥2 distinct
    agents (one agent listing the same token twice is NOT a collision).

    Returns {token: [agent1, agent2, ...]} for colliding tokens only (empty = no collisions).
    """
    # token → set of distinct agent names
    token_agents: dict[str, set[str]] = {}

    for agents_dir in agents_dirs:
        if not agents_dir.is_dir():
            continue
        for md_file in sorted(agents_dir.glob("*.md")):
            agent_name = md_file.stem
            fm = _extract_frontmatter(md_file.read_text(encoding="utf-8"))
            for tok in _parse_owns(fm):
                token_agents.setdefault(tok, set()).add(agent_name)

    return {
        tok: sorted(agents)
        for tok, agents in token_agents.items()
        if len(agents) >= 2
    }
