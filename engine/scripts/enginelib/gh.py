"""enginelib.gh — thin wrappers around the gh CLI for issue queries.

Public API (taxonomy lock):
  gh_advisor_issues(advisor, repo) -> list[str]
  gh_global_p0(repo) -> list[str]

Each row: "#<number> | <title> | <space-joined label names>" (R-F2 format).
"""

import json
import subprocess


def _run_gh(args: list[str]) -> str:
    """Thin seam: call gh with *args, return stdout. Raises RuntimeError on failure."""
    result = subprocess.run(["gh", *args], capture_output=True, text=True)
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
        "--label", f"advisor:{advisor}",
        "--state", "open",
        "--json", "number,title,labels",
    ]
    return _parse_rows(_run_gh(args))


def search_issues(label_stem: str, repos: list[str]) -> str:
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
        "--label", f"advisor:{label_stem}",
        "--state", "open",
        "--json", "number,title,labels,state,repository",
        "--limit", "50",
    ])


def search_closed_by_labels(label_stem: str, repos: list[str], sticky_labels: list[str]) -> str:
    """Closed issues labelled advisor:<stem> AND a sticky label, as one JSON array.

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
            "--label", f"advisor:{label_stem}",
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
