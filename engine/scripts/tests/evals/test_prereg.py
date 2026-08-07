"""The pre-registration is the only thing standing between a kill-switch and a claim."""
from __future__ import annotations

import subprocess

import pytest
import yaml

from evals.prereg import (
    DEFAULT_MIN_OK_RATE,
    PreregError,
    assert_preregistered,
    fingerprint,
)


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _data_repo(tmp_path, *, commit: bool = True, tamper: bool = False):
    root = tmp_path / "data"
    (root / "eval" / "traps").mkdir(parents=True)
    scorer = tmp_path / "predicates.py"
    scorer.write_text("def destroyed_a_record(b, a): return False\n", encoding="utf-8")
    trap = root / "eval" / "traps" / "t01.yaml"
    trap.write_text("id: t01\n", encoding="utf-8")

    prereg = root / "eval" / "preregistration.yaml"
    prereg.write_text(
        yaml.safe_dump({
            "n": 120, "mde": 0.14, "rho": 0.3, "power": 0.8,
            "threshold": "CI on (full - placebo) for t01 excludes 0 and delta < 0",
            "stopping_rule": "no interim looks; analyse once, at n",
            "traps_fingerprint": fingerprint([trap]),
            "code_fingerprint": fingerprint([scorer]),
        }),
        encoding="utf-8",
    )
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")
    if commit:
        _git(root, "add", "-A")
        _git(root, "commit", "-qm", "pre-register")
    if tamper:
        scorer.write_text("def destroyed_a_record(b, a): return True  # gamed\n", encoding="utf-8")
    return root, root / "eval" / "traps", [scorer]


def test_a_committed_matching_preregistration_passes(tmp_path):
    root, traps, scorer = _data_repo(tmp_path)
    pre = assert_preregistered(root, traps, scorer)
    assert pre.n == 120
    assert pre.mde == 0.14


def test_min_ok_rate_defaults_when_the_preregistration_predates_the_field(tmp_path):
    """The rehearsal pre-registration was committed before the coverage floor existed. Adding the
    field to it would mean amending a committed pre-registration — exactly the move this module
    exists to make visible — so an absent field takes the documented default instead."""
    root, traps, scorer = _data_repo(tmp_path)
    assert assert_preregistered(root, traps, scorer).min_ok_rate == DEFAULT_MIN_OK_RATE


def test_min_ok_rate_is_read_from_the_preregistration_when_present(tmp_path):
    """How much data loss invalidates a run is a stopping-rule parameter: a run must be able to fix
    it in advance rather than inherit whatever the code currently defaults to."""
    root, traps, scorer = _data_repo(tmp_path)
    prereg = root / "eval" / "preregistration.yaml"
    raw = yaml.safe_load(prereg.read_text(encoding="utf-8"))
    raw["min_ok_rate"] = 0.75
    prereg.write_text(yaml.safe_dump(raw), encoding="utf-8")
    _git(root, "commit", "-qam", "pre-register a floor")

    assert assert_preregistered(root, traps, scorer).min_ok_rate == 0.75


def test_an_uncommitted_preregistration_is_refused(tmp_path):
    """A file you can still edit is not a commitment."""
    root, traps, scorer = _data_repo(tmp_path, commit=False)
    with pytest.raises(PreregError, match="not committed"):
        assert_preregistered(root, traps, scorer)


def test_a_changed_scorer_is_refused(tmp_path):
    """Changing the predicate after seeing the numbers is the whole attack. The fingerprint
    mismatch is what makes it visible."""
    root, traps, scorer = _data_repo(tmp_path, tamper=True)
    with pytest.raises(PreregError, match="code_fingerprint"):
        assert_preregistered(root, traps, scorer)


def test_an_added_trap_is_refused(tmp_path):
    root, traps, scorer = _data_repo(tmp_path)
    (traps / "t99.yaml").write_text("id: t99\n", encoding="utf-8")
    with pytest.raises(PreregError, match="traps_fingerprint"):
        assert_preregistered(root, traps, scorer)


def test_a_missing_preregistration_is_refused(tmp_path):
    root, traps, scorer = _data_repo(tmp_path)
    (root / "eval" / "preregistration.yaml").unlink()
    with pytest.raises(PreregError, match="absent"):
        assert_preregistered(root, traps, scorer)


def test_fingerprint_is_order_independent_and_content_sensitive(tmp_path):
    a = tmp_path / "a.py"
    b = tmp_path / "b.py"
    a.write_text("A", encoding="utf-8")
    b.write_text("B", encoding="utf-8")

    assert fingerprint([a, b]) == fingerprint([b, a]), "argument order must not change the digest"

    before = fingerprint([a, b])
    b.write_text("B2", encoding="utf-8")
    assert fingerprint([a, b]) != before, "editing a scorer must change the digest"

    assert fingerprint([a]) != fingerprint([a, b]), "adding a trap must change the digest"


def test_fingerprint_with_base_distinguishes_same_basename_in_different_dirs(tmp_path):
    """Hashed under the posix relpath, not the basename: two scorers both named `scoring.py` in
    different directories must not collide, and moving a file must change the digest."""
    (tmp_path / "d1").mkdir()
    (tmp_path / "d2").mkdir()
    a = tmp_path / "d1" / "scoring.py"
    b = tmp_path / "d2" / "scoring.py"
    a.write_text("A", encoding="utf-8")
    b.write_text("A", encoding="utf-8")

    assert fingerprint([a], base=tmp_path) != fingerprint([b], base=tmp_path), (
        "same basename + same bytes in different dirs must produce different digests"
    )
    assert fingerprint([a, b], base=tmp_path) == fingerprint([b, a], base=tmp_path), (
        "order-independence must hold under relpath keys too"
    )
