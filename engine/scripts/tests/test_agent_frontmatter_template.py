"""Doc-tests for the agent-frontmatter template + its aspect reference.

Forge Iron Law (writing-skills): TDD for documentation. These assertions guard
the delegation pointer baked into every advisor agent-def scaffolded by
`engine advisor create`. Static distribution files (CODE root), so reading them
directly is hermetic.

Provenance:
  #59 — scaffold baked a phantom `agent-authoring` skill ref (surfaced by the #3
        phantom-skills scanner). The real skill is `plugin-dev:agent-development`.
"""
from pathlib import Path

# engine/scripts/tests/test_agent_frontmatter_template.py → parents[3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_REFS = _REPO_ROOT / "skills" / "forge-operations" / "references"
_TEMPLATE = _REFS / "templates" / "agent-frontmatter.md"
_ASPECT = _REFS / "aspects" / "agent-frontmatter.md"

_PHANTOM = "agent-authoring"
_REAL = "plugin-dev:agent-development"


def _read(p: Path) -> str:
    assert p.exists(), f"expected file missing: {p}"
    return p.read_text()


def test_template_delegates_to_real_skill():
    """#59 — the scaffold template must not point at the phantom skill."""
    body = _read(_TEMPLATE)
    assert _PHANTOM not in body, "template still references phantom skill agent-authoring"
    assert _REAL in body, "template missing real delegation skill plugin-dev:agent-development"


def test_aspect_ref_free_of_phantom():
    """#59 — the aspect ref that documents the delegation must match the template."""
    body = _read(_ASPECT)
    assert _PHANTOM not in body, "aspect ref still advertises phantom skill agent-authoring"
    assert _REAL in body, "aspect ref missing real delegation skill plugin-dev:agent-development"
