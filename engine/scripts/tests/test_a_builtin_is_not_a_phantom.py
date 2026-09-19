"""A skill with no file is not thereby absent (#168).

`enginelib.skill.verify` searches five on-disk roots and returns None when none of them
holds a SKILL.md. `engine skill verify` prints that None as `PHANTOM` and exits 1, and
`audit phantom-skills` prints it as "references phantom skill". Both sentences claim the
name does not exist. What was measured is narrower: *this instrument reads disk, and disk
does not have it.*

Harness built-ins have no SKILL.md anywhere — they are compiled into the Claude Code
binary — and are invocable all the same. The cost is not a noisy line. On this very
instance an advisor deleted a skill from its own toolbox and wrote the reason down:

    > `dataviz` is deliberately **not** listed: it is a harness-builtin and
    > `engine skill verify` reports it PHANTOM, which would fail audit Cat 12 on every run.
    —  .conclave/.claude/skills/conclave-kosmos-cxo/memory/personality.md

#168 asks for a third verdict "backed by the session skill listing". Measured before
building: no such listing is reachable from a process. It is not in `~/.claude/` and not
in `settings.json`; the names live only inside the CLI binary, behind a minifier-renamed
registration function — `_o(` in 2.1.270, `Po(` in 2.1.273, `Do(` in 2.1.277 and .278,
four builds in four days. A scan keyed on that spelling reads 14 built-ins today and **0**
on last week's binary, and 0 means every built-in silently becomes a phantom again: the
exact defect, rebuilt with a longer fuse. Anchoring on a known name instead of the spelling
does work and returns the same 14 on all four binaries — but at ~1.6s of `strings` over
226 MB per call, inside a blocking gate, after first guessing which of several install
layouts holds the binary.

So the third verdict is backed by a **declaration** instead, and the declaration is held to
the terms this codebase requires of one: it names its provenance, it states how to
re-measure it, and a gate fails when its subject moves (#133 F1 — an exemption whose
subject is gone does not expire, it waits).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

from enginelib import skill
from enginelib.audit import phantom_skills
from tests.cmd.helpers import run_engine

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[1]

DECLARATION = REPO / "skills" / "forge-operations" / "references" / "harness-builtins.md"

#: Names from #168's own reproduction, verbatim.
REPORTED = ("update-config", "fewer-permission-prompts", "keybindings-help")

#: A name no harness ships and no disk holds. The control for every assertion below.
INVENTED = "no-such-skill-zzz-fixture"


def _hermetic(tmp_path: Path, builtins: tuple[str, ...] = REPORTED) -> tuple[Path, dict]:
    """A tmp engine root with its own declaration file, reachable via forge_dir().

    `forge_dir()` is `engine_root().parent/skills/forge-operations`, so pinning
    CONCLAVE_ENGINE_ROOT moves the declaration along with the skills tree — one anchor,
    not two. Global and cache roots are pinned at empty dirs so nothing reaches ~/.claude.
    """
    engine_root = tmp_path / "engine"
    skills = engine_root / "skills"
    skills.mkdir(parents=True)
    decl = tmp_path / "skills" / "forge-operations" / "references" / "harness-builtins.md"
    decl.parent.mkdir(parents=True)
    decl.write_text(
        "# fixture\n\n## Harness built-ins\n\n"
        + "".join(f"- `{n}`\n" for n in builtins),
        encoding="utf-8",
    )
    env = {
        "CONCLAVE_ENGINE_ROOT": str(engine_root),
        "CONCLAVE_GLOBAL_SKILLS_DIR": str(tmp_path / "global"),
        "CLAUDE_PLUGINS_CACHE": str(tmp_path / "cache"),
    }
    return skills, env


# ---------------------------------------------------------------- the third verdict


def test_the_reported_names_still_have_no_file_anywhere(tmp_path, monkeypatch):
    """Anti-vacuity, and the premise the whole fix rests on.

    If a SKILL.md for these ever appears, the third verdict is answering a question that
    no longer exists and this file should be deleted rather than kept green.
    """
    skills, env = _hermetic(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for name in REPORTED:
        assert skill.verify(name) is None, (
            f"{name} resolves on disk now — the built-in premise of #168 has expired")


def test_a_declared_builtin_classifies_as_builtin_and_an_invention_as_phantom(
        tmp_path, monkeypatch):
    skills, env = _hermetic(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    for name in REPORTED:
        verdict, _ = skill.classify(name)
        assert verdict == "BUILTIN", f"{name}: {verdict}"

    verdict, _ = skill.classify(INVENTED)
    assert verdict == "PHANTOM", (
        "the third verdict swallowed the second — a typo now passes the gate that "
        "exists to catch typos")

    (skills / "real-fixture-skill").mkdir()
    (skills / "real-fixture-skill" / "SKILL.md").write_text("# x\n")
    verdict, where = skill.classify("real-fixture-skill")
    assert verdict == "OK" and where.endswith("SKILL.md"), (verdict, where)


def test_declaring_a_builtin_does_not_shadow_a_file_that_exists(tmp_path, monkeypatch):
    """OK beats BUILTIN. A declaration must never hide what is actually on disk —
    otherwise the day someone installs a real skill by that name, the verdict keeps
    pointing at the harness and no path is ever printed."""
    skills, env = _hermetic(tmp_path, builtins=("update-config",))
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    (skills / "update-config").mkdir()
    (skills / "update-config" / "SKILL.md").write_text("# shadow\n")

    verdict, where = skill.classify("update-config")

    assert verdict == "OK", f"a declaration outranked a real file: {verdict} {where}"


def test_an_absent_declaration_file_leaves_the_two_old_verdicts(tmp_path, monkeypatch):
    """A consumer instance whose CODE root predates this file still gets the old
    behaviour, not a crash. Absence of the declaration means "nothing is declared"."""
    engine_root = tmp_path / "engine"
    (engine_root / "skills").mkdir(parents=True)
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(engine_root))
    monkeypatch.setenv("CONCLAVE_GLOBAL_SKILLS_DIR", str(tmp_path / "global"))
    monkeypatch.setenv("CLAUDE_PLUGINS_CACHE", str(tmp_path / "cache"))

    assert skill.builtin_names() == frozenset()
    assert skill.classify("update-config")[0] == "PHANTOM"


# ---------------------------------------------------------------- the two consumers


def test_the_cli_exits_zero_on_a_builtin_and_one_on_a_phantom(tmp_path):
    """The reported harm: exit 1 aborted the whole G1 batch over a working skill."""
    skills, env = _hermetic(tmp_path)
    (skills / "real-fixture-skill").mkdir()
    (skills / "real-fixture-skill" / "SKILL.md").write_text("# x\n")

    ok = run_engine("skill", "verify", *REPORTED, "real-fixture-skill", env=env)
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "PHANTOM" not in ok.stdout, ok.stdout
    for name in REPORTED:
        assert f"BUILTIN\t{name}" in ok.stdout, ok.stdout

    bad = run_engine("skill", "verify", *REPORTED, INVENTED, env=env)
    assert bad.returncode == 1, bad.stdout + bad.stderr
    assert f"PHANTOM\t{INVENTED}" in bad.stdout, bad.stdout


def test_the_audit_and_the_cli_give_one_instance_one_answer(tmp_path):
    """Cat 12 is the consumer that made kosmos-cxo drop an entry. It must read the same
    declaration the CLI reads — two gates disagreeing about one name is #133 F1's defect
    in a different pair of modules."""
    skills, env = _hermetic(tmp_path)
    advisor = skills / "team._fixture"
    advisor.mkdir()
    (advisor / "SKILL.md").write_text(
        "---\nname: team._fixture\n---\n\n"
        "- `update-config`\n"
        f"- `{INVENTED}`\n"
    )

    r = run_engine("audit", "phantom-skills", "--skills-dir", str(skills), env=env)

    assert f"phantom skill: {INVENTED}" in r.stdout, r.stdout
    assert "phantom skill: update-config" not in r.stdout, r.stdout


def test_the_audit_module_reads_the_declaration_directly(tmp_path, monkeypatch):
    """The same claim at the unit boundary, so a CLI wiring change cannot hide a
    regression here."""
    skills, env = _hermetic(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    advisor = skills / "team._fixture"
    advisor.mkdir()
    (advisor / "SKILL.md").write_text(
        "---\nname: team._fixture\n---\n\n- `keybindings-help`\n")

    findings = phantom_skills.run(skills)

    assert findings.warn == [], findings.warn


# ---------------------------------------------------------------- the declaration itself


def test_the_shipped_declaration_covers_the_reported_names(tmp_path, monkeypatch):
    assert DECLARATION.is_file(), f"no declaration at {DECLARATION}"
    declared = set(skill.parse_builtins(DECLARATION.read_text(encoding="utf-8")))
    missing = [n for n in REPORTED if n not in declared]
    assert not missing, f"#168's own reproduction is still unfixed for: {missing}"


def test_no_declared_builtin_resolves_on_disk():
    """The staleness direction a process CAN measure.

    A declared name that suddenly has a SKILL.md is no longer a built-in: something
    installed a skill under that name, and the row now grants an exemption to a file
    nobody reviewed. `classify` prefers OK, so nothing breaks — but the row is dead and
    a dead row is what #133 F1 was about.
    """
    shadowed = [
        n for n in skill.parse_builtins(DECLARATION.read_text(encoding="utf-8"))
        if skill.verify(n) is not None
    ]
    assert not shadowed, (
        f"these are declared harness built-ins but now resolve on disk: {shadowed}. "
        "Delete the rows — a skill with a file needs no exemption.")


def test_the_declaration_states_how_to_re_measure_itself():
    """The other staleness direction is NOT measurable from disk, and pretending
    otherwise is how a hand-kept list rots quietly. A new built-in ships with the next
    harness update and nothing here will notice. The list therefore has to carry the
    harness it was read from, the version, and a command that reproduces the reading —
    so a human who doubts it can settle it in one paste instead of trusting the file.
    """
    text = DECLARATION.read_text(encoding="utf-8")
    assert re.search(r"\b\d+\.\d+\.\d+\b", text), (
        "no harness version in the declaration — a built-in list with no version is a "
        "claim about no particular harness")
    assert "minif" in text.lower(), (
        "the declaration does not record WHY it is hand-kept: the only structural "
        "handle in the binary is a minifier-renamed identifier (_o/Po/Do across four "
        "installed builds), so a spelling-keyed scraper is not an option")

    # Inside a fenced block, not merely mentioned in prose. The first draft of this
    # assertion was `"strings" in text`, and a probe that broke the command to
    # `/usr/bin/STR1NGS` came back GREEN — the word survives in the paragraph that
    # explains the cost. An assertion a reader can satisfy by talking about the command
    # is not an assertion about the command.
    blocks = re.findall(r"^```\n(.*?)^```", text, re.S | re.M)
    assert blocks, "no fenced command block in the declaration"
    command = "\n".join(blocks)
    assert "/usr/bin/strings" in command, (
        "the re-measure command does not name an unproxied instrument (#104 item 9): "
        "a bare `strings` can be rewritten under the agent and a zero result then means "
        "nothing at all")
    assert "keybindings-help" in command, (
        "the command hardcodes the registration identifier instead of deriving it from "
        "a known built-in — which is the failure the table above measures")


# ---------------------------------------------------------------- the instrument gate


#: `verify` answers "where is the file"; `classify` answers "does this exist". A caller
#: that judges a name with `verify` re-ships #168. Rows here are the callers allowed to
#: ask the narrower question, each with the reason it is the right one.
VERIFY_CALLERS_ALLOWED: dict[str, str] = {
    "enginelib/skill.py": "the home of both — classify() is built on verify()",
}

_VERIFY_JUDGEMENT = re.compile(r"verify\(")


def _modules_calling_verify() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in sorted(SCRIPTS.rglob("*.py")):
        rel = path.relative_to(SCRIPTS).as_posix()
        if rel.startswith(("tests/", "evals/", ".venv/")) or "/tests/" in rel:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        lines = [
            node.lineno
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (
                (isinstance(node.func, ast.Name) and node.func.id == "verify")
                or (isinstance(node.func, ast.Attribute) and node.func.attr == "verify")
            )
        ]
        if lines:
            found[rel] = lines
    return found


def test_the_verify_scan_sees_its_own_home():
    """Anti-vacuity: a scan that matched nothing would pass the gate below silently."""
    found = _modules_calling_verify()
    assert "enginelib/skill.py" in found, (
        f"the scan does not see skill.py — it is measuring nothing: {sorted(found)}")


def test_no_module_judges_existence_with_the_disk_only_query():
    strays = sorted(
        f"{rel}:{lines}" for rel, lines in _modules_calling_verify().items()
        if rel not in VERIFY_CALLERS_ALLOWED
    )
    assert not strays, (
        f"these call verify() — the disk-only query — outside {sorted(VERIFY_CALLERS_ALLOWED)}: "
        f"{', '.join(strays)}.\nA None from verify() means 'not on disk', not 'does not "
        "exist'; printing it as PHANTOM is #168. Call classify().")


def test_no_allowance_outlives_the_module_it_names():
    stale = [
        rel for rel in VERIFY_CALLERS_ALLOWED
        if not (SCRIPTS / rel).is_file()
    ]
    assert not stale, (
        f"these rows allow a verify() caller that no longer exists: {stale} — an "
        "exemption whose subject is gone does not expire, it waits (#133 F1).")


# ---------------------------------------------------------------- the surface gate


#: Where a reader learns what the verdicts mean. Same roots #88's batch gate scans — the
#: lesson there was that a repair shipped with no gate and three surfaces went on teaching
#: the retired form for weeks.
SURFACE_DIRS = ("skills", "commands", "agents", "docs")

_TEACHES_PHANTOM = re.compile(r"`?PHANTOM`?\b")
_TEACHES_BUILTIN = re.compile(r"`?BUILTIN`?\b")


def _surfaces_naming_the_verdict() -> list[Path]:
    out: list[Path] = []
    for d in SURFACE_DIRS:
        root = REPO / d
        if not root.is_dir():
            continue
        for md in sorted(root.rglob("*.md")):
            if _TEACHES_PHANTOM.search(md.read_text(encoding="utf-8")):
                out.append(md)
    return out


def test_the_surface_scan_sees_the_protocol_that_defines_the_gate():
    """Anti-vacuity: hire.md is the surface G1 is specified on. If the scan cannot see
    it, every name below is absent for the wrong reason."""
    found = {p.relative_to(REPO).as_posix() for p in _surfaces_naming_the_verdict()}
    assert "skills/forge-operations/references/protocols/hire.md" in found, found


def test_no_shipped_surface_teaches_a_two_verdict_vocabulary():
    """A surface that names PHANTOM and not BUILTIN is teaching the retired contract.

    Derived rather than listed: the declaration file itself is the only exception, and it
    earns it by being the definition of the third verdict rather than a user of it.
    """
    allowed = {"skills/forge-operations/references/harness-builtins.md"}
    strays = sorted(
        rel for rel in (
            p.relative_to(REPO).as_posix() for p in _surfaces_naming_the_verdict()
        )
        if rel not in allowed
        and not _TEACHES_BUILTIN.search((REPO / rel).read_text(encoding="utf-8"))
    )
    assert not strays, (
        f"these teach PHANTOM without BUILTIN: {', '.join(strays)}.\n"
        "A reader following them drops a skill the harness ships (#168), which is what "
        "#88 found the last time a verdict changed and no gate watched the surfaces.")
