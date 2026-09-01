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


def test_nomination_names_the_consumer_that_can_act(tmp_path):
    """The routing line must name 091 L1, the only consumer that exists.

    It shipped naming `spec 090 L2/L3`, which is a design-locked stub blocked on the 089
    oracle — every nomination flowed into a dead end while spec 093's own frontmatter and
    docs/architecture/engine-modules.md both named 091. The old test asserted the file count
    and echoed the observation, so it was true either way and never saw this.
    """
    noms = [{"feedback_id": "fb-1", "item_id": "it-1", "fingerprint": "abcdef1234",
             "observation": "path resolution fails", "category": "script-defect"}]
    text = write_nominations(noms, out_dir=tmp_path)[0].read_text()
    assert "091" in text
    assert "090" not in text


def test_colliding_slugs_get_distinct_files(tmp_path):
    """Two findings sharing the first 48 slug characters must not share a filename."""
    common = "the briefing builder resolves the wrong root when invoked from "
    noms = [
        {"feedback_id": "fb-1", "item_id": "it-1", "fingerprint": "aaaaaaaa11",
         "observation": common + "DATA", "category": "script-defect"},
        {"feedback_id": "fb-2", "item_id": "it-2", "fingerprint": "bbbbbbbb22",
         "observation": common + "CODE", "category": "script-defect"},
    ]
    paths = write_nominations(noms, out_dir=tmp_path)
    assert len({p.name for p in paths}) == 2
    assert len(list(tmp_path.glob("*.md"))) == 2


def test_existing_nomination_is_never_overwritten(tmp_path):
    """The `target:` line is operator work; a re-sweep must not erase it (G-7)."""
    nom = {"feedback_id": "fb-1", "item_id": "it-1", "fingerprint": "abcdef1234",
           "observation": "path resolution fails", "category": "script-defect"}
    written = write_nominations([nom], out_dir=tmp_path)[0]
    written.write_text(written.read_text().replace("TBD (skill | contract | briefing)", "skill"))

    again = write_nominations([nom], out_dir=tmp_path)

    assert again == [], "a preserved nomination must not be reported as newly written"
    assert "- target: skill" in written.read_text()


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


def _run_verify(root: Path, extra: list[str],
                env_extra: dict[str, str] | None = None) -> _sp.CompletedProcess:
    env = {"PYTHONPATH": str(_SCRIPTS), "CONCLAVE_AI_ROOT": str(root),
           "PATH": "/usr/bin:/bin"}
    # The env is built from scratch, not inherited, so a test that needs a second root
    # (e.g. #170's CONCLAVE_ENGINE_ROOT) has to name it here rather than export it.
    env.update(env_extra or {})
    return _sp.run(
        [_sys.executable, str(_FEEDBACK / "feedback_verify.py"), *extra],
        capture_output=True, text=True, env=env,
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


def _setverify_layout(tmp_path, target_text: str | None = "still has the BUG\n"):
    """Checkout layout for --set-verify: DATA root under .conclave, predicate target a
    sibling at the checkout root. `target_text=None` leaves the target absent."""
    data_root = tmp_path / ".conclave"
    if target_text is not None:
        (tmp_path / "foo.py").write_text(target_text)
    path = _write_review_file(data_root, "sage-setverify.md", _accepted_no_verify_meta())
    return data_root, path


def test_set_verify_attaches_predicate(tmp_path):
    """--set-verify attaches a predicate to an accepted item via the sanctioned write
    path; the finalized frontmatter stays schema-valid (093 P1 T3)."""
    data_root, path = _setverify_layout(tmp_path)
    res = _run_verify(data_root, ["--set-verify", "fb-sv-aaaaaa", "i1", "grep-absent",
                                  "--file", "foo.py", "--pattern", "BUG"])
    assert res.returncode == 0, res.stderr
    from briefing.frontmatter_io import read_commented
    from feedback.schema import Review
    meta2, _ = read_commented(path)
    item = next(i for i in meta2["items"] if i["id"] == "i1")
    assert item["verify"]["kind"] == "grep-absent"
    assert item["verify"]["pattern"] == "BUG"
    Review.model_validate(meta2)  # re-validates cleanly


# --- #165: the admission test on a freshly authored predicate ---

def test_set_verify_refuses_a_predicate_that_already_passes(tmp_path):
    """A predicate that passes the moment it is attached auto-closes its item on the
    next sweep with nothing fixed. That manufactures a resolution, and afterwards a
    false close is indistinguishable from a real one — so it is refused at the door."""
    data_root, path = _setverify_layout(tmp_path, "the fix already landed\n")
    res = _run_verify(data_root, ["--set-verify", "fb-sv-aaaaaa", "i1", "grep-absent",
                                  "--file", "foo.py", "--pattern", "BUG"])
    assert res.returncode == 1
    assert "already passes" in res.stderr

    from briefing.frontmatter_io import read_commented
    item = next(i for i in read_commented(path)[0]["items"] if i["id"] == "i1")
    assert "verify" not in item, "a refused predicate must not be written"


def test_set_verify_refuses_a_predicate_born_broken(tmp_path):
    """Shape validation cannot see an unreadable target. Attaching one gives the item a
    predicate that reports BROKEN on every sweep and can never close it — the state the
    103 move left two of 093's own predicates in, unnoticed for seven weeks."""
    data_root, _ = _setverify_layout(tmp_path, target_text=None)
    res = _run_verify(data_root, ["--set-verify", "fb-sv-aaaaaa", "i1", "grep-absent",
                                  "--file", "foo.py", "--pattern", "BUG"])
    assert res.returncode == 1
    assert "cannot be evaluated" in res.stderr


def test_set_verify_force_attaches_an_already_passing_predicate(tmp_path):
    """--force is the escape hatch for the honest case: the item really is resolved and
    the operator wants the sweep to close it on the record rather than by hand."""
    data_root, path = _setverify_layout(tmp_path, "the fix already landed\n")
    res = _run_verify(data_root, ["--set-verify", "fb-sv-aaaaaa", "i1", "grep-absent",
                                  "--file", "foo.py", "--pattern", "BUG", "--force"])
    assert res.returncode == 0, res.stderr

    from briefing.frontmatter_io import read_commented
    item = next(i for i in read_commented(path)[0]["items"] if i["id"] == "i1")
    assert item["verify"]["pattern"] == "BUG"


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


# --- #165: the fuel gauge on the accepted pool ---

def test_predicate_coverage_counts_only_the_accepted_pool():
    """`accepted` is the pool the sweep drains; a predicate on anything else is not fuel."""
    from feedback_verify import predicate_coverage
    rows = [
        {"status": "accepted", "verify": {"kind": "file-absent", "path": "x"}},
        {"status": "accepted"},
        {"status": "accepted", "verify_waiver": "no file-readable oracle"},
        {"status": "deferred", "verify": {"kind": "file-absent", "path": "y"}},
        {"status": "resolved", "verify": {"kind": "file-absent", "path": "z"}},
    ]
    assert predicate_coverage(rows) == (1, 1, 3)


def test_a_waiver_never_counts_as_coverage():
    """A waiver says the item can never close mechanically. Folding it into the covered
    count would report the loop as fuelled by the very items it can never drain."""
    from feedback_verify import predicate_coverage
    rows = [{"status": "accepted", "verify_waiver": "judgement call"} for _ in range(5)]
    covered, waived, accepted_n = predicate_coverage(rows)
    assert (covered, waived, accepted_n) == (0, 5, 5)


# --- #170: a predicate may name the CODE tree, which in plugin mode is not under the project ---

import pytest as _pytest


def _plugin_layout(tmp_path, target_text: str = "still has the BUG\n"):
    """Plugin-mode topology: the DATA root sits under the operator's project, and the
    engine distribution (engine/, skills/, commands/) is a separate checkout entirely.

    This is the supported distribution mode, and it is the one the dogfooding instance
    cannot exhibit: there the project root IS the CODE checkout, so both roots name the
    same directory and a single-root resolver looks correct.

    Returns (data_root, code_root, review_path)."""
    data_root = tmp_path / "project" / ".conclave"
    code_root = tmp_path / "plugin"
    src = code_root / "engine" / "scripts" / "feedback"
    src.mkdir(parents=True)
    (src / "thing.py").write_text(target_text)
    path = _write_review_file(data_root, "sage-setverify.md", _accepted_no_verify_meta())
    return data_root, code_root, path


def test_code_predicate_is_broken_when_resolved_against_the_project(tmp_path):
    """The defect. With one root for every predicate, an engine-layer target lies outside
    the project on any instance where the engine is a separate checkout, containment
    refuses it, and the #165 accept-gate is left with nothing but a waiver — which is the
    unfalsifiable self-report that gate exists to prevent."""
    _plugin_layout(tmp_path)
    assert classify_predicate(
        Predicate(kind="grep-absent", file="engine/scripts/feedback/thing.py",
                  pattern="BUG"), root=tmp_path / "project") == "broken"


def test_code_predicate_resolves_against_the_code_root(tmp_path):
    """root='code' resolves against the engine distribution root instead, so the same
    predicate becomes an oracle again: `fail` while the bug is there, `pass` once it is
    gone."""
    _, code_root, _ = _plugin_layout(tmp_path)
    project = tmp_path / "project"
    p = Predicate(kind="grep-absent", file="engine/scripts/feedback/thing.py",
                  pattern="BUG", root="code")
    assert classify_predicate(p, root=project, code_root=code_root) == "fail"
    (code_root / "engine" / "scripts" / "feedback" / "thing.py").write_text("fixed\n")
    assert classify_predicate(p, root=project, code_root=code_root) == "pass"


def test_predicate_root_defaults_to_project(tmp_path):
    """Back-compat: every predicate written before #170 carries no root and must keep
    resolving exactly where it did."""
    assert Predicate(kind="file-absent", path="x").root == "project"
    (tmp_path / "here.py").write_text("BUG\n")
    assert classify_predicate(
        Predicate(kind="grep-absent", file="here.py", pattern="BUG"), root=tmp_path) == "fail"


def test_code_predicate_containment_holds_against_the_code_root(tmp_path):
    """T6 is re-based, never widened: a traversal out of the CODE root is refused, and
    so is one that would land inside the project root. Two allowed trees, not a
    filesystem-wide read oracle."""
    _, code_root, _ = _plugin_layout(tmp_path)
    project = tmp_path / "project"
    (tmp_path / "sibling.txt").write_text("PWNED\n")
    assert classify_predicate(
        Predicate(kind="file-contains", file="../sibling.txt", pattern="PWNED",
                  root="code"), root=project, code_root=code_root) == "broken"


def test_code_predicate_without_a_code_root_raises(tmp_path):
    """A caller that cannot say where the CODE tree is has a wiring bug, not a rotted
    predicate. Raise rather than fold to 'broken': a silent degradation here is the exact
    shape of the defect being fixed."""
    with _pytest.raises(ValueError, match="code_root"):
        classify_predicate(
            Predicate(kind="grep-absent", file="a.py", pattern="x", root="code"),
            root=tmp_path)


def test_sweep_evaluates_code_rows_against_the_code_root(tmp_path):
    """End to end: a CODE-rooted row auto-closes on the sweep that runs from the DATA
    root, with the project and the engine in different trees."""
    _, code_root, _ = _plugin_layout(tmp_path, target_text="fixed\n")
    rows = [{"feedback_id": "fb-1", "item_id": "i1", "status": "accepted",
             "verify": {"kind": "grep-absent", "root": "code",
                        "file": "engine/scripts/feedback/thing.py", "pattern": "BUG"}}]
    res = sweep(rows, tmp_path / "project", code_root=code_root)
    assert res.auto_close == [("fb-1", "i1")]
    assert res.broken == []


def test_set_verify_attaches_a_code_root_predicate(tmp_path):
    """The operator-facing path: `--root code` gets an engine-layer predicate past the
    admission test on an instance where the engine is not under the project."""
    data_root, code_root, path = _plugin_layout(tmp_path)
    res = _run_verify(data_root, ["--set-verify", "fb-sv-aaaaaa", "i1", "grep-absent",
                                  "--file", "engine/scripts/feedback/thing.py",
                                  "--pattern", "BUG", "--root", "code"],
                      env_extra={"CONCLAVE_ENGINE_ROOT": str(code_root / "engine")})
    assert res.returncode == 0, res.stderr

    from briefing.frontmatter_io import read_commented
    from feedback.schema import Review
    meta, _ = read_commented(path)
    item = next(i for i in meta["items"] if i["id"] == "i1")
    assert item["verify"]["root"] == "code"
    Review.model_validate(meta)


def test_set_verify_without_root_code_still_refuses_an_engine_target(tmp_path):
    """The same attach without `--root code` is refused as born-broken — the refusal an
    operator on a plugin instance hits today on every engine-layer item."""
    data_root, code_root, _ = _plugin_layout(tmp_path)
    res = _run_verify(data_root, ["--set-verify", "fb-sv-aaaaaa", "i1", "grep-absent",
                                  "--file", "engine/scripts/feedback/thing.py",
                                  "--pattern", "BUG"],
                      env_extra={"CONCLAVE_ENGINE_ROOT": str(code_root / "engine")})
    assert res.returncode == 1
    assert "cannot be evaluated" in res.stderr


# --- #160: a close must rest on evidence that shipped, not on the working tree ---

import subprocess as _subprocess


def _git_checkout_layout(tmp_path, committed: str):
    """A real git checkout holding the predicate target, with .conclave as its DATA root.

    The existing --apply tests run in a plain tmp dir, which is not a repo at all — so
    they exercise the 'installed tree' branch and say nothing about this one."""
    checkout = tmp_path / "checkout"
    (checkout / "engine").mkdir(parents=True)
    target = checkout / "engine" / "x.py"
    target.write_text(committed)
    for args in (("init", "-q", "-b", "main"), ("config", "user.email", "t@t"),
                 ("config", "user.name", "t"), ("add", "engine/x.py"),
                 ("commit", "-qm", "seed")):
        _subprocess.run(["git", "-C", str(checkout), *args], check=True,
                        capture_output=True, text=True)
    data_root = checkout / ".conclave"
    path = _write_review_file(data_root, "sage-checkout.md", _checkout_layout_meta())
    return data_root, target, path


def test_apply_holds_a_close_whose_evidence_is_only_in_the_working_tree(tmp_path):
    """The measured defect: the fix is on disk and in no commit, the predicate reads it
    as done, and --apply would record `resolved` against work that may never merge.
    Abandoning the branch would leave a permanently, silently false closure."""
    data_root, target, path = _git_checkout_layout(tmp_path, "no marker yet\n")
    target.write_text("# MARKER: the fix landed\n")   # uncommitted

    res = _run_verify(data_root, ["--apply"])
    assert res.returncode == 0, res.stderr

    from briefing.frontmatter_io import read_commented
    status = read_commented(path)[0]["items"][0]["status"]
    assert status == "accepted", "closed on evidence that exists in no commit"
    assert "HELD" in res.stderr, f"a held close must be reported by name\n{res.stderr}"
    assert "held-unshipped=1" in res.stdout


def test_apply_closes_once_the_evidence_is_committed(tmp_path):
    """The other half: holding must not be a permanent block. The same item closes as
    soon as the work lands, which is what makes 'held' a wait rather than a refusal."""
    data_root, target, path = _git_checkout_layout(tmp_path, "no marker yet\n")
    target.write_text("# MARKER: the fix landed\n")
    _subprocess.run(["git", "-C", str(target.parent.parent), "commit", "-qam", "fix"],
                    check=True, capture_output=True, text=True)

    res = _run_verify(data_root, ["--apply"])
    assert res.returncode == 0, res.stderr

    from briefing.frontmatter_io import read_commented
    status = read_commented(path)[0]["items"][0]["status"]
    assert status == "resolved", f"{res.stdout}{res.stderr}"
    assert "held-unshipped=0" in res.stdout
