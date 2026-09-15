"""tests/cmd/test_session_checkpoint.py — `engine session checkpoint` (spec 117 T4).

The verb's value is entirely in what it REFUSES, so these tests are mostly about lines that
were not written. Every one of them asserts the record's contents afterwards, not merely the
exit code: a refusal that still appends is worse than no check at all — it produces a record
that looks verified and is not, which is the diary R6 was written against.

Driven through `engine.__main__.main(argv)` rather than by calling `_checkpoint` directly. A
unit test proves the function exists; going through the parser proves a reader who copies the
contract line can actually run it.
"""
from __future__ import annotations

import pytest

from engine.__main__ import main
from enginelib import paths


@pytest.fixture()
def instance(tmp_path, monkeypatch):
    """A DATA root the path resolvers accept, with the session token set."""
    root = tmp_path / ".conclave"
    (root / "ops").mkdir(parents=True)
    (root / ".claude").mkdir(parents=True)
    (root / "roster.yaml").write_text("github: {}\n", encoding="utf-8")
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(root))
    monkeypatch.setenv("ADVISOR_NAME", "sage-cto")
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "3f412791-7be8-4260-a65b-e4c293f407e7")
    return root


def _records() -> list:
    d = paths.checkpoints_dir()
    return sorted(d.glob("*.md")) if d.is_dir() else []


def _body(path) -> list[str]:
    return [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.startswith("- [")]


def test_an_intent_is_written_and_the_token_names_the_file(instance):
    """Mutation: drop the token from `record_path`, or mint a new identifier for it.

    R7 — one session's lines never land in another's — is enforced by the filename and by
    nothing else: two sessions of one advisor get different `CLAUDE_CODE_SESSION_ID` values,
    so they get different files, and the operating system is the fence. Minting a second
    identifier would give one session two identities, because hot.md's `Now` line is fenced by
    this same token and there would be no way to join them.
    """
    assert main(["session", "checkpoint", "--intent", "T4 — the verb"]) == 0

    (record,) = _records()
    assert record.name.endswith("-sage-cto-3f412791.md")
    assert _body(record) == [ln for ln in _body(record) if "intent: T4 — the verb" in ln]
    assert len(_body(record)) == 1


def test_a_done_without_evidence_is_refused_and_appends_nothing(instance):
    """Mutation: drop the `not refs` guard.

    Without it the verb accepts `--done "shipped it"` on the agent's word alone, which is the
    one thing R6 forbids — and the line is then indistinguishable, in the tally and to every
    later reader, from one an external check confirmed.
    """
    assert main(["session", "checkpoint", "--done", "T4 — the verb"]) == 1
    assert _records() == []


def test_a_done_whose_evidence_does_not_resolve_appends_nothing(instance):
    """Mutation: append the line first and check the evidence afterwards.

    Order is the assertion. A verb that writes and then reports a failed check leaves the
    record holding a completion that nothing confirms — and nothing downstream re-runs the
    check, so the line is true forever from that moment.
    """
    assert main(["session", "checkpoint", "--done", "T4", "--evidence", "commit:deadbeefdead"]) == 1
    assert main(["session", "checkpoint", "--done", "T4", "--evidence", "file:nope.md"]) == 1
    assert _records() == []


def test_a_done_lands_once_its_evidence_resolves(instance):
    """The positive half, so the guards above cannot be "fixed" by refusing everything.

    A test file that only proves refusals passes with the verb replaced by `return 1`.
    """
    (instance / "report.md").write_text("findings\n", encoding="utf-8")

    assert main(["session", "checkpoint", "--intent", "T4 — the verb"]) == 0
    assert main(["session", "checkpoint", "--done", "T4 — the verb",
                 "--evidence", "file:report.md"]) == 0

    (record,) = _records()
    lines = _body(record)
    assert len(lines) == 2
    assert "[ev: file:report.md]" in lines[1]


def test_an_intent_refuses_evidence(instance):
    """Mutation: accept `--evidence` on an intent line and render it.

    An intent is a unit taken on, not completed — evidence attached to it would be counted by
    nothing and read by a human as a completion. `tally` keys on the line's kind, so the
    damage is to the reader rather than to the row, which is why it must be refused at the
    only place a human is watching.
    """
    assert main(["session", "checkpoint", "--intent", "T4", "--evidence", "commit:abc1234"]) == 1
    assert _records() == []


def test_a_session_with_no_token_degrades_to_unfenced_and_says_so(instance, monkeypatch, capsys):
    """Mutation: mint an identifier when the harness exported none, or proceed silently.

    `hot.py` makes no fencing claim without a token and this must not either: with nothing to
    fence on, two sessions of one advisor genuinely are indistinguishable. Sharing one
    `unfenced` record is the honest rendering of that, and the warning is the part that keeps
    it from looking like a fenced record.
    """
    monkeypatch.delenv("CLAUDE_CODE_SESSION_ID")

    assert main(["session", "checkpoint", "--intent", "T4 — unfenced"]) == 0

    (record,) = _records()
    assert record.name.endswith("-sage-cto-unfenced.md")
    assert "fenced to no session" in capsys.readouterr().err


def test_the_header_is_written_once_however_many_lines_follow(instance):
    """Mutation: rewrite the frontmatter on every append, or create with truncation.

    `session_init` runs twice per Claude session under one token, so two processes reach a
    missing record at the same moment. "Write the header if absent" lets the loser truncate
    whatever the winner already appended; `O_EXCL` makes losing the create the normal outcome
    rather than a data loss.
    """
    for n in range(3):
        assert main(["session", "checkpoint", "--intent", f"unit {n}"]) == 0

    (record,) = _records()
    text = record.read_text(encoding="utf-8")
    assert text.count("type: checkpoint") == 1
    assert text.count("schema_version: 1") == 1
    assert len(_body(record)) == 3
