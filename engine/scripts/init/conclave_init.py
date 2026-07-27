#!/usr/bin/env python3
"""conclave_init.py — scaffold a consumer project's Conclave DATA tree (098 D-6).

Scaffolds `<consumer>/.conclave/` (the DATA root), writes `roster.yaml` (096 nested
schema), scaffolds a wiki vault, mints >=1 advisor headlessly via `engine advisor create`,
and registers the SessionStart hook DATA-side in `<consumer>/.claude/settings.json`
with a RESOLVED absolute command path (never a literal ${CLAUDE_PLUGIN_ROOT}).

Path resolution is anchored on THIS file's location (engine/scripts/init/), NOT on
CONCLAVE_ENGINE_ROOT — the caller may pass an inconsistent value (098 D-6 reconcile #4).
Idempotent: re-running does not duplicate the roster, wiki, advisor, or hook entry.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Interpreter floor, enforced before the first thing that can fail below it. This file is the
# worst of the three without a guard: nothing here trips the floor early, so a sub-floor user
# answers the entire interactive interview and only then hits the failure. Refuse up front.
# Measured, not declared; see engine/__main__.py for the full note.
if sys.version_info < (3, 11):  # noqa: UP036 — see engine/__main__.py
    sys.stderr.write(
        f"Conclave requires Python 3.11 or newer.\n"
        f"This is Python {sys.version.split()[0]} at {sys.executable}.\n"
        f"Install a newer interpreter (e.g. `uv python install 3.13`) and re-run.\n"
    )
    sys.exit(1)

# Plugin/repo root resolved from this file: engine/scripts/init/ -> parents[3] = root.
ROOT = Path(__file__).resolve().parents[3]
ENGINE = ROOT / "engine"
HOOK_SCRIPT = ROOT / "hooks" / "sessionstart-conclave.py"
OBSIDIAN_SRC = ROOT / "engine" / "templates" / "obsidian"
OBSIDIAN_FILES = ("app.json", "appearance.json", "core-plugins.json")

NONINTERACTIVE = os.environ.get("CONCLAVE_INIT_NONINTERACTIVE") == "1"

DATA_SUBDIRS = (
    "agent-memory/advisors/briefings",
    "agent-memory/advisors/sessions",
    "agent-memory/advisors/decisions",
    "agent-memory/advisors/audits",
    "ops/specs",
    "ops/handoffs",
    "ops/decisions",
    "wiki",
)

DEFAULT_ADVISOR_ID = "advisor"
DEFAULT_ADVISOR_ROLE = "Advisor"
DEFAULT_ADVISOR_COLOR = "blue"


def _prompt(label: str, env_key: str, default: str) -> str:
    """Env var (non-interactive) or input() prompt for the same value."""
    val = os.environ.get(env_key)
    if val:
        return val
    if NONINTERACTIVE:
        return default
    entered = input(f"{label} [{default}]: ").strip()
    return entered or default


def resolve_data_root() -> Path:
    """DATA root (D-5): CONCLAVE_AI_ROOT if set, else ${CLAUDE_PROJECT_DIR}/.conclave,
    else $PWD/.conclave (standalone run outside the plugin runtime, #44 it-2)."""
    explicit = os.environ.get("CONCLAVE_AI_ROOT")
    if explicit:
        return Path(explicit).resolve()
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    if project:
        return (Path(project) / ".conclave").resolve()
    cwd_data = (Path.cwd() / ".conclave").resolve()
    sys.stderr.write(f"conclave_init: defaulting DATA root to {cwd_data}\n")
    return cwd_data


def consumer_root(data: Path) -> Path:
    project = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(project).resolve() if project else data.parent


def scaffold_tree(data: Path) -> None:
    for sub in DATA_SUBDIRS:
        (data / sub).mkdir(parents=True, exist_ok=True)


_GITIGNORE_BODY = (
    "# Conclave DATA caches — regenerated every session, never commit (#52)\n"
    "agent-memory/gh-cache/\n"
    "agent-memory/git-cache/\n"
    "agent-memory/run-log/\n"
    "# Obsidian volatile per-machine workspace state\n"
    "wiki/.obsidian/workspace*.json\n"
)


def write_gitignore(data: Path) -> bool:
    """Write .conclave/.gitignore excluding regenerated caches. Idempotent (#52)."""
    gi = data / ".gitignore"
    if gi.exists():
        return False
    gi.write_text(_GITIGNORE_BODY)
    return True


def offer_git_init(project: Path) -> str:
    """Version-control offer for a consumer project that isn't a git repo (#52).

    Runs `git init` only when CONCLAVE_GIT_INIT is truthy (durable opt-in — a repo
    is an external side-effect). Otherwise returns a suggestion. Returns a status
    string for the summary: 'exists' | 'initialized' | 'suggest' | 'skipped'.
    """
    if (project / ".git").exists():
        return "exists"
    if os.environ.get("CONCLAVE_GIT_INIT", "").strip().lower() in ("1", "true", "yes"):
        try:
            subprocess.run(["git", "init"], cwd=str(project), check=True,
                           capture_output=True, text=True)
            return "initialized"
        except (OSError, subprocess.CalledProcessError):
            return "skipped"
    return "suggest"


def write_roster(data: Path, name: str, owner: str) -> bool:
    """Write roster.yaml (096 nested schema). Idempotent — skip if present."""
    roster = data / "roster.yaml"
    if roster.exists():
        return False
    roster.write_text(
        "project:\n"
        f"  name: {name}\n"
        "  context_path: project-context.md\n"
        "  language: English\n"
        "  stack_profile: none\n"
        "github:\n"
        f"  owner: {owner}\n"
        "  ai_repo: null\n"
        "  main_repo: null\n"
        "  board_number: null\n"
        "knowledge:\n"
        "  wiki_path: wiki\n"
    )
    return True


def write_project_context(data: Path, name: str) -> bool:
    """Write the project-context.md stub roster.yaml:context_path points at (spec 103 §4).

    Idempotent — skip if present. Without it, every fresh instance carries a roster
    whose context_path names a file that nothing ever created.
    """
    context = data / "project-context.md"
    if context.exists():
        return False
    context.write_text(
        f"# {name} — Project Context\n\n"
        "> Canonical identity of this instance. Advisors read it for what the project *is*;\n"
        "> the engine never writes here. Fill it in — the scaffold is deliberately empty.\n\n"
        "## What this project is\n\n_(one paragraph — the problem, not the solution)_\n\n"
        "## Domain vocabulary\n\n_(terms an advisor must not get wrong)_\n\n"
        "## Constraints\n\n_(what the project will not trade away)_\n"
    )
    return True


def scaffold_wiki(data: Path, name: str) -> None:
    """Copy obsidian config (minus volatile workspace.json) + write a config stub."""
    obsidian_dst = data / "wiki" / ".obsidian"
    obsidian_dst.mkdir(parents=True, exist_ok=True)
    for fname in OBSIDIAN_FILES:
        src = OBSIDIAN_SRC / fname
        dst = obsidian_dst / fname
        if src.exists() and not dst.exists():
            shutil.copyfile(src, dst)
    config = data / "wiki" / "wiki.config.md"
    if not config.exists():
        config.write_text(
            f"# {name} — Conclave Wiki\n\n"
            "This Obsidian vault is the project's Conclave knowledge wiki.\n"
            "Advisors capture decisions, concepts, and domain context here.\n"
        )


def mint_advisor(data: Path, project: Path, advisor_id: str, role: str) -> bool:
    """Invoke `engine advisor create` in plugin mode. Idempotent — skip if flat .md exists."""
    agent_file = project / ".claude" / "agents" / f"{advisor_id}.md"
    if agent_file.exists():
        return False
    env = {
        **os.environ,
        "CLAUDE_PROJECT_DIR": str(project),
        "CONCLAVE_ENGINE_ROOT": str(ENGINE),
        "CONCLAVE_AI_ROOT": str(data),
        "CLAUDE_PLUGIN_DATA": os.environ.get("CLAUDE_PLUGIN_DATA", ""),
    }
    subprocess.run(
        [sys.executable, "-m", "engine", "advisor", "create",
         "--id", advisor_id, "--role", role, "--color", DEFAULT_ADVISOR_COLOR],
        env=env, cwd=str(ENGINE / "scripts"), check=True,
    )
    return True


def scaffold_forge_router(project: Path) -> bool:
    """Invoke `engine advisor scaffold-router --id forge`. Idempotent — skip if it already exists."""
    skill_file = project / ".claude" / "skills" / "conclave-forge" / "SKILL.md"
    if skill_file.exists():
        return False
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(project)}
    subprocess.run(
        [sys.executable, "-m", "engine", "advisor", "scaffold-router", "--id", "forge"],
        env=env, cwd=str(ENGINE / "scripts"), check=True,
    )
    return True


def register_hook(project: Path, data: Path) -> Path:
    """Merge a SessionStart hook + env into <consumer>/.claude/settings.json.

    The command is a RESOLVED absolute path — never a literal ${CLAUDE_PLUGIN_ROOT}
    (empty at SessionStart). Merges with existing keys/hooks/env; idempotent on command.
    """
    settings_path = project / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)

    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except json.JSONDecodeError:
            settings = {}

    command = f'python3 "{HOOK_SCRIPT}"'

    hooks = settings.setdefault("hooks", {})
    session_start = hooks.setdefault("SessionStart", [])
    already = any(
        h.get("command") == command
        for entry in session_start
        for h in entry.get("hooks", [])
    )
    if not already:
        session_start.append(
            {"matcher": "*", "hooks": [{"type": "command", "command": command}]}
        )

    env = settings.setdefault("env", {})
    env["CONCLAVE_ENGINE_ROOT"] = str(ENGINE)
    env["CONCLAVE_AI_ROOT"] = str(data)
    # Persist CLAUDE_PROJECT_DIR so every Bash subprocess (incl. the /conclave-<id> router
    # bootstrap) inherits it — else canonical_advisors() finds no project agent-defs and
    # drops the hired advisor, so its First Launch never fires (#56a). The value is the true
    # project root, not a worktree, so the enginelib worktree-escape guard is unaffected.
    env["CLAUDE_PROJECT_DIR"] = str(project)

    settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    return settings_path


def main() -> int:
    name = _prompt("Project / roster name", "ROSTER_NAME", "Conclave Project")
    owner = _prompt("GitHub owner", "ROSTER_GH_OWNER", "")

    data = resolve_data_root()
    project = consumer_root(data)

    scaffold_tree(data)
    gitignore_written = write_gitignore(data)
    roster_written = write_roster(data, name, owner)
    context_written = write_project_context(data, name)
    scaffold_wiki(data, name)

    sys.path.insert(0, str(ENGINE / "scripts"))
    from enginelib.provision import ensure_deps  # stdlib-only; safe on system python3
    _pdata = os.environ.get("CLAUDE_PLUGIN_DATA")
    if _pdata:
        ensure_deps(ROOT, Path(_pdata))  # best-effort

    minted = mint_advisor(data, project, DEFAULT_ADVISOR_ID, DEFAULT_ADVISOR_ROLE)
    forge_router = scaffold_forge_router(project)
    settings_path = register_hook(project, data)
    git_status = offer_git_init(project)

    print("conclave_init: scaffolded Conclave instance")
    print(f"  DATA root      : {data}")
    print(f"  .gitignore     : {'written' if gitignore_written else 'kept (exists)'}"
          f"  ({data / '.gitignore'})")
    print(f"  roster.yaml    : {'written' if roster_written else 'kept (exists)'}")
    print(f"  project-context: {'written' if context_written else 'kept (exists)'}")
    print(f"  wiki vault     : {data / 'wiki'}")
    print(f"  advisor minted : {'advisor' if minted else 'kept (exists)'}"
          f"  ({project / '.claude/agents' / (DEFAULT_ADVISOR_ID + '.md')})")
    print(f"  forge router   : {'scaffolded' if forge_router else 'kept (exists)'}"
          f"  ({project / '.claude/skills/conclave-forge/SKILL.md'})")
    print(f"  SessionStart   : {settings_path} -> {HOOK_SCRIPT}")
    _git_msg = {
        "exists": "already a git repo",
        "initialized": "git init ran (CONCLAVE_GIT_INIT set)",
        "suggest": "not a git repo — run `git init` to version-control .conclave/ "
                   "(or set CONCLAVE_GIT_INIT=1 to auto-init)",
        "skipped": "git init failed — run it manually",
    }[git_status]
    print(f"  git            : {_git_msg}")
    print("  next step      : /conclave:start")
    return 0


if __name__ == "__main__":
    sys.exit(main())
