import pathlib

from enginelib import gh

FIXTURES = pathlib.Path(__file__).parent.parent / "fixtures"
# Inert: every test below monkeypatches `gh._run_gh`, so this slug is never resolved against
# GitHub — it only has to be shaped like one. A real slug here published the origin instance's
# private repo into a public tree for no test benefit at all (#194).
REPO = "example-owner/example-ai"


def _fixture_json() -> str:
    return (FIXTURES / "gh_issue_list.json").read_text()


def _empty_json() -> str:
    return "[]"


# Case 1 (bats): gh_advisor_issues returns rows containing #37 and "grant"
def test_gh_advisor_issues_nexus(monkeypatch):
    monkeypatch.setattr(gh, "_run_gh", lambda _args: _fixture_json())
    rows = gh.gh_advisor_issues("nexus", REPO)
    combined = "\n".join(rows)
    assert "#37" in combined
    assert "grant" in combined


# Case 2 (bats): gh_advisor_issues empty result returns []
def test_gh_advisor_issues_empty(monkeypatch):
    monkeypatch.setattr(gh, "_run_gh", lambda _args: _empty_json())
    rows = gh.gh_advisor_issues("ghost", REPO)
    assert rows == []


# Case 3 (bats): gh_global_p0 returns rows containing #58 and #37
def test_gh_global_p0_returns_rows(monkeypatch):
    monkeypatch.setattr(gh, "_run_gh", lambda _args: _fixture_json())
    rows = gh.gh_global_p0(REPO)
    combined = "\n".join(rows)
    assert "#58" in combined
    assert "#37" in combined


# Case 4 (bats): gh_global_p0 empty result returns []
def test_gh_global_p0_empty(monkeypatch):
    monkeypatch.setattr(gh, "_run_gh", lambda _args: _empty_json())
    rows = gh.gh_global_p0(REPO)
    assert rows == []


# R-F2 lock: exact byte-identical row for issue #37
def test_r_f2_exact_row_format(monkeypatch):
    monkeypatch.setattr(gh, "_run_gh", lambda _args: _fixture_json())
    rows = gh.gh_advisor_issues("nexus", REPO)
    row_37 = next(r for r in rows if r.startswith("#37"))
    assert row_37 == "#37 | [grant] OTF | grant p1 advisor:nexus"


# #50 privacy: search_issues scopes by --repo per slug, never account-wide (--owner).
def test_search_issues_scopes_by_repo_not_owner(monkeypatch):
    captured = {}
    monkeypatch.setattr(gh, "_run_gh", lambda args: captured.setdefault("args", args) or "[]")
    gh.search_issues("kai", ["acme/conclave", "acme/product"])
    args = captured["args"]
    assert "--owner" not in args
    assert args.count("--repo") == 2
    assert "acme/conclave" in args
    assert "acme/product" in args
    assert "advisor:kai" in args


# #204: the snapshot must carry the field its consumer renders. queue.py has formatted an
# "updated <N>d ago" suffix since spec 084, and search_issues has never requested the field
# it reads — 0 of 50 items in the live cache carry it, so the enrichment has never rendered.
def test_search_issues_requests_the_field_the_queue_renders(monkeypatch):
    captured = {}
    monkeypatch.setattr(gh, "_run_gh", lambda args: captured.setdefault("args", args) or "[]")
    gh.search_issues("kai", ["acme/conclave"])
    json_fields = captured["args"][captured["args"].index("--json") + 1].split(",")
    assert "updatedAt" in json_fields, (
        f"queue.py renders issue age from this field; the producer never asks for it: {json_fields}"
    )


# #204: a cap that is never disclosed is indistinguishable from a complete list. The live
# instance had 74 open issues for one advisor and a snapshot of exactly 50.
def test_search_issues_limit_is_above_the_measured_queue(monkeypatch):
    captured = {}
    monkeypatch.setattr(gh, "_run_gh", lambda args: captured.setdefault("args", args) or "[]")
    gh.search_issues("kai", ["acme/conclave"])
    limit = int(captured["args"][captured["args"].index("--limit") + 1])
    assert limit >= 200, f"--limit {limit} silently truncates a real advisor queue"


# #50 privacy: empty repo list is fail-closed — refuse rather than search account-wide.
def test_search_issues_refuses_empty_repos(monkeypatch):
    called = []
    monkeypatch.setattr(gh, "_run_gh", lambda args: called.append(args) or "[]")
    import pytest
    with pytest.raises(ValueError):
        gh.search_issues("kai", [])
    assert called == [], "gh must not be invoked without a repo scope"


# ---------------------------------------------------------------------------
# H5 — the manifest's userConfig.GH_TOKEN must actually reach gh
# ---------------------------------------------------------------------------

class _Recorder:
    """Stand-in for subprocess.run that captures the kwargs _run_gh passes."""

    def __init__(self):
        self.kwargs = None

    def __call__(self, cmd, **kwargs):
        import subprocess

        self.kwargs = kwargs
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="[]", stderr="")


def _record(monkeypatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setattr(gh.subprocess, "run", rec)
    return rec


def test_plugin_option_token_is_promoted_to_gh_token(monkeypatch):
    """plugin.json declares userConfig.GH_TOKEN and commands/init.md promises it reaches engine
    subprocesses — but gh only honours GH_TOKEN/GITHUB_TOKEN, and nothing bridged the two."""
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_GH_TOKEN", "tok-from-plugin-config")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    rec = _record(monkeypatch)
    gh._run_gh(["issue", "list"])

    assert rec.kwargs.get("env") is not None, "gh inherited the ambient env — token not bridged"
    assert rec.kwargs["env"]["GH_TOKEN"] == "tok-from-plugin-config"


def test_explicit_gh_token_is_never_overridden(monkeypatch):
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_GH_TOKEN", "tok-from-plugin-config")
    monkeypatch.setenv("GH_TOKEN", "tok-the-user-set")

    rec = _record(monkeypatch)
    gh._run_gh(["issue", "list"])

    env = rec.kwargs.get("env")
    assert env is None or env["GH_TOKEN"] == "tok-the-user-set"


def test_no_plugin_token_leaves_gh_auth_alone(monkeypatch):
    """With nothing configured, gh must fall through to the user's own `gh auth` session."""
    monkeypatch.delenv("CLAUDE_PLUGIN_OPTION_GH_TOKEN", raising=False)
    monkeypatch.delenv("GH_TOKEN", raising=False)
    # GITHUB_TOKEN too: it is exported by GitHub Actions, devcontainers and direnv, and it
    # short-circuits _gh_env() the same way GH_TOKEN does. Left set, this passes for the
    # wrong reason on any such machine.
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    rec = _record(monkeypatch)
    gh._run_gh(["issue", "list"])

    assert rec.kwargs.get("env") is None


def test_whitespace_only_plugin_token_is_not_bridged(monkeypatch):
    """A settings field the user opened and left blank must not become an empty GH_TOKEN —
    that would authenticate as nobody instead of falling through to `gh auth`."""
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_GH_TOKEN", "   \t ")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    rec = _record(monkeypatch)
    gh._run_gh(["issue", "list"])

    assert rec.kwargs.get("env") is None


def test_ambient_github_token_alone_suppresses_the_bridge(monkeypatch):
    """Documented precedence, pinned: GITHUB_TOKEN counts as explicit even with no GH_TOKEN."""
    monkeypatch.setenv("CLAUDE_PLUGIN_OPTION_GH_TOKEN", "tok-from-plugin-config")
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "tok-from-the-ambient-environment")

    rec = _record(monkeypatch)
    gh._run_gh(["issue", "list"])

    assert rec.kwargs.get("env") is None
