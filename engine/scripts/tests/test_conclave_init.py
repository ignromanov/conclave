import os
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[3]
INIT = ROOT / "engine/scripts/init/conclave_init.py"


def _run(tmp_path):
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path), "CONCLAVE_ENGINE_ROOT": str(ROOT / "engine"),
           "CONCLAVE_INIT_NONINTERACTIVE": "1", "ROSTER_NAME": "demo", "ROSTER_GH_OWNER": "acme"}
    return subprocess.run(["python3", str(INIT)], env=env, check=True, cwd=str(tmp_path),
                          capture_output=True, text=True)


def test_init_scaffolds_data_tree(tmp_path):
    _run(tmp_path)
    d = tmp_path / ".conclave"
    assert (d / "roster.yaml").exists()
    for sub in ["agent-memory/advisors/briefings", "agent-memory/advisors/sessions",
                "agent-memory/advisors/decisions", "agent-memory/advisors/audits",
                "ops/specs", "ops/handoffs", "ops/decisions", "wiki"]:
        assert (d / sub).is_dir(), sub
    settings = (tmp_path / ".claude/settings.json")
    assert settings.exists()
    raw = settings.read_text()
    assert "SessionStart" in raw
    assert "${CLAUDE_PLUGIN_ROOT}" not in raw
    # env-export (#56a): CLAUDE_PROJECT_DIR must be persisted so every Bash subprocess
    # (incl. the /conclave-<id> router bootstrap) inherits it — else canonical_advisors()
    # drops the hired advisor and its First Launch never fires.
    import json
    env = json.loads(raw).get("env", {})
    assert env.get("CLAUDE_PROJECT_DIR") == str(tmp_path), "init must persist CLAUDE_PROJECT_DIR"
    assert list((tmp_path / ".claude/agents").rglob("*.md")), "init must mint >=1 advisor"


def test_init_scaffolds_the_file_context_path_names(tmp_path):
    # roster.yaml declares `context_path: project-context.md`; before spec 103 W3 nothing
    # ever created it, so every fresh instance's roster named a file that did not exist.
    _run(tmp_path)
    d = tmp_path / ".conclave"
    context_path = [ln.split(":", 1)[1].strip()
                    for ln in (d / "roster.yaml").read_text().splitlines()
                    if ln.strip().startswith("context_path:")][0]
    assert (d / context_path).exists(), f"roster names {context_path}, init did not create it"


def test_init_copies_obsidian_template_into_the_vault(tmp_path):
    # scaffold_wiki() copies the config with `if src.exists()`, so a template that is
    # not where OBSIDIAN_SRC points produces a vault with no Obsidian config and a
    # green suite. Assert the files land, not just that wiki/ was created.
    _run(tmp_path)
    vault = tmp_path / ".conclave/wiki/.obsidian"
    for fname in ("app.json", "appearance.json", "core-plugins.json"):
        assert (vault / fname).exists(), f"obsidian template not copied: {fname}"
    assert "file-explorer" in (vault / "core-plugins.json").read_text()


def test_init_is_idempotent(tmp_path):
    _run(tmp_path)
    roster_before = (tmp_path / ".conclave/roster.yaml").read_text()
    advisors_before = sorted(p.name for p in (tmp_path / ".claude/agents").rglob("*.md"))
    # Second run must not raise nor duplicate the advisor / roster.
    _run(tmp_path)
    roster_after = (tmp_path / ".conclave/roster.yaml").read_text()
    advisors_after = sorted(p.name for p in (tmp_path / ".claude/agents").rglob("*.md"))
    assert roster_before == roster_after
    assert advisors_before == advisors_after


def test_init_scaffolds_forge_router(tmp_path):
    import init.conclave_init as ci

    project = tmp_path / "proj"
    (project / ".claude").mkdir(parents=True)
    created = ci.scaffold_forge_router(project)
    assert created is True
    assert (project / ".claude" / "skills" / "conclave-forge-chro" / "SKILL.md").is_file()
    # idempotent
    assert ci.scaffold_forge_router(project) is False


def test_write_gitignore_content_and_idempotent(tmp_path):
    """#52: .conclave/.gitignore excludes regenerated caches; second call is a no-op."""
    import init.conclave_init as ci
    data = tmp_path / ".conclave"
    data.mkdir()
    assert ci.write_gitignore(data) is True
    gi = data / ".gitignore"
    assert gi.is_file()
    body = gi.read_text()
    for pat in ("agent-memory/gh-cache/", "agent-memory/git-cache/", "agent-memory/run-log/"):
        assert pat in body
    assert ci.write_gitignore(data) is False  # second call: kept


def test_offer_git_init_suggests_by_default(tmp_path, monkeypatch):
    import init.conclave_init as ci
    monkeypatch.delenv("CONCLAVE_GIT_INIT", raising=False)
    proj = tmp_path / "proj"
    proj.mkdir()
    assert ci.offer_git_init(proj) == "suggest"
    assert not (proj / ".git").exists()  # never side-effects without opt-in


def test_offer_git_init_runs_on_opt_in(tmp_path, monkeypatch):
    import init.conclave_init as ci
    monkeypatch.setenv("CONCLAVE_GIT_INIT", "1")
    proj = tmp_path / "proj"
    proj.mkdir()
    status = ci.offer_git_init(proj)
    assert status == "initialized"
    assert (proj / ".git").is_dir()


def test_offer_git_init_noop_when_already_repo(tmp_path, monkeypatch):
    import init.conclave_init as ci
    monkeypatch.setenv("CONCLAVE_GIT_INIT", "1")
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    assert ci.offer_git_init(proj) == "exists"


def test_resolve_data_root_defaults_to_cwd_when_env_unset(tmp_path, monkeypatch, capsys):
    """it-2 (#44): a standalone run with neither env var set must fall back to
    $PWD/.conclave instead of exiting — CLAUDE_PROJECT_DIR is only guaranteed inside
    the plugin runtime."""
    import init.conclave_init as ci

    monkeypatch.delenv("CONCLAVE_AI_ROOT", raising=False)
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    result = ci.resolve_data_root()

    assert result == (tmp_path / ".conclave").resolve()
    assert "defaulting DATA root" in capsys.readouterr().err
