import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]  # repo root


def test_plugin_json_shape():
    m = json.loads((ROOT / ".claude-plugin/plugin.json").read_text())
    assert m["name"] == "conclave"
    assert "version" in m
    # Real CC plugin.json schema shapes (caught at operator-install 2026-06-25; shape
    # tests had false-PASSed these). author=object, dependencies=array, userConfig.*.title=str.
    assert isinstance(m.get("author"), dict) and m["author"].get("name"), "author must be an object with name"
    deps = m.get("dependencies")
    assert isinstance(deps, list), "dependencies must be an array"
    dep_names = [d["name"] if isinstance(d, dict) else d for d in deps]
    # native dependency — may carry a `@<marketplace>` qualifier (e.g. agent-teams@claude-code-workflows)
    assert any(d.split("@")[0] == "agent-teams" for d in dep_names), f"agent-teams dependency required, got {dep_names}"
    uc = m.get("userConfig")
    assert uc, "userConfig must declare install-time prompts"
    for key, field in uc.items():
        assert field.get("title"), f"userConfig.{key} must have a title string"


def test_marketplace_json_shape():
    mk = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    plugins = mk.get("plugins", [])
    assert any(p.get("name") == "conclave" for p in plugins)
    # CC marketplace schema requires a top-level `owner` OBJECT (name required).
    # Caught at operator-install 2026-06-25 — the prior shape test missed it.
    assert isinstance(mk.get("owner"), dict), "marketplace.json: `owner` must be an object"
    assert mk["owner"].get("name"), "marketplace.json: owner.name required"


def test_commands_tree():
    # D-2: lifecycle team.* skills become FLAT commands/*.md → /conclave:<verb>
    cmds = ROOT / "commands"
    names = {p.stem for p in cmds.glob("*.md")}
    expected = {"start", "processing", "done", "handoff", "forge",
                "feedback", "triage", "hire", "retro"}
    assert expected <= names, expected - names


def test_agents_tree():
    # D-3: forge + exec.* personas become agents/*.md
    # (D-9: exec-argus-test removed — superseded pre-rename twin of exec-iris-test, argus→iris 2026-05-08)
    agents = (ROOT / "agents")
    names = {p.stem for p in agents.glob("*.md")}
    assert "forge" in names
    # (#61: exec-scout-dev retired — self-declared atlas duplicate, no real contract
    #  difference; retiring it also frees the `scout` name for exec-scout-research.)
    expected_exec = {f"exec-{x}" for x in
        ["scout-research", "metron-rank", "socra-critic", "themis-judge", "atlas-dev", "iris-test"]}
    assert expected_exec <= names, expected_exec - names
