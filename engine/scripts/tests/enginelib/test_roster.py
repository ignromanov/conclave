"""tests/enginelib/test_roster.py — ports roster-loader.bats (3 cases + missing-file).

Baseline bats bug: ROSTER_FILE pointed at engine/scripts/roster.yaml (doesn't exist),
so cases 1 and 2 were always failing. These tests fix that by setting ROSTER_FILE to
a tmp_path fixture with the intended content, making all 3 assertions genuinely green.
"""
from pathlib import Path

import pytest

from enginelib.roster import roster_get, roster_get_list

FIXTURE_YAML = """\
github:
  owner: ignromanov
  board_number: 3
"""


@pytest.fixture()
def roster_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    f = tmp_path / "roster.yaml"
    f.write_text(FIXTURE_YAML)
    monkeypatch.setenv("ROSTER_FILE", str(f))
    monkeypatch.delenv("CONCLAVE_AI_ROOT", raising=False)
    monkeypatch.delenv("VOIDPAY_AI_ROOT", raising=False)
    return f


def test_roster_get_owner(roster_file):
    """Ports bats case 1: github.owner → 'ignromanov'."""
    assert roster_get("github.owner") == "ignromanov"


def test_roster_get_board_number_as_string(roster_file):
    """Ports bats case 2: github.board_number → '3' (STRING, not int)."""
    assert roster_get("github.board_number") == "3"


def test_roster_get_missing_key(roster_file):
    """Ports bats case 3: missing key → '' (empty string), no error."""
    assert roster_get("github.nonexistent") == ""


def test_roster_get_missing_file(tmp_path, monkeypatch):
    """Extra case: missing roster file entirely → '' (no error)."""
    monkeypatch.setenv("ROSTER_FILE", str(tmp_path / "does_not_exist.yaml"))
    monkeypatch.delenv("CONCLAVE_AI_ROOT", raising=False)
    monkeypatch.delenv("VOIDPAY_AI_ROOT", raising=False)
    assert roster_get("github.owner") == ""


def test_roster_get_list_returns_yaml_list(tmp_path, monkeypatch):
    """A YAML list value → list of its string items (#7 sticky_labels)."""
    f = tmp_path / "roster.yaml"
    f.write_text("github:\n  sticky_labels: [grant, bounty]\n")
    monkeypatch.setenv("ROSTER_FILE", str(f))
    monkeypatch.delenv("CONCLAVE_AI_ROOT", raising=False)
    monkeypatch.delenv("VOIDPAY_AI_ROOT", raising=False)
    assert roster_get_list("github.sticky_labels") == ["grant", "bounty"]


def test_roster_get_list_missing_key_returns_empty(roster_file):
    """Absent key → [] (no error), the domain-agnostic engine default."""
    assert roster_get_list("github.sticky_labels") == []
