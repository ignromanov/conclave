"""A contract declares who loads it, and something reads the declaration (#268).

#268 counts the contracts `commands/start.md` auto-imports and finds most of them named
by no step below the header. Re-measured on master the count holds — 8 of the 12 contracts
start.md imports appear nowhere in its body — but the instrument was a grep for the
filename, and the conclusion it invites is wrong. A *policy* contract is not supposed to be
named by a step: `advisor-anti-patterns` binds by being in context, and a ceremonial
sentence pointing at it would add nothing a reader obeys.

Measured across all 17 contracts before building anything: exactly **one** carries a trigger
condition and a `## Steps` block to enter — `first-launch-protocol` ("Triggered when
`session_init.py` prints `first-launch: yes` … read at `/conclave:start` Step 1a"). The
other sixteen are policy, style or schema. So the harm #268 names is real for one contract
in seventeen, and that one was wired up by #169 (f56315d); before it, `first-launch-protocol`
appeared in start.md exactly once — on the import line — and every hire since #75 skipped
First Launch in silence.

What is broken right now is one layer down. The field that answers "which command loads
this" already exists, and **nothing reads it**: `/usr/bin/grep -rn 'appliers\\|applies_to'`
over `engine/scripts` finds zero production callers and zero tests. Left unread it acquired
every defect an unread field can:

  * three spellings of the key — `appliers:` on nine contracts, `applies_to:` on three,
    `applies-to:` on four. The third was found only because the first scan reported those
    four as having no field at all; it carried untyped prose (`advisors+executors`), which
    no parser could have read even if one had existed
  * one contract with no such field at all — `feedback-protocol`, imported by seven of the
    ten commands
  * a free-text value, `appliers: [all advisors via lifecycle skills]`
  * `team.quorum` — a command that does not exist anywhere in `commands/`
  * disagreement with the import blocks in **both** directions: `start.md` imports
    `decision-framework`, which declares `[team.processing]`; `state-report` declares
    `team.processing`, which does not import it

That is why #268 had to be measured with a grep in the first place. The gates below make the
declaration load-bearing, so the relation between a command's import block and a contract's
declared scope is checked rather than remembered.
"""
from __future__ import annotations

from pathlib import Path

from enginelib import contracts

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[1]

CONTRACTS_DIR = REPO / "skills" / "advisor-contracts" / "references"
COMMANDS_DIR = REPO / "commands"

#: The one branch contract in the tree, and the issue that wired it up.
BRANCH = "first-launch-protocol"


def _contracts() -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(CONTRACTS_DIR.glob("*.md"))}


def _commands() -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in sorted(COMMANDS_DIR.glob("*.md"))}


# ---------------------------------------------------------------- anti-vacuity


def test_both_scans_see_their_corpus():
    """A scan that matched nothing would satisfy every assertion below."""
    found = _contracts()
    assert BRANCH in found and len(found) >= 15, sorted(found)

    imports = {c: contracts.contract_imports(t) for c, t in _commands().items()}
    assert imports.get("start"), f"no imports parsed out of start.md: {imports}"
    assert BRANCH in imports["start"], imports["start"]


# ---------------------------------------------------------------- one key, one vocabulary


def test_every_contract_declares_who_loads_it():
    missing = sorted(n for n, t in _contracts().items() if contracts.parse_appliers(t) is None)
    assert not missing, (
        f"these contracts declare no `appliers:`: {missing}.\n"
        "An unread field rots; an absent one cannot even be repaired. "
        "`feedback-protocol` shipped without one while seven commands imported it.")


def test_the_key_is_spelled_one_way():
    """There were three spellings. `applies_to:` sat on the three contracts whose
    frontmatter also uses `type:`/`name:` instead of `contract:`/`version:`; `applies-to:`
    sat on four more and carried prose rather than a list, so the first version of this
    scan reported those four as having no scope field at all."""
    strays = sorted(
        f"{n} ({contracts.legacy_key(t)})"
        for n, t in _contracts().items() if contracts.legacy_key(t))
    assert not strays, (
        f"these use a retired spelling of the scope field: {strays}. "
        f"One question asked under {len(contracts.LEGACY_KEYS) + 1} names is three "
        "questions as far as any reader is concerned.")


def test_every_applier_is_a_word_the_parser_knows():
    known = set(_commands())
    bad: list[str] = []
    for name, text in _contracts().items():
        for entry in contracts.parse_appliers(text) or []:
            if entry in contracts.AUDIENCES:
                continue
            if not entry.startswith("team."):
                bad.append(
                    f"{name}: {entry!r} (not one of {sorted(contracts.AUDIENCES)} "
                    "or team.<command>)")
            elif entry[len("team."):] not in known:
                bad.append(f"{name}: {entry!r} — no commands/{entry[len('team.'):]}.md")
    assert not bad, (
        "these appliers entries name nothing that exists:\n  " + "\n  ".join(bad) +
        "\n`agent-data-policy` carried `team.quorum` for as long as nothing read the field.")


# ---------------------------------------------------------------- the two directions


def test_a_command_imports_only_contracts_scoped_to_it():
    strays: list[str] = []
    for cmd, text in _commands().items():
        for name in contracts.contract_imports(text):
            entries = contracts.parse_appliers(_contracts().get(name, "")) or []
            if contracts.UNIVERSAL in entries or f"team.{cmd}" in entries:
                continue
            strays.append(f"commands/{cmd}.md imports {name} (appliers: {entries})")
    assert not strays, (
        "these imports are not covered by the contract's own declared scope:\n  "
        + "\n  ".join(sorted(strays)) +
        "\nEither the command should not load it, or the contract's scope is stale. "
        "`start.md` imported `decision-framework`, scoped to `[team.processing]`, "
        "for as long as the field was decoration.")


def test_a_contract_scoped_to_a_command_is_imported_by_it():
    """The reverse direction, which is the quieter one: a contract can claim a command
    that never loads it and nothing in the session is any the wiser. `state-report`
    claimed `team.processing`, which imports 10 files and not that one."""
    strays: list[str] = []
    cmds = _commands()
    for name, text in _contracts().items():
        for entry in contracts.parse_appliers(text) or []:
            if entry in contracts.AUDIENCES:
                continue
            cmd = entry[len("team."):]
            if cmd in cmds and name not in contracts.contract_imports(cmds[cmd]):
                strays.append(f"{name} claims {entry}, but commands/{cmd}.md does not import it")
    assert not strays, "\n  ".join(["stale scope claims:"] + sorted(strays))


# ---------------------------------------------------------------- the branch gate


def test_exactly_the_expected_contracts_are_branches():
    """Derived, not declared. #268 proposes a hand-set `kind: absorbed|branch`; measured
    over this tree it would carry one non-default value in seventeen, and a field set by
    hand on one file is a field nobody remembers to set on the second.

    A branch is detectable from the document: it says what fires it and it has steps to
    run. If this assertion fails because a new contract became a branch, that is the gate
    working — wire it into the command that loads it and add it here.
    """
    branches = sorted(n for n, t in _contracts().items() if contracts.is_branch(t))
    assert branches == [BRANCH], branches


def test_a_branch_contract_is_named_by_the_command_that_loads_it():
    unentered: list[str] = []
    for cmd, text in _commands().items():
        for name in contracts.contract_imports(text):
            body = contracts.command_body(text)
            if contracts.is_branch(_contracts().get(name, "")) and name not in body:
                unentered.append(f"commands/{cmd}.md loads {name} and never enters it")
    assert not unentered, (
        "\n  ".join(["a contract with a trigger and steps, entered by nothing:"] + sorted(unentered))
        + "\nThat is #169: `first-launch-protocol` sat in start.md's import block with no "
          "step evaluating its trigger, and every hire between #75 and f56315d skipped "
          "First Launch in silence.")


def test_the_branch_gate_reddens_on_the_shape_it_was_written_for():
    """Anti-vacuity with teeth: today the gate has one subject and it passes, so nothing
    above distinguishes a working gate from a vacuous one.

    The fixture is the pre-#169 shape, not a paraphrase: a command whose import block
    names a trigger-carrying contract while its body never does. Verified against history
    — `git show f56315d^:commands/start.md` contains `first-launch-protocol` exactly once,
    on the import line.
    """
    branch_text = (
        "---\ncontract: fixture-protocol\nappliers: [team.fixture]\n---\n\n"
        "# Fixture Protocol\n\nTriggered when the preflight prints `fixture: yes`.\n\n"
        "## Steps\n\n1. Do the thing.\n"
    )
    assert contracts.is_branch(branch_text)

    command_text = (
        "---\ndescription: x\n---\n\n"
        "!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/fixture-protocol.md`\n\n"
        "# /conclave:fixture\n\n## Process\n\n### 1. Do something unrelated\n"
    )
    imported = contracts.contract_imports(command_text)
    assert imported == ["fixture-protocol"], imported
    assert "fixture-protocol" not in contracts.command_body(command_text), (
        "the fixture does not reproduce the defect — the body names the contract")
