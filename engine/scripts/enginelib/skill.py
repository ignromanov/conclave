"""enginelib/skill.py — skill existence resolution. Port of verify-skill.sh.

I/O-free: no print / argparse / sys.exit.

Accepted name forms:
  1. plain          e.g. "subagent-driven-development"
  2. plugin:skill   e.g. "superpowers:brainstorming"
  3. team.<advisor> e.g. "team.kai-cto"

Plugin cache layout: <CACHE>/<owner>/<plugin>/<version>/skills/<skill>/SKILL.md
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from enginelib import paths


def _global_dir() -> Path:
    env = os.environ.get("CONCLAVE_GLOBAL_SKILLS_DIR")
    return Path(env) if env else Path.home() / ".claude" / "skills"


def _cache_dir() -> Path:
    env = os.environ.get("CLAUDE_PLUGINS_CACHE")
    return Path(env) if env else Path.home() / ".claude" / "plugins" / "cache"


def _consumer_skill_dirs() -> list[Path]:
    """The consumer PROJECT's own skill roots, anchored on CLAUDE_PROJECT_DIR (#74).

    Distinct from `paths.skills_dir()`, which is `engine_root()/skills` — the skills the
    ENGINE ships. Outside the engine repo those are different trees, so a consumer's own
    skills resolved nowhere and the phantom audit reported them all as PHANTOM.

    `project_root()` falls back to `repo_root()`, which raises when no DATA root is
    locatable; a caller with neither anchor still deserves the global/cache roots, so an
    unresolvable project degrades to "no project roots" rather than an exception.
    """
    try:
        project = paths.project_root()
    except RuntimeError:
        return []
    return [project / ".claude" / "skills", project / ".agents" / "skills"]


def verify(name: str) -> Path | None:
    """Return the SKILL.md (or command .md) Path if the skill is found, else None.

    Search order (first match wins), most specific first:
      1. Consumer project: <project>/.claude/skills/ then <project>/.agents/skills/
      2. Engine-shipped: skills_dir() (== engine_root()/skills) / name / SKILL.md
      3. Global user skills: GLOBAL/name/SKILL.md then GLOBAL/bare/SKILL.md
      4. Plugin cache skills: CACHE/*/*/*/skills/bare/SKILL.md
         (if namespaced, prefer match whose plugin dir == namespace)
      5. Plugin cache commands: CACHE/*/*/*/commands/bare.md (same preference)

    Step 1 precedes the global root deliberately: before #74 a consumer skill sharing a
    name with a global one resolved to the GLOBAL file — a wrong-content hit, quieter and
    worse than the PHANTOM the audit reported for the rest.
    """
    bare = name.split(":", 1)[-1]   # "superpowers:brainstorming" -> "brainstorming"
    ns = name.split(":", 1)[0] if ":" in name else ""

    # 1. Consumer project roots
    for root in _consumer_skill_dirs():
        for key in (name, bare):
            candidate = root / key / "SKILL.md"
            if candidate.is_file():
                return candidate

    # 2. Engine-shipped skills
    candidate = paths.skills_dir() / name / "SKILL.md"
    if candidate.is_file():
        return candidate

    # 3. Global user skills
    global_dir = _global_dir()
    for key in (name, bare):
        candidate = global_dir / key / "SKILL.md"
        if candidate.is_file():
            return candidate

    cache = _cache_dir()

    # 4. Plugin cache skills (owner/plugin/version/skills/bare/SKILL.md)
    skill_matches = sorted(cache.glob(f"*/*/*/skills/{bare}/SKILL.md"))
    if ns:
        for p in skill_matches:
            if p.parents[3].name == ns:   # parents[3] == .../plugin
                return p
    if skill_matches:
        return skill_matches[0]

    # 5. Plugin cache commands (owner/plugin/version/commands/bare.md)
    cmd_matches = sorted(cache.glob(f"*/*/*/commands/{bare}.md"))
    if ns:
        for p in cmd_matches:
            if p.parents[2].name == ns:   # parents[2] == .../plugin
                return p
    if cmd_matches:
        return cmd_matches[0]

    return None


def stocktake_rows(skills_dir: Path, sessions_dir: Path, now_epoch: int) -> list[dict]:
    """Evaluate every immediate subdir of skills_dir for a quarterly audit.

    Returns a list of row dicts: name, verdict, age_days, lines, bytes, invocations, mtime.
    For dirs with no SKILL.md, verdict is 'missing_skillmd' and age_days/invocations/mtime
    are the string "N/A" (matching bash emit for that edge case).

    now_epoch is injectable so tests are deterministic.
    I/O-free of stdout/argparse/sys.exit (file reads + glob OK).
    """
    rows: list[dict] = []

    subdirs = sorted(d for d in skills_dir.iterdir() if d.is_dir())
    for skill_dir in subdirs:
        name = skill_dir.name
        skill_md = skill_dir / "SKILL.md"

        if not skill_md.is_file():
            rows.append({
                "name": name,
                "verdict": "missing_skillmd",
                "age_days": "N/A",
                "lines": 0,
                "bytes": 0,
                "invocations": "N/A",
                "mtime": "N/A",
            })
            continue

        stat = skill_md.stat()
        mtime = int(stat.st_mtime)
        age_days = (now_epoch - mtime) // 86400

        content_bytes = skill_md.read_bytes()
        nbytes = len(content_bytes)
        nlines = content_bytes.count(b"\n")

        text = content_bytes.decode("utf-8", errors="replace")
        has_name = sum(1 for ln in text.splitlines() if ln.startswith("name:"))
        has_description = sum(1 for ln in text.splitlines() if ln.startswith("description:"))

        # Count invocations: total lines across SESSIONS_DIR matching the grep pattern.
        # Mirrors: grep -rE "Skill\s*:\s*<name>|/<name>\s" SESSIONS_DIR | wc -l
        invocations = 0
        if sessions_dir.is_dir():
            pattern = re.compile(
                rf"Skill\s*:\s*{re.escape(name)}|/{re.escape(name)}\s"
            )
            for session_file in sorted(sessions_dir.rglob("*")):
                if session_file.is_file():
                    try:
                        content = session_file.read_text(encoding="utf-8", errors="replace")
                        for line in content.splitlines():
                            if pattern.search(line):
                                invocations += 1
                    except OSError:
                        pass

        # Verdict cascade — order matters, first hit wins.
        if has_name == 0 or has_description == 0:
            verdict = "Improve(frontmatter)"
        elif nlines < 30:
            verdict = "Improve(stub)"
        elif age_days > 180 and invocations < 2:
            verdict = "Retire(stale+unused)"
        elif invocations == 0 and age_days > 90:
            verdict = "Retire(unused)"
        else:
            verdict = "Keep"

        rows.append({
            "name": name,
            "verdict": verdict,
            "age_days": age_days,
            "lines": nlines,
            "bytes": nbytes,
            "invocations": invocations,
            "mtime": mtime,
        })

    return rows
