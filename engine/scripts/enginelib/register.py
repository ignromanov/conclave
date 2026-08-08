"""enginelib/register.py — discover advisors and build the Custom-Agents table;
also scaffold new Executor agents (create_executor).

I/O-free core: no stdout, no argparse, no sys.exit. File reads are fine.
CLI adapter lives in engine/cmd/register.py.

Advisor names include the full 'team.' prefix (the SKILL dir name).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Bare lifecycle/meta skill ids — infrastructure, not advisors. Excluded from
# discovery regardless of the conclave-/team. dir prefix (#48).
_LIFECYCLE: frozenset[str] = frozenset({
    "start", "processing", "done", "handoff", "forge",
    "hire", "retro", "feedback", "feedback-triage",
})

# Advisor SKILL-dir prefixes tolerated during the #48 migration (conclave- is
# canonical; team. is legacy). Kept local to avoid an enginelib.paths import cycle.
_ADVISOR_PREFIXES = ("conclave-", "team.")


def discover_advisors(roster_dir: Path) -> list[str]:
    """Return sorted BARE advisor ids from roster_dir SKILL dirs, tolerating both
    the canonical conclave-<id> and legacy team.<id> layouts, excluding lifecycle.

    Bare ids (not dir-names) are the contract: the agent-def files consumers look
    up are bare `<id>.md`, so returning `team.<id>` mis-resolved the lookup (#48).
    """
    ids: set[str] = set()
    for prefix in _ADVISOR_PREFIXES:
        for p in roster_dir.glob(f"{prefix}*/SKILL.md"):
            bare = p.parent.name[len(prefix):]
            if bare not in _LIFECYCLE:
                ids.add(bare)
    return sorted(ids)


def advisor_role(agent_file: Path) -> str:
    """Return the stripped description from an agent .md file, or '—' if absent.

    DELIBERATE DEVIATION from bash: the bash `|| echo "—"` fallback was dead code
    (the pipe always exits 0, so empty string "" was returned on a missing file or
    missing description). Python honors the intent: return "—" when no description
    is found.
    """
    if agent_file.is_file():
        for line in agent_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("description:"):
                return line[len("description:"):].strip().replace('"', '').replace('|', '')
    return "—"


def agents_table(advisors: list[str], agents_dir: Path) -> str:
    """Build the Custom-Agents markdown table for the given advisor list."""
    rows = ["| Agent | Purpose |", "|-------|---------|"]
    for a in advisors:
        rows.append(f"| `{a}` | {advisor_role(agents_dir / f'{a}.md')} |")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Executor scaffolding — port of register-executor.sh
# ---------------------------------------------------------------------------

@dataclass
class ExecutorOpts:
    chosen_name: str
    role: str
    emoji: str
    color: str
    tools: str = ""


# The colours the harness renders for a subagent. Source: the `color` row of the subagent
# frontmatter reference (https://code.claude.com/docs/en/sub-agents). Anything else is accepted
# by YAML and dropped at render time, which is how seven shipped agents ended up sharing the
# same absence of a colour while appearing to be distinctly labelled.
VALID_AGENT_COLORS: frozenset[str] = frozenset(
    {"red", "blue", "green", "yellow", "purple", "orange", "pink", "cyan"}
)


class EmojiCollisionError(Exception):
    """Raised when the requested emoji is reserved or already used by another agent."""


def create_executor(
    opts: ExecutorOpts,
    today: str,
    dry_run: bool = False,
) -> tuple[Path, Path]:
    """Scaffold a new Executor agent-def; return (agent_def_path, memory_dir).

    #68 create-path reconcile: emits the `agents/exec-<name>-<role>.md` agent-def
    the live roster actually uses (inline voice, `conclave:exec-*` dispatch), NOT a
    dead `skills/exec.<name>-<role>/` skill-dir. Memory lives at the canonical
    `agent-memory/executors/<name>-<role>/` (bare `<name>-<role>` — the parent dir
    already says "executors", so the `exec-`/`exec.` surface-prefix is dropped here).

    Raises ValueError (→ exit 2) on invalid inputs.
    Raises EmojiCollisionError (→ exit 3) on emoji collision.
    File reads are fine; no print/argparse/sys.exit.
    """
    from enginelib import paths, snapshot

    # 1. Validate inputs (faithful port of bash argument checks)
    if not opts.chosen_name:
        raise ValueError("missing --chosen-name")
    if re.search(r"[^a-zA-Z0-9_-]", opts.chosen_name):
        raise ValueError("invalid --chosen-name: must contain only alphanumeric, hyphen, underscore")
    if not opts.role:
        raise ValueError("missing --role")
    if not opts.emoji:
        raise ValueError("missing --emoji")
    if not opts.color:
        raise ValueError("missing --color")
    if opts.color not in VALID_AGENT_COLORS:
        raise ValueError(
            f"invalid --color: {opts.color} (must be one of {', '.join(sorted(VALID_AGENT_COLORS))})"
        )
    if opts.role not in {"dev", "test"}:
        raise ValueError(f"invalid role: {opts.role} (must be dev|test)")

    # 2. Tool scope. A subagent whose `tools:` entries resolve to nothing fails to launch, so
    #    this must never fall through to the free-text placeholder collapse below.
    tools = opts.tools or (
        "Read, Write, Edit, Grep, Glob, Bash" if opts.role == "dev" else "Read, Grep, Glob, Bash"
    )

    # 3. Reserved-emoji collision (bash: grep -A1 "## Reserved emojis" | tail -1)
    palette_lines = (paths.forge_references_dir() / "color-palette.md").read_text(encoding="utf-8").splitlines()
    reserved_line = ""
    for i, line in enumerate(palette_lines):
        if "## Reserved emojis" in line:
            if i + 1 < len(palette_lines):
                reserved_line = palette_lines[i + 1]
            break
    if reserved_line and opts.emoji in reserved_line:
        raise EmojiCollisionError(
            f"emoji collision: {opts.emoji} is reserved (see color-palette.md)"
        )

    # 4. Personality collision (bash: find skills_dir -maxdepth 2 -name personality.md)
    # -maxdepth 2 finds skills/<dir>/personality.md but NOT skills/<dir>/memory/personality.md
    # (depth 3). Faithful bash quirk: memory/personality.md is missed — preserve it.
    for pmd in paths.skills_dir().glob("*/personality.md"):
        for line in pmd.read_text(encoding="utf-8").splitlines():
            if re.match(rf"^# .*{re.escape(opts.emoji)}", line):
                raise EmojiCollisionError(
                    f"emoji collision: {opts.emoji} is used by another agent"
                )

    # 5. Target paths
    #    agent-def stem uses the hyphenated `exec-<name>-<role>` (flat agents/ dir needs
    #    the `exec-` prefix to disambiguate from advisor defs); memory slug is the bare
    #    `<name>-<role>` (the executors/ parent already scopes it — no surface-prefix).
    slug = f"exec-{opts.chosen_name}-{opts.role}"
    mem_slug = f"{opts.chosen_name}-{opts.role}"
    agent_def = paths.plugin_agents_dir() / f"{slug}.md"
    memory_dir = paths.repo_root() / "agent-memory" / "executors" / mem_slug

    # 6. Dry-run: validate only, no writes
    if dry_run:
        return agent_def, memory_dir

    # 7. Create directories
    agent_def.parent.mkdir(parents=True, exist_ok=True)
    memory_dir.mkdir(parents=True, exist_ok=True)

    # agent-def — literal identity substitutions, then collapse remaining free-text
    # placeholders to a self-introduction stub. The catch-all is character-class-bounded
    # (`[^}]` can't cross a `}}`), so it can't over-match between placeholders and it
    # handles multi-line placeholders; it MUST run AFTER the literal replaces above.
    tmpl = (paths.templates_dir() / "executor-agent.md").read_text(encoding="utf-8")
    rendered = tmpl
    rendered = rendered.replace("{{chosen-name}}", opts.chosen_name)
    rendered = rendered.replace("{{role}}", opts.role)
    rendered = rendered.replace("{{emoji}}", opts.emoji)
    rendered = rendered.replace("{{color}}", opts.color)
    rendered = rendered.replace("{{tools}}", tools)
    rendered = rendered.replace("{{YYYY-MM-DD}}", today)
    rendered = rendered.replace("{{Name}}", opts.chosen_name)
    rendered = rendered.replace("{{Emoji}}", opts.emoji)
    rendered = rendered.replace("{{Role description}}", f"{opts.role} worker")
    rendered = re.sub(r"\{\{[^}]*\}\}", "TBD by self-introduction", rendered)
    snapshot.snapshot_write(agent_def, rendered)

    # MEMORY.md — static heredoc (trailing blank line matches bash <<EOF)
    memory_content = (
        f"# Memory — {opts.chosen_name} (exec-{opts.chosen_name}-{opts.role})\n"
        "\n"
        "> Flaky-ledger style. ≤50 lines hard cap. Only new entries are appended here."
        " Oldest entries pruned manually on overflow.\n"
        "\n"
        "## Burns + wins\n"
        "\n"
    )
    snapshot.snapshot_write(memory_dir / "MEMORY.md", memory_content)

    return agent_def, memory_dir
