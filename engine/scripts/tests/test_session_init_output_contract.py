"""The session-init output contract binds in both directions (GH#169).

`session_init.py` prints a machine-readable block; `commands/start.md` is the protocol
that tells the agent what to do with each line. Nothing checked that the two agree, and
the failure that exposed it was not an ordering bug but an *unimplemented* one:
`AWAITING_FIRST_LAUNCH` had a writer (`enginelib/advisor.py`), three prose documents
saying the protocol detects it, one test asserting it was written — and **no reader
anywhere in the engine**. Every hire since #75 skipped First Launch in silence.

The class of defect is "the protocol tells you to read something nothing produces".
This gate closes it: every session-init key the start protocol instructs the agent to
act on must actually be emitted by the script. It is deliberately one-directional —
a key the script emits and no document consumes is a *different* (weaker) defect,
tracked separately, and asserting it here would redden on nine pre-existing keys and
have to be waived, which is how a gate becomes decoration.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
SESSION_INIT = REPO / "engine" / "scripts" / "lifecycle" / "session_init.py"
START_MD = REPO / "commands" / "start.md"
FIRST_LAUNCH_CONTRACT = (
    REPO / "skills" / "advisor-contracts" / "references" / "first-launch-protocol.md"
)

# A session-init output line is two leading spaces, a key, a colon. Matching the string
# literal rather than the `.append(` call is deliberate: `handoff:` is built into a local
# and appended one line later, and a call-shaped matcher silently misses it — the same
# "looked one indirection away from the defect" failure recorded on spec 116.
_EMITTED = re.compile(r'(?:^|[^\w])f?"  ([a-z][\w-]*):')

# Keys `commands/start.md` instructs the agent to act on. Hand-declared, and that is the
# point: it is a pre-registration, checked against two independent artefacts (the script's
# source and the protocol's text). Neither artefact can satisfy it alone.
CONSUMED_BY_PROTOCOL = frozenset({
    "first-launch",
    "resume",
    "spec-resume",
    "handoff",
    "reflexion",
    "overlays",
    "overlay",
    "feedback",
    "degraded",
})


def emitted_keys(source: str) -> set[str]:
    return set(_EMITTED.findall(source))


@pytest.fixture(scope="module")
def keys() -> set[str]:
    return emitted_keys(SESSION_INIT.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# The gate
# ---------------------------------------------------------------------------

def test_every_key_the_protocol_reads_is_emitted(keys: set[str]) -> None:
    missing = sorted(CONSUMED_BY_PROTOCOL - keys)
    assert not missing, (
        f"commands/start.md tells the agent to read {missing} from session-init's output, "
        f"but session_init.py never prints those keys. This is the #169 shape: a protocol "
        f"step whose input has no producer."
    )


def test_every_consumed_key_is_actually_named_in_the_protocol() -> None:
    """The other half of the pre-registration: the declared set is not fiction.

    Without this, CONSUMED_BY_PROTOCOL could drift into a list of keys no document
    mentions, and the gate above would still pass — asserting a contract nobody holds.
    """
    text = START_MD.read_text(encoding="utf-8")
    unnamed = [k for k in sorted(CONSUMED_BY_PROTOCOL) if not re.search(rf"`\s*{re.escape(k)}:", text)]
    assert not unnamed, (
        f"{unnamed} are declared as consumed by the start protocol but appear in no "
        f"backticked `key:` reference in commands/start.md."
    )


def test_start_protocol_routes_first_launch_to_its_contract() -> None:
    """A key printed and read is not yet a protocol — the step has to say what to do."""
    text = START_MD.read_text(encoding="utf-8")
    assert "first-launch: yes" in text, (
        "commands/start.md must name the positive verdict verbatim, so the agent matches "
        "on the line it actually sees rather than on a paraphrase."
    )
    assert "first-launch-protocol.md" in text, (
        "the first-launch step must route to the contract that defines the bootstrap; "
        "auto-importing the contract at the top of the file is not a step."
    )


def test_the_dead_sentinel_is_no_longer_documented_as_the_detector() -> None:
    """`AWAITING_FIRST_LAUNCH` lives in a file `briefing build` regenerates on every start.

    It stays as a human-visible marker in the hire stub; it may not be described as the
    thing detection reads, or the next reader re-implements the defect from the document.
    """
    text = FIRST_LAUNCH_CONTRACT.read_text(encoding="utf-8")
    triggered = re.search(r"Triggered when.{0,400}", text, re.S)
    assert triggered, "first-launch-protocol.md lost its trigger paragraph"
    assert "AWAITING_FIRST_LAUNCH" not in triggered.group(0), (
        "the trigger paragraph still names the sentinel as the detector — that is the "
        "prose #169 was filed against."
    )


# ---------------------------------------------------------------------------
# Anti-vacuity — the extractor is measured, not trusted
# ---------------------------------------------------------------------------

def test_extractor_finds_the_full_known_surface(keys: set[str]) -> None:
    """A regex that matched nothing would make the gate above pass on an empty repo."""
    assert len(keys) >= 15, f"extractor found only {len(keys)} keys: {sorted(keys)}"
    for expected in ("git-fetch", "gh-fetch", "briefing-path", "handoff", "reflexion-resolved"):
        assert expected in keys, f"extractor missed the known key {expected!r}"


def test_extractor_sees_a_key_built_through_a_local() -> None:
    """`handoff:` is the real shape that a `.append(`-anchored matcher misses."""
    src = 'line = f"  handoff: {h.name} age={age}h"\nfound.append(line)\n'
    assert emitted_keys(src) == {"handoff"}


def test_extractor_ignores_prose_and_deeper_indents() -> None:
    src = '''
    """Docstring: not an emission."""
    lines.append(f"    stderr: {x}")
    lines.append("[session-init] advisor=x")
    '''
    assert emitted_keys(src) == set()


def test_gate_reddens_when_the_producer_is_removed(keys: set[str]) -> None:
    """Mutation, not inspection: strip the emission and the assertion must fail."""
    mutated = keys - {"first-launch"}
    assert "first-launch" in sorted(CONSUMED_BY_PROTOCOL - mutated), (
        "removing the first-launch emission left the gate green — it is not measuring "
        "the thing it names."
    )
