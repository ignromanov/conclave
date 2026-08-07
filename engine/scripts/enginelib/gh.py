"""enginelib.gh — thin wrappers around the gh CLI for issue queries.

Public API (taxonomy lock):
  gh_advisor_issues(advisor, repo) -> list[str]
  gh_global_p0(repo) -> list[str]

Each row: "#<number> | <title> | <space-joined label names>" (R-F2 format).
"""

import json
import os
import subprocess

from enginelib.advisors import advisor_label


def _gh_env() -> dict[str, str] | None:
    """Env for the gh call, or None to inherit.

    plugin.json declares `userConfig.GH_TOKEN` (sensitive) and commands/init.md promised the
    platform would expose it to engine subprocesses — but the platform exposes it as
    CLAUDE_PLUGIN_OPTION_GH_TOKEN, and gh honours only GH_TOKEN/GITHUB_TOKEN. Nothing bridged the
    two, so the declared setting did nothing and every call silently used whatever ambient
    `gh auth` session happened to exist. With no plugin token configured we inherit, so plain
    `gh auth login` keeps working.

    Precedence caveat: an already-set GH_TOKEN *or* GITHUB_TOKEN suppresses the bridge. Those
    two are not equally deliberate — GITHUB_TOKEN is injected automatically by GitHub Actions
    and commonly exported by devcontainers and direnv. In any of those environments a user who
    fills in the plugin's GH_TOKEN setting has it silently ignored in favour of the ambient one,
    which is the same "declared setting does nothing" shape this function exists to fix.
    """
    token = os.environ.get("CLAUDE_PLUGIN_OPTION_GH_TOKEN", "").strip()
    if not token or os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"):
        return None
    return {**os.environ, "GH_TOKEN": token}


def _run_gh(args: list[str]) -> str:
    """Thin seam: call gh with *args, return stdout. Raises RuntimeError on failure."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True, env=_gh_env())
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout


def _parse_rows(json_str: str) -> list[str]:
    issues = json.loads(json_str)
    rows = []
    for issue in issues:
        number = issue["number"]
        title = issue["title"]
        labels = " ".join(label["name"] for label in issue["labels"])
        rows.append(f"#{number} | {title} | {labels}")
    return rows


def gh_advisor_issues(advisor: str, repo: str) -> list[str]:
    """Open issues labeled advisor:<advisor> in repo. Returns formatted rows."""
    args = [
        "issue", "list",
        "-R", repo,
        "--label", advisor_label(advisor),
        "--state", "open",
        "--json", "number,title,labels",
    ]
    return _parse_rows(_run_gh(args))


def search_issues(advisor: str, repos: list[str]) -> str:
    # TRIPWIRE — sole `gh search issues` call site (lifecycle gh snapshot).
    # Fail-closed on privacy: scope by explicit --repo slugs, NEVER account-wide
    # (--owner). An empty repo list is a caller bug — refuse rather than leak
    # every repo the account owns into this instance's memory tree (#50).
    if not repos:
        raise ValueError("search_issues requires at least one repo scope (privacy)")
    repo_args = [arg for repo in repos for arg in ("--repo", repo)]
    return _run_gh([
        "search", "issues",
        *repo_args,
        "--label", advisor_label(advisor),
        "--state", "open",
        "--json", "number,title,labels,state,repository",
        "--limit", "50",
    ])


def search_closed_by_labels(advisor: str, repos: list[str], sticky_labels: list[str]) -> str:
    """Closed issues labelled advisor:<id> AND a sticky label, as one JSON array.

    One `gh search issues --state closed` per sticky label (AND within a call, OR
    across labels), results de-duped by issue number. Keeps closed "sticky" issues
    (e.g. grants) visible in briefings without pulling every closed issue (#7).
    Empty `sticky_labels` → "[]" (no gh call). Scope by explicit --repo, never
    account-wide (#50 privacy — same fail-closed contract as search_issues).
    """
    if not repos:
        raise ValueError("search_closed_by_labels requires at least one repo scope (privacy)")
    repo_args = [arg for repo in repos for arg in ("--repo", repo)]
    seen: dict[int, dict] = {}
    for sticky in sticky_labels:
        raw = _run_gh([
            "search", "issues",
            *repo_args,
            "--label", advisor_label(advisor),
            "--label", sticky,
            "--state", "closed",
            "--json", "number,title,labels,state,repository",
            "--limit", "50",
        ])
        for issue in json.loads(raw):
            seen[issue["number"]] = issue
    return json.dumps(list(seen.values()))


def gh_global_p0(repo: str) -> list[str]:
    """Open p0 issues in repo. Returns formatted rows."""
    args = [
        "issue", "list",
        "-R", repo,
        "--label", "p0",
        "--state", "open",
        "--json", "number,title,labels",
    ]
    return _parse_rows(_run_gh(args))


def create_issue(title: str, body: str, labels: list[str]) -> None:
    """Create a GitHub issue via the gh CLI (routes through _run_gh seam)."""
    _run_gh([
        "issue", "create",
        "--title", title,
        "--body", body,
        *(x for label in labels for x in ("--label", label)),
    ])
