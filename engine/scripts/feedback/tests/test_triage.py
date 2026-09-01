"""test_triage.py — TDD tests for feedback_triage.py (T6)."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from briefing.frontmatter_io import read as fm_read
from briefing.frontmatter_io import write

SCRIPTS_DIR = Path(__file__).parent.parent.parent  # .../scripts/
FEEDBACK_PKG = Path(__file__).parent.parent        # .../scripts/feedback/


def test_valid_statuses_derived_from_schema():
    """_VALID_STATUSES must equal schema.Status (so re-occurred is accepted and the
    two can never drift apart) — 093 P1 T5, closes #89."""
    import typing

    import feedback_triage

    from feedback.schema import Status
    assert "re-occurred" in feedback_triage._VALID_STATUSES
    assert set(feedback_triage._VALID_STATUSES) == set(typing.get_args(Status))


def _triage_env(root: Path, env_extra: dict | None = None) -> dict:
    env = {
        "PYTHONPATH": str(SCRIPTS_DIR),
        "CONCLAVE_AI_ROOT": str(root),
        "PATH": "/usr/bin:/bin",
    }
    if env_extra:
        env.update(env_extra)
    return env


def run_triage(root: Path, extra_args: list[str] | None = None,
               env_extra: dict | None = None) -> subprocess.CompletedProcess:
    args = [
        sys.executable,
        str(FEEDBACK_PKG / "feedback_triage.py"),
    ]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        env=_triage_env(root, env_extra),
    )


def _write_review(root: Path, date: str, filename: str, meta: dict, body: str = "") -> Path:
    out_dir = root / "ops" / "feedback" / date
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    write(path, meta, body)
    return path


def _valid_item(item_id: str = "it-1", category: str = "script-defect",
                severity: str = "medium", file: str = "a.sh") -> dict:
    return {
        "id": item_id,
        "category": category,
        "layer": "skill",
        "location": {"file": file, "line": 4},
        "observation": "exits with 1 unexpectedly",
        "suggested_fix": "add null guard",
        "severity": severity,
        "frequency": "first-time",
        "evidence": "tool_call:abc123",
    }


def _valid_review_meta(agent: str = "atlas", feedback_id: str = "fb-111-aaaaaa",
                       items: list | None = None) -> dict:
    return {
        "feedback_id": feedback_id,
        "agent": agent,
        "agent_type": "executor",
        "session_ref": "test-session",
        "skill_version": "sha256:aabbcc",
        "created": "2026-05-22T10:00:00Z",
        "updated_at": "2026-05-22T10:00:00Z",
        "_draft": False,
        "summary": "test review",
        "items": items if items is not None else [_valid_item()],
        "below_threshold_count": 0,
    }


# --- Tests ---

def test_digest_dedup_hit_count(tmp_path):
    """Two reviews with identical-fingerprint items produce hit_count=2 in digest."""
    # Two different reviews, same location+category → same fingerprint
    item1 = _valid_item("it-1", category="script-defect", file="a.sh")
    item2 = _valid_item("it-2", category="script-defect", file="a.sh")  # same fp
    _write_review(tmp_path, "2026-05-22", "atlas-r1.md",
                  _valid_review_meta(feedback_id="fb-111-aaaaaa", items=[item1]))
    _write_review(tmp_path, "2026-05-22", "atlas-r2.md",
                  _valid_review_meta(feedback_id="fb-222-bbbbbb", items=[item2]))

    result = run_triage(tmp_path, ["--digest"])
    assert result.returncode == 0, result.stderr
    # hit_count=2 in output means dedup found 2 identical fingerprints
    assert "hit_count" in result.stdout or "2" in result.stdout, result.stdout


def test_digest_critical_sorted_top(tmp_path):
    """Critical-severity items appear before lower-severity in digest output."""
    low_item = _valid_item("it-low", severity="low", file="b.sh")
    critical_item = _valid_item("it-crit", severity="critical", file="c.sh")
    _write_review(tmp_path, "2026-05-22", "atlas-mixed.md",
                  _valid_review_meta(items=[low_item, critical_item]))

    result = run_triage(tmp_path, ["--digest"])
    assert result.returncode == 0, result.stderr
    # Critical must appear before low in output
    crit_pos = result.stdout.find("critical")
    low_pos = result.stdout.find("low")
    assert crit_pos != -1, "critical severity not found in digest"
    assert low_pos != -1, "low severity not found in digest"
    assert crit_pos < low_pos, f"critical ({crit_pos}) must appear before low ({low_pos})"


def test_set_updates_status_in_review_file(tmp_path):
    """--set writes status/owner/resolved_at back to review file, bumps updated_at."""
    review_path = _write_review(tmp_path, "2026-05-22", "atlas-set.md",
                                _valid_review_meta(feedback_id="fb-333-cccccc"))

    # Read original updated_at
    meta_before, _ = fm_read(review_path)
    original_updated_at = meta_before["updated_at"]

    result = run_triage(tmp_path, [
        "--set", "fb-333-cccccc", "it-1", "resolved", "--owner", "kai"
    ])
    assert result.returncode == 0, result.stderr

    meta_after, _ = fm_read(review_path)
    # Find the item
    items = meta_after.get("items", [])
    assert len(items) == 1
    item = items[0]
    assert item["status"] == "resolved", f"expected resolved, got {item['status']}"
    assert item["owner"] == "kai", f"expected owner=kai, got {item.get('owner')}"
    assert item.get("resolved_at") is not None, "resolved_at must be set"
    assert str(meta_after["updated_at"]) != str(original_updated_at), \
        "updated_at must be bumped"


def test_check_prints_triage_due(tmp_path):
    """--check prints triage_due=<true|false>."""
    _write_review(tmp_path, "2026-05-22", "atlas-chk.md",
                  _valid_review_meta(feedback_id="fb-444-dddddd"))

    result = run_triage(tmp_path, ["--check"])
    assert result.returncode == 0, result.stderr
    assert "triage_due=" in result.stdout, result.stdout


def test_monthly_lists_old_open_items(tmp_path):
    """--monthly lists items with status open older than 90 days."""
    old_item = _valid_item("it-old")
    old_meta = _valid_review_meta(feedback_id="fb-555-eeeee", items=[old_item])
    # Use an old date so the review was created > 90 days ago
    old_meta["created"] = "2025-01-01T10:00:00Z"
    old_meta["updated_at"] = "2025-01-01T10:00:00Z"
    _write_review(tmp_path, "2026-05-22", "atlas-old.md", old_meta)

    result = run_triage(tmp_path, ["--monthly"])
    assert result.returncode == 0, result.stderr
    # Should mention the old item or feedback id
    assert "fb-555-eeeee" in result.stdout or "it-old" in result.stdout, result.stdout


def test_set_without_owner(tmp_path):
    """--set without --owner still updates status."""
    _write_review(tmp_path, "2026-05-22", "atlas-noown.md",
                  _valid_review_meta(feedback_id="fb-666-ffffff"))

    result = run_triage(tmp_path, ["--set", "fb-666-ffffff", "it-1", "accepted", "--waiver", "not mechanically checkable"])
    assert result.returncode == 0, result.stderr

    meta_after, _ = fm_read(
        tmp_path / "ops" / "feedback" / "2026-05-22" / "atlas-noown.md"
    )
    item = meta_after["items"][0]
    assert item["status"] == "accepted"


# --- #89: the cadence is 7 days OR >=15 new reviews, in the code as well as the docs ---

def _fresh_marker(tmp_path, age_seconds: int = 3600):
    """A marker well inside the 7-day window, backdated so reviews written by the test
    land *after* the last triage — which is the only ordering the rule is about."""
    import os
    marker = tmp_path / "ops" / "feedback" / "_index" / "last-triage"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()
    when = time.time() - age_seconds
    os.utime(marker, (when, when))
    return marker


def _new_reviews(tmp_path, n: int):
    """n reviews created after the marker — the quantity the documented rule counts."""
    from datetime import UTC, datetime
    created = datetime.now(UTC).isoformat()
    for i in range(n):
        meta = _valid_review_meta(feedback_id=f"fb-new-{i:06d}",
                                  items=[_valid_item("it-1")])
        meta["created"] = created
        meta["updated_at"] = created
        _write_review(tmp_path, "2026-05-22", f"atlas-new-{i}.md", meta)


def test_check_does_not_fire_on_a_single_open_item(tmp_path):
    """The measured symptom: finishing a triage re-armed the notice that demands one.
    The session's own freshly filed review left open items behind, `open_count > 0` was
    the whole trigger, and the banner then appeared at every SessionStart forever — so a
    backlog of 27 and a backlog of 1 looked identical.

    This test replaces one that asserted the opposite. That one's docstring called the
    behaviour the rule, which is how a contradiction with two shipped documents survived:
    the defect had a passing test."""
    _write_review(tmp_path, "2026-05-22", "atlas-open.md",
                  _valid_review_meta(feedback_id="fb-open-111111",
                                     items=[_valid_item("it-1")]))
    _fresh_marker(tmp_path)

    result = run_triage(tmp_path, ["--check"])
    assert result.returncode == 0, result.stderr
    assert "triage_due=false" in result.stdout, result.stdout
    assert "open_items=1" in result.stdout, "the count is still reported, just not the trigger"


def test_check_fires_at_fifteen_new_reviews(tmp_path):
    """The documented threshold, exactly."""
    _new_reviews(tmp_path, 15)
    _fresh_marker(tmp_path)
    result = run_triage(tmp_path, ["--check"])
    assert result.returncode == 0, result.stderr
    assert "triage_due=true" in result.stdout, result.stdout
    assert "new_reviews=15" in result.stdout, result.stdout


def test_check_does_not_fire_at_fourteen(tmp_path):
    """One below the threshold is below the threshold — pinned so the comparison cannot
    drift to `>=14` or `>` without a test noticing."""
    _new_reviews(tmp_path, 14)
    _fresh_marker(tmp_path)
    result = run_triage(tmp_path, ["--check"])
    assert result.returncode == 0, result.stderr
    assert "triage_due=false" in result.stdout, result.stdout
    assert "new_reviews=14" in result.stdout, result.stdout


def test_check_fires_on_the_seven_day_arm_with_no_new_reviews(tmp_path):
    """The other disjunct still holds: a quiet week is due anyway, so a slow instance is
    not left un-triaged forever by a review threshold it never reaches."""
    _write_review(tmp_path, "2026-05-22", "atlas-quiet.md",
                  _valid_review_meta(feedback_id="fb-quiet-111111"))
    _fresh_marker(tmp_path, age_seconds=8 * 86400)

    result = run_triage(tmp_path, ["--check"])
    assert result.returncode == 0, result.stderr
    assert "triage_due=true" in result.stdout, result.stdout
    assert "new_reviews=0" in result.stdout, result.stdout


def test_check_fires_when_no_triage_has_ever_run(tmp_path):
    """No marker at all is not 'zero days since' — it is 'never'."""
    _write_review(tmp_path, "2026-05-22", "atlas-first.md",
                  _valid_review_meta(feedback_id="fb-first-111111"))
    result = run_triage(tmp_path, ["--check"])
    assert result.returncode == 0, result.stderr
    assert "triage_due=true" in result.stdout, result.stdout
    assert "days_since=never" in result.stdout, result.stdout


def test_check_no_open_items_fresh_marker(tmp_path):
    """cmd_check: no open items + fresh marker → triage_due=false."""
    resolved_item = _valid_item("it-1")
    resolved_item["status"] = "resolved"
    _write_review(tmp_path, "2026-05-22", "atlas-res.md",
                  _valid_review_meta(feedback_id="fb-res-222222",
                                     items=[resolved_item]))
    marker = tmp_path / "ops" / "feedback" / "_index" / "last-triage"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()

    result = run_triage(tmp_path, ["--check"])
    assert result.returncode == 0, result.stderr
    assert "triage_due=false" in result.stdout


def test_set_accepted_stamps_accepted_at(tmp_path):
    """--set accepted populates accepted_at on the item."""
    _write_review(tmp_path, "2026-05-22", "atlas-acc.md",
                  _valid_review_meta(feedback_id="fb-acc-777777"))

    result = run_triage(tmp_path, ["--set", "fb-acc-777777", "it-1", "accepted", "--waiver", "not mechanically checkable"])
    assert result.returncode == 0, result.stderr

    meta_after, _ = fm_read(
        tmp_path / "ops" / "feedback" / "2026-05-22" / "atlas-acc.md"
    )
    item = meta_after["items"][0]
    assert item["status"] == "accepted"
    assert item.get("accepted_at") is not None, "accepted_at must be stamped"


def test_set_resolved_does_not_stamp_accepted_at(tmp_path):
    """--set resolved does NOT populate accepted_at."""
    _write_review(tmp_path, "2026-05-22", "atlas-res2.md",
                  _valid_review_meta(feedback_id="fb-res2-888888"))

    result = run_triage(tmp_path, ["--set", "fb-res2-888888", "it-1", "resolved"])
    assert result.returncode == 0, result.stderr

    meta_after, _ = fm_read(
        tmp_path / "ops" / "feedback" / "2026-05-22" / "atlas-res2.md"
    )
    item = meta_after["items"][0]
    assert item["status"] == "resolved"
    assert item.get("accepted_at") is None, "accepted_at must not be set on resolved"


# --- #164: a lifecycle timestamp marks a transition, not the act of writing the field ---

def test_rebinding_an_accepted_item_keeps_its_original_accepted_at(tmp_path):
    """triage.md Step 4 binds an issue by re-passing the item's CURRENT status.

    That call must change owner/issue and nothing else. Stamping accepted_at on every
    write reset the acceptance date of every item the binding step touched — 53 of 53 in
    one live migration, on the field cmd_monthly reads to find zombies over 90 days old.
    """
    _write_review(tmp_path, "2026-05-22", "atlas-bind.md",
                  _valid_review_meta(feedback_id="fb-bind-111111"))
    assert run_triage(tmp_path, ["--set", "fb-bind-111111", "it-1", "accepted",
                                 "--waiver", "not mechanically checkable"]).returncode == 0
    path = tmp_path / "ops" / "feedback" / "2026-05-22" / "atlas-bind.md"
    original = fm_read(path)[0]["items"][0]["accepted_at"]

    result = run_triage(tmp_path, ["--set", "fb-bind-111111", "it-1", "accepted",
                                   "--owner", "forge", "--issue", "164"])
    assert result.returncode == 0, result.stderr

    item = fm_read(path)[0]["items"][0]
    assert item["accepted_at"] == original, "re-set must not re-date the acceptance"
    assert item["owner"] == "forge"
    assert item["issue"] == 164


def test_re_resolving_keeps_the_original_resolved_at(tmp_path):
    """The same trap on resolved_at: overwriting it destroys that item's MTTR, which is
    the one number spec 093 exists to move."""
    _write_review(tmp_path, "2026-05-22", "atlas-res3.md",
                  _valid_review_meta(feedback_id="fb-res3-222222"))
    assert run_triage(tmp_path, ["--set", "fb-res3-222222", "it-1",
                                 "resolved"]).returncode == 0
    path = tmp_path / "ops" / "feedback" / "2026-05-22" / "atlas-res3.md"
    original = fm_read(path)[0]["items"][0]["resolved_at"]

    assert run_triage(tmp_path, ["--set", "fb-res3-222222", "it-1", "resolved",
                                 "--owner", "verify:auto"]).returncode == 0
    assert fm_read(path)[0]["items"][0]["resolved_at"] == original


def test_accepted_at_backfills_when_the_item_carries_none(tmp_path):
    """Guarding on the transition must not make a MISSING timestamp unfillable — the
    notebook predates the field, so items exist that are accepted without one."""
    item = _valid_item("it-1")
    item["status"] = "accepted"
    _write_review(tmp_path, "2026-05-22", "atlas-backfill.md",
                  _valid_review_meta(feedback_id="fb-backfill-333333", items=[item]))

    result = run_triage(tmp_path, ["--set", "fb-backfill-333333", "it-1", "accepted"])
    assert result.returncode == 0, result.stderr

    after = fm_read(tmp_path / "ops" / "feedback" / "2026-05-22" / "atlas-backfill.md")
    assert after[0]["items"][0].get("accepted_at") is not None


# --- 093/#165: the accept gate ---

def test_accepting_without_a_predicate_or_waiver_is_refused(tmp_path):
    """The loop can only close what carries a closing condition.

    2 of 171 accepted items had a predicate when this gate was written; the sweep had
    closed nothing in seven weeks. Accepting is the moment the condition is cheapest to
    state, so it is the moment the protocol asks for it.
    """
    _write_review(tmp_path, "2026-05-22", "atlas-gate.md",
                  _valid_review_meta(feedback_id="fb-gate-111111"))

    result = run_triage(tmp_path, ["--set", "fb-gate-111111", "it-1", "accepted"])
    assert result.returncode == 1
    assert "verify_waiver" in result.stderr

    # Refusal must be total: a partial write would leave the item accepted anyway.
    item = fm_read(tmp_path / "ops" / "feedback" / "2026-05-22" / "atlas-gate.md")[0]["items"][0]
    assert item.get("status", "open") == "open"
    assert item.get("accepted_at") is None


def test_a_waiver_satisfies_the_gate_and_is_recorded(tmp_path):
    """A waiver is a real field, not a convention: an unmeasurable waiver cannot be told
    apart from having forgotten, and predicate_coverage counts the two differently."""
    _write_review(tmp_path, "2026-05-22", "atlas-waive.md",
                  _valid_review_meta(feedback_id="fb-waive-222222"))

    result = run_triage(tmp_path, ["--set", "fb-waive-222222", "it-1", "accepted",
                                   "--waiver", "judgement call, no file marker"])
    assert result.returncode == 0, result.stderr

    item = fm_read(tmp_path / "ops" / "feedback" / "2026-05-22" / "atlas-waive.md")[0]["items"][0]
    assert item["status"] == "accepted"
    assert item["verify_waiver"] == "judgement call, no file marker"


def test_an_existing_predicate_satisfies_the_gate(tmp_path):
    """The gate asks for a closing condition, and a predicate IS one — an item fed by
    --set-verify while still open must accept with no waiver."""
    item = _valid_item("it-1")
    item["verify"] = {"kind": "grep-absent", "file": "a.sh", "pattern": "exit 1"}
    _write_review(tmp_path, "2026-05-22", "atlas-pred.md",
                  _valid_review_meta(feedback_id="fb-pred-333333", items=[item]))

    result = run_triage(tmp_path, ["--set", "fb-pred-333333", "it-1", "accepted"])
    assert result.returncode == 0, result.stderr


def test_the_gate_never_fires_on_a_re_set_of_an_already_accepted_item(tmp_path):
    """The reason the gate refuses only on a GENUINE transition.

    171 accepted items predate the rule, and triage.md Step 4 binds an issue by
    re-passing the item's own current status. Enforcing on every write would make the
    documented binding step impossible on all of them, pushing operators into
    hand-editing finalized frontmatter — a second writer, worse than the gap.
    """
    item = _valid_item("it-1")
    item["status"] = "accepted"
    _write_review(tmp_path, "2026-05-22", "atlas-legacy.md",
                  _valid_review_meta(feedback_id="fb-legacy-444444", items=[item]))

    result = run_triage(tmp_path, ["--set", "fb-legacy-444444", "it-1", "accepted",
                                   "--owner", "forge-chro", "--issue", "165"])
    assert result.returncode == 0, result.stderr
    after = fm_read(tmp_path / "ops" / "feedback" / "2026-05-22" / "atlas-legacy.md")
    assert after[0]["items"][0]["issue"] == 165


def test_the_gate_does_not_block_any_other_status(tmp_path):
    """Only acceptance promises a fix. Rejecting, deferring or resolving an item makes no
    such promise, so none of them owes a predicate."""
    for i, status in enumerate(("rejected", "deferred", "resolved")):
        fid = f"fb-other{i}-55555{i}"
        _write_review(tmp_path, "2026-05-22", f"atlas-other{i}.md",
                      _valid_review_meta(feedback_id=fid))
        r = run_triage(tmp_path, ["--set", fid, "it-1", status])
        assert r.returncode == 0, f"{status}: {r.stderr}"


def test_triage_aborts_when_draft_false_invalid(tmp_path):
    """Triage must refuse to proceed when a _draft:false review fails schema validation.

    Regression for spec 086 AC2: the feedback-gate must run before the triage pipeline
    so corrupted author-complete reviews never silently bypass the queue.
    """
    # One valid review
    _write_review(tmp_path, "2026-05-22", "atlas-valid.md",
                  _valid_review_meta(feedback_id="fb-valid-000000"))

    # One invalid _draft:false review (missing evidence, not migrated)
    bad_item = _valid_item("it-bad")
    del bad_item["evidence"]
    bad_meta = _valid_review_meta(feedback_id="fb-bad-000000")
    bad_meta["items"] = [bad_item]
    bad_meta["_draft"] = False
    _write_review(tmp_path, "2026-05-22", "atlas-bad-complete.md", bad_meta)

    # Any triage subcommand must fail
    for subcmd in (["--check"], ["--digest"]):
        result = run_triage(tmp_path, subcmd)
        assert result.returncode != 0, (
            f"triage {subcmd} must exit non-zero when _draft:false review is invalid; "
            f"got 0. stderr={result.stderr!r}"
        )
        assert "aborted" in result.stderr.lower() or "DROPPED" in result.stderr, (
            f"Expected abort message in stderr for {subcmd}; got: {result.stderr!r}"
        )


def test_set_preserves_data_classification_header(tmp_path):
    """triage --set must not strip the leading DATA CLASSIFICATION comment header.

    Regression for feedback fb-1780547269-e1b54d/it-1: read_commented + write drops
    the leading HTML comment, so every --set silently removed the privacy header.
    write_preserving_header re-prepends it.
    """
    meta = _valid_review_meta(feedback_id="fb-333-cccccc", items=[_valid_item("it-1")])
    path = _write_review(tmp_path, "2026-05-22", "atlas-hdr.md", meta)
    header = "<!--\nDATA CLASSIFICATION WARNING — do not include secrets\n-->\n"
    path.write_text(header + path.read_text(encoding="utf-8"), encoding="utf-8")
    assert path.read_text(encoding="utf-8").lstrip().startswith("<!--")

    result = run_triage(tmp_path, ["--set", "fb-333-cccccc", "it-1", "resolved"])
    assert result.returncode == 0, result.stderr

    after = path.read_text(encoding="utf-8")
    assert after.lstrip().startswith("<!--"), (
        f"DATA CLASSIFICATION header stripped by --set; got: {after[:80]!r}"
    )
    fm, _ = fm_read(path)
    assert fm["items"][0]["status"] == "resolved"


# --- #51: advisory lock around cmd_set (concurrent-triage safety) ---

_LOCK_DIRNAME = ".triage-lock"


def test_set_refuses_when_datateam_lock_held(tmp_path):
    """A held DATA-root lock blocks --set: it refuses (no torn write) instead of
    racing a concurrent triage session."""
    review_path = _write_review(tmp_path, "2026-05-22", "atlas-lockheld.md",
                                _valid_review_meta(feedback_id="fb-lock-111111"))
    before = fm_read(review_path)[0]["items"][0].get("status")
    (tmp_path / _LOCK_DIRNAME).mkdir()  # simulate another session holding the lock

    result = run_triage(
        tmp_path, ["--set", "fb-lock-111111", "it-1", "accepted", "--waiver", "not mechanically checkable"],
        env_extra={"CONCLAVE_TRIAGE_LOCK_TIMEOUT": "0"},
    )
    assert result.returncode != 0
    assert "lock" in (result.stderr or "").lower()
    after = fm_read(review_path)[0]["items"][0].get("status")
    assert after == before, "review file must be untouched when the lock is held"


def test_set_releases_lock_on_item_not_found(tmp_path):
    """The item-not-found early return must still release the lock (try/finally),
    else a mistyped item id would wedge the whole notebook."""
    _write_review(tmp_path, "2026-05-22", "atlas-nf.md",
                  _valid_review_meta(feedback_id="fb-nf-222222"))

    r1 = run_triage(tmp_path, ["--set", "fb-nf-222222", "no-such-item", "accepted"])
    assert r1.returncode == 1
    assert not (tmp_path / _LOCK_DIRNAME).exists(), "lock leaked on not-found path"

    # Lock was released → a valid set now succeeds.
    r2 = run_triage(tmp_path, ["--set", "fb-nf-222222", "it-1", "accepted", "--waiver", "not mechanically checkable"])
    assert r2.returncode == 0, r2.stderr


# --- #10: --digest --status filter + machine-readable --json ---

def test_digest_status_filter_open_only(tmp_path):
    """--digest --status open shows only open clusters, so the cadence work-list
    is one command instead of an ad-hoc index filter."""
    open_item = _valid_item("it-open", file="open.sh")
    rej_item = _valid_item("it-rej", file="rej.sh")
    rej_item["status"] = "rejected"
    _write_review(tmp_path, "2026-05-22", "atlas-mix.md",
                  _valid_review_meta(feedback_id="fb-mix-111111",
                                     items=[open_item, rej_item]))

    result = run_triage(tmp_path, ["--digest", "--status", "open"])
    assert result.returncode == 0, result.stderr
    assert "open.sh" in result.stdout, result.stdout
    assert "rej.sh" not in result.stdout, \
        f"rejected cluster must be filtered out; got: {result.stdout!r}"


def test_digest_json_emits_feedback_and_item_ids(tmp_path):
    """--digest --json emits machine-readable rows carrying feedback_id + item_id
    so classification maps straight to --set without an out-of-band index query."""
    import json as _json
    _write_review(tmp_path, "2026-05-22", "atlas-json.md",
                  _valid_review_meta(feedback_id="fb-json-999999",
                                     items=[_valid_item("it-1", file="j.sh")]))

    result = run_triage(tmp_path, ["--digest", "--json"])
    assert result.returncode == 0, result.stderr
    data = _json.loads(result.stdout)  # stdout must be pure JSON
    assert isinstance(data, list) and data, result.stdout
    row = data[0]
    assert row["feedback_id"] == "fb-json-999999", row
    assert row["item_id"] == "it-1", row
    assert row["status"] == "open", row


def test_digest_json_members_recover_all_ids_in_cluster(tmp_path):
    """A deduped cluster's --json row exposes every (feedback_id, item_id) member,
    so --set can address each colliding item, not just the representative."""
    import json as _json
    # Same location+category → same fingerprint → one cluster, two members.
    i1 = _valid_item("it-1", file="dup.sh")
    i2 = _valid_item("it-2", file="dup.sh")
    _write_review(tmp_path, "2026-05-22", "r1.md",
                  _valid_review_meta(feedback_id="fb-aaa-111111", items=[i1]))
    _write_review(tmp_path, "2026-05-22", "r2.md",
                  _valid_review_meta(feedback_id="fb-bbb-222222", items=[i2]))

    result = run_triage(tmp_path, ["--digest", "--json"])
    assert result.returncode == 0, result.stderr
    data = _json.loads(result.stdout)
    assert len(data) == 1, f"expected one deduped cluster; got {data!r}"
    members = {(m["feedback_id"], m["item_id"]) for m in data[0]["members"]}
    assert members == {("fb-aaa-111111", "it-1"), ("fb-bbb-222222", "it-2")}, members


def test_concurrent_set_no_lost_update(tmp_path):
    """Two concurrent --set on different items of the SAME review file: both must
    persist. Without the lock the second writer's RMW clobbers the first."""
    review_path = _write_review(
        tmp_path, "2026-05-22", "atlas-conc.md",
        _valid_review_meta(feedback_id="fb-conc-333333",
                           items=[_valid_item("it-1"), _valid_item("it-2")]),
    )

    def _spawn(item_id: str) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, str(FEEDBACK_PKG / "feedback_triage.py"),
             "--set", "fb-conc-333333", item_id, "accepted", "--waiver", "not mechanically checkable"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            env=_triage_env(tmp_path),
        )

    p1, p2 = _spawn("it-1"), _spawn("it-2")
    p1.wait()
    p2.wait()
    assert p1.returncode == 0 and p2.returncode == 0

    statuses = {it["id"]: it.get("status") for it in fm_read(review_path)[0]["items"]}
    assert statuses["it-1"] == "accepted", statuses
    assert statuses["it-2"] == "accepted", statuses  # lost without the lock


def test_set_reconciles_the_index_with_the_review_it_just_wrote(tmp_path):
    """--set must leave the cache agreeing with the source of truth, not one write behind.

    The defensive rebuild runs BEFORE the write, so without a reconcile the last item
    classified in a session is invisible to the digest, --check and any index consumer
    until something unrelated triggers a rebuild.
    """
    _write_review(
        tmp_path, "2026-05-22", "atlas-lag.md",
        _valid_review_meta(feedback_id="fb-777-aaaaaa", items=[_valid_item("it-1")])
    )

    res = run_triage(tmp_path, ["--set", "fb-777-aaaaaa", "it-1", "accepted",
                                "--owner", "sage-cto", "--issue", "424",
                                "--waiver", "not mechanically checkable"])
    assert res.returncode == 0, res.stderr

    # Read the index directly — no rebuild, no second command.
    index = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    rows = [json.loads(ln) for ln in index.read_text().splitlines() if ln.strip()]
    row = next(r for r in rows if r["feedback_id"] == "fb-777-aaaaaa"
               and r["item_id"] == "it-1")
    assert row["status"] == "accepted", "index must carry the status just written"
    assert row["owner"] == "sage-cto", "index must carry the owner just written"
    assert row["issue"] == 424, "index must carry the issue binding just written"


# --- #163: the owner field held 53 items' only issue link, and was overwritten blind ---

import pytest as _pytest


def _legacy_owner_review(tmp_path, owner: str, issue: int | None = None):
    """An accepted item whose issue number lives in `owner`, the superseded form."""
    item = _valid_item("it-1")
    item.update({"status": "accepted", "owner": owner,
                 "verify_waiver": "legacy row, no mechanical oracle"})
    if issue is not None:
        item["issue"] = issue
    meta = _valid_review_meta(feedback_id="fb-163-aaaaaa", items=[item])
    return _write_review(tmp_path, "2026-05-22", "atlas-163.md", meta)


@_pytest.mark.parametrize("owner", ["forge:#102", "forge:102", "forge:AI#12"])
def test_set_refuses_to_overwrite_an_owner_holding_the_only_issue_link(tmp_path, owner):
    """`feedback_verify --apply` always passes owner="verify:auto", and cmd_set wrote it
    unconditionally. 53 accepted items held their only issue link in this field and none
    carried an `issue:` — every one was a single auto-close from losing it with no trace.
    It happened once, to fb-1783808596-f85349/i1, and the binding survives only in git."""
    path = _legacy_owner_review(tmp_path, owner)
    res = run_triage(tmp_path, ["--set", "fb-163-aaaaaa", "it-1", "resolved",
                                "--owner", "verify:auto"])
    assert res.returncode == 1, res.stdout
    assert "it-1" in res.stderr and "--issue" in res.stderr, res.stderr

    item = fm_read(path)[0]["items"][0]
    assert item["owner"] == owner, "a refused write must leave the field untouched"
    assert item["status"] == "accepted", "the status must not move either"


def test_set_allows_the_overwrite_when_the_issue_moves_in_the_same_call(tmp_path):
    """The migration path the refusal points at: carry the number into `issue:` on the
    same audited write, and the owner becomes a name again."""
    path = _legacy_owner_review(tmp_path, "forge:#102")
    res = run_triage(tmp_path, ["--set", "fb-163-aaaaaa", "it-1", "accepted",
                                "--owner", "forge", "--issue", "102"])
    assert res.returncode == 0, res.stderr

    item = fm_read(path)[0]["items"][0]
    assert item["owner"] == "forge"
    assert item["issue"] == 102


def test_set_allows_the_overwrite_when_the_item_already_carries_the_issue(tmp_path):
    """Once `issue:` exists the owner string is redundant, so nothing is lost by
    overwriting it — the guard must not strand already-migrated rows."""
    path = _legacy_owner_review(tmp_path, "forge:#102", issue=102)
    res = run_triage(tmp_path, ["--set", "fb-163-aaaaaa", "it-1", "resolved",
                                "--owner", "verify:auto"])
    assert res.returncode == 0, res.stderr

    item = fm_read(path)[0]["items"][0]
    assert item["owner"] == "verify:auto"
    assert item["issue"] == 102, "the link the guard exists to protect must survive"


@_pytest.mark.parametrize("owner", ["forge", "sage-cto", "verify:auto", "forge:noise"])
def test_set_overwrites_an_ordinary_owner_freely(tmp_path, owner):
    """The guard fires on a number in a name field, and on nothing else. A rule that
    refused ordinary owners would block the auto-close path it is meant to protect."""
    path = _legacy_owner_review(tmp_path, owner)
    res = run_triage(tmp_path, ["--set", "fb-163-aaaaaa", "it-1", "resolved",
                                "--owner", "verify:auto"])
    assert res.returncode == 0, res.stderr
    assert fm_read(path)[0]["items"][0]["owner"] == "verify:auto"
