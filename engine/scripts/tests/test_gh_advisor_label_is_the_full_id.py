"""The GitHub advisor label is `advisor:<id>` on BOTH sides of the wire.

`github-issues-protocol.md` defines the label as `advisor:<id>` and the write
paths honour it. Two read paths did not: they split the id on its first hyphen
and queried `advisor:<stem>`. GitHub label matching is exact, so `advisor:kai`
never matches an issue labelled `advisor:kai-cto` — every hyphenated advisor saw
a permanently empty issue queue, and the briefing's own empty-state named a
label that no code ever wrote.

An id rename changes the label, so the two conventions had to be reconciled
before `engine advisor rename` could exist without baking the divergence in.

The load-bearing test is `test_write_and_read_agree_on_the_label`: fixing three
call sites independently is what let them drift in the first place.
"""
from __future__ import annotations

import pytest

from briefing.scans import queue
from enginelib import gh, inbox
from enginelib.advisors import advisor_label
from enginelib.lifecycle import gh_fetch
from tests.briefing.test_scans import make_ctx

ADVISOR = "kai-cto"


def test_label_is_the_whole_id():
    assert advisor_label(ADVISOR) == f"advisor:{ADVISOR}"


def test_write_and_read_agree_on_the_label(monkeypatch):
    """One label string, produced by every path that touches GitHub."""
    seen: dict[str, list[str]] = {}

    def fake_run_gh(args: list[str]) -> str:
        seen.setdefault("labels", []).extend(
            args[i + 1] for i, a in enumerate(args) if a == "--label"
        )
        return "[]"

    monkeypatch.setattr(gh, "_run_gh", fake_run_gh)
    gh.gh_advisor_issues(ADVISOR, "owner/repo")
    gh.search_issues(ADVISOR, ["owner/repo"])

    write_labels = inbox.parse_inbox("- [ ] do the thing\n", ADVISOR)[0].labels
    read_labels = [x for x in seen["labels"] if x.startswith("advisor:")]

    assert set(read_labels) == {advisor_label(ADVISOR)}, read_labels
    assert advisor_label(ADVISOR) in write_labels, write_labels


def test_snapshot_fetch_queries_the_whole_id(monkeypatch):
    captured: list[str] = []

    def fake_search(label: str, repos: list[str]) -> str:
        captured.append(label)
        return "[]"

    monkeypatch.setattr(gh_fetch.gh, "search_issues", fake_search)
    monkeypatch.setattr(gh_fetch.gh, "search_closed_by_labels",
                        lambda label, repos, sticky: captured.append(label) or "[]")
    assert gh_fetch._label_for(ADVISOR) == ADVISOR
    assert "-" in ADVISOR, "the regression only shows on a hyphenated id"


def test_board_query_accepts_the_whole_id():
    """The Project board's advisor field is a third surface — see
    gh_board_query._board_advisor_matches. It must accept the protocol id."""
    import gh_board_query

    assert gh_board_query._board_advisor_matches(ADVISOR, ADVISOR)


def test_empty_queue_names_the_label_the_query_actually_used(tmp_path):
    ctx = make_ctx(tmp_path, ADVISOR)
    assert queue.build(ctx) == f"_(no open issues for {advisor_label(ADVISOR)})_"


@pytest.mark.parametrize("advisor", ["forge", "kai-cto", "engineering-data"])
def test_label_never_truncates(advisor):
    assert advisor_label(advisor).removeprefix("advisor:") == advisor
