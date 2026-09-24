"""test_advisor_label.py — hire gives a new advisor its GH label (#153).

The hire path wrote the agent-def, the skill dir and `personality.md`, and never the
`advisor:<id>` label, so the first `gh issue create --label advisor:<id>` routed to a newly
hired advisor aborted with `could not add label ... not found` — for kosmos-cxo (2026-08-14)
and again for helm-ceo (2026-09-06), created by hand both times. `audit advisor-labels`
reports the gap, but only after the fact; `engine advisor label` closes it at hire.

Its repo scope is the audit's resolver, so hire creates the label on exactly the boards the
audit measures, and the two can never disagree about where a label belongs.
"""

from __future__ import annotations

import pathlib
import types

REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
HIRE = REPO_ROOT / "skills/forge-operations/references/protocols/hire.md"


def _run(monkeypatch, *, advisor="kosmos-cxo", repos=("o/code", "o/data"), labels=None,
         raises=None, repo=None):
    from engine.cmd import advisor as advisor_cmd
    from enginelib import gh

    created: list[tuple[str, str]] = []
    monkeypatch.setattr("enginelib.lifecycle.gh_fetch.resolve_repos", lambda _owner: list(repos))
    monkeypatch.setattr("enginelib.roster.roster_get", lambda _key: "o")

    def _list(r):
        if raises:
            raise raises
        return list((labels or {}).get(r, []))

    monkeypatch.setattr(gh, "list_labels", _list)
    monkeypatch.setattr(gh, "create_label", lambda r, name: created.append((r, name)))
    code = advisor_cmd._label(types.SimpleNamespace(id=advisor, repo=repo))
    return code, created


def test_a_missing_label_is_created_on_every_repo_in_scope(monkeypatch, capsys):
    code, created = _run(monkeypatch)
    assert code == 0
    assert created == [("o/code", "advisor:kosmos-cxo"), ("o/data", "advisor:kosmos-cxo")]
    assert capsys.readouterr().out.count("created") == 2


def test_an_existing_label_is_left_alone(monkeypatch, capsys):
    """Idempotent: a re-run after a partial hire must not fail on the repo already done."""
    code, created = _run(monkeypatch, labels={"o/code": ["advisor:kosmos-cxo"]})
    assert code == 0
    assert created == [("o/data", "advisor:kosmos-cxo")]
    out = capsys.readouterr().out
    assert "exists\to/code" in out and "created\to/data" in out


def test_gh_failure_is_reported_not_clean(monkeypatch, capsys):
    """An unauthenticated gh and a label already in place must not share an exit code."""
    code, created = _run(monkeypatch, raises=RuntimeError("gh: not authenticated"))
    assert code == 1 and created == []
    out = capsys.readouterr().out
    assert "FAILED\to/code" in out and "not authenticated" in out


def test_no_repo_scope_is_refused_rather_than_widened(monkeypatch, capsys):
    """Fail-closed on privacy (#50), same as the audit it mirrors."""
    code, created = _run(monkeypatch, repos=())
    assert code == 2 and created == []
    assert "no repo scope" in capsys.readouterr().err


def test_an_explicit_repo_narrows_the_scope(monkeypatch):
    code, created = _run(monkeypatch, repo="o/code")
    assert code == 0 and created == [("o/code", "advisor:kosmos-cxo")]


def test_an_invalid_id_is_refused_before_any_gh_call(monkeypatch):
    code, created = _run(monkeypatch, advisor="Bad Id")
    assert code == 1 and created == []


def test_create_label_scopes_the_call_to_the_repo(monkeypatch):
    from enginelib import gh
    seen: list[list[str]] = []
    monkeypatch.setattr(gh, "_run_gh", lambda args: (seen.append(args), "")[1])
    gh.create_label("o/code", "advisor:x")
    assert seen[0][:3] == ["label", "create", "advisor:x"]
    assert seen[0][seen[0].index("-R") + 1] == "o/code"


def test_hire_protocol_invokes_the_verb():
    """A verb no protocol invokes is not a path (the #165 lesson): the hire must call it."""
    assert "engine advisor label" in HIRE.read_text(encoding="utf-8")
