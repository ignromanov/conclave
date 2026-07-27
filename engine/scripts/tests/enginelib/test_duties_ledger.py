"""test_duties_ledger.py — the session-end duty ledger (spec 091 §4).

The ledger is what turns the duty model from documentation into something with teeth: it is
the only record that a duty was ever acted on. Its two hard properties are append-only
(never-silent-delete, VISION §6) and honest outcomes — a ledger that only records successes
would make the §5 health sweep compute `dead` for duties that error every time.

Hermetic: tmp_path only.
"""
from __future__ import annotations

import pytest

from enginelib.duties.ledger import OUTCOMES, append_entry, read_entries


def test_append_creates_the_ledger_and_round_trips(tmp_path):
    append_entry(tmp_path, duty_id="d_x", session_id="s1", outcome="discharged")
    entries = read_entries(tmp_path)
    assert len(entries) == 1
    assert entries[0].duty_id == "d_x"
    assert entries[0].session_id == "s1"
    assert entries[0].outcome == "discharged"
    assert entries[0].ts, "entry carries no timestamp — the health sweep needs it to age"


def test_reading_an_absent_ledger_is_empty_not_an_error(tmp_path):
    """An agent that has never closed a session has no ledger. That is a normal state and
    must not read as a failure — otherwise every first run reports a problem."""
    assert read_entries(tmp_path / "nowhere") == []


@pytest.mark.parametrize("outcome", sorted(OUTCOMES))
def test_every_declared_outcome_is_accepted(outcome):
    assert outcome in OUTCOMES


def test_outcome_vocabulary_is_exactly_the_spec_five():
    """Spec §4 names five. Pinned as a set so adding a sixth is a deliberate edit here,
    not a silent widening at some call site."""
    assert OUTCOMES == {"discharged", "deferred", "skipped", "errored", "condition-unmet"}


def test_unknown_outcome_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="outcome"):
        append_entry(tmp_path, duty_id="d_x", session_id="s1", outcome="probably-fine")


def test_append_preserves_earlier_entries(tmp_path):
    """Append-only. A rewrite that dropped history would erase exactly the evidence the
    health sweep reads (never-silent-delete, VISION §6)."""
    append_entry(tmp_path, duty_id="d_a", session_id="s1", outcome="discharged")
    append_entry(tmp_path, duty_id="d_b", session_id="s1", outcome="deferred")
    append_entry(tmp_path, duty_id="d_a", session_id="s2", outcome="errored")

    entries = read_entries(tmp_path)
    assert [(e.duty_id, e.outcome) for e in entries] == [
        ("d_a", "discharged"), ("d_b", "deferred"), ("d_a", "errored")]


def test_failures_are_recorded_not_swallowed(tmp_path):
    """A ledger that only holds successes would let the §5 sweep read an every-time-erroring
    duty as healthy. The unhappy outcomes are the ones with diagnostic value."""
    for outcome in ("errored", "skipped", "condition-unmet"):
        append_entry(tmp_path, duty_id="d_x", session_id="s1", outcome=outcome)
    assert {e.outcome for e in read_entries(tmp_path)} == {
        "errored", "skipped", "condition-unmet"}


def test_note_is_optional_and_round_trips(tmp_path):
    append_entry(tmp_path, duty_id="d_x", session_id="s1", outcome="deferred",
                 note="blocked on the operator's decision")
    assert read_entries(tmp_path)[0].note == "blocked on the operator's decision"


def test_ledger_file_is_yaml_at_the_documented_path(tmp_path):
    append_entry(tmp_path, duty_id="d_x", session_id="s1", outcome="discharged")
    assert (tmp_path / "duty-ledger.yaml").is_file()


def test_a_corrupt_ledger_fails_loudly_rather_than_silently_resetting(tmp_path):
    """The dangerous alternative is treating an unparseable ledger as empty: the next
    append would then rewrite the file and the prior history would be gone for good."""
    (tmp_path / "duty-ledger.yaml").write_text("entries: [ unclosed\n", encoding="utf-8")
    with pytest.raises(Exception):
        read_entries(tmp_path)


def test_concurrent_appends_do_not_lose_entries(tmp_path):
    """Read-modify-write is only safe under the lock. Without it two sessions closing at
    once both read the same history and the second write silently drops the first entry.
    Parallel sessions are ordinary in this project, not hypothetical."""
    import concurrent.futures

    def _write(i: int) -> None:
        append_entry(tmp_path, duty_id=f"d_{i}", session_id=f"s{i}", outcome="discharged")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(_write, range(24)))

    entries = read_entries(tmp_path)
    assert len(entries) == 24, f"lost {24 - len(entries)} entries to a lost update"
    assert {e.duty_id for e in entries} == {f"d_{i}" for i in range(24)}
