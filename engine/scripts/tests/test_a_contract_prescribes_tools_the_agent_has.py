"""A contract may not tell an executor to use a tool its own definition withholds (#185).

`executor-protocol.md` binds every executor. Each `agents/exec-*.md` grants its executor an
explicit `tools:` list — the gate `test_executor_defs.py` already insists the key is present,
precisely because "an optional key is a key that drifts". Nothing checks the two against each
other, so the contract can prescribe a verb the agent has no tool for and the suite stays green.

MEASURED, NOT ARGUED. Five of the seven shipped executors — iris, metron, scout, socra,
themis — are granted no `Write` and no `Edit`. All seven are granted `Bash`. So:

  * `executor-protocol.md` §Memory model says `MEMORY.md` is "Written by executor itself
    (manual edit during run)". For five of seven there is no editing tool to do it with; it
    is reachable only through a shell redirect, which the contract never says;
  * `agents/exec-iris-test.md` gives iris an output-path convention for a verdict file, and
    iris has no `Write`.

Nothing here is impossible — `Bash` can create a file — which is exactly why it has stayed
broken. The cost is not a refusal, it is a dispatched agent improvising delivery, and #185
records what that looked like: four consecutive final reports truncated mid-sentence, the
last recovered only by having the agent write to disk.

WHAT THIS GATE IS FOR. #185's suggested fix is a delivery rule in the contract. Written
naively — "return a long report by writing it with `Write`" — it would prescribe a tool five
of seven executors do not have, which is #315's defect one level down: a binding document
asserting a capability the distribution does not grant. This gate makes that failure loud.

WHAT IT IS NOT FOR. It does not require the contract to mention only tools; it looks at
**prescriptions** — a tool named in an imperative about what the executor does — and it reads
the granted set from the agent definitions rather than from a list restated here, so a new
executor with a narrower grant is covered the day it is minted.
"""
from __future__ import annotations

import re
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
REPO = SCRIPTS.parents[1]
AGENTS = REPO / "agents"
CONTRACT = REPO / "skills" / "advisor-contracts" / "references" / "executor-protocol.md"

#: The tool vocabulary of the harness, as the agent definitions spell it. Derived from what
#: the defs actually grant plus the ones a contract might reach for and no def grants — the
#: second half is the point, since a name nobody grants is exactly what must be caught.
KNOWN_TOOLS = {
    "Read", "Write", "Edit", "Grep", "Glob", "Bash", "WebSearch", "WebFetch",
    "Agent", "TeamCreate", "SendMessage", "ListAgents", "ToolSearch", "NotebookEdit",
}

#: A tool named inside backticks, as every contract in this tree writes tool names.
TOOL_IN_TEXT = re.compile(r"`(" + "|".join(sorted(KNOWN_TOOLS)) + r")`")

#: An imperative aimed at the executor. A line that merely *mentions* a tool — naming what
#: the caller does, or recording that something is not available — is not a prescription.
#: The use/mention distinction #310 had to learn, in its third setting.
PRESCRIBES = re.compile(
    r"\b(use|uses|using|call|calls|run|runs|write|writes|append|appends|return|returns"
    r"|deliver|delivers|via|with)\b",
    re.IGNORECASE,
)
EXCUSES = re.compile(
    r"\b(not available|never|must not|may not|cannot|can not|no such|neither|nor"
    r"|withheld|withhold|withholds|do(?:es)? not (?:have|grant)|is not granted"
    r"|are not granted|no shipped|caller)\b",
    re.IGNORECASE,
)


def _granted() -> dict[str, set[str]]:
    """{executor name: granted tools} read from the agent definitions."""
    out: dict[str, set[str]] = {}
    for path in sorted(AGENTS.glob("exec-*.md")):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("tools:"):
                out[path.stem] = {t.strip() for t in line[len("tools:"):].split(",")}
                break
    return out


def _units(text: str) -> list[tuple[int, str]]:
    """(line number, sentence) over the document, sentences reassembled across line breaks.

    These contracts hard-wrap mid-sentence, so a line-scoped scan splits the negation from
    the thing negated: "granted neither `Write` nor `Edit` ... so a rule written as" lands on
    one line and "is a rule most executors cannot follow" on the next, and the excuse never
    reaches the claim. Measured on this very file, against text written for this very gate.
    """
    units: list[tuple[int, str]] = []
    line_no = 1
    for block in re.split(r"\n\s*\n", text):
        flat = " ".join(block.split())
        for piece in re.split(r"(?<=[.:;])\s+", flat):
            if piece.strip():
                units.append((line_no, piece.strip()))
        line_no += block.count("\n") + 2
    return units


def prescribes(unit: str) -> set[str]:
    """The tools a sentence tells the executor to use — empty when it only mentions them.

    THE VERB IS SOUGHT WITH THE TOOL NAMES REMOVED. `Write` is both a tool and the imperative
    that would prescribe it, and the verb pattern is case-insensitive, so every occurrence of
    the token satisfied the test that was supposed to judge it: for `Write` the gate was a
    tautology, flagging the name in any context at all — including the sentence in
    `executor-protocol.md` that exists to say five executors do not have it. A predicate
    answerable only one way measures nothing (#313's `vera-cto==b`, in prose).
    """
    tools = {m.group(1) for m in TOOL_IN_TEXT.finditer(unit)}
    if not tools:
        return set()
    without_tools = TOOL_IN_TEXT.sub(" ", unit)
    if not PRESCRIBES.search(without_tools) or EXCUSES.search(unit):
        return set()
    return tools


def _prescribed() -> dict[int, set[str]]:
    """{line number: tools the contract tells the executor to use}."""
    out: dict[int, set[str]] = {}
    for line_no, unit in _units(CONTRACT.read_text(encoding="utf-8")):
        tools = prescribes(unit)
        if tools:
            out[line_no] = out.get(line_no, set()) | tools
    return out


# ----------------------------------------------------------------------------- the gate


def test_no_executor_is_told_to_use_a_tool_it_is_not_granted() -> None:
    granted = _granted()
    assert granted, "no executor definitions found — the gate has no subject"
    universal = set.intersection(*granted.values())

    violations = []
    for n, tools in _prescribed().items():
        for tool in sorted(tools - universal):
            lacking = sorted(name for name, have in granted.items() if tool not in have)
            violations.append(
                f"  executor-protocol.md:{n}: prescribes `{tool}`, withheld from "
                f"{len(lacking)} of {len(granted)}: {', '.join(lacking)}"
            )
    assert not violations, (
        "the binding contract prescribes tools the agent definitions do not grant:\n"
        + "\n".join(violations)
    )


# -------------------------------------------------------- the instrument, held to its job


def test_the_grants_are_read_from_the_definitions_not_restated() -> None:
    """Anti-vacuity, and the measurement the contract text rests on.

    If the grants stop being read — a renamed key, a moved directory — every assertion above
    passes by finding nothing, and the contract could then prescribe anything at all."""
    granted = _granted()
    assert len(granted) >= 7, f"only {len(granted)} executor definitions found"
    assert all(granted.values()), "an executor parsed with an empty tool set"
    universal = set.intersection(*granted.values())
    assert universal == {"Read", "Grep", "Bash"}, (
        f"the universally-granted set is now {sorted(universal)}; the contract states it "
        "verbatim, so correct the sentence rather than the assertion"
    )

    #: The main gate passes by finding nothing — after this change the contract prescribes no
    #: tool at all, by design. So the subject is asserted separately: the contract must still
    #: *name* tools, or a rewrite could empty it and every check above would read as success.
    units = _units(CONTRACT.read_text(encoding="utf-8"))
    naming = [u for _, u in units if TOOL_IN_TEXT.search(u)]
    assert len(naming) >= 2, (
        f"the contract names tools in only {len(naming)} sentences; the delivery rule rests "
        "on stating which tools executors have, and that statement has gone"
    )
    assert all(prescribes(u) == set() for u in naming), (
        "a sentence naming a tool is now read as prescribing it — check it is not the "
        "tautology this gate was rewritten to remove"
    )
    without_write = {name for name, have in granted.items() if "Write" not in have}
    assert len(without_write) >= 5, (
        f"only {len(without_write)} executors lack Write; 5 of 7 were measured. If they "
        "gained it, the delivery rule can be simplified — check before assuming"
    )


def test_the_matcher_separates_a_prescription_from_a_mention() -> None:
    assert prescribes("Deliver the report by writing it with `Write`.") == {"Write"}
    assert prescribes("Append the line using `Bash`, since `Write` is not available.") == set()
    assert prescribes("The caller spawns the executor via the `Agent` tool.") == set()
    assert prescribes("Executors never use `Edit` on advisor memory.") == set()
    assert prescribes("A plain sentence with no tool name at all.") == set()

    #: The tautology. Before the tool names were stripped, the token `Write` satisfied the
    #: case-insensitive verb pattern by itself, so this sentence — which denies the tool —
    #: was scored as prescribing it.
    denial = "Executors are granted neither `Write` nor `Edit`; only `Bash` is universal."
    assert prescribes(denial) == set()
    assert PRESCRIBES.search(denial), "the raw verb pattern still matches its own subject"


def test_the_gate_would_fire_on_the_rule_this_change_nearly_wrote() -> None:
    """The reproduction. #185's fix, written the obvious way, must be caught.

    The gate is written after the contract text it polices, against a tree that satisfies it,
    which is the shape that let a briefing gate pass its own orphan (spec 116). So the
    rejected wording is replayed here against the real grants."""
    granted = _granted()
    universal = set.intersection(*granted.values())
    naive = "A report over ~2000 words is returned by writing it to a file with `Write`."
    named = prescribes(naive)
    assert named == {"Write"}, "the gate no longer reads the rule it was written to reject"
    assert not named <= universal, (
        "Write is granted to every executor after all — the measurement this contract rests "
        "on has changed"
    )
