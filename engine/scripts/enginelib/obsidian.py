"""Obsidian markdown primitives parser (port of lib/obsidian-parse.sh).

Public API — each function takes a Path and returns list[str]:
    parse_wikilinks      [[target]] links (not embeds), aliases stripped
    parse_embeds         ![[target]] embed links, aliases stripped
    parse_tags           frontmatter + body tags, sorted and deduplicated
    parse_block_ids      ^block-id at EOL, formatted <linenum>:<id>
    parse_yaml_relations frontmatter related: list or singleton

Returns [] when no matches. I/O-free core: no stdout, no CLI parsing, no process exit — pathlib reads only.
"""

import re
from pathlib import Path


def _resolve_alias(s: str) -> str:
    """Strip unescaped | alias suffix; escaped \\| survives as literal |.

    Mirrors the bash _resolve_alias awk helper:
      1. Replace \\| with SOH placeholder (\x01)
      2. Strip everything from the first remaining | onward
      3. Restore \x01 to |
    """
    s = s.replace('\\|', '\x01')
    pipe = s.find('|')
    if pipe != -1:
        s = s[:pipe]
    return s.replace('\x01', '|')


def parse_wikilinks(file: Path) -> list[str]:
    """Return [[target]] links; ![[embeds]] excluded; aliases stripped."""
    content = file.read_text(encoding="utf-8")
    # Strip all ![[...]] embeds first (mirrors sed 's/!\[\[[^]]*\]\]//g')
    content = re.sub(r'!\[\[[^\]]*\]\]', '', content)
    # Extract [[...]] contents (mirrors grep -oE '\[\[[^]]+\]\]')
    matches = re.findall(r'\[\[([^\]]+)\]\]', content)
    return [_resolve_alias(m) for m in matches]


def parse_embeds(file: Path) -> list[str]:
    """Return ![[target]] embed links; plain [[wikilinks]] excluded; aliases stripped."""
    content = file.read_text(encoding="utf-8")
    matches = re.findall(r'!\[\[([^\]]+)\]\]', content)
    return [_resolve_alias(m) for m in matches]


# Body tag: at start-of-line or after whitespace; must start with [a-z] after #
_BODY_TAG_RE = re.compile(r'(?:^|[ \t])#([a-z][a-z0-9/_-]*)')


def _parse_frontmatter_tags(lines: list[str]) -> list[str]:
    """Extract tags from YAML frontmatter (between first two --- fences)."""
    in_fm = False
    fence_count = 0
    result: list[str] = []
    for line in lines:
        if line == '---':
            fence_count += 1
            if fence_count == 1:
                in_fm = True
                continue
            if fence_count == 2:
                break
        if not in_fm:
            continue
        if line.startswith('tags:'):
            value = line[len('tags:'):].strip()
            # Strip surrounding brackets (mirrors awk gsub(/^\[|\]$/, "", line))
            if value.startswith('['):
                value = value[1:]
            if value.endswith(']'):
                value = value[:-1]
            for item in value.split(','):
                item = item.strip()
                if item:
                    result.append(item)
    return result


def _parse_body_tags(lines: list[str]) -> list[str]:
    """Extract #tag references from body (after frontmatter). Mirrors _parse_body_tags awk.

    Note: body tags inside fenced code blocks ARE matched (bash known limitation).
    Tags are only extracted when past_fm is True (requires frontmatter fences).
    """
    in_fm = False
    fence_count = 0
    past_fm = False
    result: list[str] = []
    for line in lines:
        if line == '---':
            fence_count += 1
            if fence_count == 1:
                in_fm = True
                continue
            if fence_count == 2:
                in_fm = False
                past_fm = True
                continue
        if in_fm:
            continue
        if past_fm:
            result.extend(_BODY_TAG_RE.findall(line))
    return result


def parse_tags(file: Path) -> list[str]:
    """Return frontmatter + body tags, sorted and deduplicated (mirrors sort -u)."""
    lines = file.read_text(encoding="utf-8").splitlines()
    all_tags = _parse_frontmatter_tags(lines) + _parse_body_tags(lines)
    return sorted(set(t for t in all_tags if t))


def parse_block_ids(file: Path) -> list[str]:
    """Return ^block-id anchors at EOL, formatted <linenum>:<id> (1-based line numbers).

    Mirrors: grep -nE '\\^[a-z0-9][a-z0-9_-]*$' | sed 's/:(.*)\\^(...)/:\\2/'
    Block IDs mid-line are NOT matched (only EOL).
    """
    pattern = re.compile(r'\^([a-z0-9][a-z0-9_-]*)$')
    result: list[str] = []
    for i, line in enumerate(file.read_text(encoding="utf-8").splitlines(), start=1):
        m = pattern.search(line)
        if m:
            result.append(f"{i}:{m.group(1)}")
    return result


def parse_yaml_relations(file: Path) -> list[str]:
    """Return frontmatter related: entries (list or singleton). [] if missing."""
    in_fm = False
    fence_count = 0
    for line in file.read_text(encoding="utf-8").splitlines():
        if line == '---':
            fence_count += 1
            if fence_count == 1:
                in_fm = True
                continue
            if fence_count == 2:
                break
        if not in_fm:
            continue
        if line.startswith('related:'):
            value = line[len('related:'):].strip()
            if value.startswith('['):
                # List form: strip brackets, split by comma
                inner = value[1:]
                if inner.endswith(']'):
                    inner = inner[:-1]
                return [item.strip() for item in inner.split(',') if item.strip()]
            else:
                # Singleton
                return [value] if value else []
    return []
