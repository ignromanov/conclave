"""scans/identity.py — section 1: Who I am (personality.md body).

Port of briefing-build.sh lines 165-186.
Reads personality-eager.md (preferred) or falls back to personality.md.
Strips YAML frontmatter, trims leading blank lines.
"""
from __future__ import annotations

from briefing.scans import ScanCtx

# The remedy must name a command that exists. `/team.forge` never shipped under
# that name and the `team.` prefix is retired entirely, so the one line an advisor
# sees when its persona is missing pointed at nothing it could run.
_PLACEHOLDER = "_(personality.md not yet written — run /conclave:forge to seed it)_"


def build(ctx: ScanCtx) -> str:
    """Return the body of the personality file with frontmatter stripped.

    Prefers personality-eager.md (≤500 words, briefing-optimised half);
    falls back to personality.md if eager variant is absent.
    Falls back to the placeholder string if neither file exists.
    Matches bash awk logic: strip opening/closing --- block, then trim
    leading blank lines.
    """
    eager_path = ctx.personality_path.parent / "personality-eager.md"
    path = eager_path if eager_path.is_file() else ctx.personality_path
    if not path.is_file():
        return _PLACEHOLDER

    text = path.read_text(encoding="utf-8")
    body = _strip_frontmatter(text)
    # Trim leading blank lines (bash: awk 'NF{found=1} found').
    lines = body.splitlines(keepends=False)
    # Find first non-empty line.
    start = 0
    for i, line in enumerate(lines):
        if line.strip():
            start = i
            break
    else:
        # All blank — return placeholder.
        return _PLACEHOLDER

    result = "\n".join(lines[start:])
    # If nothing meaningful remains, fall back.
    if not result.strip():
        return _PLACEHOLDER
    return result


def _strip_frontmatter(text: str) -> str:
    """Strip YAML frontmatter block (--- ... ---) from the top of text.

    Mirrors the bash awk logic exactly:
      BEGIN{fm=0; body=0}
      /^---$/ { toggle fm/body }
      body==1 { print }
      body==0 && fm==0 { print }

    Lines before the opening --- are printed (fm==0, body==0).
    Lines inside --- block are suppressed.
    Lines after closing --- are printed (body==1).
    """
    lines = text.splitlines(keepends=False)
    fm = False
    body = False
    out: list[str] = []
    for line in lines:
        if line == "---":
            if not fm and not body:
                fm = True
                continue
            if fm:
                fm = False
                body = True
                continue
        if body:
            out.append(line)
        elif not fm:
            out.append(line)
    return "\n".join(out)
