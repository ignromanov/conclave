"""Doc-tests for executor agent-defs + the executor-agent template.

Forge Iron Law (writing-skills): TDD for documentation. These assertions guard
behavioral contract text that lives in the shipped executor surface — the two
introduced executors (atlas, iris), the research/dev executor (scout), and the
`executor-agent.md` template every future hire is scaffolded from (#68: the
create-path emits an agent-def, not a skill-dir).

Static distribution files (CODE root), so reading them directly is hermetic —
no instance-root fixture needed.

Provenance:
  #17 — bake model=sonnet into executor dispatch defaults (override to opus explicitly)
  #18 — iris must instrument before naming a root cause
  #15 — executor return-contract commits[] derived from git, not intent
  #14 — no progress-narration sentences before an action
"""
import re
from pathlib import Path

# engine/scripts/tests/test_executor_defs.py → parents[3] = repo root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_AGENTS = _REPO_ROOT / "agents"
_TEMPLATE = (
    _REPO_ROOT
    / "skills"
    / "forge-operations"
    / "references"
    / "templates"
    / "executor-agent.md"
)

_EXECUTOR_DEFS = ("exec-atlas-dev.md", "exec-iris-test.md")


def _read(p: Path) -> str:
    assert p.exists(), f"expected file missing: {p}"
    return p.read_text()


def _dispatch_line(body: str) -> str:
    """The `Agent(...)` line in the Dispatch protocol block (the only place a
    model= default is authoritative; prose may legitimately mention opus)."""
    for line in body.splitlines():
        if line.startswith("Agent(") and "subagent_type=" in line:
            return line
    raise AssertionError("no Agent(...) dispatch line found")


# ── #17 — model=sonnet dispatch default ───────────────────────────────────────


def test_executor_defs_default_to_sonnet():
    """Every executor dispatch line defaults model=sonnet (not opus)."""
    for name in _EXECUTOR_DEFS:
        line = _dispatch_line(_read(_AGENTS / name))
        assert 'model="opus"' not in line, f"{name} dispatch still hardcodes opus"
        assert 'model="sonnet"' in line, f"{name} dispatch missing sonnet default"


def test_executor_template_defaults_to_sonnet():
    line = _dispatch_line(_read(_TEMPLATE))
    assert 'model="opus"' not in line, "template dispatch still hardcodes opus"
    assert 'model="sonnet"' in line, "template dispatch missing sonnet default"


# ── #18 — iris must instrument before naming a root cause ──────────────────────


def test_iris_requires_instrumentation_before_root_cause():
    """Iris must not name a root cause from inspection alone (feedback it-2:
    a confidently-wrong macOS diagnosis passed by luck)."""
    body = _read(_AGENTS / "exec-iris-test.md").lower()
    assert "root cause" in body
    assert "instrument" in body or "subprocess stdout" in body, (
        "iris def missing the instrument-before-root-cause gate"
    )


def test_template_documents_instrumentation_gate():
    """The executor template's anti-pattern guidance flags the gate so future
    test/debug executors inherit it."""
    body = _read(_TEMPLATE).lower()
    assert "root cause" in body and "instrument" in body, (
        "executor template missing instrument-before-root-cause guidance"
    )


# ── #15 / #14a — executor standing behavioral rules (dev-executor template) ────


def test_template_derives_commits_from_git():
    """#15 — return-contract commits[] must come from `git log`, not intent."""
    body = _read(_TEMPLATE).lower()
    assert "commits[]" in body and "git log" in body, (
        "executor template missing commits[]-from-git-not-intent rule"
    )


def test_template_forbids_progress_narration():
    """#14a — no progress-narration sentence before an action."""
    body = _read(_TEMPLATE).lower()
    assert "progress-narration" in body, (
        "executor template missing no-progress-narration rule"
    )


# ── #61 — executor naming-standard guard (drift-proof, catches hire/rename drift) ─


def _frontmatter_field(body: str, key: str) -> str | None:
    m = re.search(rf"^{re.escape(key)}:\s*(.+?)\s*$", body, re.MULTILINE)
    return m.group(1) if m else None


def test_executor_naming_standard():
    """#61: lock the executor identity convention so hire/rename drift is caught.

    For every agents/exec-*.md the identity triple must cohere:
      filename stem == `exec-<name>-<role>` (exactly 3 hyphen segments)
      frontmatter `name:` == the stem
      frontmatter `chosen-name:` == the <name> segment
      body carries the name-keyed sentinel `<!-- exec:<name> v1 -->`

    This is exactly the drift #61 fixed: `ranker` used its role as its name
    (name==role) and `critic`/`judge` filenames were role-only (no name segment).
    The guard fails on that shape, so a future hire/rename can't reintroduce it.
    """
    execs = sorted(_AGENTS.glob("exec-*.md"))
    assert execs, "no executor defs found under agents/"
    for md in execs:
        stem = md.stem  # e.g. exec-atlas-dev
        parts = stem.split("-")
        assert len(parts) == 3 and parts[0] == "exec", (
            f"{md.name}: filename must be exec-<name>-<role> (3 segments), got {stem!r}"
        )
        _, name_seg, role_seg = parts
        body = _read(md)
        name_fld = _frontmatter_field(body, "name")
        chosen = _frontmatter_field(body, "chosen-name")
        assert name_fld == stem, f"{md.name}: frontmatter name: {name_fld!r} != stem {stem!r}"
        assert chosen == name_seg, (
            f"{md.name}: chosen-name: {chosen!r} must equal the <name> segment {name_seg!r} "
            f"(a role-word as name — e.g. 'ranker' — is the drift this guard forbids)"
        )
        assert role_seg, f"{md.name}: empty role segment"
        sentinel = f"<!-- exec:{name_seg} v1 -->"
        assert sentinel in body, f"{md.name}: missing name-keyed sentinel {sentinel!r}"
