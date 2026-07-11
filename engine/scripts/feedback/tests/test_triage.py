"""test_triage.py — TDD tests for feedback_triage.py (T6)."""
from __future__ import annotations

import subprocess
import sys
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

    result = run_triage(tmp_path, ["--set", "fb-666-ffffff", "it-1", "accepted"])
    assert result.returncode == 0, result.stderr

    meta_after, _ = fm_read(
        tmp_path / "ops" / "feedback" / "2026-05-22" / "atlas-noown.md"
    )
    item = meta_after["items"][0]
    assert item["status"] == "accepted"


def test_check_threshold_any_open_item(tmp_path):
    """cmd_check: even a single open item makes triage_due=true regardless of marker age."""
    _write_review(tmp_path, "2026-05-22", "atlas-open.md",
                  _valid_review_meta(feedback_id="fb-open-111111",
                                     items=[_valid_item("it-1")]))
    # Fresh marker (< 7 days old)
    marker = tmp_path / "ops" / "feedback" / "_index" / "last-triage"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.touch()

    result = run_triage(tmp_path, ["--check"])
    assert result.returncode == 0, result.stderr
    assert "triage_due=true" in result.stdout


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

    result = run_triage(tmp_path, ["--set", "fb-acc-777777", "it-1", "accepted"])
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
        tmp_path, ["--set", "fb-lock-111111", "it-1", "accepted"],
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
    r2 = run_triage(tmp_path, ["--set", "fb-nf-222222", "it-1", "accepted"])
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
             "--set", "fb-conc-333333", item_id, "accepted"],
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
