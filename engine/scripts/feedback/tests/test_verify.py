from pathlib import Path

from feedback_verify import evaluate_predicate

from feedback.schema import Predicate


def test_grep_absent_true_when_pattern_gone(tmp_path: Path):
    f = tmp_path / "gh.sh"
    f.write_text("gh issue list --state all\n")
    p = Predicate(kind="grep-absent", file=str(f), pattern="--state open")
    assert evaluate_predicate(p, root=tmp_path) is True


def test_grep_absent_false_when_pattern_present(tmp_path: Path):
    f = tmp_path / "gh.sh"
    f.write_text("gh issue list --state open\n")
    p = Predicate(kind="grep-absent", file=str(f), pattern="--state open")
    assert evaluate_predicate(p, root=tmp_path) is False


def test_grep_absent_false_when_file_missing(tmp_path: Path):
    # missing file => cannot confirm resolution => False (conservative)
    p = Predicate(kind="grep-absent", file="nope.sh", pattern="x")
    assert evaluate_predicate(p, root=tmp_path) is False


def test_file_contains_true(tmp_path: Path):
    f = tmp_path / "a.py"
    f.write_text("def verify(): pass\n")
    p = Predicate(kind="file-contains", file=str(f), pattern="def verify")
    assert evaluate_predicate(p, root=tmp_path) is True


def test_file_absent_true_when_gone(tmp_path: Path):
    p = Predicate(kind="file-absent", path="ghost.sh")
    assert evaluate_predicate(p, root=tmp_path) is True


def test_file_absent_false_when_present(tmp_path: Path):
    (tmp_path / "real.sh").write_text("x")
    p = Predicate(kind="file-absent", path="real.sh")
    assert evaluate_predicate(p, root=tmp_path) is False


# --- Task 3: sweep classifier ---

from feedback_verify import sweep


def _row(**o):
    base = dict(feedback_id="fb-1", item_id="it-1", status="accepted",
                severity="high", frequency="every-dispatch", hit_count=5,
                category="script-defect", observation="o", verify=None)
    base.update(o)
    return base


def test_sweep_auto_closes_passing_predicate(tmp_path):
    f = tmp_path / "x.sh"
    f.write_text("--state all\n")
    rows = [_row(verify={"kind": "grep-absent", "file": str(f), "pattern": "--state open"})]
    res = sweep(rows, root=tmp_path)
    assert ("fb-1", "it-1") in res.auto_close
    assert not res.llm_candidates


def test_sweep_evaluates_predicates_beyond_the_candidate_cap(tmp_path):
    """Spec 093: predicate items are ALWAYS evaluated; only the LLM-candidate tail is
    capped at `limit`. A predicate-carrying row sitting AFTER `limit` predicate-less
    rows must still be evaluated (predicate eval is cheap + deterministic) — it must not
    be starved by the cap that exists to bound the expensive LLM-sweep. On a real store
    with a >40 accepted backlog this starvation is what makes a green predicate close 0."""
    f = tmp_path / "x.sh"
    f.write_text("--state all\n")  # grep-absent '--state open' => passes
    rows = [_row(feedback_id=f"fb-noise-{i}", item_id="it-1", frequency="occasional",
                 verify=None) for i in range(45)]
    rows.append(_row(feedback_id="fb-green", item_id="it-1", frequency="occasional",
                     verify={"kind": "grep-absent", "file": str(f), "pattern": "--state open"}))
    res = sweep(rows, root=tmp_path, limit=40)
    assert ("fb-green", "it-1") in res.auto_close, "predicate beyond the cap was starved"
    assert len(res.llm_candidates) == 40, f"LLM tail not capped at limit: {len(res.llm_candidates)}"


def test_sweep_routes_prose_only_to_candidates(tmp_path):
    rows = [_row(verify=None)]
    res = sweep(rows, root=tmp_path)
    assert res.auto_close == []
    assert ("fb-1", "it-1") in res.llm_candidates


def test_sweep_skips_non_accepted(tmp_path):
    rows = [_row(status="deferred", verify=None)]
    res = sweep(rows, root=tmp_path)
    assert not res.auto_close and not res.llm_candidates


def test_sweep_nominates_recurring_high_freq_cluster(tmp_path):
    rows = [_row(hit_count=3, frequency="every-dispatch", severity="high")]
    res = sweep(rows, root=tmp_path)
    assert res.nominations  # one cluster nominated


def test_sweep_no_nomination_below_threshold(tmp_path):
    rows = [_row(hit_count=2, frequency="every-dispatch", severity="high")]
    res = sweep(rows, root=tmp_path)
    assert not res.nominations


# --- Task 4: writers ---

from feedback_verify import write_candidates_digest, write_nominations


def test_write_candidates_digest_creates_file(tmp_path):
    out = write_candidates_digest(
        [("fb-1", "it-1")], {("fb-1", "it-1"): "umami path wrong"},
        out_dir=tmp_path, date="2026-06-11")
    assert out.exists()
    assert "fb-1" in out.read_text()


def test_write_nominations_one_file_per_cluster(tmp_path):
    noms = [{"feedback_id": "fb-1", "item_id": "it-1",
             "observation": "path resolution fails", "category": "script-defect"}]
    paths = write_nominations(noms, out_dir=tmp_path)
    assert len(paths) == 1 and paths[0].exists()
    assert "path resolution fails" in paths[0].read_text()


# --- 093 P1 T2: archive-aware hit_count + fingerprint-deduped nominations ---

from feedback_verify import _derive_hit_counts


def test_derive_hit_counts_folds_in_archive(tmp_path):
    """hit_count counts occurrences across live + archived rows on one fingerprint,
    so recidivism that already resolved is not undercounted (critic #3)."""
    live = [_row(feedback_id="fb-a", fingerprint="ff"),
            _row(feedback_id="fb-b", status="open", fingerprint="ff")]
    archived = [{"fingerprint": "ff"}]
    counts = _derive_hit_counts(live, archived)
    assert counts["ff"] == 3  # 2 live + 1 archived


def test_sweep_dedupes_nominations_by_fingerprint(tmp_path):
    """3 rows sharing a fingerprint yield ONE nomination, not one per row (critic #4)."""
    rows = [_row(feedback_id=f"fb-{i}", item_id="it-1", hit_count=3, fingerprint="ff")
            for i in range(3)]
    res = sweep(rows, root=tmp_path)
    assert len(res.nominations) == 1


# --- 093 P1 T4: --apply auto-close is serialized + reconciles the index ---

import json as _json
import subprocess as _sp
import sys as _sys

_SCRIPTS = Path(__file__).parent.parent.parent
_FEEDBACK = Path(__file__).parent.parent


def _run_verify(root: Path, extra: list[str]) -> _sp.CompletedProcess:
    return _sp.run(
        [_sys.executable, str(_FEEDBACK / "feedback_verify.py"), *extra],
        capture_output=True, text=True,
        env={"PYTHONPATH": str(_SCRIPTS), "CONCLAVE_AI_ROOT": str(root),
             "PATH": "/usr/bin:/bin"},
    )


def _write_review_file(root: Path, filename: str, meta: dict) -> Path:
    from briefing.frontmatter_io import write
    d = root / "ops" / "feedback" / "2026-07-10"
    d.mkdir(parents=True, exist_ok=True)
    p = d / filename
    write(p, meta, "")
    return p


def _apply_item(i: int) -> dict:
    return {"id": f"i{i}", "category": "script-defect", "layer": "skill",
            "location": {"file": f"f{i}.py"}, "observation": "o", "suggested_fix": "x",
            "severity": "high", "frequency": "occasional", "evidence": "tc:1",
            "status": "accepted", "verify": {"kind": "file-absent", "path": f"ghost{i}.sh"}}


def _accepted_no_verify_meta() -> dict:
    return {"feedback_id": "fb-sv-aaaaaa", "agent": "sage-cto", "agent_type": "advisor",
            "session_ref": "s1", "skill_version": "sha256:aabbcc",
            "created": "2026-07-10T00:00:00Z", "updated_at": "2026-07-10T00:00:00Z",
            "_draft": False, "summary": "t", "below_threshold_count": 0,
            "items": [{"id": "i1", "category": "script-defect", "layer": "skill",
                       "location": {"file": "foo.py"}, "observation": "o",
                       "suggested_fix": "x", "severity": "high", "frequency": "occasional",
                       "evidence": "tc:1", "status": "accepted"}]}


def test_set_verify_attaches_predicate(tmp_path):
    """--set-verify attaches a predicate to an accepted item via the sanctioned write
    path; the finalized frontmatter stays schema-valid (093 P1 T3)."""
    path = _write_review_file(tmp_path, "sage-setverify.md", _accepted_no_verify_meta())
    res = _run_verify(tmp_path, ["--set-verify", "fb-sv-aaaaaa", "i1", "grep-absent",
                                 "--file", "foo.py", "--pattern", "BUG"])
    assert res.returncode == 0, res.stderr
    from briefing.frontmatter_io import read_commented
    from feedback.schema import Review
    meta2, _ = read_commented(path)
    item = next(i for i in meta2["items"] if i["id"] == "i1")
    assert item["verify"]["kind"] == "grep-absent"
    assert item["verify"]["pattern"] == "BUG"
    Review.model_validate(meta2)  # re-validates cleanly


def _checkout_layout_meta() -> dict:
    return {"feedback_id": "fb-cr-aaaaaa", "agent": "sage-cto", "agent_type": "advisor",
            "session_ref": "s1", "skill_version": "sha256:aabbcc",
            "created": "2026-07-10T00:00:00Z", "updated_at": "2026-07-10T00:00:00Z",
            "_draft": False, "summary": "t", "below_threshold_count": 0,
            "items": [{"id": "i1", "category": "script-defect", "layer": "skill",
                       "location": {"file": "engine/x.py"}, "observation": "o",
                       "suggested_fix": "x", "severity": "high", "frequency": "occasional",
                       "evidence": "tc:1", "status": "accepted",
                       "verify": {"kind": "file-contains",
                                  "file": "engine/x.py", "pattern": "MARKER"}}]}


def test_apply_resolves_predicate_target_at_checkout_root(tmp_path):
    """Predicate paths are checkout-relative. After the 103 code/data split the DATA
    root is <checkout>/.conclave, but predicate targets (engine code, repo-root docs)
    live at the checkout root — a SIBLING of .conclave. The sweep must resolve them
    against the checkout root, not the .conclave DATA root, or no code-backlog item can
    ever auto-close (its target resolves to a non-existent .conclave/engine/... path)."""
    checkout = tmp_path
    data_root = checkout / ".conclave"
    (checkout / "engine").mkdir(parents=True)
    (checkout / "engine" / "x.py").write_text("# MARKER: the fix landed\n")
    path = _write_review_file(data_root, "sage-checkout.md", _checkout_layout_meta())
    res = _run_verify(data_root, ["--apply"])
    assert res.returncode == 0, res.stderr

    from briefing.frontmatter_io import read_commented
    meta2, _ = read_commented(path)
    status = meta2["items"][0]["status"]
    assert status == "resolved", (
        f"predicate target at checkout root not resolved (still {status}); "
        f"sweep resolved against the .conclave DATA root, not the checkout root\n"
        f"{res.stdout}{res.stderr}")


def test_apply_closes_all_items_and_reconciles_index(tmp_path):
    """--apply auto-closes all predicate-true items in one review with zero lost
    writes AND rebuilds the index after the batch (no stale/phantom accepted rows)."""
    meta = {"feedback_id": "fb-app-aaaaaa", "agent": "sage-cto", "agent_type": "advisor",
            "session_ref": "s1", "skill_version": "sha256:aabbcc",
            "created": "2026-07-10T00:00:00Z", "updated_at": "2026-07-10T00:00:00Z",
            "_draft": False, "summary": "t", "below_threshold_count": 0,
            "items": [_apply_item(1), _apply_item(2), _apply_item(3)]}
    path = _write_review_file(tmp_path, "sage-apply.md", meta)
    res = _run_verify(tmp_path, ["--apply"])
    assert res.returncode == 0, res.stderr

    from briefing.frontmatter_io import read_commented
    meta2, _ = read_commented(path)
    file_status = {i["id"]: i["status"] for i in meta2["items"]}
    assert file_status == {"i1": "resolved", "i2": "resolved", "i3": "resolved"}, \
        f"review-file lost a write: {file_status}\n{res.stdout}{res.stderr}"

    index = tmp_path / "ops" / "feedback" / "_index" / "index.jsonl"
    rows = [_json.loads(line) for line in index.read_text().splitlines() if line.strip()]
    idx_status = {r["item_id"]: r["status"] for r in rows}
    assert idx_status == {"i1": "resolved", "i2": "resolved", "i3": "resolved"}, \
        f"index not reconciled after batch (phantom rows): {idx_status}"


# --- Task A (105 killgate): a rotted / escaping predicate is `broken`, not False ---

from feedback_verify import classify_predicate


def test_classify_pass_fail_broken_for_grep_absent(tmp_path):
    f = tmp_path / "gh.sh"
    f.write_text("gh issue list --state all\n")
    # pattern gone => resolved
    assert classify_predicate(
        Predicate(kind="grep-absent", file=str(f), pattern="--state open"), tmp_path) == "pass"
    # pattern still present => not done yet
    assert classify_predicate(
        Predicate(kind="grep-absent", file=str(f), pattern="--state all"), tmp_path) == "fail"


def test_classify_broken_when_target_file_missing(tmp_path):
    """A grep-absent/file-contains predicate whose target file does not exist is BROKEN
    (cannot READ the oracle) — distinct from `fail` (fix not done). This is the 2 rotted
    predicates whose 103-moved target vanished; they must not read as permanent backlog."""
    assert classify_predicate(
        Predicate(kind="grep-absent", file="gone.md", pattern="x"), tmp_path) == "broken"
    assert classify_predicate(
        Predicate(kind="file-contains", file="gone.py", pattern="x"), tmp_path) == "broken"


def test_classify_file_absent_missing_path_is_pass_not_broken(tmp_path):
    """file-absent: a missing target is the SUCCESS condition, never broken."""
    assert classify_predicate(
        Predicate(kind="file-absent", path="ghost.sh"), tmp_path) == "pass"
    (tmp_path / "real.sh").write_text("x")
    assert classify_predicate(
        Predicate(kind="file-absent", path="real.sh"), tmp_path) == "fail"


def test_classify_broken_on_absolute_path_escape(tmp_path):
    """Containment (T6): an absolute path OUTSIDE the project root is refused as broken,
    never read — no filesystem-wide read oracle."""
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("SECRET\n")
    try:
        assert classify_predicate(
            Predicate(kind="file-contains", file=str(outside), pattern="SECRET"),
            root=tmp_path / "proj") == "broken"
    finally:
        outside.unlink(missing_ok=True)


def test_classify_broken_on_dotdot_traversal(tmp_path):
    """Containment (T6): a `../../..` traversal escaping the project root is refused."""
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "sibling.txt").write_text("PWNED\n")
    assert classify_predicate(
        Predicate(kind="file-contains", file="../sibling.txt", pattern="PWNED"),
        root=root) == "broken"
    # file-absent must also refuse a traversal (no external oracle laundering)
    assert classify_predicate(
        Predicate(kind="file-absent", path="../../etc/nonexistent-xyz"),
        root=root) == "broken"


def test_evaluate_predicate_bool_folds_broken_to_false(tmp_path):
    """The bool wrapper is preserved for existing callers: broken folds to False (a
    broken predicate never auto-closes an item)."""
    assert evaluate_predicate(
        Predicate(kind="grep-absent", file="gone.md", pattern="x"), tmp_path) is False


def test_sweep_routes_broken_predicate_distinctly(tmp_path):
    """A broken predicate is surfaced in SweepResult.broken — never auto-closed, and NOT
    routed to llm_candidates (it already has a predicate; it just rotted)."""
    rows = [_row(verify={"kind": "grep-absent", "file": "vanished.md", "pattern": "x"})]
    res = sweep(rows, root=tmp_path)
    assert res.auto_close == []
    assert ("fb-1", "it-1") not in res.llm_candidates
    assert any((fid, iid) == ("fb-1", "it-1") for fid, iid, _rel in res.broken), res.broken


def test_sweep_escaping_predicate_is_broken_not_closed(tmp_path):
    """A file-absent predicate pointing outside the root would pass VACUOUSLY (the path is
    absent inside the tree) — containment routes it to broken instead of a false close."""
    rows = [_row(verify={"kind": "file-absent", "path": "/nonexistent/abs/ghost.sh"})]
    res = sweep(rows, root=tmp_path)
    assert res.auto_close == [], "escaping file-absent must NOT auto-close vacuously"
    assert any((fid, iid) == ("fb-1", "it-1") for fid, iid, _rel in res.broken), res.broken
