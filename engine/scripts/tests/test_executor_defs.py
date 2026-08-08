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

# Spec 109 Task 1 — the canonical frontmatter, in order. Harness-recognized fields first
# (code.claude.com/docs/en/sub-agents), then Conclave's own metadata. Every key is required:
# an optional key is a key that drifts, and `tools:` absent on the executor with full write
# access is how the intended boundary went unwritten for two months (109 §1).
_CANONICAL_KEYS: tuple[str, ...] = (
    "name", "description", "tools", "model",
    "tier", "chosen-name", "emoji", "color", "created",
)

# Derived by glob, never enumerated — a hardcoded list is the coverage hole this repo has
# now hit six times (most recently a type gate that ran over 82 of 169 files). The count is
# asserted so that ADDING an executor without revisiting these gates fails loudly.
_EXPECTED_EXECUTOR_COUNT = 6


def _executor_defs() -> list[Path]:
    defs = sorted(_AGENTS.glob("exec-*.md"))
    assert len(defs) == _EXPECTED_EXECUTOR_COUNT, (
        f"executor count changed: found {len(defs)} ({[p.name for p in defs]}), "
        f"expected {_EXPECTED_EXECUTOR_COUNT}. Update _EXPECTED_EXECUTOR_COUNT and re-check "
        f"every gate in this file against the new def before bumping the number."
    )
    return defs


def _read(p: Path) -> str:
    assert p.exists(), f"expected file missing: {p}"
    return p.read_text()


def _frontmatter_keys(body: str) -> list[str]:
    """Top-level YAML keys of the frontmatter block, in file order.

    Folded scalars (`description: >-`) continue on indented lines; only column-0 `key:`
    lines are top-level, so indentation is the discriminator.
    """
    lines = body.splitlines()
    assert lines and lines[0] == "---", "file does not open with a frontmatter fence"
    keys: list[str] = []
    for line in lines[1:]:
        if line == "---":
            return keys
        m = re.match(r"^([A-Za-z][A-Za-z0-9-]*):", line)
        if m:
            keys.append(m.group(1))
    raise AssertionError("unterminated frontmatter block")


def _dispatch_line_or_none(body: str) -> str | None:
    """`_dispatch_line` without the raise — used to MEASURE how many defs carry a block."""
    for line in body.splitlines():
        if line.startswith("Agent(") and "subagent_type=" in line:
            return line
    return None


def _dispatch_line(body: str) -> str:
    """The `Agent(...)` line in the Dispatch protocol block (the only place a
    model= default is authoritative; prose may legitimately mention opus)."""
    for line in body.splitlines():
        if line.startswith("Agent(") and "subagent_type=" in line:
            return line
    raise AssertionError("no Agent(...) dispatch line found")


# ── #17 — model=sonnet dispatch default ───────────────────────────────────────


def test_executor_defs_default_to_sonnet():
    """Every executor dispatch line defaults model=sonnet (not opus).

    Coverage is measured, not assumed: this gate used to iterate a hardcoded pair and so
    graded 2 of 6 defs while reading as a roster-wide check. It now globs, and pins how many
    defs actually carry a dispatch block — exec-socra-critic has none, and that gap must not
    grow silently.
    """
    with_dispatch = [p for p in _executor_defs() if _dispatch_line_or_none(_read(p))]
    assert len(with_dispatch) == 5, (
        f"{len(with_dispatch)} of {_EXPECTED_EXECUTOR_COUNT} executor defs carry a dispatch "
        f"block, expected 5 (exec-socra-critic is the known gap). A def that lost its block "
        f"silently drops out of this gate — add the block, don't lower the number."
    )
    for md in with_dispatch:
        line = _dispatch_line(_read(md))
        assert 'model="opus"' not in line, f"{md.name} dispatch still hardcodes opus"
        assert 'model="sonnet"' in line, f"{md.name} dispatch missing sonnet default"


# ── #109 Task 1 — one frontmatter field set, one order ────────────────────────


def test_executor_frontmatter_is_canonical():
    """Same keys, same order, on every executor def.

    Order matters for a read surface: a consumer scanning six files should find `tools:` in
    the same place each time. Set membership matters more — `tools:` was absent on atlas and
    metron, so their tool scope was inferred from silence rather than stated.
    """
    for md in _executor_defs():
        keys = _frontmatter_keys(_read(md))
        assert tuple(keys) == _CANONICAL_KEYS, (
            f"{md.name}: frontmatter keys {keys} != canonical {list(_CANONICAL_KEYS)}"
        )


def test_executor_model_declared_sonnet():
    """`model:` is declared in the file, not only typed by a well-behaved dispatcher.

    #17 wanted sonnet by default. Leaving that to the caller's dispatch string makes it a
    step someone has to remember — the exact shape spec 108 measured to be worth nothing.
    """
    for md in _executor_defs():
        assert _frontmatter_field(_read(md), "model") == "sonnet", (
            f"{md.name}: frontmatter must declare model: sonnet"
        )


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
