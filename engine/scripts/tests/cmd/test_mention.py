"""tests/cmd/test_mention.py — integration tests for `engine mention create/resolve`.

Hermetic: uses ai_root fixture (DATA+CODE tree + env vars). Ports all 11 create bats
cases from engine/scripts/tests/mention.bats and all 7 resolve bats cases from
engine/scripts/tests/resolve-mention.bats.
"""
from __future__ import annotations

from pathlib import Path

from enginelib.frontmatter import fm_get
from enginelib.paths import mentions_dir
from tests.cmd.helpers import run_engine

_NOW = "2026-04-22T16:30:00-03:00"


def _run_create(body: Path, frm: str = "nexus-ceo", to: str = "spark-cmo", **kwargs):
    args = [
        "mention", "create",
        "--from", frm, "--to", to,
        "--body-file", str(body),
        "--now", _NOW,
    ]
    for k, v in kwargs.items():
        args += [f"--{k.replace('_', '-')}", v]
    return run_engine(*args)


# 1. Creates mentions/<to>/open/<id>.md on exit 0
def test_creates_mention_file(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo", "kai-cto")
    body = tmp_path / "body.md"
    body.write_text("Body content.\n")
    r = _run_create(body)
    assert r.returncode == 0
    mid = r.stdout.strip()
    assert mid
    assert (mentions_dir() / "spark-cmo" / "open" / f"{mid}.md").is_file()


# 2. Id format YYYY-MM-DD-HHMM-<from>-to-<to>-<slug>
def test_id_format(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo", "kai-cto")
    body = tmp_path / "body.md"
    body.write_text("video approval please\n")
    r = _run_create(body)
    assert r.returncode == 0
    assert r.stdout.strip().startswith("2026-04-22-1630-nexus-ceo-to-spark-cmo-")


# 3. Frontmatter status=open and created == --now ISO
def test_frontmatter_status_and_created(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo", "kai-cto")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_create(body, frm="kai-cto", to="nexus-ceo")
    assert r.returncode == 0
    mid = r.stdout.strip()
    f = mentions_dir() / "nexus-ceo" / "open" / f"{mid}.md"
    assert fm_get(f, "status") == "open"
    assert fm_get(f, "created") == _NOW


# 4. Default priority p2 when --priority absent
def test_default_priority_p2(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo", "kai-cto")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_create(body, frm="kai-cto", to="nexus-ceo")
    assert r.returncode == 0
    mid = r.stdout.strip()
    f = mentions_dir() / "nexus-ceo" / "open" / f"{mid}.md"
    assert fm_get(f, "priority") == "p2"


# 5. Refuses if same id exists in open/
def test_refuses_open_collision(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo", "kai-cto")
    body = tmp_path / "body.md"
    body.write_text("duplicate body\n")
    r1 = _run_create(body, frm="kai-cto", to="nexus-ceo")
    assert r1.returncode == 0
    r2 = _run_create(body, frm="kai-cto", to="nexus-ceo")
    assert r2.returncode != 0
    combined = r2.stdout + r2.stderr
    assert "collision" in combined or "exists" in combined


# 6. Refuses if same id exists in archive/
def test_refuses_archive_collision(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo", "kai-cto")
    body = tmp_path / "body.md"
    body.write_text("archived body\n")
    mid = "2026-04-22-1630-kai-cto-to-nexus-ceo-archived-body"
    archive_dir = mentions_dir() / "nexus-ceo" / "archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / f"{mid}.md").write_text(f"---\nid: {mid}\n---\n")
    r = _run_create(body, frm="kai-cto", to="nexus-ceo")
    assert r.returncode != 0
    assert "archive" in r.stdout + r.stderr


# 7. --ref-session populates frontmatter
def test_ref_session_in_frontmatter(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo", "kai-cto")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = run_engine(
        "mention", "create",
        "--from", "kai-cto", "--to", "nexus-ceo",
        "--body-file", str(body),
        "--now", _NOW,
        "--ref-session", "2026-04-22-nexus-ceo-vid",
    )
    assert r.returncode == 0
    mid = r.stdout.strip()
    f = mentions_dir() / "nexus-ceo" / "open" / f"{mid}.md"
    assert fm_get(f, "ref_session") == "2026-04-22-nexus-ceo-vid"


# 8. --ref-issue populates frontmatter
def test_ref_issue_in_frontmatter(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo", "kai-cto")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = run_engine(
        "mention", "create",
        "--from", "kai-cto", "--to", "nexus-ceo",
        "--body-file", str(body),
        "--now", _NOW,
        "--ref-issue", "AI#58",
    )
    assert r.returncode == 0
    mid = r.stdout.strip()
    f = mentions_dir() / "nexus-ceo" / "open" / f"{mid}.md"
    assert fm_get(f, "ref_issue") == "AI#58"


# 9. Prints id to stdout for chaining
def test_prints_id_to_stdout(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo", "kai-cto")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_create(body, frm="kai-cto", to="nexus-ceo")
    assert r.returncode == 0
    assert r.stdout.strip().startswith("2026-04-22-1630-")


# 10. Required args enforced
def test_required_args_enforced(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo", "kai-cto")
    r = run_engine("mention", "create", "--from", "nexus-ceo")
    assert r.returncode != 0
    assert "required" in r.stderr


# 11. Regression guard fb-1779219510: cyrillic body + p1 must exit 0.
# In Python there is no set-u multibyte variable-scanner bug; the hot-append is
# the guarded deferred no-op (3D.3 not built yet) — still must exit 0.
def test_cyrillic_p1_exits_zero(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo", "kai-cto")
    body = tmp_path / "body.md"
    body.write_text("Срочный апдейт по релизу → нужно решение\n", encoding="utf-8")
    r = run_engine(
        "mention", "create",
        "--from", "nexus-ceo", "--to", "spark-cmo",
        "--body-file", str(body),
        "--priority", "p1",
        "--now", "2026-05-19T16:45:00-03:00",
    )
    assert r.returncode == 0
    assert "unbound variable" not in r.stdout
    assert "unbound variable" not in r.stderr


# ── resolve (7 cases — ports resolve-mention.bats) ──────────────────────────

_RESOLVE_NOW = "2026-04-22T17:00:00-03:00"


def _seed_open(tmp_path: Path, frm: str = "nexus-ceo", to: str = "spark-cmo", body_text: str = "please review") -> str:
    """Create an open mention via CLI; return its printed id."""
    body = tmp_path / "body.md"
    body.write_text(body_text + "\n")
    r = run_engine(
        "mention", "create",
        "--from", frm, "--to", to,
        "--body-file", str(body),
        "--now", _NOW,
    )
    assert r.returncode == 0, f"seed failed: {r.stderr}"
    return r.stdout.strip()


# R1. Moves file from open/ to archive/
def test_resolve_moves_open_to_archive(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo")
    mid = _seed_open(tmp_path)
    r = run_engine("mention", "resolve", "--id", mid, "--by", "spark-cmo", "--now", _RESOLVE_NOW)
    assert r.returncode == 0
    assert not (mentions_dir() / "spark-cmo" / "open" / f"{mid}.md").exists()
    assert (mentions_dir() / "spark-cmo" / "archive" / f"{mid}.md").is_file()


# R2. Mutates frontmatter status=resolved + resolved=now
def test_resolve_frontmatter_status_and_timestamp(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo")
    mid = _seed_open(tmp_path)
    run_engine("mention", "resolve", "--id", mid, "--by", "spark-cmo", "--now", _RESOLVE_NOW)
    f = mentions_dir() / "spark-cmo" / "archive" / f"{mid}.md"
    assert fm_get(f, "status") == "resolved"
    assert fm_get(f, "resolved") == _RESOLVE_NOW


# R3. Sets resolved_by and resolved_note
def test_resolve_sets_resolved_by_and_note(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo")
    mid = _seed_open(tmp_path)
    run_engine(
        "mention", "resolve",
        "--id", mid, "--by", "spark-cmo",
        "--note", "Shipped in v1.2",
        "--now", _RESOLVE_NOW,
    )
    f = mentions_dir() / "spark-cmo" / "archive" / f"{mid}.md"
    assert fm_get(f, "resolved_by") == "spark-cmo"
    assert fm_get(f, "resolved_note") == "Shipped in v1.2"


# R4. --by required
def test_resolve_by_required(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo")
    mid = _seed_open(tmp_path)
    r = run_engine("mention", "resolve", "--id", mid)
    assert r.returncode != 0
    assert "required" in r.stderr


# R5. --id required
def test_resolve_id_required(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo")
    r = run_engine("mention", "resolve", "--by", "spark-cmo")
    assert r.returncode != 0
    assert "required" in r.stderr


# R6. Errors if id not found in any open/
def test_resolve_id_not_in_open(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo")
    r = run_engine(
        "mention", "resolve",
        "--id", "2026-04-22-1630-x-to-y-nonexistent",
        "--by", "spark-cmo",
    )
    assert r.returncode != 0
    combined = r.stdout + r.stderr
    assert "not found" in combined or "open" in combined


# R7. Preserves body after move
def test_resolve_preserves_body(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "spark-cmo")
    mid = _seed_open(tmp_path, body_text="please review the deck")
    run_engine("mention", "resolve", "--id", mid, "--by", "spark-cmo", "--now", _RESOLVE_NOW)
    f = mentions_dir() / "spark-cmo" / "archive" / f"{mid}.md"
    assert "please review the deck" in f.read_text()
