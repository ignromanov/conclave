"""The code repo a briefing reports is the instance's, not the one the process stands in (#314).

An advisor on safe-unfollow opened a session and read ten commits under "Recent commits" that
belong to the *engine* repository. The reporter shipped a control with the probe, which is why
this is a measurement and not an impression: `git cat-file -e cb605ff` fails in the product repo
and succeeds in the engine's. The section is not stale and not empty — it is reading a different
repository and labelling the result as this project's recent work.

Re-measured on master before changing anything, by calling `_detect_code_root` against the
reporting instance's live DATA root from five working directories:

    cwd = the product checkout   -> the product repo    feat(seo): publish the IndexNow key ...
    cwd = the engine checkout    -> the ENGINE repo     docs(contracts): the glyph carries ...
    cwd = an engine worktree     -> the WORKTREE        fix(status): the glyph carries ...
    cwd = an unrelated library   -> that LIBRARY        fix(types): emit resolution-correct ...
    cwd = the DATA repo itself   -> None

The second line is the live briefing: all four of the reporting instance's advisors carried the
engine's HEAD subject at the head of their "Recent commits", and one additionally reported
`docs/architecture/lifecycle.md` — a file that exists only in the engine. The fourth line is the
part the issue's title states and its mechanism section under-sells: the guard rejects exactly one
wrong answer, so *any* repository on the machine can be reported, not just the engine.

WHY THE FIX IS NOT THE ONE THE ISSUE PROPOSES. The issue says to resolve from "the DATA root's
parent, the same derivation `CONCLAVE_AI_ROOT` already uses". The parent is the right *place* but
the wrong *rule*: `project_root()` derives it with a name test (`root.name == ".conclave"`) while
`repo_root()` identifies a DATA root by a marker — `roster.yaml` beside a real `ops/` and a
`.claude/` — precisely because the name is not the invariant. The pre-split layout's is `ai/`, and a
name test answers with the DATA root itself for it.

So the derivation here is name-free and positive: **the instance's code repo is the git repository
that contains the DATA root**. `git rev-parse --show-toplevel` from the DATA root's parent answers
that for every layout including deeper nesting, needs no name, and cannot be moved by the process
cwd. Measured on the four live instances reachable from this checkout, the DATA root is a real
directory (no symlinks) inside its project repo in 4 of 4 cases; after the change, three of them
resolve to their own repository from all five working directories above — 15 of 15 cells.

WHY THE EXISTING TESTS WERE GREEN THROUGHOUT. `tests/briefing/test_scans_2_4.py` builds
`ai_root = tmp/ai` and `code_root = tmp/code` as **siblings** and chdirs into the second. That is
a topology no instance has: it puts the DATA root outside the project, so the only thing that could
connect them is the cwd — and the fixture then supplies the right cwd. Seven tests passed on a
shape that does not exist, and none of them could fail on the shape that does. Those fixtures are
re-nested in this change rather than left beside these tests, because two fixtures disagreeing
about where a DATA root lives is how the next reader decides which one to trust.

WHAT THIS DELIBERATELY GIVES UP: in a git worktree of the instance's own repo, the section now
reports the main checkout rather than the worktree's branch. That is a change, and it is the one
wanted here — the briefing is built by `session_init.py` at session start, before any worktree is
chosen, and "what has just landed" is a property of the instance's repository, not of whichever
directory the process happens to occupy. `test_a_worktree_of_the_instance_repo_reports_the_repo`
pins it so the choice is visible rather than incidental.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from briefing.scans import ScanCtx, code_repo

pytestmark = pytest.mark.usefixtures("_no_ambient_roots")


@pytest.fixture
def _no_ambient_roots(monkeypatch: pytest.MonkeyPatch) -> None:
    """No inherited root may reach this module: every answer must come from the fixture."""
    for var in ("CONCLAVE_AI_ROOT", "CLAUDE_PROJECT_DIR", "CONCLAVE_GIT_REMOTE_CWD"):
        monkeypatch.delenv(var, raising=False)


def _git(repo: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )
    return out.stdout.strip()


def _repo(path: Path, subject: str) -> Path:
    """A git repo whose single commit subject identifies it uniquely."""
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", str(path)], check=True, capture_output=True)
    _git(path, "config", "user.email", "test@test.com")
    _git(path, "config", "user.name", "Test")
    (path / "seed.txt").write_text(subject + "\n", encoding="utf-8")
    _git(path, "add", "seed.txt")
    _git(path, "commit", "-m", subject)
    return path


def _ctx(data: Path, product: Path, advisor: str = "kai-cto") -> ScanCtx:
    return ScanCtx(
        advisor=advisor,
        short_name=advisor.split("-")[0],
        repo_root=data,
        decisions_dir=data / "agent-memory" / "advisors" / "decisions",
        sessions_dir=data / "agent-memory" / "advisors" / "sessions",
        mentions_dir=data / "agent-memory" / "advisors" / "mentions",
        gh_cache_dir=data / "agent-memory" / "gh-cache",
        personality_path=data / ".claude" / "personality.md",
        project_root=product,
        plans_dir=data / ".claude" / "plans",
    )


class Topology:
    """The three-repo shape a real instance has, which the live instance cannot show.

    On conclave-self the DATA root's parent *is* the checkout the process stands in, so the
    defect and the fix produce the same answer there. Only a synthetic tree separates them.
    """

    def __init__(self, tmp_path: Path) -> None:
        self.product = _repo(tmp_path / "product", "product: the only commit in the product")
        self.data = _repo(self.product / ".conclave", "data: the only commit in DATA")
        for name in ("ops", ".claude"):
            (self.data / name).mkdir(exist_ok=True)
        (self.data / "roster.yaml").write_text("advisors: []\n", encoding="utf-8")
        self.engine = _repo(tmp_path / "engine", "engine: the only commit in the engine")
        self.elsewhere = _repo(tmp_path / "elsewhere", "elsewhere: an unrelated repository")
        self.plain = tmp_path / "plain"
        self.plain.mkdir()

    def ctx(self, advisor: str = "kai-cto") -> ScanCtx:
        return _ctx(self.data, self.product, advisor)

    def every_cwd(self) -> list[tuple[str, Path]]:
        return [
            ("the product checkout", self.product),
            ("the engine checkout", self.engine),
            ("an unrelated repository", self.elsewhere),
            ("the DATA repo itself", self.data),
            ("a non-git directory", self.plain),
        ]


@pytest.fixture
def topo(tmp_path: Path) -> Topology:
    return Topology(tmp_path)


# ------------------------------------------------------------------ the fixture's own control


def test_the_fixture_is_three_mutually_unreachable_repositories(topo: Topology) -> None:
    """The reporter's control, rebuilt: a commit of one repo must not resolve in another.

    Without this the tests below could all pass against three views of one repository.
    """
    heads = {
        name: _git(repo, "rev-parse", "HEAD")
        for name, repo in (
            ("product", topo.product), ("engine", topo.engine), ("elsewhere", topo.elsewhere)
        )
    }
    assert len(set(heads.values())) == 3, heads
    for owner, sha in heads.items():
        for name, repo in (
            ("product", topo.product), ("engine", topo.engine), ("elsewhere", topo.elsewhere)
        ):
            found = subprocess.run(
                ["git", "-C", str(repo), "cat-file", "-e", sha],
                capture_output=True,
            ).returncode == 0
            assert found is (owner == name), f"{sha[:7]} of {owner} resolvable in {name}"


# ------------------------------------------------------------------------------- the detector


def test_the_answer_is_the_same_from_every_working_directory(
    topo: Topology, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The invariant, stated as an equivalence rather than five expectations.

    Five hand-written expectations can be wrong in the same direction; "the process cwd does
    not enter the answer" cannot be satisfied by a detector that reads it.
    """
    answers = {}
    for label, cwd in topo.every_cwd():
        monkeypatch.chdir(cwd)
        answers[label] = code_repo._detect_code_root(topo.data)
    assert set(answers.values()) == {topo.product.resolve()}, answers


def test_the_engine_checkout_is_not_the_instances_code_repo(
    topo: Topology, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The reported defect, reproduced: engine commits under a product advisor's briefing."""
    monkeypatch.chdir(topo.engine)
    rendered = code_repo.build(topo.ctx())
    assert "product: the only commit in the product" in rendered
    assert "engine:" not in rendered, rendered


def test_an_unrelated_repository_is_not_the_instances_code_repo(
    topo: Topology, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The general case the single negative guard misses — any repo, not only the engine."""
    monkeypatch.chdir(topo.elsewhere)
    rendered = code_repo.build(topo.ctx())
    assert "product: the only commit in the product" in rendered
    assert "elsewhere:" not in rendered, rendered


def test_standing_in_the_data_repo_no_longer_hides_the_code_repo(
    topo: Topology, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absence was a claim about the cwd, not about the instance.

    On master this rendered the placeholder — "no code repo in cwd" — which reads as *this
    project has no code repo* while the code repo is the directory the DATA root sits in.
    """
    monkeypatch.chdir(topo.data)
    rendered = code_repo.build(topo.ctx())
    assert "product: the only commit in the product" in rendered
    assert "data:" not in rendered, rendered


def test_an_instance_outside_any_git_repo_gets_the_placeholder(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The placeholder still has a job — and it is now a fact about the instance.

    The cwd is a perfectly good git repo, and that is exactly what must not rescue the answer.
    """
    loose = tmp_path / "loose" / ".conclave"
    loose.mkdir(parents=True)
    elsewhere = _repo(tmp_path / "elsewhere", "elsewhere: an unrelated repository")
    monkeypatch.chdir(elsewhere)
    assert code_repo._detect_code_root(loose) is None
    assert code_repo.build(_ctx(loose, loose.parent)) == code_repo._PLACEHOLDER


def test_a_worktree_of_the_instance_repo_reports_the_repo(
    topo: Topology, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The deliberate loss, pinned. A worktree reports its repository, not its own branch."""
    wt = topo.product.parent / "wt"
    _git(topo.product, "worktree", "add", "-b", "side", str(wt))
    (wt / "side.txt").write_text("side\n", encoding="utf-8")
    _git(wt, "add", "side.txt")
    _git(wt, "commit", "-m", "side: a commit that exists only on the worktree branch")

    monkeypatch.chdir(wt)
    rendered = code_repo.build(topo.ctx())
    assert "product: the only commit in the product" in rendered
    assert "side:" not in rendered, rendered


# ------------------------------------------------------------------------------ the docs scan


def test_the_docs_scan_reads_the_instances_docs_not_the_cwds(
    topo: Topology, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The second half of the section had the same source and the same defect.

    On the reporting instance one advisor's briefing named `docs/architecture/lifecycle.md`,
    which exists in the engine and not in the product.
    """
    for repo, name in ((topo.product, "product-only.md"), (topo.engine, "engine-only.md")):
        (repo / "docs").mkdir(exist_ok=True)
        (repo / "docs" / name).write_text("x\n", encoding="utf-8")

    monkeypatch.chdir(topo.engine)
    rendered = code_repo.build(topo.ctx())
    assert "docs/product-only.md" in rendered
    assert "engine-only.md" not in rendered, rendered
