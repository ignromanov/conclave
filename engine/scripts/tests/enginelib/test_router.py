import pytest

from enginelib import paths, router


def _seed_template(tmp_path, monkeypatch):
    # templates_dir() resolves via forge_dir() = engine_root().parent / "skills" / ...
    # i.e. a *sibling* of engine/, not nested inside it (post Wave-4 repoint, a8da572).
    engine = tmp_path / "engine"
    tdir = tmp_path / "skills" / "forge-operations" / "references" / "templates"
    tdir.mkdir(parents=True, exist_ok=True)
    (tdir / "advisor-router.md").write_text(
        "---\nname: conclave-${ID}\n---\n\nYou are the **${ID}** advisor. "
        "Enter /conclave:start bound to ${ID}.\n"
    )
    monkeypatch.setenv("CONCLAVE_ENGINE_ROOT", str(engine))


def test_scaffold_writes_router(tmp_path, monkeypatch):
    _seed_template(tmp_path, monkeypatch)
    skills_root = tmp_path / ".claude" / "skills"
    info = router.scaffold_router("iris-cpo", skills_root=skills_root)
    p = skills_root / "conclave-iris-cpo" / "SKILL.md"
    assert p.is_file()
    body = p.read_text()
    assert "name: conclave-iris-cpo" in body
    assert "iris-cpo" in body and "/conclave:start" in body
    assert info == {"id": "iris-cpo", "skill": str(p)}


def test_scaffold_resolves_without_a_project_root(tmp_path, monkeypatch):
    """No DATA root anywhere: the agent-def lookup must degrade, not raise.

    A fresh CI checkout has no `.conclave/`, so `repo_root()`'s upward walk finds
    nothing and `project_agents_dir()` raises. The caller already supplied
    `skills_root`, which is the only directory this path needs — an unresolvable
    project dir means "no agent-def there", not a crash.

    Every other scaffold test passes locally either way, because the walk finds the
    maintainer's checkout through its gitignored orphan `ops/` tree (#87). This one
    states the requirement independently of that accident.
    """
    _seed_template(tmp_path, monkeypatch)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(RuntimeError):  # precondition: the CI condition holds here
        paths.repo_root()
    skills_root = tmp_path / ".claude" / "skills"
    info = router.scaffold_router("iris-cpo", skills_root=skills_root)
    skill = skills_root / "conclave-iris-cpo" / "SKILL.md"
    assert info == {"id": "iris-cpo", "skill": str(skill)}
    assert skill.is_file()


def test_scaffold_rejects_bad_id(tmp_path, monkeypatch):
    _seed_template(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        router.scaffold_router("Bad Id!", skills_root=tmp_path)


def test_scaffold_idempotent_overwrite(tmp_path, monkeypatch):
    _seed_template(tmp_path, monkeypatch)
    skills_root = tmp_path / ".claude" / "skills"
    router.scaffold_router("iris-cpo", skills_root=skills_root)
    router.scaffold_router("iris-cpo", skills_root=skills_root)  # no raise
    assert (skills_root / "conclave-iris-cpo" / "SKILL.md").is_file()


def _enrich(path):
    """Simulate hire-time enrichment: a forge: block + a ## Scope section."""
    body = path.read_text()
    body = body.replace(
        "name: conclave-iris-cpo\n",
        "name: conclave-iris-cpo\nforge:\n  model-version: 1.0.0\n",
    )
    path.write_text(body + "\n## Scope\n\nIris owns quality gates.\n")


def test_scaffold_skips_enriched_wrapper(tmp_path, monkeypatch):
    """#58: re-running scaffold on an enriched wrapper must NOT clobber it."""
    _seed_template(tmp_path, monkeypatch)
    skills_root = tmp_path / ".claude" / "skills"
    router.scaffold_router("iris-cpo", skills_root=skills_root)
    p = skills_root / "conclave-iris-cpo" / "SKILL.md"
    _enrich(p)
    info = router.scaffold_router("iris-cpo", skills_root=skills_root)  # re-run
    body = p.read_text()
    assert "forge:" in body and "## Scope" in body  # enrichment preserved
    assert info == {"id": "iris-cpo", "skill": str(p), "skipped": "enriched"}


def test_scaffold_force_overwrites_enriched(tmp_path, monkeypatch):
    """#58: --force still allows a full re-render (escape hatch)."""
    _seed_template(tmp_path, monkeypatch)
    skills_root = tmp_path / ".claude" / "skills"
    router.scaffold_router("iris-cpo", skills_root=skills_root)
    p = skills_root / "conclave-iris-cpo" / "SKILL.md"
    _enrich(p)
    info = router.scaffold_router("iris-cpo", skills_root=skills_root, force=True)
    assert "## Scope" not in p.read_text()  # force re-render drops enrichment
    assert info == {"id": "iris-cpo", "skill": str(p)}
