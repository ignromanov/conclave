"""A binding contract may not name an executable the distribution does not ship (#315).

`github-issues-protocol.md` asserted, twice and in the present tense, that a `PreToolUse`
hook at `.claude/hooks/gh-issue-repo-guard.sh` blocks `gh issue create` without `-R` and
rejects label-vs-repo mismatches. That file has never existed in any generation — not in
an instance, not in the distribution. This is not the generational skew of #171; there was
no generation that had it.

It is load-bearing rather than cosmetic. `commands/triage.md` records what the missing `-R`
costs: `gh` run from inside `.conclave/` resolves against DATA, returns an empty issue list,
and every dedup check passes — "a dedup guard that always passes is worse than none, because
it is believed" (#162). That is the failure the phantom hook was claimed to prevent, and the
failure that produced conclave#47 duplicating conclave#46. An advisor who reads the contract
has been told the mistake is mechanically impossible, so the one discipline that does prevent
it — type `-R` every time — reads as redundant ceremony.

WHY A GATE AND NOT JUST A REWORD. The claim had been recorded three times in DATA before this
ticket: a constitution-rewrite synthesis called it a "phantom hook" in 2026-07, a triage
feedback item filed a `grep-absent` predicate against it in 2026-07-20, and that predicate was
still sitting unchecked in the verify-candidates list. Three recordings and no repair is a
signal about the loop, not about the readers: nothing could fail.

The nearest existing gate, `test_referenced_scripts_exist.py`, could not have caught it on two
counts — its perimeter is `commands/` + `agents/`, and its pattern is `scripts/**.py`. A hook
is an executable a document tells the system to run, and it was invisible on both axes.

SCOPE, MEASURED RATHER THAN ARGUED. A first cut of this gate looked for any `*.sh` named
anywhere under the shipped surfaces. That finds **78 references and zero existing files** —
the shell layer is entirely retired — and a gate on that number would demand rewriting most of
two documents. Broken down, the 78 are four different things:

  * `forge-operations/ARCHITECTURE.md` — 57 of 57 already carry the `**retired**` marker that
    `test_referenced_scripts_exist.py` established for exactly this. It is an honest
    retirement ledger, and a gate blind to the marker would fire on the honest text;
  * `forge-operations/CHANGELOG.md` — 22, and a changelog naming a script it removed is
    correct by genre;
  * `commands/feedback.md` — 6, every one of them *mentioning* rather than *using*
    ("replaces the old `emit.sh` path entirely"; an error string quoted inside a worked
    example). The use/mention distinction #310 had to learn applies here and not in #313;
  * the four contracts under `advisor-contracts/references/` — **8 references that genuinely
    send an advisor to a tool that is not there.** Those are repaired in this change.

So the perimeter is the contracts: the documents that *prescribe*, loaded into every session by
the command import blocks, and binding by construction. Documents that *record* are out, and
the retirement marker is honoured so a retirement ledger can stay a retirement ledger.
"""
from __future__ import annotations

import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[1]
CONTRACTS = REPO / "skills" / "advisor-contracts" / "references"

#: Anything a document can tell the system to execute. `.claude/hooks/<x>` is listed on its
#: own because a hook is the one form that asserts an *installed enforcement point* — the
#: shape #315 was, and the shape a `*.sh` pattern alone would still miss for a hook with no
#: extension.
EXECUTABLE = re.compile(r"(\.claude/hooks/[A-Za-z0-9_.-]+|[A-Za-z0-9_./-]+\.sh)")

#: The convention `test_referenced_scripts_exist.py` established: a line that marks the thing
#: gone is declaring an absence, not claiming a presence. Copied rather than imported so the
#: two gates can be read independently; `test_the_two_gates_agree_on_what_retirement_looks_like`
#: below keeps the copies honest.
RETIRED = re.compile(r"\*\*(deleted|retired|removed)\b", re.IGNORECASE)


def _shipped_executables() -> set[str]:
    """Basenames of every shell script and hook the distribution actually contains."""
    found = {p.name for p in REPO.rglob("*.sh") if ".git" not in p.parts}
    hooks = REPO / "engine" / "hooks"
    if hooks.is_dir():
        found |= {p.name for p in hooks.iterdir() if p.is_file()}
    return found


def _claims() -> dict[str, list[str]]:
    """Executable references in the contracts that do not declare themselves retired."""
    shipped = _shipped_executables()
    out: dict[str, list[str]] = {}
    for path in sorted(CONTRACTS.glob("*.md")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if RETIRED.search(line):
                continue
            for match in EXECUTABLE.finditer(line):
                ref = match.group(1)
                if Path(ref).name in shipped:
                    continue
                out.setdefault(f"{path.name}:{n}", []).append(ref)
    return out


# ----------------------------------------------------------------------------- the gate


def test_no_contract_names_an_executable_the_distribution_does_not_ship() -> None:
    found = _claims()
    assert not found, (
        "contracts send advisors to tools that are not in the distribution:\n"
        + "\n".join(f"  {where}: {', '.join(refs)}" for where, refs in found.items())
    )


def test_no_contract_claims_an_installed_hook() -> None:
    """The narrower statement, kept separate because it is the one with teeth.

    A missing `*.sh` is a broken pointer; a named `.claude/hooks/...` path is a claim that an
    enforcement point is installed in the reader's own instance. The distribution registers
    exactly one hook (SessionStart, written into the consumer's settings by
    `conclave_init.register_hook`), and a contract asserting a second one is asserting a
    guarantee no installer provides.
    """
    hits = [
        f"{path.name}:{n}: {line.strip()[:90]}"
        for path in sorted(CONTRACTS.glob("*.md"))
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if ".claude/hooks/" in line and not RETIRED.search(line)
    ]
    assert not hits, "a contract claims an installed hook:\n" + "\n".join(hits)


# -------------------------------------------------------- the instrument, held to its job


def test_the_scan_reaches_the_contracts_it_claims_to() -> None:
    """Anti-vacuity. After this change the gate has zero live subjects, so an empty glob,
    a moved directory or a pattern that stopped matching would all read as success."""
    contracts = sorted(CONTRACTS.glob("*.md"))
    assert len(contracts) >= 12, f"the contract glob found only {len(contracts)} documents"
    names = {p.name for p in contracts}
    assert "github-issues-protocol.md" in names, "the contract #315 is about is not in scan"
    assert "agent-data-policy.md" in names


def test_the_matcher_finds_the_shapes_it_is_for_and_spares_prose() -> None:
    flagged = [
        "A `PreToolUse` hook (`.claude/hooks/gh-issue-repo-guard.sh`) blocks it",
        "run `briefing-build.sh` to rebuild",
        "`lib/feedback.sh` holds the vocabularies",
    ]
    spared = [
        "run `engine briefing build` to rebuild",
        "the shell layer is gone; use the CLI",
        "see `engine/scripts/briefing/render.py`",
    ]
    assert [s for s in flagged if not EXECUTABLE.search(s)] == []
    assert [s for s in spared if EXECUTABLE.search(s)] == []


def test_a_retired_reference_is_a_record_and_not_a_claim() -> None:
    """The convention this gate borrows, asserted rather than assumed.

    A gate that fires on `| wiki-hot-sync.sh | **retired (spec 099)** |` teaches people to
    delete the retirement record — which is how the knowledge that something was retired, and
    why, gets lost. Measured: 57 of ARCHITECTURE.md's 57 references carry this marker.
    """
    assert RETIRED.search("| wiki/wiki-hot-sync.sh | **retired (spec 099)** — none |")
    assert RETIRED.search("`emit.sh` — **removed** in spec 121")
    assert not RETIRED.search("run `emit.sh` to file the review")


def test_the_two_gates_agree_on_what_retirement_looks_like() -> None:
    """`RETIRED` here is a copy of the pattern in `test_referenced_scripts_exist.py`.

    A copy nobody compares is a cache. If that gate relaxes or tightens its convention and
    this one does not, one of the two starts flagging text the other blesses, and the next
    author has two rules to satisfy and no way to know it.
    """
    sibling = (SCRIPTS / "tests" / "test_referenced_scripts_exist.py").read_text(
        encoding="utf-8"
    )
    assert RETIRED.pattern in sibling, (
        "the retirement convention has drifted between the two gates that use it; "
        f"this one holds {RETIRED.pattern!r}"
    )


def test_the_gate_would_have_caught_the_defect_it_was_written_for() -> None:
    """The reproduction. Restoring the removed sentence must redden the gate.

    A gate written after the fix, against a tree that no longer holds the defect, has never
    been shown to detect anything — the shape that let a briefing gate pass its own orphan
    (spec 116). The original line is replayed here verbatim.
    """
    original = (
        "A `PreToolUse` hook (`.claude/hooks/gh-issue-repo-guard.sh`) blocks "
        "`gh issue create` without `-R` and rejects label-vs-repo mismatches."
    )
    assert EXECUTABLE.search(original), "the matcher does not see the defect it exists for"
    assert not RETIRED.search(original), "the defect line would be excused as a retirement"
    assert ".claude/hooks/" in original
    assert "gh-issue-repo-guard.sh" not in _shipped_executables()
