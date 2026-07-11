"""enginelib/audit/skills.py — I/O-free report builder for `engine audit skills`.

Contract: filesystem READS are allowed (dirs, JSON files). No print / argparse / sys.exit.
The file WRITE, date clock, and stdout lines all live in the adapter (_skills in engine/cmd/audit.py).

Public surface used by the adapter:
  - _claude_home()        path helpers for env-overridable roots
  - user_skills_dir()
  - plugins_json()
  - settings_json()
  - SkillsReport          dataclass returned by run()
  - run(...)              build and return the report
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Env-overridable path helpers (testable; called by the adapter)
# ---------------------------------------------------------------------------

_GROUPS = [
    ("bash", ["bash-pro", "bash-scripting", "bash-defensive-patterns"]),
    (
        "token-context",
        [
            "context-management",
            "context-engineering",
            "token-optimizer",
            "token-efficiency",
            "claude-cost-optimization",
        ],
    ),
    (
        "agent-skill-author",
        ["agent-authoring", "subagent-authoring", "subagent-creator", "skill-creator"],
    ),
    ("video", ["ai-marketing-videos", "video-script", "remotion-best-practices"]),
    (
        "advisor-mimic",
        ["cto-advisor", "c-level-advisor", "agentic-workflow-orchestration"],
    ),
    (
        "next",
        ["next-best-practices", "next-cache-components", "vercel-react-best-practices"],
    ),
]


def _claude_home() -> Path:
    env = os.environ.get("CONCLAVE_CLAUDE_HOME")
    return Path(env) if env else Path.home() / ".claude"


def user_skills_dir() -> Path:
    env = os.environ.get("CONCLAVE_GLOBAL_SKILLS_DIR")
    return Path(env) if env else _claude_home() / "skills"


def plugins_json() -> Path:
    return _claude_home() / "plugins" / "installed_plugins.json"


def settings_json() -> Path:
    return _claude_home() / "settings.json"


# ---------------------------------------------------------------------------
# Report dataclass
# ---------------------------------------------------------------------------


@dataclass
class SkillsReport:
    markdown: str
    user_count: int
    project_count: int
    plugin_count: int


# ---------------------------------------------------------------------------
# Pure helpers (port of bash helper functions)
# ---------------------------------------------------------------------------


def _list_skills(d: Path) -> list[str]:
    """Sorted skill names under d, excluding exactly '_quarantine'. Missing dir → []."""
    if not d.is_dir():
        return []
    return sorted(
        entry.name
        for entry in d.iterdir()
        if entry.name != "_quarantine"
    )


def _load_json(p: Path) -> dict:
    """Load JSON from p; return {} on missing file, unreadable file, or parse error."""
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}


def _enabled_state(ep: dict) -> str:
    on = sum(1 for v in ep.values() if v)
    off = sum(1 for v in ep.values() if not v)
    return f"{on} enabled, {off} explicitly disabled, {len(ep)} total in map"


def _duplicate_skill_candidates(user_skills: list[str], project_skills: list[str]) -> str:
    """Port of duplicate_skill_candidates bash helper.

    Two parts (in order):
    1. Substring cross-check (port of awk): for each skill in sorted union, check all
       prior skills for substring match. Deterministic sorted insertion order.
    2. Manual GROUPS heuristic: for each group, if >1 members are present, emit a line.
    """
    all_skills = sorted(set(user_skills) | set(project_skills))
    lines: list[str] = []

    # Part 1: substring awk port — seen grows in sorted order (insertion = sorted order)
    seen: list[str] = []
    for line in all_skills:
        for kw in seen:
            if kw in line:
                lines.append(f"{kw}: {line}")
        seen.append(line)

    # Part 2: GROUPS heuristic — verbatim bash member order, leading-space accumulation
    for name, members in _GROUPS:
        present = ""
        for m in members:
            if m in all_skills:
                present += " " + m
        count = len(present.split())
        if count > 1:
            lines.append(f"  - **{name}** ({count}×):{present}")

    return "\n".join(lines)


def _installed_not_in_enabled_map(plugins: dict, ep: dict) -> str:
    """Port of installed_not_in_enabled_map: S8 candidates."""
    absent = sorted(set(plugins) - set(ep))
    parts = [f"Count: {len(absent)}"]
    for p in absent:
        parts.append(f"  - {p}")
    return "\n".join(parts)


def _project_scoped_duplicates(plugins: dict) -> str:
    """Port of project_scoped_duplicates: S10 — plugin at both project + user scope."""
    lines: list[str] = []
    for name, instances in plugins.items():
        scopes = [i.get("scope") for i in instances]
        if "project" in scopes and "user" in scopes:
            for inst in instances:
                if inst.get("scope") == "project":
                    lines.append(f"  - {name} (project: {inst.get('projectPath', '?')})")
                    break
    return "\n".join(lines)


def _disabled_plugins_list(ep: dict) -> str:
    """Port of disabled_plugins_list: explicit false in enabledPlugins."""
    lines: list[str] = []
    for k, v in sorted(ep.items()):
        if not v:
            lines.append(f"  - {k}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report emitter
# ---------------------------------------------------------------------------


def _emit_report(
    today: str,
    user_count: int,
    project_count: int,
    plugin_count: int,
    enabled_str: str,
    s3: str,
    s8: str,
    s10: str,
    disabled: str,
    user_list: str,
    project_list: str,
) -> str:
    return f"""\
---
date: {today}
operator: forge
protocol: audit-skills
mode: inventory-only
version: 1.0.0
---

# Skills/Plugins Inventory — {today}

## Headline counts

| Surface | Count |
|---------|-------|
| Loose user skills (`~/.claude/skills/`) | {user_count} |
| Loose project skills (`.claude/skills/`) | {project_count} |
| Installed plugins | {plugin_count} |
| Plugin enable-map state | {enabled_str} |

## Defect candidates

### S3 — Duplicate-canon clusters
{s3}

### S8 — Sleeping plugins (installed but absent from enabledPlugins map)
{s8}

### S10 — Project-scoped duplicates
{s10}

### Currently disabled (explicit `false` in enabledPlugins)
{disabled}

## Full inventory

<details>
<summary>User skills ({user_count})</summary>

```
{user_list}
```
</details>

<details>
<summary>Project skills ({project_count})</summary>

```
{project_list}
```
</details>

## Next stages

This report covers Stage 1 (INVENTORY) only.
For Stages 2-8 (CLUSTER, PROPOSE, APPROVE, APPLY, VERIFY, LOG, COMMIT),
follow `protocols/audit-skills.md` interactively — agent dispatch + AskUserQuestion gates required.

"""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    user_skills_dir: Path,
    project_skills_dir: Path,
    plugins_json: Path,
    settings_json: Path,
    today: str,
) -> SkillsReport:
    """Build and return a SkillsReport. Reads dirs + JSON files; never prints or exits."""
    user_skills = _list_skills(user_skills_dir)
    project_skills = _list_skills(project_skills_dir)
    user_count = len(user_skills)
    project_count = len(project_skills)

    plugins_data = _load_json(plugins_json)
    settings_data = _load_json(settings_json)
    plugins = plugins_data.get("plugins", {})
    ep = settings_data.get("enabledPlugins", {})
    plugin_count = len(plugins)

    enabled_str = _enabled_state(ep)
    s3 = _duplicate_skill_candidates(user_skills, project_skills)
    s8 = _installed_not_in_enabled_map(plugins, ep)
    s10 = _project_scoped_duplicates(plugins)
    disabled = _disabled_plugins_list(ep)
    user_list = "\n".join(user_skills)
    project_list = "\n".join(project_skills)

    markdown = _emit_report(
        today,
        user_count,
        project_count,
        plugin_count,
        enabled_str,
        s3,
        s8,
        s10,
        disabled,
        user_list,
        project_list,
    )

    return SkillsReport(
        markdown=markdown,
        user_count=user_count,
        project_count=project_count,
        plugin_count=plugin_count,
    )
