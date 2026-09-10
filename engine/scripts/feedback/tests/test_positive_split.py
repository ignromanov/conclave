"""#250 — `positive` had no terminal verb, and it was carrying two different things.

Six items existed when this was designed. Three were `removed-step` findings, the form
spec 117 built the category for: an artefact removed a step. The other three were
first-person near-misses -- a claim written before the command that would decide it,
then caught and run; a mutation scoped to the wrong files that nearly became a filed
issue. Those are not observations about an artefact, they are the record of an error
that did not ship and of what caught it.

Neither can be `resolved` (nothing was fixed) or `rejected` (both are valid), so both
sat at `open` or `deferred` forever. `acknowledged` is the terminal verb for both; the
split is so that a near-miss keeps travelling and a removed-step stops.
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError
from schema import FeedbackItem, Location


def _item(**over):
    base = dict(
        id="i1",
        category="near-miss",
        layer="workflow",
        location=Location(file="engine/scripts/x.py"),
        observation="I wrote the claim before running the command that decides it.",
        evidence="transcript: the docstring predates the probe by two tool calls",
        severity="medium",
        frequency="first-time",
        status="acknowledged",
    )
    base.update(over)
    return FeedbackItem(**base)


class TestSchema:
    def test_near_miss_is_a_category(self):
        assert _item().category == "near-miss"

    def test_acknowledged_is_a_status(self):
        assert _item(status="acknowledged").status == "acknowledged"

    def test_a_positive_can_be_acknowledged(self):
        """The whole point: the category that had no terminal verb now has one."""
        assert _item(category="positive", status="acknowledged").status == "acknowledged"

    def test_an_invented_category_is_still_rejected(self):
        """The enum must stay an enum -- widening it twice is not opening it."""
        with pytest.raises(ValidationError):
            _item(category="what-went-well")

    def test_an_invented_status_is_still_rejected(self):
        with pytest.raises(ValidationError):
            _item(status="noted")


class TestArchiver:
    def test_acknowledged_counts_as_done(self):
        """`_DONE_STATUSES` is a hardcoded set, so a new terminal status is invisible to
        the archiver until it is added -- and the archiver is what appends a finding to
        hot.md, which is the only path by which a near-miss reaches a future briefing.
        A terminal status that never archives is a terminal status that teaches nobody.
        """
        from feedback_archive import _DONE_STATUSES
        assert "acknowledged" in _DONE_STATUSES


class TestDigestOrdering:
    def test_a_non_defect_never_outranks_a_defect(self, capsys):
        """The digest sorts by severity alone, so a `medium` near-miss printed above a
        `medium` defect is a reviewer's attention spent on something with no fix. Rank
        every non-defect below every defect, whatever its severity."""
        from feedback_triage import cmd_digest

        rows = [
            {"fingerprint": "fp-a", "feedback_id": "fb-1", "item_id": "i1",
             "severity": "medium", "category": "near-miss", "layer": "workflow",
             "observation": "near miss", "location": {"file": "a.py"},
             "frequency": "first-time", "status": "open"},
            {"fingerprint": "fp-b", "feedback_id": "fb-2", "item_id": "i1",
             "severity": "medium", "category": "positive", "layer": "infra",
             "observation": "removed-step", "location": {"file": "b.py"},
             "frequency": "first-time", "status": "open"},
            {"fingerprint": "fp-c", "feedback_id": "fb-3", "item_id": "i1",
             "severity": "low", "category": "script-defect", "layer": "infra",
             "observation": "a real defect", "location": {"file": "c.py"},
             "frequency": "first-time", "status": "open"},
        ]
        cmd_digest(rows, as_json=True)
        entries = json.loads(capsys.readouterr().out)
        cats = [e["category"] for e in entries]
        assert cats[0] == "script-defect", (
            f"a low-severity defect must outrank a medium non-defect; got {cats}")
        assert set(cats[1:]) == {"near-miss", "positive"}, cats

    def test_defects_still_sort_critical_first_among_themselves(self, capsys):
        """The change must not cost the ordering that was already right."""
        from feedback_triage import cmd_digest

        rows = [
            {"fingerprint": "fp-a", "feedback_id": "fb-1", "item_id": "i1",
             "severity": "low", "category": "script-defect", "layer": "infra",
             "observation": "low one", "location": {"file": "a.py"},
             "frequency": "first-time", "status": "open"},
            {"fingerprint": "fp-b", "feedback_id": "fb-2", "item_id": "i1",
             "severity": "critical", "category": "script-defect", "layer": "infra",
             "observation": "critical one", "location": {"file": "b.py"},
             "frequency": "first-time", "status": "open"},
        ]
        cmd_digest(rows, as_json=True)
        entries = json.loads(capsys.readouterr().out)
        assert [e["severity"] for e in entries] == ["critical", "low"]
