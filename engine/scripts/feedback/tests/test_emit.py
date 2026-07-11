"""test_emit.py — TDD tests for feedback_emit.py (T3)."""
import subprocess
import sys
from pathlib import Path

from briefing.frontmatter_io import read

SCRIPTS_DIR = Path(__file__).parent.parent.parent  # .../scripts/


def run_emit(tmp_path: Path, extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run feedback_emit.py with standard args; feedback_root overridden via env."""
    args = [
        sys.executable,
        str(SCRIPTS_DIR / "feedback" / "feedback_emit.py"),
        "--agent", "atlas",
        "--agent-type", "executor",
        "--session-ref", "test-session-001",
        "--skill-version", "sha256:aabbccdd1234",
    ]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        env={
            "PYTHONPATH": str(SCRIPTS_DIR),
            "CONCLAVE_AI_ROOT": str(tmp_path.resolve()),
            "PATH": "/usr/bin:/bin",
        },
    )


def _emitted_file(result: subprocess.CompletedProcess) -> Path:
    """Extract the emitted file path from stdout (subprocess prints canonical path)."""
    return Path(result.stdout.strip())


def test_emit_creates_file(tmp_path):
    """emit writes a file at ops/feedback/<today>/<agent>-<session>.md."""
    result = run_emit(tmp_path)
    assert result.returncode == 0, result.stderr

    review_file = _emitted_file(result)
    assert review_file.exists(), f"expected file at {review_file}"
    assert review_file.name.startswith("atlas-")
    assert "ops/feedback" in str(review_file)


def test_emit_prints_path(tmp_path):
    result = run_emit(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "ops/feedback" in result.stdout


def test_emit_draft_true(tmp_path):
    """Scaffold must have _draft: true."""
    result = run_emit(tmp_path)
    assert result.returncode == 0, result.stderr

    review_file = _emitted_file(result)
    meta, _body = read(review_file)
    assert meta["_draft"] is True


def test_emit_agent_type_stored(tmp_path):
    """agent_type is recorded correctly."""
    result = run_emit(tmp_path)
    assert result.returncode == 0, result.stderr

    review_file = _emitted_file(result)
    meta, _body = read(review_file)
    assert meta["agent_type"] == "executor"


def test_emit_items_empty(tmp_path):
    """Items list starts empty."""
    result = run_emit(tmp_path)
    assert result.returncode == 0, result.stderr

    review_file = _emitted_file(result)
    meta, _body = read(review_file)
    assert meta["items"] == [] or meta.get("items") is None or meta.get("items") == []


def test_emit_fingerprint_field_absent_or_null(tmp_path):
    """Scaffold items list is empty; no fingerprint fields at top level."""
    result = run_emit(tmp_path)
    assert result.returncode == 0, result.stderr

    review_file = _emitted_file(result)
    meta, _body = read(review_file)
    # Scaffold emits empty items; no stray top-level fingerprint key
    assert meta.get("items") == [] or meta.get("items") is None
    assert "fingerprint" not in meta  # fingerprint lives on items, not top level


def test_emit_noop_flag(tmp_path):
    """--no-op flag writes no_op: true into the scaffold frontmatter."""
    result = run_emit(tmp_path, extra_args=["--no-op"])
    assert result.returncode == 0, result.stderr

    review_file = _emitted_file(result)
    assert review_file.exists(), f"expected file at {review_file}"
    meta, _body = read(review_file)
    assert meta.get("no_op") is True, f"no_op must be true in frontmatter, got: {meta}"




def run_emit_with_env(tmp_path: Path, extra_env: dict | None = None,
                      extra_args: list[str] | None = None) -> subprocess.CompletedProcess:
    """Run feedback_emit.py with custom env vars merged in."""
    base_env = {
        "PYTHONPATH": str(SCRIPTS_DIR),
        "CONCLAVE_AI_ROOT": str(tmp_path.resolve()),
        "PATH": "/usr/bin:/bin",
    }
    if extra_env:
        base_env.update(extra_env)
    args = [
        sys.executable,
        str(SCRIPTS_DIR / "feedback" / "feedback_emit.py"),
        "--agent", "atlas",
        "--agent-type", "executor",
        "--session-ref", "test-session-001",
        "--skill-version", "sha256:aabbccdd1234",
    ]
    if extra_args:
        args.extend(extra_args)
    return subprocess.run(args, capture_output=True, text=True, env=base_env)


def test_data_classification_header_present_in_emitted_file(tmp_path):
    """Emitted file must start with the DATA CLASSIFICATION HTML comment block."""
    result = run_emit_with_env(tmp_path)
    assert result.returncode == 0, result.stderr

    review_file = _emitted_file(result)
    raw = review_file.read_text()
    assert raw.startswith("<!--"), f"file must start with HTML comment, got: {raw[:80]}"
    assert "DATA CLASSIFICATION WARNING" in raw, "classification header text missing"
    assert raw.index("---") > raw.index("-->"), "frontmatter must come after comment block"


def test_trace_ref_env_populated_when_set(tmp_path):
    """CLAUDE_SESSION_ID env var populates trace_ref in frontmatter."""
    result = run_emit_with_env(tmp_path, extra_env={"CLAUDE_SESSION_ID": "sess-xyz-999"})
    assert result.returncode == 0, result.stderr

    review_file = _emitted_file(result)
    meta, _body = read(review_file)
    assert meta.get("trace_ref") == "sess-xyz-999", f"trace_ref mismatch: {meta}"


def test_trace_ref_absent_when_env_unset(tmp_path):
    """When CLAUDE_SESSION_ID is not set, trace_ref is None/absent."""
    env = {
        "PYTHONPATH": str(SCRIPTS_DIR),
        "CONCLAVE_AI_ROOT": str(tmp_path.resolve()),
        "PATH": "/usr/bin:/bin",
        # explicitly no CLAUDE_SESSION_ID
    }
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS_DIR / "feedback" / "feedback_emit.py"),
            "--agent", "atlas",
            "--agent-type", "executor",
            "--session-ref", "test-session-001",
            "--skill-version", "sha256:aabbccdd1234",
        ],
        capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr

    review_file = _emitted_file(result)
    meta, _body = read(review_file)
    assert meta.get("trace_ref") is None, f"trace_ref must be None when env unset: {meta}"


def test_parent_session_ref_env_populated_when_set(tmp_path):
    """CLAUDE_PARENT_SESSION env var populates parent_session_ref in frontmatter."""
    result = run_emit_with_env(tmp_path, extra_env={"CLAUDE_PARENT_SESSION": "parent-abc-111"})
    assert result.returncode == 0, result.stderr

    review_file = _emitted_file(result)
    meta, _body = read(review_file)
    assert meta.get("parent_session_ref") == "parent-abc-111", f"parent_session_ref mismatch: {meta}"


# --- --finalize: validating draft-flip gate (prevents schema-invalid _draft:false) ---

from briefing.frontmatter_io import write as _fm_write  # noqa: E402


def _valid_review_meta() -> dict:
    return {
        "feedback_id": "fb-1780000000-aaaaaa",
        "agent": "atlas", "agent_type": "executor",
        "session_ref": "test-finalize", "skill_version": "sha256:aabbccdd1234",
        "created": "2026-06-04T00:00:00Z", "updated_at": "2026-06-04T00:00:00Z",
        "_draft": True, "summary": "test finalize",
        "items": [{
            "id": "it-1", "category": "process-friction", "layer": "workflow",
            "location": {"skill": "team.kai-cto"},
            "observation": "x", "suggested_fix": "y",
            "severity": "low", "frequency": "first-time", "evidence": "tool_call:abc",
        }],
        "below_threshold_count": 0,
    }


def run_finalize(file_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "feedback" / "feedback_emit.py"),
         "--finalize", str(file_path)],
        capture_output=True, text=True,
        env={"PYTHONPATH": str(SCRIPTS_DIR), "PATH": "/usr/bin:/bin"},
    )


def test_finalize_valid_flips_draft(tmp_path):
    """A schema-valid review flips _draft:false and exits 0."""
    f = tmp_path / "rev.md"
    _fm_write(f, _valid_review_meta(), "## Review items\n")
    result = run_finalize(f)
    assert result.returncode == 0, result.stderr
    meta, _ = read(f)
    assert meta["_draft"] is False


def test_finalize_invalid_layer_rejected_keeps_draft(tmp_path):
    """An invalid enum (layer) is rejected; _draft stays true (file not finalized)."""
    meta = _valid_review_meta()
    meta["items"][0]["layer"] = "dispatch"
    f = tmp_path / "rev.md"
    _fm_write(f, meta, "## Review items\n")
    result = run_finalize(f)
    assert result.returncode != 0
    assert "layer" in (result.stdout + result.stderr).lower()
    meta2, _ = read(f)
    assert meta2["_draft"] is True


def test_finalize_invalid_frequency_rejected_keeps_draft(tmp_path):
    """An invented frequency value is rejected and the file is left as draft."""
    meta = _valid_review_meta()
    meta["items"][0]["frequency"] = "recurring"
    f = tmp_path / "rev.md"
    _fm_write(f, meta, "## Review items\n")
    result = run_finalize(f)
    assert result.returncode != 0
    meta2, _ = read(f)
    assert meta2["_draft"] is True


# --- 093 P1 T5: re-occurred reopen on finalize (fingerprint match) ---

import json as _json

FEEDBACK_PKG = Path(__file__).parent.parent  # .../scripts/feedback/


def _run_finalize(tmp_path: Path, path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(FEEDBACK_PKG / "feedback_emit.py"), "--finalize", str(path)],
        capture_output=True, text=True,
        env={"PYTHONPATH": str(SCRIPTS_DIR),
             "CONCLAVE_AI_ROOT": str(tmp_path.resolve()), "PATH": "/usr/bin:/bin"},
    )


def _draft_review(tmp_path: Path, feedback_id: str,
                  file: str = "foo.py", category: str = "script-defect") -> Path:
    from briefing.frontmatter_io import write
    d = tmp_path / "ops" / "feedback" / "2026-07-10"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{feedback_id}.md"
    write(p, {"feedback_id": feedback_id, "agent": "sage-cto", "agent_type": "advisor",
              "session_ref": "s1", "skill_version": "sha256:aabbcc",
              "created": "2026-07-10T00:00:00Z", "updated_at": "2026-07-10T00:00:00Z",
              "_draft": True, "summary": "t", "below_threshold_count": 0,
              "items": [{"id": "i1", "category": category, "layer": "skill",
                         "location": {"file": file}, "observation": "o",
                         "suggested_fix": "x", "severity": "high",
                         "frequency": "occasional", "evidence": "tc:1",
                         "status": "open"}]}, "")
    return p


def _seed_archive_resolved(tmp_path: Path, fid: str = "fb-old-xxxxxx") -> None:
    arch = tmp_path / "ops" / "feedback" / "_archive"
    arch.mkdir(parents=True, exist_ok=True)
    (arch / "2026-06.jsonl").write_text(_json.dumps({
        "feedback_id": fid,
        "items": [{"id": "i1", "location": {"file": "foo.py"},
                   "category": "script-defect", "status": "resolved"}]}) + "\n")


def test_finalize_reopens_on_archived_resolved_match(tmp_path):
    """A new item whose fingerprint matches an archived RESOLVED item is stamped
    re-occurred + reopened_from at finalize (093 P1 T5, closes #89)."""
    _seed_archive_resolved(tmp_path)
    new = _draft_review(tmp_path, "fb-new-bbbbbb")
    res = _run_finalize(tmp_path, new)
    assert res.returncode == 0, res.stderr
    item = read(new)[0]["items"][0]
    assert item["status"] == "re-occurred"
    assert item["reopened_from"] == "fb-old-xxxxxx:i1"


def test_finalize_no_reopen_when_live_nonterminal_dup(tmp_path):
    """Guard: an ordinary still-open duplicate at the same fingerprint must NOT be
    misclassified as a regression even when an archived resolved match exists."""
    from feedback.schema import fingerprint
    fp = fingerprint({"file": "foo.py"}, "script-defect")
    _seed_archive_resolved(tmp_path)
    idx = tmp_path / "ops" / "feedback" / "_index"
    idx.mkdir(parents=True, exist_ok=True)
    (idx / "index.jsonl").write_text(_json.dumps({
        "feedback_id": "fb-live-cccccc", "item_id": "i9",
        "fingerprint": fp, "status": "accepted"}) + "\n")
    new = _draft_review(tmp_path, "fb-new-dddddd")
    res = _run_finalize(tmp_path, new)
    assert res.returncode == 0, res.stderr
    item = read(new)[0]["items"][0]
    assert item["status"] != "re-occurred"
