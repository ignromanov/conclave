"""`engine audit advisor-labels` — the roster against the board (#111).

The defect this guards: `advisor rename` asserts completeness over the file tree, and a
GitHub label is not a file, so a surface that is 100% missed reports as 0 unclassified.
The advisor whose label went stale read `_(no open issues)_` for twenty hours while
carrying 34.

Every test below is named by the state it would let through if it were deleted.
"""
from __future__ import annotations

import json
import types

import pytest

from enginelib.audit import advisor_labels

ROSTER = ["forge-chro", "sage-cto"]


def _labels(*names: str) -> list[str]:
    # A real board's label list is mostly not advisor labels. Mixing them in is the
    # point: a prefix filter that matched everything would pass a roster-only fixture.
    return ["bug", "p1", "agent-infra", *names]


def test_a_roster_advisor_with_no_label_is_reported():
    f = advisor_labels.run(ROSTER, _labels("advisor:forge-chro"), repo="o/r")
    assert len(f.warn) == 1
    assert "sage-cto has no label" in f.warn[0]
    assert "gh label create advisor:sage-cto -R o/r" in f.warn[0]


def test_a_label_naming_nobody_in_the_roster_is_reported():
    f = advisor_labels.run(
        ROSTER, _labels("advisor:forge-chro", "advisor:sage-cto", "advisor:kai"),
        issue_counts={"advisor:kai": 34}, repo="o/r")
    assert len(f.warn) == 1
    assert "advisor:kai" in f.warn[0] and "34 open issue" in f.warn[0]


def test_an_orphan_label_is_never_told_to_be_deleted():
    """A label carrying issues is the only record that those issues were ever assigned,
    so the rule against quiet removal binds hardest where the thing looks like garbage."""
    f = advisor_labels.run(ROSTER, _labels("advisor:forge-chro", "advisor:sage-cto", "advisor:kai"),
                           repo="o/r")
    assert "delete" in f.warn[0], "the finding must say what it will not do"
    assert "label delete" not in f.warn[0]
    assert "--confirm" not in f.warn[0]


def test_a_board_in_parity_reports_nothing():
    f = advisor_labels.run(ROSTER, _labels("advisor:forge-chro", "advisor:sage-cto"), repo="o/r")
    assert (f.crit, f.warn) == ([], [])


def test_an_empty_roster_reports_that_it_measured_nothing():
    """Otherwise a resolver that returns [] is indistinguishable from a clean board:
    every comparison is satisfied and the audit exits 0."""
    f = advisor_labels.run([], _labels("advisor:kai"), repo="o/r")
    assert len(f.warn) == 1 and "measured nothing" in f.warn[0]


def test_a_capped_issue_count_is_reported_as_a_floor():
    """A count that silently stops at the page limit is a wrong answer; one known to be
    a floor is a fact."""
    f = advisor_labels.run(ROSTER, _labels("advisor:forge-chro", "advisor:sage-cto", "advisor:kai"),
                           issue_counts={"advisor:kai": 200}, capped=True, repo="o/r")
    assert "≥200 open issue" in f.warn[0]


def test_the_label_prefix_comes_from_the_one_function_that_builds_labels():
    """A second `"advisor:"` literal is exactly how the write side came to say
    `advisor:kai-cto` while two read sides asked for `advisor:kai`."""
    from enginelib.advisors import advisor_label
    assert advisor_labels.LABEL_PREFIX == advisor_label("")
    assert advisor_labels.advisor_labels(["advisor:x", "advisorx", "x:advisor"]) == {"advisor:x"}


# --- the adapter: the only layer that can tell "in parity" from "never asked" ---

def _run_adapter(monkeypatch, *, labels=None, counts=None, raises=None, repo="o/r"):
    from engine.cmd import audit as audit_cmd
    from enginelib import gh

    monkeypatch.setattr(
        "enginelib.advisors.canonical_advisors", lambda: list(ROSTER))

    def _list_labels(_repo):
        if raises:
            raise raises
        return labels or []

    def _counts(_repo):
        if raises:
            raise raises
        return (counts or {}), False

    monkeypatch.setattr(gh, "list_labels", _list_labels)
    monkeypatch.setattr(gh, "open_issue_label_counts", _counts)
    args = types.SimpleNamespace(repo=repo)
    return audit_cmd._AUDITS["advisor-labels"](args)


def test_gh_failure_exits_warn_not_clean(monkeypatch, capsys):
    """The whole point: an unauthenticated gh and a board in perfect parity produce the
    same empty finding list. Collapsing them into exit 0 is the false-clean this audit
    exists to prevent."""
    code = _run_adapter(monkeypatch, raises=RuntimeError("gh: not authenticated"))
    out = capsys.readouterr().out
    assert code == 2, "a gh failure must not exit 0"
    assert "parity NOT measured" in out
    assert "not authenticated" in out


def test_no_repo_scope_is_refused_rather_than_widened(monkeypatch, capsys):
    """Fail-closed on privacy (#50): an empty scope is never widened to account-wide."""
    monkeypatch.setattr(
        "enginelib.lifecycle.gh_fetch.resolve_repos", lambda _owner: [])
    code = _run_adapter(monkeypatch, labels=[], repo=None)
    err = capsys.readouterr().err
    assert code == 2 and "measured nothing" in err


def test_the_adapter_names_the_roster_it_compared_against(monkeypatch, capsys):
    """The orphan finding accuses a label of naming nobody, and is only as right as the
    resolver behind it — six of them disagree in this tree (#69). A count alone cannot
    show a reader that the roster came back short."""
    _run_adapter(monkeypatch, labels=["advisor:forge-chro", "advisor:sage-cto"])
    out = capsys.readouterr().out
    assert "forge-chro, sage-cto" in out


def test_gh_list_labels_asks_for_more_than_one_page(monkeypatch):
    """gh's default page is 30. A truncated label set makes live advisors report as
    label-less — a false finding dressed as a measurement."""
    from enginelib import gh
    seen: list[list[str]] = []
    monkeypatch.setattr(gh, "_run_gh", lambda args: (seen.append(args), "[]")[1])
    gh.list_labels("o/r")
    assert "--limit" in seen[0], "no --limit means gh's 30-row default"
    assert int(seen[0][seen[0].index("--limit") + 1]) > 30


def test_issue_counts_are_computed_client_side(monkeypatch):
    """For ~60s after a `gh label edit`, a server-side per-label count under-reports —
    measured returning 0, then 30, then the true 34 for the same label."""
    from enginelib import gh
    payload = json.dumps([
        {"labels": [{"name": "advisor:kai"}, {"name": "p1"}]},
        {"labels": [{"name": "advisor:kai"}]},
    ])
    seen: list[list[str]] = []
    monkeypatch.setattr(gh, "_run_gh", lambda args: (seen.append(args), payload)[1])
    counts, capped = gh.open_issue_label_counts("o/r")
    assert counts["advisor:kai"] == 2 and counts["p1"] == 1
    assert capped is False
    assert "--label" not in seen[0], "one query for all labels, not one per label"


@pytest.mark.parametrize("name", ["advisor-labels"])
def test_the_audit_is_registered_under_its_own_name(name):
    """Registration is what puts it in the protocol's derived Run loop (#302). An audit
    outside that loop is an audit nothing invokes."""
    from engine.cmd.audit import _AUDITS
    assert name in _AUDITS
