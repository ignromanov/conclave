"""tests/cmd/test_file_decision.py — integration tests for `engine file decision`.

Hermetic: uses ai_root fixture (DATA+CODE tree + env vars). Ports all 8 bats
cases from engine/scripts/tests/file-decision.bats.
"""
from __future__ import annotations

from pathlib import Path

from enginelib.frontmatter import fm_get
from enginelib.paths import decisions_dir, repo_root, sessions_dir
from tests.cmd.helpers import run_engine

_DATE = "2026-04-22"


def _run_decision(body: Path, slug: str = "move-to-base", by: str = "nexus-ceo", **kwargs):
    args = [
        "file", "decision",
        "--slug", slug,
        "--by", by,
        "--date", _DATE,
        "--body-file", str(body),
    ]
    for k, v in kwargs.items():
        if isinstance(v, bool):
            if v:
                args.append(f"--{k.replace('_', '-')}")
        else:
            args += [f"--{k.replace('_', '-')}", str(v)]
    return run_engine(*args)


# 1. Creates decisions/{date}-{by}-{slug}.md, exit 0
def test_creates_decision_file(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "kai-cto", "quorum", "shade-ciso")
    body = tmp_path / "body.md"
    body.write_text("Body content.\n")
    r = _run_decision(body)
    assert r.returncode == 0
    assert (decisions_dir() / f"{_DATE}-nexus-ceo-move-to-base.md").is_file()


# 2. Frontmatter has slug, by, date, status=active
def test_frontmatter_fields(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "kai-cto", "quorum", "shade-ciso")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_decision(body, slug="x", by="kai-cto")
    assert r.returncode == 0
    f = decisions_dir() / f"{_DATE}-kai-cto-x.md"
    assert fm_get(f, "slug") == "x"
    assert fm_get(f, "by") == "kai-cto"
    assert fm_get(f, "date") == _DATE
    assert fm_get(f, "status") == "active"


# 2b. #52: a slug that repeats the advisor id does not stutter the filename.
def test_slug_stutter_is_stripped(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "kai-cto", "quorum", "shade-ciso")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_decision(body, slug="kai-cto-first-launch", by="kai-cto")
    assert r.returncode == 0
    # Single advisor id, not "…-kai-cto-kai-cto-first-launch.md".
    assert (decisions_dir() / f"{_DATE}-kai-cto-first-launch.md").is_file()
    assert not (decisions_dir() / f"{_DATE}-kai-cto-kai-cto-first-launch.md").exists()


# 3. --meeting appends cross-ref to meeting file
def test_meeting_cross_ref(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "kai-cto", "quorum", "shade-ciso")
    meeting_dir = repo_root() / "ops" / "meetings"
    meeting_dir.mkdir(parents=True, exist_ok=True)
    meeting_file = meeting_dir / "2026-04-22-weekly.md"
    meeting_file.write_text("# Meeting\n\nNotes.\n")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_decision(body, slug="x", by="kai-cto", meeting="2026-04-22-weekly")
    assert r.returncode == 0
    content = meeting_file.read_text()
    assert f"{_DATE}-kai-cto-x" in content


# 4. --session appends cross-ref to session file
def test_session_cross_ref(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "kai-cto", "quorum", "shade-ciso")
    session_file = sessions_dir() / "2026-04-22-nexus-ceo-vid.md"
    session_file.write_text("# Session\n")
    body = tmp_path / "body.md"
    body.write_text("Body.\n")
    r = _run_decision(body, slug="x", by="nexus-ceo", session="2026-04-22-nexus-ceo-vid")
    assert r.returncode == 0
    content = session_file.read_text()
    assert f"{_DATE}-nexus-ceo-x" in content


# 5. Idempotent — same slug+date upserts without dupe
def test_idempotent(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "kai-cto", "quorum", "shade-ciso")
    body = tmp_path / "body.md"
    body.write_text("Body v1.\n")
    r1 = _run_decision(body, slug="x", by="nexus-ceo")
    assert r1.returncode == 0

    body.write_text("Body v2.\n")
    r2 = _run_decision(body, slug="x", by="nexus-ceo")
    assert r2.returncode == 0

    dec_file = decisions_dir() / f"{_DATE}-nexus-ceo-x.md"
    text = dec_file.read_text()
    assert text.count("Body v2") == 1
    # Exactly one file in decisions/
    files = list(decisions_dir().glob("*.md"))
    assert len(files) == 1


# 6. No cross-advisor collision on same date+slug
def test_no_cross_advisor_collision(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "kai-cto", "quorum", "shade-ciso")
    body_q = tmp_path / "q.md"
    body_q.write_text("quorum body\n")
    body_s = tmp_path / "s.md"
    body_s.write_text("shade body\n")

    r1 = run_engine("file", "decision", "--slug", "entry", "--by", "quorum",
                    "--date", "2026-03-26", "--body-file", str(body_q))
    r2 = run_engine("file", "decision", "--slug", "entry", "--by", "shade-ciso",
                    "--date", "2026-03-26", "--body-file", str(body_s))
    assert r1.returncode == 0
    assert r2.returncode == 0

    dec_dir = decisions_dir()
    q_file = dec_dir / "2026-03-26-quorum-entry.md"
    s_file = dec_dir / "2026-03-26-shade-ciso-entry.md"
    assert q_file.is_file()
    assert s_file.is_file()
    assert "quorum body" in q_file.read_text()
    assert "shade body" in s_file.read_text()


# 7. Required args enforced — missing --by/--date/--body-file → exit != 0, "required"
def test_required_args_enforced(seed_advisors, tmp_path):
    seed_advisors("nexus-ceo", "kai-cto", "quorum", "shade-ciso")
    r = run_engine("file", "decision", "--slug", "x")
    assert r.returncode != 0
    assert "required" in r.stderr


# 8. Does NOT commit — no git invocation in filing.py or file.py source
def test_does_not_commit(tmp_path):
    import re
    scripts_root = Path(__file__).resolve().parents[2]
    for src in (
        scripts_root / "enginelib" / "filing.py",
        scripts_root / "engine" / "cmd" / "file.py",
    ):
        text = src.read_text()
        assert not re.search(r'\bgit\b', text), (
            f"{src.name} must not invoke git (found 'git' in source)"
        )
