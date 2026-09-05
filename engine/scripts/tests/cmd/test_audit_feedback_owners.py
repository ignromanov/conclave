"""test_audit_feedback_owners.py — the notebook's owner field resolves to a live advisor.

The guard in feedback_triage closes the door for new writes. This reports what is
already inside: 71 live items name `forge` or `sage`, ids the roster does not hold,
and every owner-scoped query omits them without a word.
"""
from __future__ import annotations

import json
from pathlib import Path

from enginelib.audit import feedback_owners


def _index(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return p


def _row(fid: str, item: str, owner: str | None) -> dict:
    return {"feedback_id": fid, "item_id": item, "owner": owner, "status": "accepted"}


def test_reports_an_owner_the_roster_does_not_hold(tmp_path):
    idx = _index(tmp_path, [
        _row("fb-1", "i1", "sage-cto"),
        _row("fb-2", "i1", "sage"),
        _row("fb-3", "i1", "forge"),
    ])

    f = feedback_owners.run(idx, roster={"sage-cto", "forge-chro"})

    joined = " ".join(f.crit + f.warn)
    assert "sage" in joined and "forge" in joined, joined
    assert "sage-cto" not in [line.split(":")[0] for line in f.crit + f.warn]


def test_counts_each_unresolved_owner_once_with_its_item_count(tmp_path):
    """Two names, four items — the report groups, so the fix is one decision per name."""
    idx = _index(tmp_path, [
        _row("fb-1", "i1", "sage"), _row("fb-2", "i1", "sage"),
        _row("fb-3", "i1", "forge"), _row("fb-4", "i1", "forge"),
    ])

    f = feedback_owners.run(idx, roster={"sage-cto", "forge-chro"})

    assert len(f.crit) + len(f.warn) == 2, f.crit + f.warn
    assert any("2" in line for line in f.crit + f.warn)


def test_silent_when_every_owner_resolves(tmp_path):
    idx = _index(tmp_path, [_row("fb-1", "i1", "sage-cto"), _row("fb-2", "i1", None)])

    f = feedback_owners.run(idx, roster={"sage-cto", "forge-chro"})

    assert not f.crit and not f.warn, f.crit + f.warn


def test_reserved_owner_is_not_an_advisor_and_is_not_reported(tmp_path):
    """`verify:auto` is stamped by the auto-close path, not hired."""
    idx = _index(tmp_path, [_row("fb-1", "i1", "verify:auto")])

    f = feedback_owners.run(idx, roster={"sage-cto", "forge-chro"})

    assert not f.crit and not f.warn, f.crit + f.warn


def test_an_unreadable_roster_reports_nothing_rather_than_everything(tmp_path):
    """Membership is unjudgeable without a roster; accusing all of it is the #170 shape."""
    idx = _index(tmp_path, [_row("fb-1", "i1", "sage-cto"), _row("fb-2", "i1", "forge")])

    f = feedback_owners.run(idx, roster=set())

    assert not f.crit and not f.warn, f.crit + f.warn
