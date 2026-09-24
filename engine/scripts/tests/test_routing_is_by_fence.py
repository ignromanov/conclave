"""test_routing_is_by_fence.py — triage routes an item to whoever decides the shape of its fix.

The rule used to key the owner on `layer`: `skill` / `contract` / `memory` / `infra` → Forge.
Those four values cover nearly every defect an agent can observe, so the rule sent engine
Python, loop closure and display defects alike to the meta-advisor. Measured on the dogfood
instance 2026-09-23: 99 of 172 open issues carried `advisor:forge-chro`, and all ten issues the
day's triage filed (#372-#381) landed there, six of them engine Python (helm-ceo decision
`queue-rank-and-route-2026-09-23`, 48 issues rerouted by hand).

The rule lived in two copies — `feedback-protocol.md` §Routing and a layer→owner table in
`commands/triage.md`, which already imports the contract — and the table still named `forge`
and `quorum`, ids this instance does not hold and `feedback_triage --set` refuses.

A shipped contract cannot name the fence's owners: only the meta-role ships, the rest are
hired per instance. So the contract names the *rule* and where its data lives (each advisor's
declared scope), and these gates hold it there.
"""

from __future__ import annotations

import pathlib
import re

import pytest

# tests/ -> scripts/ -> engine/ -> <code root>. Same derivation as test_gates.py.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CONTRACT = REPO_ROOT / "skills/advisor-contracts/references/feedback-protocol.md"
TRIAGE = REPO_ROOT / "commands/triage.md"
# Every command, not the two files the rule was known to live in: a third copy sat in
# `commands/feedback.md` ("Routing hint") and a gate scoped to the known two passed it.
COMMANDS = sorted((REPO_ROOT / "commands").glob("*.md"))

LAYERS = ("infra", "skill", "contract", "memory", "workflow")
_LAYER = "|".join(LAYERS)

# A markdown table row whose first cell is a backticked layer value: `| `infra` | forge |`.
_LAYER_TABLE_ROW = re.compile(rf"^\|\s*`(?:{_LAYER})`\s*\|", re.MULTILINE)
# A layer value mapped by arrow: "`infra` → **Forge**", "`workflow` → the facilitator".
_LAYER_ARROW = re.compile(rf"`(?:{_LAYER})`[^\n]*→")
# `--owner <a|b|c>` — an enumeration of concrete ids posing as a placeholder.
_OWNER_ENUM = re.compile(r"--owner <[^>]*\|[^>]*>")
# `advisor:forge` — a concrete label in an example, where `advisor:<owner>` is meant.
_CONCRETE_LABEL = re.compile(r"advisor:[a-z][a-z0-9-]*")


def routing_section(text: str) -> str:
    """The body of the contract's `### Routing` heading, up to the next heading."""
    m = re.search(r"^###\s+Routing\b[^\n]*\n(.*?)(?=^#{1,3}\s)", text, re.MULTILINE | re.DOTALL)
    return m.group(1) if m else ""


def layer_keyed(text: str) -> list[str]:
    """Every place *text* assigns an owner by `layer` value."""
    return _LAYER_TABLE_ROW.findall(text) + _LAYER_ARROW.findall(text)


def concrete_owner_examples(text: str) -> list[str]:
    return _OWNER_ENUM.findall(text) + _CONCRETE_LABEL.findall(text)


# --- meta-tests: each gate reddens on the text it replaced -----------------------------------

OLD_ROUTING = """### Routing (set by triage)

`layer` → fix owner: `skill` / `contract` / `memory` / `infra` → **Forge**;
`workflow` → **the facilitator role** (the `quorum` slot, if the instance hired one).

## How to emit
"""

OLD_TRIAGE = """| `layer` | Default owner |
|---------|---------------|
| `infra` | forge |
| `workflow` | quorum |

  [--owner <forge|quorum|advisor-slug>]
| `advisor:<owner>` | owner from the Step-2 layer→owner table (e.g. `advisor:forge`) |
"""


def test_meta_section_extractor_finds_the_old_routing():
    assert routing_section(OLD_ROUTING).strip(), "extractor returned nothing — every gate is vacuous"


def test_meta_layer_gate_reddens_on_the_old_rule():
    assert layer_keyed(routing_section(OLD_ROUTING))
    assert layer_keyed(OLD_TRIAGE)


def test_meta_example_gate_reddens_on_the_old_triage():
    assert concrete_owner_examples(OLD_TRIAGE) == ["--owner <forge|quorum|advisor-slug>", "advisor:forge"]


# --- gates over the shipped tree -------------------------------------------------------------


def test_contract_routing_section_exists():
    assert routing_section(CONTRACT.read_text(encoding="utf-8")).strip(), (
        f"{CONTRACT.name}: no `### Routing` section — the rule has nowhere to live")


def test_commands_are_scanned():
    assert TRIAGE in COMMANDS and len(COMMANDS) > 2, "command glob found nothing — the gate is vacuous"


@pytest.mark.parametrize("path", [CONTRACT, *COMMANDS], ids=lambda p: p.name)
def test_no_owner_is_keyed_on_layer(path):
    text = path.read_text(encoding="utf-8")
    scope = routing_section(text) if path == CONTRACT else text
    hits = layer_keyed(scope)
    assert not hits, (
        f"{path.name} assigns an owner by `layer` ({hits}). `layer` says where a defect was "
        f"observed, not who decides its fix — route by the fence in {CONTRACT.name} §Routing.")


def test_contract_names_the_fence_and_where_its_data_lives():
    section = routing_section(CONTRACT.read_text(encoding="utf-8"))
    assert "decides the shape of the fix" in section
    # The fence's owners are instance data. The contract points at where they are declared.
    assert "description" in section


def test_triage_defers_to_the_contract():
    text = TRIAGE.read_text(encoding="utf-8")
    assert "§Routing" in text, "triage.md assigns owners without pointing at the rule it applies"


@pytest.mark.parametrize("path", [CONTRACT, TRIAGE], ids=lambda p: p.name)
def test_owner_examples_are_placeholders(path):
    hits = concrete_owner_examples(path.read_text(encoding="utf-8"))
    assert not hits, (
        f"{path.name} shows concrete owner ids {hits} where a placeholder is meant; a shipped "
        f"example names ids an instance may not hold, and `--set` refuses them.")
