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


def test_a_resolved_mention_is_still_YAML_when_the_note_is_prose(seed_advisors, tmp_path):
    """The note is free prose and `fm_set` writes its value verbatim, so an ordinary
    verdict — "Ruled: C0 killed as written" — closed the mapping and made the whole
    record a ScannerError. Measured 2026-09-15: 5 of 28 mention records on this instance
    do not parse, the newest written 2026-09-14, five days after the identical defect was
    fixed in the session writer (#254/#255). The fix never reached this writer (#249).

    Reddens under: dropping the `as_block` at `mention.py:204`.
    """
    import yaml

    note = "Ruled: C0 killed as written; T5 recorded not met; C0b are yours."
    seed_advisors("nexus-ceo", "spark-cmo")
    mid = _seed_open(tmp_path)
    run_engine("mention", "resolve", "--id", mid, "--by", "spark-cmo",
               "--note", note, "--now", _RESOLVE_NOW)

    f = mentions_dir() / "spark-cmo" / "archive" / f"{mid}.md"
    meta = yaml.safe_load(f.read_text(encoding="utf-8").split("---", 2)[1])
    assert meta["resolved_note"] == note, "the note must survive serialization intact"
    assert meta["status"] == "resolved", "the keys after the note must still be reachable"


def test_a_note_that_needs_no_quoting_is_written_unchanged(seed_advisors, tmp_path):
    """The three sibling fields are tokens and timestamps, and 23 of 28 live notes are
    already plain. Serializing those too would rewrite the corpus for nothing, so
    `as_block` must stay a no-op wherever the plain form is already valid YAML.
    """
    seed_advisors("nexus-ceo", "spark-cmo")
    mid = _seed_open(tmp_path)
    run_engine("mention", "resolve", "--id", mid, "--by", "spark-cmo",
               "--note", "Shipped in v1.2", "--now", _RESOLVE_NOW)
    f = mentions_dir() / "spark-cmo" / "archive" / f"{mid}.md"
    assert "resolved_note: Shipped in v1.2" in f.read_text(encoding="utf-8")


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


# --- #301: the reference survives the write -----------------------------------------

def test_a_bare_issue_reference_round_trips_through_a_yaml_reader(seed_advisors, tmp_path):
    """`--ref-issue "#297"` wrote `ref_issue: #297` — a VALID document whose value is None.

    The assertion goes through a real YAML parser because that is what the consumer uses:
    `briefing/scans/mentions.py::_build_ref` reads this field with `python-frontmatter`,
    so the loss showed up as a mention appearing in the briefing with no reference at all.
    A line-based `fm_get` sees `#297` either way and would pass on the broken file.

    Reddens under: `frontmatter.render_record` -> `template.render` in `mention.create`.
    """
    import yaml
    seed_advisors("nexus-ceo", "spark-cmo", "kai-cto")
    body = tmp_path / "body.md"
    body.write_text("Reference me.\n")
    r = _run_create(body, ref_issue="#297")
    assert r.returncode == 0
    f = mentions_dir() / "spark-cmo" / "open" / f"{r.stdout.strip()}.md"
    meta = yaml.safe_load(f.read_text(encoding="utf-8").split("---\n")[1])
    assert meta["ref_issue"] == "#297"


def test_the_three_reference_forms_that_were_already_safe_are_unchanged(seed_advisors, tmp_path):
    """`--ref-issue` advertises four forms; only the bare `#N` one broke, because in
    `AI#12` and `owner/repo#12` the `#` is not preceded by whitespace. Those must not
    start gaining quotes — a fix that churns every record buries the ones that changed.

    Reddens under: quoting unconditionally in `as_scalar`.
    """
    seed_advisors("nexus-ceo", "spark-cmo", "kai-cto")
    for form in ("AI#12", "ignromanov/conclave#12", "https://github.com/x/y/issues/12"):
        body = tmp_path / f"body-{abs(hash(form))}.md"
        body.write_text(f"Body for {form}.\n")
        r = _run_create(body, ref_issue=form)
        assert r.returncode == 0
        f = mentions_dir() / "spark-cmo" / "open" / f"{r.stdout.strip()}.md"
        assert f"ref_issue: {form}\n" in f.read_text(encoding="utf-8"), form
