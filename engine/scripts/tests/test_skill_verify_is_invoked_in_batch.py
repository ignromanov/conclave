"""Shipped surfaces invoke `engine skill verify` in batch, never once per name (#88).

#88 reports that hire.md's G1 gate returned PHANTOM for 11 of 12 skills that each
resolved fine alone, aborting the hire and blaming the skills. The report names shell
word-splitting in a backslash-continuation list as the cause. Executed, that is not it:
a backslash-continued list iterates completely in bash and in zsh, and no version of
hire.md in this repository's history ever contained one — it shipped a placeholder and
a per-name loop:

    for name in <candidate skills>; do
      path=$(engine skill verify "$name")
      if [[ -z "$path" ]]; then echo "PHANTOM: $name"; phantom=1; fi
    done

Running that loop today over twelve real skills reproduced the report exactly — eleven
PHANTOM, the first one clean — with this on stderr:

    (eval):5: command not found: python3

`python3` exists: `which python3` resolves in every iteration of the same loop and PATH
is byte-identical across them. Re-run, the interpreter was fine 12 of 12 and `head`
vanished instead; run a third time, nothing vanished. So commands invoked inside a loop
in one shell call intermittently die with `command not found` for binaries that are
present, and the loop's contract — EMPTY STDOUT MEANS THE SKILL IS ABSENT — converts a
lost invocation into a verdict about the skills.

That is why the #62 repair worked, and it is not the reason #62 gave. Batch mode's
verdict is the exit code plus an explicit `PHANTOM\t<name>` line per missing skill, so a
lost invocation reads as a failed command instead of as an absent skill. The per-name
form is unsafe here for a reason no amount of shell quoting addresses.

#62 shipped that repair to hire.md with no gate: nothing under tests/ named `skill
verify` or G1 until this file. Three other shipped surfaces still described the retired
per-name form when it was written, one of them the ARCHITECTURE diagram a reader consults
to learn what the protocol does.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]

#: The trees an agent reads as instructions. `docs/` is descriptive architecture and is
#: scanned too — a diagram that shows the retired form teaches it just as well.
SURFACE_DIRS = ("skills", "commands", "agents", "docs")

#: An INVOCATION, not a mention: the command followed by a `<placeholder>`. Prose that
#: names the command without showing a call ("a skill that `engine skill verify` cannot
#: resolve") is not an instruction about how to call it.
INVOCATION = re.compile(r"skill verify\s+((?:<[^>\n]+>|\.\.\.|\s)+)")
PLACEHOLDER = re.compile(r"<[^>\n]+>")


def _surface_files() -> list[Path]:
    out: list[Path] = []
    for d in SURFACE_DIRS:
        out.extend(sorted((REPO / d).rglob("*.md")))
    return out


def _invocations() -> list[tuple[str, int, str]]:
    """(relpath, line number, line) for every shown call of `engine skill verify`."""
    found: list[tuple[str, int, str]] = []
    for path in _surface_files():
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if INVOCATION.search(line):
                found.append((path.relative_to(REPO).as_posix(), n, line.strip()))
    return found


def test_the_scan_sees_the_call_it_is_named_for():
    """Anti-vacuity. A pattern that matched nothing reports every surface compliant, and
    this gate's whole subject is a call that two regexes could easily miss."""
    hits = _invocations()
    assert hits, "the scan found no invocation at all — it is measuring nothing"
    assert any(rel.endswith("protocols/hire.md") for rel, _, _ in hits), (
        f"the scan does not see hire.md's G1 call, the one it exists for: {hits}")


def test_every_shown_call_passes_the_whole_candidate_list():
    """One invocation for the whole list, or none of this is worth anything: the failure
    mode is per-INVOCATION, so N calls are N chances to lose one and call it a phantom."""
    singular = [
        f"{rel}:{n}  {line}"
        for rel, n, line in _invocations()
        if len(PLACEHOLDER.findall(INVOCATION.search(line).group(1))) < 2
        and "..." not in INVOCATION.search(line).group(1)
    ]
    assert not singular, (
        "these show `engine skill verify` called with a single name:\n  "
        + "\n  ".join(singular)
        + "\nPass the whole candidate list as argv. A per-name call reports absence by "
        "printing nothing, and a command that never ran prints nothing too — that is "
        "how eleven present skills were reported PHANTOM and a valid hire aborted (#88)."
    )


def test_no_surface_reads_the_verdict_off_captured_stdout():
    """The contract, not the shape. Batch mode answers with an exit code and a labelled
    line per name; capturing stdout and testing it for emptiness re-creates the channel
    on which a lost invocation is indistinguishable from an absent skill."""
    captures = [
        f"{path.relative_to(REPO).as_posix()}:{n}  {line.strip()}"
        for path in _surface_files()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "skill verify" in line and "$(" in line
    ]
    assert not captures, (
        "these capture `engine skill verify`'s stdout into a shell variable:\n  "
        + "\n  ".join(captures)
        + "\nRead the exit code and the PHANTOM lines instead (#88)."
    )
