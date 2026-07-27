"""tests/cmd/test_lifecycle_gh_fetch.py — integration tests for `engine lifecycle gh-fetch`.

Hermetic: bare tmp_path (NOT ai_root). Uses CONCLAVE_AI_ROOT + PATH seams for isolation.
Port of engine/scripts/tests/lifecycle/gh-fetch.bats (10 cases).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from tests.cmd.helpers import make_git_repo, non_repo_dir, run_engine

# helpers.py lives at engine/scripts/tests/cmd/helpers.py
# parents[0]=cmd  parents[1]=tests  parents[2]=scripts
_SCRIPTS_DIR = Path(__file__).resolve().parents[2]

_MOCK_GH_SCRIPT = """\
#!/usr/bin/env python3
import sys, os
sentinel = os.environ.get("GH_MOCK_SENTINEL")
if sentinel:
    with open(sentinel, "a") as f:
        f.write(" ".join(sys.argv[1:]) + "\\n")
print('[{"number":1,"title":"Upgrade Next.js to v16","labels":[{"name":"advisor:kai"}],"state":"open","repository":{"name":"main"}}]')
"""

# Fresh snapshot — >=100 bytes so staleness check passes.
_FRESH_BODY = (
    '---\ntype: gh-snapshot\nschema_version: 1\ntags: [op/gh-snapshot]\n'
    'advisor: kai-cto\ncaptured_at: "2026-06-27T00:00:00Z"\nttl_seconds: 3600\n'
    'source: gh search issues\n---\n\n# GH Snapshot — kai-cto\n\n'
    '```json\n[]\n```\n'
    'Content padding to exceed the 100-byte minimum size threshold for staleness check.\n'
)


def _setup_mock_gh(tmp: Path) -> None:
    bin_dir = tmp / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(_MOCK_GH_SCRIPT)
    gh.chmod(0o755)


def _env(tmp: Path) -> dict:
    return {
        "CONCLAVE_AI_ROOT": str(tmp),
        "SNAPSHOT_GH_TTL": "3600",
        "PATH": f"{tmp / 'bin'}:{os.environ['PATH']}",
        "GH_MOCK_SENTINEL": str(tmp / "gh-called.log"),
    }


def _seed_roster(tmp: Path, owner: str = "acme", ai_repo: str = "conclave") -> None:
    """Write a minimal roster.yaml so search scope resolves from config (layer 1),
    not the ambient git remote — keeps the argv assertion hermetic."""
    (tmp / "roster.yaml").write_text(
        f"github:\n  owner: {owner}\n  ai_repo: {ai_repo}\n  main_repo: null\n",
        encoding="utf-8",
    )


def _cache_path(tmp: Path, advisor: str = "kai-cto") -> Path:
    return tmp / "agent-memory" / "gh-cache" / f"{advisor}.md"


def _run_log_path(tmp: Path) -> Path:
    today = datetime.now(UTC).date().isoformat()
    return tmp / "agent-memory" / "run-log" / f"{today}.jsonl"


# ---------------------------------------------------------------------------
# 1. Fresh cache → exit 0 (cache hit).
# ---------------------------------------------------------------------------
def test_fresh_cache_returns_hit(tmp_path):
    _setup_mock_gh(tmp_path)
    cache = _cache_path(tmp_path)
    cache.parent.mkdir(parents=True, exist_ok=True)
    assert len(_FRESH_BODY.encode()) >= 100
    cache.write_text(_FRESH_BODY, encoding="utf-8")

    r = run_engine("lifecycle", "gh-fetch", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 0


# ---------------------------------------------------------------------------
# 2. No cache → exit 2, writes snapshot.
# ---------------------------------------------------------------------------
def test_no_cache_writes_snapshot_and_exits_2(tmp_path):
    _setup_mock_gh(tmp_path)
    cache = _cache_path(tmp_path)
    assert not cache.parent.exists()

    r = run_engine("lifecycle", "gh-fetch", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 2
    assert cache.exists()


# ---------------------------------------------------------------------------
# 3. --no-cache flag always re-fetches even with fresh cache → exit 2.
# ---------------------------------------------------------------------------
def test_no_cache_flag_forces_refetch(tmp_path):
    _setup_mock_gh(tmp_path)
    cache = _cache_path(tmp_path)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(_FRESH_BODY, encoding="utf-8")

    r = run_engine("lifecycle", "gh-fetch", "--advisor", "kai-cto", "--no-cache", env=_env(tmp_path))
    assert r.returncode == 2


# ---------------------------------------------------------------------------
# 4. Written snapshot has valid frontmatter (type, schema_version, advisor).
# ---------------------------------------------------------------------------
def test_frontmatter_valid(tmp_path):
    _setup_mock_gh(tmp_path)

    r = run_engine("lifecycle", "gh-fetch", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 2
    text = _cache_path(tmp_path).read_text(encoding="utf-8")
    assert "type: gh-snapshot" in text
    assert "schema_version: 1" in text
    assert "advisor: kai-cto" in text


# ---------------------------------------------------------------------------
# 5. Snapshot contains known substring from canned mock response.
# ---------------------------------------------------------------------------
def test_snapshot_contains_canned_content(tmp_path):
    _setup_mock_gh(tmp_path)

    r = run_engine("lifecycle", "gh-fetch", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 2
    assert "Upgrade Next.js" in _cache_path(tmp_path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 6. Run-log row appended; script "engine lifecycle gh-fetch"; advisor "kai-cto".
# ---------------------------------------------------------------------------
def test_run_log_row_script_name_and_advisor(tmp_path):
    _setup_mock_gh(tmp_path)

    r = run_engine("lifecycle", "gh-fetch", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 2

    log = _run_log_path(tmp_path)
    assert log.exists()
    rows = [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    matching = [row for row in rows if row.get("script") == "engine lifecycle gh-fetch"]
    assert matching, f"expected script='engine lifecycle gh-fetch' in run-log; got: {rows}"
    assert matching[-1].get("advisor") == "kai-cto", (
        f"expected advisor='kai-cto' in run-log; got: {matching[-1]}"
    )


# ---------------------------------------------------------------------------
# 7. TRIPWIRE comment present in enginelib/gh.py (the search_issues call site).
# ---------------------------------------------------------------------------
def test_tripwire_in_enginelib_gh():
    module = Path(__file__).resolve().parents[2] / "enginelib" / "gh.py"
    assert module.exists(), f"module not found: {module}"
    assert "# TRIPWIRE" in module.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 8. gh NOT called on cache hit (sentinel must be absent or empty).
# ---------------------------------------------------------------------------
def test_gh_not_called_on_cache_hit(tmp_path):
    _setup_mock_gh(tmp_path)
    cache = _cache_path(tmp_path)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(_FRESH_BODY, encoding="utf-8")
    sentinel = tmp_path / "gh-called.log"

    r = run_engine("lifecycle", "gh-fetch", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 0

    if sentinel.exists():
        lines = [ln for ln in sentinel.read_text().splitlines() if ln.strip()]
        assert len(lines) == 0, f"gh must not be called on cache hit; sentinel: {lines}"


# ---------------------------------------------------------------------------
# 8b. Concurrent invocations: gh called exactly once (lock coalescing).
# ---------------------------------------------------------------------------
def test_concurrent_lock_coalescing(tmp_path):
    _setup_mock_gh(tmp_path)
    cache = _cache_path(tmp_path)
    if cache.exists():
        cache.unlink()
    env = _env(tmp_path)
    sentinel = tmp_path / "gh-called.log"

    cmd = [sys.executable, "-m", "engine", "lifecycle", "gh-fetch", "--advisor", "kai-cto"]
    p1 = subprocess.Popen(cmd, cwd=str(_SCRIPTS_DIR), env={**os.environ, **env})
    p2 = subprocess.Popen(cmd, cwd=str(_SCRIPTS_DIR), env={**os.environ, **env})
    p1.wait()
    p2.wait()

    lines = []
    if sentinel.exists():
        lines = [ln for ln in sentinel.read_text().splitlines() if ln.strip()]
    assert len(lines) == 1, (
        f"expected gh called exactly once (first writer wins lock); sentinel lines: {lines}"
    )


# ---------------------------------------------------------------------------
# 9. Repo-scoped search, no --assignee, never account-wide (fb-1783285368 #50
#    privacy regression guard; supersedes the old org-wide --owner assertion).
# ---------------------------------------------------------------------------
def test_search_scoped_by_repo_not_account_wide(tmp_path):
    _setup_mock_gh(tmp_path)
    _seed_roster(tmp_path, owner="acme", ai_repo="conclave")
    sentinel = tmp_path / "gh-called.log"

    r = run_engine("lifecycle", "gh-fetch", "--advisor", "kai-cto", env=_env(tmp_path))
    assert r.returncode == 2

    assert sentinel.exists(), "sentinel not written — gh was not called"
    argv_line = sentinel.read_text().splitlines()[0]
    assert "search" in argv_line
    assert "issues" in argv_line
    assert "--label" in argv_line
    assert "advisor:kai" in argv_line
    assert "--state" in argv_line
    assert "open" in argv_line
    # Privacy: scope by repo, NEVER account-wide, and no --assignee.
    assert "--repo" in argv_line
    assert "acme/conclave" in argv_line
    assert "--owner" not in argv_line
    assert "--assignee" not in argv_line


# ---------------------------------------------------------------------------
# 9b. No repo scope configured (roster null + no git remote) → refuse:
#     warn, leave cache stale, and NEVER fall back to account-wide search.
# ---------------------------------------------------------------------------
def test_unscoped_refuses_account_wide_search(tmp_path):
    _setup_mock_gh(tmp_path)
    sentinel = tmp_path / "gh-called.log"
    # No roster.yaml seeded; pin git at a directory PROVEN to be outside any repository, so
    # the remote fallback yields nothing. Asserted rather than inherited from tmp_path's
    # location — see non_repo_dir.
    non_repo = non_repo_dir(tmp_path, "elsewhere")

    r = run_engine(
        "lifecycle", "gh-fetch", "--advisor", "kai-cto",
        env={**_env(tmp_path), "CONCLAVE_GIT_REMOTE_CWD": str(non_repo)},
    )
    assert r.returncode == 1
    assert "scope" in (r.stderr or "").lower()

    # gh must NOT have been called — no account-wide leak.
    if sentinel.exists():
        lines = [ln for ln in sentinel.read_text().splitlines() if ln.strip()]
        assert not lines, f"gh must not run without a repo scope; sentinel: {lines}"


# ---------------------------------------------------------------------------
# 10. resolve_repos() layering: roster (ai_repo/main_repo) → git remote → empty.
# ---------------------------------------------------------------------------
def _write_roster(tmp: Path, body: str, monkeypatch) -> None:
    roster_file = tmp / "roster.yaml"
    roster_file.write_text(body, encoding="utf-8")
    monkeypatch.setenv("ROSTER_FILE", str(roster_file))


def test_resolve_repos_prefers_roster_and_normalizes_bare_names(tmp_path, monkeypatch):
    from enginelib.lifecycle import gh_fetch
    _write_roster(
        tmp_path,
        "github:\n  owner: acme\n  ai_repo: conclave\n  main_repo: acme/product\n",
        monkeypatch,
    )
    monkeypatch.setattr(gh_fetch, "_git_remote_slug", lambda: "should/notused")
    # Bare name gets owner-prefixed; already-qualified slug passes through.
    assert gh_fetch.resolve_repos("acme") == ["acme/conclave", "acme/product"]


def test_resolve_repos_falls_back_to_git_remote_when_roster_null(tmp_path, monkeypatch):
    from enginelib.lifecycle import gh_fetch
    _write_roster(
        tmp_path,
        "github:\n  owner: acme\n  ai_repo: null\n  main_repo: null\n",
        monkeypatch,
    )
    monkeypatch.setattr(gh_fetch, "_git_remote_slug", lambda: "acme/conclave")
    assert gh_fetch.resolve_repos("acme") == ["acme/conclave"]


def test_resolve_repos_empty_when_no_roster_no_remote(tmp_path, monkeypatch):
    from enginelib.lifecycle import gh_fetch
    _write_roster(
        tmp_path,
        "github:\n  owner: acme\n  ai_repo: null\n  main_repo: null\n",
        monkeypatch,
    )
    monkeypatch.setattr(gh_fetch, "_git_remote_slug", lambda: "")
    assert gh_fetch.resolve_repos("acme") == []


def test_resolve_repos_drops_the_slug_a_null_owner_leaves_malformed(tmp_path, monkeypatch):
    """`owner: null` + a bare repo name built "/app" — a target gh accepts and no caller
    could tell apart from a real slug. It must not survive resolution.

    NOT coverage for the layer-1 refusal below: layer 2 is stubbed empty here, so this
    assertion passes whether layer 1 refuses or falls through to a dead end.
    """
    from enginelib.lifecycle import gh_fetch
    _write_roster(
        tmp_path,
        "github:\n  owner: null\n  ai_repo: null\n  main_repo: app\n",
        monkeypatch,
    )
    monkeypatch.setattr(gh_fetch, "_git_remote_slug", lambda: "")
    assert gh_fetch.resolve_repos("") == []


# ---------------------------------------------------------------------------
# 10b. Declared-nothing vs declared-and-unusable. An emptied layer 1 used to fall through
#      to the git remote, making an operator typo indistinguishable from a roster that
#      declared nothing — and hiding it behind a scope that happens to resolve.
#
#      Both tests below give layer 2 a WORKING remote. With a dead layer 2 neither can
#      tell refusal from fall-through, which is exactly how the existing malformed-case
#      test above passes against both behaviours.
# ---------------------------------------------------------------------------
def test_malformed_layer_1_refuses_even_when_the_git_remote_would_resolve(
    tmp_path, monkeypatch, capfd
):
    from enginelib.lifecycle import gh_fetch
    _write_roster(
        tmp_path,
        "github:\n  owner: null\n  ai_repo: null\n  main_repo: app\n",
        monkeypatch,
    )
    # Layer 2 is live and would yield a perfectly usable slug.
    consumer = make_git_repo(
        tmp_path / "consumer", origin="git@github.com:real-owner/real-repo.git"
    )
    monkeypatch.setenv("CONCLAVE_GIT_REMOTE_CWD", str(consumer))
    assert gh_fetch._git_remote_slug() == "real-owner/real-repo", (
        "layer 2 is not reachable, so this test cannot distinguish the two behaviours"
    )

    assert gh_fetch.resolve_repos("") == [], "fell through to the git remote"

    err = capfd.readouterr().err
    assert "github.main_repo" in err, f"diagnostic names no roster key:\n{err}"
    assert "'app'" in err, f"diagnostic does not quote the declared value:\n{err}"
    assert "'/app'" in err, f"diagnostic does not show what the value produced:\n{err}"
    assert "github.owner" in err, f"diagnostic omits the key actually at fault:\n{err}"


def test_declared_nothing_still_falls_through_to_the_git_remote(tmp_path, monkeypatch, capfd):
    """The other half of the ruling: a roster that names no repo keys is not a typo."""
    from enginelib.lifecycle import gh_fetch
    _write_roster(
        tmp_path,
        "github:\n  owner: acme\n  ai_repo: null\n  main_repo: null\n",
        monkeypatch,
    )
    consumer = make_git_repo(
        tmp_path / "consumer", origin="git@github.com:real-owner/real-repo.git"
    )
    monkeypatch.setenv("CONCLAVE_GIT_REMOTE_CWD", str(consumer))

    assert gh_fetch.resolve_repos("acme") == ["real-owner/real-repo"]
    assert capfd.readouterr().err == "", "a roster that declared nothing must not be scolded"


def test_mixed_declared_names_the_malformed_key_but_still_returns_the_usable_sibling(
    tmp_path, monkeypatch, capfd
):
    """The third case the ruling above distinguishes: one declared key malformed, the other
    usable. The typo must not hide behind the working sibling — but the run is not refused,
    so the diagnostic cannot reuse the all-malformed wording (that would claim a refusal that
    did not happen)."""
    from enginelib.lifecycle import gh_fetch
    _write_roster(
        tmp_path,
        "github:\n  owner: null\n  ai_repo: badrepo\n  main_repo: acme/product\n",
        monkeypatch,
    )
    monkeypatch.setattr(gh_fetch, "_git_remote_slug", lambda: "should/notused")

    assert gh_fetch.resolve_repos("") == ["acme/product"], (
        "the usable sibling must still be returned, not swallowed by the typo"
    )

    err = capfd.readouterr().err
    assert "github.ai_repo" in err, f"diagnostic names no roster key:\n{err}"
    assert "'badrepo'" in err, f"diagnostic does not quote the declared value:\n{err}"
    assert "'/badrepo'" in err, f"diagnostic does not show what the value produced:\n{err}"
    assert "github.owner" in err, f"diagnostic omits the key actually at fault:\n{err}"
    assert "acme/product" in err, (
        f"diagnostic does not name the scope the run continues with:\n{err}"
    )
    assert "refusing" not in err, (
        f"mixed case is not a refusal — reusing the all-malformed wording claims one falsely:\n{err}"
    )


def test_run_refuses_unscoped_rather_than_searching_a_null_owner_slug(tmp_path, monkeypatch):
    """The privacy contract holds on the malformed-slug path too: refuse, never search."""
    from enginelib import gh
    from enginelib.lifecycle import gh_fetch
    _write_roster(
        tmp_path,
        "github:\n  owner: null\n  ai_repo: null\n  main_repo: app\n",
        monkeypatch,
    )
    monkeypatch.setenv("CONCLAVE_AI_ROOT", str(tmp_path))
    monkeypatch.setattr(gh_fetch, "_git_remote_slug", lambda: "")
    searched: list[list[str]] = []
    monkeypatch.setattr(gh, "search_issues", lambda stem, repos: searched.append(repos) or "[]")

    assert gh_fetch.run("kai-cto", no_cache=True) == "unscoped"
    assert searched == [], f"gh was handed a malformed scope: {searched}"


def test_git_remote_slug_parses_ssh_and_https(monkeypatch):
    from enginelib.lifecycle import gh_fetch
    assert gh_fetch._parse_remote_slug("git@github.com:acme/conclave.git") == "acme/conclave"
    assert gh_fetch._parse_remote_slug("https://github.com/acme/conclave.git") == "acme/conclave"
    assert gh_fetch._parse_remote_slug("https://github.com/acme/conclave") == "acme/conclave"
    assert gh_fetch._parse_remote_slug("") == ""


def _capture_git_cwd(monkeypatch) -> dict:
    """Stub `git remote get-url origin` and record the cwd it was asked to run in."""
    from enginelib.lifecycle import gh_fetch
    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, "git@github.com:acme/project.git\n", "")

    monkeypatch.setattr(gh_fetch.subprocess, "run", fake_run)
    return seen


def test_git_remote_slug_defaults_to_the_project_dir_not_the_process_cwd(tmp_path, monkeypatch):
    """Unpinned, the fallback layer read whatever checkout the shell stood in. `gh-repos` is
    invoked straight from advisor command prose and pins nothing, so the default belongs here."""
    from enginelib.lifecycle import gh_fetch
    project = tmp_path / "project"
    monkeypatch.delenv("CONCLAVE_GIT_REMOTE_CWD", raising=False)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    seen = _capture_git_cwd(monkeypatch)

    assert gh_fetch._git_remote_slug() == "acme/project"
    assert seen["cwd"] == str(project), "git ran in the process cwd, not the consumer project"


def test_git_remote_slug_explicit_seam_still_wins_over_the_project_dir(tmp_path, monkeypatch):
    from enginelib.lifecycle import gh_fetch
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "project"))
    monkeypatch.setenv("CONCLAVE_GIT_REMOTE_CWD", str(tmp_path / "explicit"))
    seen = _capture_git_cwd(monkeypatch)

    gh_fetch._git_remote_slug()
    assert seen["cwd"] == str(tmp_path / "explicit")


# ---------------------------------------------------------------------------
# 11. Sticky labels (#7): CLOSED issues carrying a configured sticky label
#     (e.g. grant) stay visible in the snapshot; without the config, no closed
#     fetch runs. The label vocabulary lives in roster.yaml (instance), never
#     in the domain-agnostic engine core.
# ---------------------------------------------------------------------------
_MOCK_GH_STICKY = """\
#!/usr/bin/env python3
import sys, os
argv = sys.argv[1:]
sentinel = os.environ.get("GH_MOCK_SENTINEL")
if sentinel:
    with open(sentinel, "a") as f:
        f.write(" ".join(argv) + "\\n")
if "closed" in argv:
    print('[{"number":9,"title":"Grant: OP RetroPGF","labels":[{"name":"advisor:kai"},{"name":"grant"}],"state":"closed","repository":{"name":"main"}}]')
else:
    print('[{"number":1,"title":"Open task","labels":[{"name":"advisor:kai"}],"state":"open","repository":{"name":"main"}}]')
"""


def _setup_mock_gh_sticky(tmp: Path) -> None:
    bin_dir = tmp / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(_MOCK_GH_STICKY)
    gh.chmod(0o755)


def test_sticky_labels_keep_closed_grants_in_snapshot(tmp_path):
    _setup_mock_gh_sticky(tmp_path)
    (tmp_path / "roster.yaml").write_text(
        "github:\n  owner: acme\n  ai_repo: conclave\n  main_repo: null\n"
        "  sticky_labels: [grant]\n",
        encoding="utf-8",
    )
    r = run_engine("lifecycle", "gh-fetch", "--advisor", "kai-cto", "--no-cache", env=_env(tmp_path))
    assert r.returncode == 2

    snap = _cache_path(tmp_path).read_text()
    assert "OP RetroPGF" in snap, "closed grant issue missing from snapshot"
    assert "Open task" in snap, "open issue dropped when merging sticky closed"

    # A second gh search, --state closed, scoped to advisor:kai AND grant.
    log = (tmp_path / "gh-called.log").read_text()
    assert "closed" in log
    assert "grant" in log


def test_no_sticky_labels_skips_closed_fetch(tmp_path):
    _setup_mock_gh_sticky(tmp_path)
    _seed_roster(tmp_path, owner="acme", ai_repo="conclave")  # no sticky_labels key
    r = run_engine("lifecycle", "gh-fetch", "--advisor", "kai-cto", "--no-cache", env=_env(tmp_path))
    assert r.returncode == 2

    log = (tmp_path / "gh-called.log").read_text()
    assert "closed" not in log, "closed fetch ran without sticky_labels configured"
