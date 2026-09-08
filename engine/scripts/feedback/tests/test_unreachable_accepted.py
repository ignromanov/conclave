"""test_unreachable_accepted.py — B2, closes GH#220.

`unreachable_accepted()` selects accepted items carrying no predicate, no waiver
and no issue link — reachable by no other mechanism, since `--monthly`'s zombie
pass scopes to status open/deferred only.
"""
from __future__ import annotations

from pathlib import Path

from feedback_triage import cmd_check, cmd_monthly, unreachable_accepted


def _row(item_id: str, status: str = "accepted", verify=None,
         verify_waiver=None, issue=None, accepted_at: str | None = None,
         updated_at: str = "2026-01-01T00:00:00Z") -> dict:
    return {
        "feedback_id": f"fb-{item_id}",
        "item_id": item_id,
        "status": status,
        "verify": verify,
        "verify_waiver": verify_waiver,
        "issue": issue,
        "accepted_at": accepted_at,
        "updated_at": updated_at,
        "observation": "obs",
    }


def test_selects_accepted_with_no_predicate_no_waiver_no_issue():
    """Of all eight (verify, waiver, issue) combinations, only the all-falsy one
    is selected — and only when status is accepted."""
    rows = []
    for i, verify in enumerate([None, {"predicate": "x"}]):
        for j, waiver in enumerate([None, "waived"]):
            for k, issue in enumerate([None, 42]):
                rows.append(_row(f"it-{i}{j}{k}", verify=verify,
                                  verify_waiver=waiver, issue=issue))
    # A non-accepted row with none of the three set must not be picked either.
    rows.append(_row("it-not-accepted", status="open"))

    found = unreachable_accepted(rows)
    assert [r["item_id"] for r in found] == ["it-000"]


def test_a_waivered_item_is_not_unreachable():
    rows = [_row("it-waived", verify=None, verify_waiver="operator waived", issue=None)]
    assert unreachable_accepted(rows) == []


def test_an_issue_linked_item_is_not_unreachable():
    rows = [_row("it-linked", verify=None, verify_waiver=None, issue=99)]
    assert unreachable_accepted(rows) == []


def test_age_comes_from_accepted_at_not_updated_at(capsys):
    """Two rows share one updated_at, differ by 20 days of accepted_at — the
    rendered ages must differ. Fails on any implementation keying on updated_at."""
    rows = [
        _row("it-old", accepted_at="2025-01-01T00:00:00Z",
             updated_at="2026-01-01T00:00:00Z"),
        _row("it-new", accepted_at="2025-01-21T00:00:00Z",
             updated_at="2026-01-01T00:00:00Z"),
    ]
    cmd_monthly(rows)
    out = capsys.readouterr().out
    section = out.split("Unreachable accepted items", 1)[1]
    old_line = [ln for ln in section.splitlines() if "it-old" in ln][0]
    new_line = [ln for ln in section.splitlines() if "it-new" in ln][0]
    old_age = int(old_line.split()[2])
    new_age = int(new_line.split()[2])
    assert old_age != new_age
    assert old_age > new_age


def test_no_age_cutoff_on_the_unreachable_section(capsys):
    """All-recent rows (3 and 10 days old) must all be listed — no 90-day cutoff
    carried over from the open/deferred pass."""
    from datetime import UTC, datetime, timedelta
    now = datetime.now(UTC)
    recent1 = (now - timedelta(days=3)).isoformat().replace("+00:00", "Z")
    recent2 = (now - timedelta(days=10)).isoformat().replace("+00:00", "Z")
    rows = [
        _row("it-recent1", accepted_at=recent1),
        _row("it-recent2", accepted_at=recent2),
    ]
    cmd_monthly(rows)
    out = capsys.readouterr().out
    assert "it-recent1" in out
    assert "it-recent2" in out


def test_unreachable_rows_are_sorted_oldest_first(capsys):
    rows = [
        _row("it-middle", accepted_at="2026-01-15T00:00:00Z"),
        _row("it-oldest", accepted_at="2026-01-01T00:00:00Z"),
        _row("it-newest", accepted_at="2026-01-31T00:00:00Z"),
    ]
    cmd_monthly(rows)
    out = capsys.readouterr().out
    section = out.split("Unreachable accepted items", 1)[1]
    assert section.find("it-oldest") < section.find("it-middle") < section.find("it-newest")


def test_missing_accepted_at_renders_dash_not_zero(capsys):
    rows = [_row("it-no-date", accepted_at=None)]
    cmd_monthly(rows)
    out = capsys.readouterr().out
    section = out.split("Unreachable accepted items", 1)[1]
    line = [ln for ln in section.splitlines() if "it-no-date" in ln][0]
    assert "—" in line
    # Age column must not read as a bare 0.
    cols = line.split()
    age_col = cols[2]
    assert age_col == "—", f"expected dash, got {age_col!r}"


def test_zero_unreachable_still_prints_the_heading(capsys):
    rows = [_row("it-fine", status="open")]
    cmd_monthly(rows)
    out = capsys.readouterr().out
    assert "Unreachable accepted items (no predicate, no waiver, no issue link): 0" in out


def test_check_emits_unreachable_accepted_key(tmp_path: Path, capsys):
    rows = [
        _row("it-unreachable", accepted_at="2026-01-01T00:00:00Z"),
        _row("it-reachable", issue=1, accepted_at="2026-01-02T00:00:00Z"),
    ]
    marker = tmp_path / "last-triage"
    cmd_check(rows, marker)
    out = capsys.readouterr().out
    assert "unreachable_accepted=1" in out
