"""Every shipped agent-def's frontmatter must be valid YAML.

test_agent_frontmatter_template.py guards what the *scaffold template* says; nothing checked that
the files actually shipped in `agents/` parse. `agents/exec-atlas-dev.md` did not: an unquoted
`description` containing `dev tasks: write code` put a `: ` inside a plain scalar, which YAML reads
as a nested mapping. One of seven agent-defs was unloadable and the suite was silent about it.
"""

from pathlib import Path

import pytest
import yaml

# engine/scripts/tests/ -> parents[3] = repo root
_AGENTS = Path(__file__).resolve().parents[3] / "agents"


def _agent_files() -> list[Path]:
    return sorted(_AGENTS.glob("*.md"))


def _frontmatter(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path.name}: no frontmatter block"
    # Split on the closing delimiter line, not on a bare `---`: a `---` inside a quoted YAML
    # value would truncate the block and make the parse below test a fragment.
    block, closed, _ = text[len("---\n") :].partition("\n---\n")
    assert closed, f"{path.name}: frontmatter block is never closed"
    return block


def test_agents_dir_is_not_empty() -> None:
    """Guard the guard: a bad glob would make every parse test below vacuously pass."""
    assert _agent_files(), f"no agent-defs found under {_AGENTS}"


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.name)
def test_frontmatter_is_valid_yaml(path: Path) -> None:
    try:
        loaded = yaml.safe_load(_frontmatter(path))
    except yaml.YAMLError as exc:
        pytest.fail(f"{path.name}: frontmatter is not valid YAML — {exc}")
    assert isinstance(loaded, dict), f"{path.name}: frontmatter is not a mapping"


@pytest.mark.parametrize("path", _agent_files(), ids=lambda p: p.name)
def test_required_keys_survive_the_parse(path: Path) -> None:
    """A description swallowed by a mis-parse is worse than a crash — it loads as the wrong shape."""
    loaded = yaml.safe_load(_frontmatter(path))
    for key in ("name", "description"):
        assert key in loaded, f"{path.name}: frontmatter lost `{key}`"
        assert isinstance(loaded[key], str), f"{path.name}: `{key}` parsed as {type(loaded[key])}"
