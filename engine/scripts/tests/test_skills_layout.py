"""098 D-4 — contracts re-homed to skills/advisor-contracts/references/ and
command bodies inject them from the plugin root (Option 1, operator 2026-06-17).

Scripts STAY at engine/scripts/ (099-deferred); only the doc/contract assets move.
"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[3]  # repo root

CONTRACTS = [
    "advisor-anti-patterns", "agent-data-policy", "autonomous-pipeline",
    "decision-framework", "executor-protocol", "feedback-protocol",
    "first-launch-protocol", "github-issues-protocol", "output-formatting",
    "persona-voice", "quality-loop", "question-shape", "session-lifecycle",
    "spawned-advisor-brief", "spec-051-invariants",
]


def _plugin_md_files():
    return (list((ROOT / "commands").rglob("*.md"))
            + list((ROOT / "agents").glob("*.md"))
            + list((ROOT / "skills").rglob("*.md")))


def test_contracts_rehomed():
    refs = ROOT / "skills/advisor-contracts/references"
    have = {p.stem for p in refs.glob("*.md")}
    assert set(CONTRACTS) <= have, set(CONTRACTS) - have


FORGE_PROTOCOLS = ["hire", "evolve", "audit", "audit-skills", "compose-roster"]


def test_no_dangling_old_contract_paths():
    # the MOVED contracts must no longer be referenced at their old homes;
    # scripts STAY at engine/scripts/ (gate-resolved) so script refs are untouched here.
    # CHANGELOG.md only grows new entries at the top (may quote old paths in dated entries) — skip it.
    bad = re.compile(r'engine/contracts/|team\.forge/contracts/')
    hits = []
    for md in _plugin_md_files():
        if md.name == "CHANGELOG.md":
            continue
        for i, line in enumerate(md.read_text().splitlines(), 1):
            if bad.search(line):
                hits.append(f"{md.relative_to(ROOT)}:{i}")
    assert not hits, hits


def test_forge_protocol_docs_rehomed():
    # D-4b: Forge protocol/reference library flattened under skills/forge-operations/references/.
    refs = ROOT / "skills/forge-operations/references/protocols"
    have = {p.stem for p in refs.glob("*.md")}
    assert set(FORGE_PROTOCOLS) <= have, set(FORGE_PROTOCOLS) - have
    assert (ROOT / "skills/forge-operations/SKILL.md").exists()
    # no command/agent body still points protocol/reference refs at the old team.forge tree
    stale = re.compile(r'team\.forge/(protocols|templates|references)/')
    hits = []
    for md in (list((ROOT / "commands").rglob("*.md")) + list((ROOT / "agents").glob("*.md"))):
        for i, line in enumerate(md.read_text().splitlines(), 1):
            if stale.search(line):
                hits.append(f"{md.relative_to(ROOT)}:{i}")
    assert not hits, hits


def test_commands_inject_contracts_from_plugin_root():
    # Option 1: command bodies auto-load contracts via `!`cat ${CLAUDE_PLUGIN_ROOT}/...``
    # injection (documented dynamic-context injection), never via @-imports.
    at_import = re.compile(r'^@\.\..*contracts/')
    injected = False
    stray = []
    for md in (ROOT / "commands").rglob("*.md"):
        for i, line in enumerate(md.read_text().splitlines(), 1):
            if at_import.search(line):
                stray.append(f"{md.relative_to(ROOT)}:{i}")
            if "${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/" in line \
                    and line.lstrip().startswith("!`"):
                injected = True
    assert not stray, f"stray @-import contract lines remain: {stray}"
    assert injected, "no command injects a contract via !`cat ${CLAUDE_PLUGIN_ROOT}/...`"
