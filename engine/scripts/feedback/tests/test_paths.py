from feedback import paths


def test_layout(tmp_path, monkeypatch):
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    assert paths.feedback_root() == tmp_path / "ops" / "feedback"
    assert paths.index_path() == tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    assert paths.last_triage_marker() == tmp_path / "ops" / "feedback" / "_index" / "last-triage"
    assert paths.archive_dir() == tmp_path / "ops" / "feedback" / "_archive"
    assert paths.migrated_dir() == tmp_path / "ops" / "feedback" / "_migrated"
    assert paths.review_dir("2026-05-22").name == "2026-05-22"
