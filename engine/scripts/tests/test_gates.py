"""test_gates.py — engine structural gates, ported from shell (Wave 4 Step 3, spec 099).

Ports the four gate scripts formerly at engine/scripts/tests/*.sh (retired by this commit) plus
grep-gate.bats' single assertion. Each pytest function preserves the DETECTION LOGIC of its shell
original exactly — same scan dirs, `--include` set, exclusions, and patterns — only the runner
changed (bash/grep -> pathlib/re).

Also adds test_enginelib_is_io_free (099 deferred-minor (a)): an AST-aware replacement for the
naive `print(|argparse|sys.exit` grep, which used to trip on docstrings describing the I/O-free
contract (e.g. enginelib/mention.py's own module docstring). enginelib/ is the I/O-free core;
engine/cmd/* and engine/__main__.py are the CLI adapters that legitimately own
stdout/argparse/sys.exit and are out of scope for this gate.
"""

from __future__ import annotations

import ast
import configparser
import pathlib
import re
import shutil
import subprocess

import pytest

# tests/ -> scripts/ -> engine/ (same derivation as grep-gate.sh's ROOT default).
ENGINE_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = pathlib.Path(__file__).resolve().parents[1]
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

# ---------------------------------------------------------------------------
# Shared scan helpers — grep-gate.sh / code-data-gate.sh both scan
# <engine_root>/{contracts,scripts,skills} over *.sh,*.py,*.md, excluding /_mirror/ and
# /tests/ paths; grep-gate additionally excludes roster.yml|roster.yaml.
# ---------------------------------------------------------------------------
_SCAN_DIRS = ("contracts", "scripts", "skills")
_SCAN_EXTS = (".sh", ".py", ".md")
_EXCLUDE_PATH_RE = re.compile(r"/_mirror/|/tests/")
_EXCLUDE_ROSTER_RE = re.compile(r"roster\.ya?ml$")


def _scan_files(*, exclude_roster: bool = False):
    for sub in _SCAN_DIRS:
        base = ENGINE_ROOT / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in _SCAN_EXTS:
                continue
            if _EXCLUDE_PATH_RE.search(str(path)):
                continue
            if exclude_roster and _EXCLUDE_ROSTER_RE.search(str(path)):
                continue
            yield path


def _grep_hits(
    pattern: re.Pattern[str], *, exclude_roster: bool = False
) -> tuple[list[str], int]:
    """Line-level hits for `pattern` across the scanned files, as file:line:content.

    Also returns the count of files actually scanned, so callers can assert it's
    non-zero — a gate that silently scans 0 files (e.g. because its target dir was
    moved/renamed) must fail loudly instead of vacuously passing (099 review, W4.2).
    """
    hits = []
    scanned = 0
    for path in _scan_files(exclude_roster=exclude_roster):
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                hits.append(f"{path.relative_to(ENGINE_ROOT)}:{lineno}:{line.strip()}")
    return hits, scanned


# ---------------------------------------------------------------------------
# 1. grep-gate.sh + grep-gate.bats — no VoidPay instance literals survive in engine source.
# ---------------------------------------------------------------------------
# Case-sensitive on purpose (audit 2026-06-17 R1): matches lowercase `voidpay` and camelCase
# `VoidPay` (branding) but NOT all-caps `VOIDPAY_AI_ROOT` (the legit back-compat env alias).
_GREP_GATE_PATTERN = re.compile(
    r"voidpay|VoidPay|ignromanov|/Users/ignat/code/voidpay|/Users/ignat/code/vl|vl/wiki"
)


def test_grep_gate_no_instance_literals():
    hits, scanned = _grep_hits(_GREP_GATE_PATTERN, exclude_roster=True)
    assert scanned > 0, "grep-gate scanned 0 files — target dirs moved/renamed?"
    assert not hits, "grep-gate FAIL — instance literals survive in engine files:\n" + "\n".join(
        hits
    )


# ---------------------------------------------------------------------------
# 1b. Publication gate (#83) — no operator-absolute path survives on the PUBLIC surface.
# ---------------------------------------------------------------------------
# grep-gate (above) is anchored at <engine_root> and therefore never sees the repo-root prose,
# the plugin manifest, or the top-level agents/commands/skills/hooks trees — all of which ship
# public per spec 103 §3.1. An absolute `/Users/<operator>/...` literal is machine-specific and
# discloses the operator's home layout; it must not survive publication anywhere in that set.
#
# Deliberately narrower than grep-gate's pattern: instance *branding* ("voidpay") is legitimate
# prose in the public docs (the dogfooding origin) and is #71's problem, not this gate's.
_PUBLIC_SURFACE_DIRS = (
    ".claude-plugin",
    "agents",
    "commands",
    "docs/architecture",
    "engine",
    "hooks",
    "skills",
)
_PUBLIC_SURFACE_FILES = ("CLAUDE.md", "README.md", "VISION.md", "constitution.md")
_PUBLIC_SURFACE_EXTS = _SCAN_EXTS + (".json", ".yaml", ".yml")
_ABS_HOME_RE = re.compile(r"/Users/[A-Za-z0-9._-]+/")
# Vendored trees carry other machines' absolute paths (`/Users/runner/…` in wheel SBOMs) and are
# never published. The pre-existing gates share _scan_files() and do not exclude these; they pass
# only because their patterns happen not to match vendored content.
_VENDOR_PATH_RE = re.compile(r"/\.venv/|/node_modules/|/__pycache__/|/\.git/")


def _public_surface_files():
    for name in _PUBLIC_SURFACE_FILES:
        path = REPO_ROOT / name
        if path.is_file():
            yield path
    for sub in _PUBLIC_SURFACE_DIRS:
        base = REPO_ROOT / sub
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix not in _PUBLIC_SURFACE_EXTS:
                continue
            if _EXCLUDE_PATH_RE.search(str(path)) or _VENDOR_PATH_RE.search(str(path)):
                continue
            yield path


def test_publication_gate_no_operator_abs_paths():
    hits = []
    scanned = 0
    for path in _public_surface_files():
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _ABS_HOME_RE.search(line):
                hits.append(f"{path.relative_to(REPO_ROOT)}:{lineno}:{line.strip()}")
    assert scanned > 0, "publication gate scanned 0 files — public surface moved/renamed?"
    assert not hits, (
        "publication gate FAIL — operator-absolute paths would ship public:\n" + "\n".join(hits)
    )


# ---------------------------------------------------------------------------
# 1b-fixtures (B8, spec 103) — public test *data* fixtures carry no operator-absolute path.
# ---------------------------------------------------------------------------
# The publication gate above skips /tests/ (_EXCLUDE_PATH_RE) — necessary, because the gate and
# decouple detectors (test_gates.py, test_decouple_gate.py) legitimately embed the operator's
# absolute voidpay path as a *search string*. But engine/scripts/tests/ ships PUBLIC per
# spec 103 §3.1, and its fixtures (data, not detector code) must be leak-free — they were scanned
# by nothing, so operator-home paths reached the public include-list while the publication gate
# stayed green (spec 103 §5 B8). This gate scans only tests/fixtures/, never the .py detectors.
_FIXTURES_ROOT = SCRIPTS_ROOT / "tests" / "fixtures"


def test_fixtures_no_operator_abs_paths():
    hits = []
    scanned = 0
    for path in sorted(_FIXTURES_ROOT.rglob("*")):
        if not path.is_file() or _VENDOR_PATH_RE.search(str(path)):
            continue
        scanned += 1
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _ABS_HOME_RE.search(line):
                hits.append(f"{path.relative_to(SCRIPTS_ROOT)}:{lineno}:{line.strip()}")
    assert scanned > 0, "fixtures gate scanned 0 files — tests/fixtures/ moved/renamed?"
    assert not hits, (
        "fixtures gate FAIL — operator-absolute paths in public test fixtures:\n" + "\n".join(hits)
    )


# ---------------------------------------------------------------------------
# 1d-placement (spec 103 §1) — working documents are DATA, and the tree enforces it.
# ---------------------------------------------------------------------------
# Specs, plans, research, audits — working documents: private by audience, owned by the instance,
# not shipped (spec 103 §4). They live in DATA (`.conclave/ops/`). CODE's `docs/` holds exactly one
# thing: *descriptive* architecture, which is shipped canon.
#
# Prose alone cannot hold this line: `superpowers:writing-plans` hardcodes a save path of
# `docs/superpowers/plans/`, and an agent following that skill will recreate the tree without ever
# reading a rule that forbids it. So the rule is a gate — a stray working doc in CODE fails the
# suite, which is the one instruction an agent cannot skim past.
#
# Allow-list, not deny-list: a deny-list only catches the trees we already know about, and the
# failure mode here is a *new* name (`docs/plans/`, `docs/design/`) nobody thought to forbid.
_DOCS_ALLOWED = {"architecture"}


def test_working_docs_not_in_code():
    docs = REPO_ROOT / "docs"
    assert docs.is_dir(), "docs/ absent — the placement gate has nothing to check"
    strays = sorted(
        p.name for p in docs.iterdir()
        if not p.name.startswith(".") and p.name not in _DOCS_ALLOWED
    )
    assert not strays, (
        "placement gate FAIL — working documents in the CODE repo: docs/"
        + ", docs/".join(strays)
        + "\nWorking docs are DATA. Specs and plans: .conclave/ops/specs/<NNN-slug>/{spec,plan}.md"
        + "\nCODE's docs/ ships descriptive architecture only."
    )


# ---------------------------------------------------------------------------
# 1c. Publication gate (#83) — machine-local wiring must be gitignored, never committable.
# ---------------------------------------------------------------------------
# `.claude/settings.json` holds resolved absolute machine paths and is regenerated per-machine by
# `/conclave:init` (spec 103 §3.3). Asked of git rather than grepped out of `.gitignore`, so the
# assertion tracks the behaviour a `git add -A` would actually get (#87).
_MACHINE_LOCAL_WIRING = (".claude/settings.json", ".claude/settings.local.json")


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, check=False
    )


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_machine_local_settings_are_gitignored():
    if _git("rev-parse", "--is-inside-work-tree").returncode != 0:
        pytest.skip("not a git work tree")
    offenders = []
    for rel in _MACHINE_LOCAL_WIRING:
        if _git("check-ignore", "-q", "--", rel).returncode != 0:
            offenders.append(f"{rel} — not gitignored (a `git add -A` would stage it)")
        if _git("ls-files", "--error-unmatch", "--", rel).returncode == 0:
            offenders.append(f"{rel} — already tracked; gitignore alone will not untrack it")
    assert not offenders, "publication gate FAIL — machine-local wiring is committable:\n" + "\n".join(
        offenders
    )


# ---------------------------------------------------------------------------
# 1d. Instance-data gate (spec 103 §4) — DATA must never be tracked in CODE.
# ---------------------------------------------------------------------------
# Hired advisors, proof-instances and the instance's own identity doc are DATA per the
# instance contract §4 — they were tracked in CODE until W3, which was a contract violation
# the tree could not detect. Asked of `git ls-files` rather than of `.gitignore`, because
# gitignore does not untrack what is already in the index: the two disagree exactly when it
# matters.
_INSTANCE_DATA_PATHS = (".claude", "instances", "project-context.md")


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
def test_instance_data_not_tracked_in_code():
    if _git("rev-parse", "--is-inside-work-tree").returncode != 0:
        pytest.skip("not a git work tree")
    tracked = [
        line
        for rel in _INSTANCE_DATA_PATHS
        for line in _git("ls-files", "--", rel).stdout.splitlines()
        if line
    ]
    assert not tracked, (
        "instance-data gate FAIL — DATA is tracked in the CODE repo:\n  "
        + "\n  ".join(tracked)
        + "\nHired advisors live in .conclave/.claude/; .claude/{agents,skills} hold symlinks."
    )


# ---------------------------------------------------------------------------
# 1e. Suite-coverage gate (GH#99) — no test file may be orphaned from the suite.
# ---------------------------------------------------------------------------
# 124 feedback tests sat green-but-unreachable for weeks: `pytest engine/scripts/tests`
# (explicit arg) overrides `testpaths`, and the bare root run had no config at all, so
# neither invocation ever collected engine/scripts/feedback/tests. The fix is a single
# repo-root pytest.ini whose `testpaths` names every suite; this gate makes the failure
# mode structural — a test_*.py outside the declared testpaths fails the suite instead
# of silently never running.
_PRUNE_DIR_NAMES = {
    ".venv", "venv", "node_modules", "__pycache__", "worktrees", "build", "dist",
}


def _repo_test_files():
    def walk(base: pathlib.Path):
        for entry in sorted(base.iterdir()):
            name = entry.name
            if entry.is_dir():
                if name.startswith(".") or name in _PRUNE_DIR_NAMES:
                    continue
                yield from walk(entry)
            elif entry.is_file() and name.startswith("test_") and name.endswith(".py"):
                yield entry

    yield from walk(REPO_ROOT)


def test_all_test_files_inside_declared_testpaths():
    ini = REPO_ROOT / "pytest.ini"
    assert ini.is_file(), (
        "suite-coverage gate FAIL — repo-root pytest.ini missing; without it the bare "
        "`pytest` run has no testpaths/pythonpath and the suite fractures (GH#99)"
    )
    parser = configparser.ConfigParser()
    parser.read(ini, encoding="utf-8")
    declared = parser.get("pytest", "testpaths", fallback="").split()
    assert declared, "suite-coverage gate FAIL — pytest.ini declares no testpaths"
    roots = [REPO_ROOT / p for p in declared]
    orphans = [
        str(f.relative_to(REPO_ROOT))
        for f in _repo_test_files()
        if not any(f.is_relative_to(r) for r in roots)
    ]
    assert not orphans, (
        "suite-coverage gate FAIL — test files outside declared testpaths "
        "(they run in NO suite):\n  "
        + "\n  ".join(orphans)
        + "\nAdd their suite dir to pytest.ini testpaths."
    )


# ---------------------------------------------------------------------------
# 2. import-check.sh (a) — dangling @import targets in skills/**/SKILL.md.
# ---------------------------------------------------------------------------
_IMPORT_RE = re.compile(r"^@([./A-Za-z0-9_-]+)")


def test_import_check_no_dangling_imports():
    dangling = []
    skills_dir = ENGINE_ROOT / "skills"
    # NOTE: don't assert SKILL.md count > 0 — engine/skills/ legitimately holds few/no
    # SKILL.md in the conclave engine repo itself (advisor rosters are hired per-instance;
    # post-098 the forge/exec.scout-research dirs here are legacy script mirrors, not SKILL.md
    # homes). The invariant to protect is that the gate targets a real directory.
    assert skills_dir.is_dir(), "import-check target skills/ dir missing — moved/renamed?"
    skill_mds = sorted(skills_dir.rglob("SKILL.md"))
    for skill_md in skill_mds:
        skill_dir = skill_md.parent
        text = skill_md.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            m = _IMPORT_RE.match(line)
            if not m:
                continue
            target = skill_dir / m.group(1)
            if not target.is_file():
                dangling.append(f"{skill_md.relative_to(ENGINE_ROOT)} -> @{m.group(1)}")
    assert not dangling, "import-check FAIL — dangling @import targets:\n" + "\n".join(dangling)


# ---------------------------------------------------------------------------
# 3. import-check.sh (b) — broken 4-level relative walks (../../../..) in scripts/**/*.sh.
# ---------------------------------------------------------------------------
# These were calibrated for VoidPay's old .claude/skills/team.forge/scripts depth and overshoot
# the engine root post-lift. Near-vacuous post-099: the shell scripts that carried this risk are
# gone (this file retires the last four under scripts/) — kept to document the invariant in case
# a *.sh reappears under scripts/ (e.g. a future hook shim) with a stale deep relative walk.
_WALK_RE = re.compile(r"\.\./\.\./\.\./\.\.")


def test_import_check_no_broken_walks():
    walks = []
    scripts_dir = ENGINE_ROOT / "scripts"
    # NOTE: don't assert file-count > 0 here — scripts/**/*.sh is legitimately near-empty
    # post-099 (all shell ported to Python). The invariant to protect is that the gate is
    # still pointed at a real location, not that the location currently has matching files.
    assert scripts_dir.is_dir(), "import-check target scripts/ dir missing — moved/renamed?"
    for path in sorted(scripts_dir.rglob("*.sh")):
        if "/tests/" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if _WALK_RE.search(line):
                walks.append(f"{path.relative_to(ENGINE_ROOT)}:{lineno}:{line.strip()}")
    assert not walks, (
        "import-check FAIL — broken 4-level relative walks (overshoot engine root):\n"
        + "\n".join(walks)
    )


# ---------------------------------------------------------------------------
# 4. code-data-gate.sh — no CODE resource (team.forge) read via the DATA .claude/ namespace.
# ---------------------------------------------------------------------------
_CODE_DATA_PATTERN = re.compile(
    r'\.claude/skills/team\.forge|"\.claude"\s*/\s*"skills"\s*/\s*"team\.forge"'
)


def test_code_data_gate_no_claude_namespace_reads():
    hits, scanned = _grep_hits(_CODE_DATA_PATTERN)
    assert scanned > 0, "code-data-gate scanned 0 files — target dirs moved/renamed?"
    assert not hits, (
        "code-data-gate FAIL — CODE resource (team.forge) read via DATA .claude/ namespace:\n"
        + "\n".join(hits)
    )


# ---------------------------------------------------------------------------
# 5. AST-aware I/O-free gate (099 deferred-minor (a)) — enginelib/ must not, at CODE level,
# call print(...)/sys.exit(...) or import/use argparse. Docstrings and comments are not code
# and must not trip it. engine/cmd/* and engine/__main__.py are out of scope (CLI adapters).
# ---------------------------------------------------------------------------
class _IOFreeVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.hits: list[tuple[int, str]] = []

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id == "print":
            self.hits.append((node.lineno, "print(...) call"))
        elif (
            isinstance(func, ast.Attribute)
            and func.attr == "exit"
            and isinstance(func.value, ast.Name)
            and func.value.id == "sys"
        ):
            self.hits.append((node.lineno, "sys.exit(...) call"))
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            if alias.name == "argparse":
                self.hits.append((node.lineno, "import argparse"))
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module == "argparse":
            self.hits.append((node.lineno, "from argparse import ..."))
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if isinstance(node.value, ast.Name) and node.value.id == "argparse":
            self.hits.append((node.lineno, f"argparse.{node.attr} use"))
        self.generic_visit(node)


def test_enginelib_is_io_free():
    enginelib_dir = SCRIPTS_ROOT / "enginelib"
    hits = []
    py_files = sorted(enginelib_dir.rglob("*.py"))
    assert py_files, "enginelib/ io-free gate scanned 0 files — enginelib/ moved/renamed?"
    for path in py_files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = _IOFreeVisitor()
        visitor.visit(tree)
        for lineno, what in visitor.hits:
            hits.append(f"{path.relative_to(ENGINE_ROOT)}:{lineno}: {what}")
    assert not hits, "enginelib/ has code-level print/argparse/sys.exit:\n" + "\n".join(hits)


# ---------------------------------------------------------------------------
# 9. Spin-out boundary (spec 091 acceptance §9) — the duty base ships to every consumer,
#    so nothing instance-specific may survive in it.
# ---------------------------------------------------------------------------
# grep-gate (§1) is anchored at <engine_root>/{contracts,scripts,skills} and therefore never
# sees skills/forge-operations/ at the REPO root, where the roster base lives. Hence a
# separate gate rather than a widened one — widening §1 would silently change what an
# existing gate covers.
#
# Honest limit: this cannot see the ids of advisors an instance hired, because those live in
# DATA (.conclave/) and the suite is hermetic against it by design (conftest clears
# CONCLAVE_AI_ROOT). What it does catch is the shape such a leak takes in CODE — instance
# branding, an operator's absolute home path, a concrete `conclave-<id>` agent home, or a
# reference into the DATA tree. A base file naming any of those is instance-specific by
# construction.
_ROSTER_BASE = REPO_ROOT / "skills" / "forge-operations" / "roster"

_INSTANCE_LEAK_PATTERNS = {
    # Reused, not re-enumerated: one owner for the branding/operator-path fact (§1).
    "instance-branding": _GREP_GATE_PATTERN,
    "operator-home-path": _ABS_HOME_RE,
    "concrete-agent-home": re.compile(r"conclave-[a-z0-9][a-z0-9-]*|team\.[a-z0-9][a-z0-9-]*"),
    "data-tree-reference": re.compile(r"\.conclave/|agent-memory/"),
}


def _roster_base_leaks(patterns: dict[str, re.Pattern[str]]) -> list[str]:
    """Instance-specific hits in the roster base. Extracted so the completeness assertions
    below can be exercised with a deliberately empty pattern set — a gate whose token list
    silently empties reports clean while checking nothing, which is the failure mode this
    repo has shipped four times."""
    assert patterns, "leak-pattern set is empty — the gate would check nothing"
    files = [p for p in sorted(_ROSTER_BASE.rglob("*"))
             if p.is_file() and "__pycache__" not in p.parts]
    assert files, f"{_ROSTER_BASE} holds no files — gate would pass vacuously"

    hits = []
    for path in files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for lineno, line in enumerate(text.splitlines(), start=1):
            for name, pattern in patterns.items():
                if pattern.search(line):
                    hits.append(
                        f"{path.relative_to(REPO_ROOT)}:{lineno}: [{name}] {line.strip()}")
    return hits


def test_roster_base_is_domain_agnostic():
    assert _ROSTER_BASE.is_dir(), (
        f"{_ROSTER_BASE} is missing — the spin-out gate has nothing to check. Either the "
        f"roster base moved (update this gate) or spec 091 was reverted (delete it)."
    )
    hits = _roster_base_leaks(_INSTANCE_LEAK_PATTERNS)
    assert not hits, (
        "spin-out boundary FAIL (spec 091 acceptance 9) — instance-specific content in the "
        "engine-owned roster base:\n" + "\n".join(hits)
    )


def test_spin_out_gate_refuses_an_empty_pattern_set():
    """The completeness assertion, asserted. Without this, a future edit that derives the
    pattern set from something that comes back empty turns the gate into a no-op that
    still reports clean."""
    with pytest.raises(AssertionError, match="would check nothing"):
        _roster_base_leaks({})
