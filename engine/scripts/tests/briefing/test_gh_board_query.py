"""Tests for lifecycle/gh-board-query.py — GitHub project board query helper."""
from __future__ import annotations

import json
from io import StringIO

import gh_board_query
import pytest

# ---------------------------------------------------------------------------
# Sample board data
# ---------------------------------------------------------------------------

_ITEMS_WITH_DATA = [
    {
        "title": "Spec 084 briefing modernization",
        "status": "In Progress",
        "advisor": "kai",
        "priority": "p1",
        "type": "agent-infra",
        "content": {"repository": "voidpay-ai", "number": 140, "title": "Spec 084 briefing modernization"},
    },
    {
        "title": "Spec 056 codec Phase 3",
        "status": "Todo",
        "advisor": "kai",
        "priority": "p1",
        "type": "feature",
        "content": {"repository": "voidpay-ai", "number": 155, "title": "Spec 056 codec Phase 3"},
    },
    {
        "title": "Onboarding kit",
        "status": "Done",
        "advisor": "nexus",
        "priority": "p2",
        "type": "growth",
        "content": {"repository": "voidpay", "number": 39, "title": "Onboarding kit"},
    },
    {
        "title": "Missing field item",
        "status": "Todo",
        "advisor": "",
        "priority": "",
        "type": "feature",
        # missing status field at top-level (overriding below)
        "content": {"repository": "voidpay", "number": 99, "title": "Missing field item"},
    },
]

_ITEMS_COMPLETE = [
    {
        "title": "All fields present",
        "status": "In Progress",
        "advisor": "kai",
        "priority": "p1",
        "type": "feature",
        "content": {"repository": "voidpay-ai", "number": 1, "title": "All fields present"},
    },
]


# ---------------------------------------------------------------------------
# mode_advisor_open
# ---------------------------------------------------------------------------

class TestAdvisorOpen:
    def test_filters_done(self, capsys):
        items = [i for i in _ITEMS_WITH_DATA]
        gh_board_query.mode_advisor_open(items, "kai-cto")
        out = capsys.readouterr().out
        # "Onboarding kit" is Done — should be excluded
        assert "Onboarding kit" not in out

    def test_filters_by_advisor_stem(self, capsys):
        gh_board_query.mode_advisor_open(_ITEMS_WITH_DATA, "kai-cto")
        out = capsys.readouterr().out
        assert "Spec 084" in out
        assert "Spec 056" in out

    def test_nexus_items_not_in_kai_query(self, capsys):
        gh_board_query.mode_advisor_open(_ITEMS_WITH_DATA, "nexus-ceo")
        out = capsys.readouterr().out
        # nexus item is Done → excluded
        assert "Onboarding kit" not in out

    def test_empty_list_prints_none_message(self, capsys):
        gh_board_query.mode_advisor_open([], "kai-cto")
        out = capsys.readouterr().out
        assert "no open items" in out

    def test_output_format_contains_repo_num_status_title(self, capsys):
        gh_board_query.mode_advisor_open(_ITEMS_WITH_DATA, "kai-cto")
        out = capsys.readouterr().out
        # Should contain repo#number [status] title format
        assert "voidpay-ai#140" in out
        assert "[In Progress]" in out


# ---------------------------------------------------------------------------
# mode_missing_fields
# ---------------------------------------------------------------------------

class TestMissingFields:
    def test_detects_missing_advisor_and_priority(self, capsys):
        gh_board_query.mode_missing_fields(_ITEMS_WITH_DATA)
        out = capsys.readouterr().out
        assert "Missing field item" in out
        assert "advisor" in out
        assert "priority" in out

    def test_complete_item_not_flagged(self, capsys):
        gh_board_query.mode_missing_fields(_ITEMS_COMPLETE)
        out = capsys.readouterr().out
        assert "all items have required fields" in out.lower()

    def test_title_truncated_to_55(self, capsys):
        items = [{"title": "A" * 100, "status": "Todo", "advisor": "", "priority": "", "type": "", "content": {}}]
        gh_board_query.mode_missing_fields(items)
        out = capsys.readouterr().out
        # Title column is exactly 55 chars
        line = [ln for ln in out.splitlines() if "MISSING" in ln][0]
        title_part = line[:55]
        assert len(title_part) == 55

    def test_empty_list_prints_clean_message(self, capsys):
        gh_board_query.mode_missing_fields([])
        out = capsys.readouterr().out
        assert "all items have required fields" in out.lower()


# ---------------------------------------------------------------------------
# _advisor_label_stem
# ---------------------------------------------------------------------------

class TestAdvisorLabelStem:
    def test_strips_role_suffix(self):
        assert gh_board_query._advisor_label_stem("kai-cto") == "kai"
        assert gh_board_query._advisor_label_stem("nexus-ceo") == "nexus"
        assert gh_board_query._advisor_label_stem("spark-cmo") == "spark"
        assert gh_board_query._advisor_label_stem("shade-ciso") == "shade"

    def test_quorum_unchanged(self):
        assert gh_board_query._advisor_label_stem("quorum") == "quorum"


# ---------------------------------------------------------------------------
# _load_items — stdin path
# ---------------------------------------------------------------------------

class TestLoadItems:
    def test_loads_list_directly(self, monkeypatch):
        data = json.dumps(_ITEMS_COMPLETE)
        monkeypatch.setattr("sys.stdin", StringIO(data))
        items = gh_board_query._load_items(fetch=False)
        assert len(items) == 1

    def test_loads_items_key(self, monkeypatch):
        data = json.dumps({"items": _ITEMS_COMPLETE})
        monkeypatch.setattr("sys.stdin", StringIO(data))
        items = gh_board_query._load_items(fetch=False)
        assert len(items) == 1

    def test_invalid_json_raises(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", StringIO("not json"))
        with pytest.raises(RuntimeError, match="not valid JSON"):
            gh_board_query._load_items(fetch=False)


# ---------------------------------------------------------------------------
# CLI arg validation
# ---------------------------------------------------------------------------

class TestMainArgValidation:
    def test_unknown_advisor_exits_1(self, tmp_path, monkeypatch):
        # Non-empty registry (one real advisor) → an id absent from it is rejected.
        (tmp_path / ".claude" / "skills" / "team.kai-cto").mkdir(parents=True)
        monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
        rc = gh_board_query.main(["--mode", "advisor-open", "--advisor", "ghost-xyz"])
        assert rc == 1

    def test_empty_registry_is_permissive(self, tmp_path, monkeypatch):
        # No registry on the DATA root → degrade to permissive (no enforcement),
        # consistent with the roster's "degrade to empty, not error" contract.
        monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
        monkeypatch.setattr("sys.stdin", StringIO("[]"))
        rc = gh_board_query.main(["--mode", "advisor-open", "--advisor", "engineering-data"])
        assert rc == 0

    def test_missing_advisor_for_advisor_open_exits_1(self, capsys):
        rc = gh_board_query.main(["--mode", "advisor-open"])
        assert rc == 1

    def test_unknown_mode_exits(self):
        with pytest.raises(SystemExit):
            gh_board_query.main(["--mode", "nonexistent"])

    def test_missing_fields_stdin(self, monkeypatch, capsys):
        data = json.dumps({"items": _ITEMS_COMPLETE})
        monkeypatch.setattr("sys.stdin", StringIO(data))
        rc = gh_board_query.main(["--mode", "missing-fields"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "all items have required fields" in out.lower()

    def test_advisor_open_stdin(self, monkeypatch, capsys):
        # main() validates --advisor against the on-disk registry; seed it
        # hermetically so the test doesn't depend on the live instance roster.
        monkeypatch.setattr(gh_board_query, "canonical_advisors", lambda: {"kai-cto"})
        data = json.dumps({"items": _ITEMS_WITH_DATA})
        monkeypatch.setattr("sys.stdin", StringIO(data))
        rc = gh_board_query.main(["--mode", "advisor-open", "--advisor", "kai-cto"])
        assert rc == 0
