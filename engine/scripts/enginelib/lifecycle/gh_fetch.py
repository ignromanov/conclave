"""enginelib.lifecycle.gh_fetch — TTL-cached GH issue snapshot writer.

Contract: no stdout, no argparse, no sys.exit.
Subprocess (via enginelib.gh) + clock + file I/O are allowed.
Port of lifecycle/gh-fetch.sh.

run(advisor, no_cache=False) -> "hit" | "refreshed" | "lock-error" | "gh-error" | "unscoped"
  "hit"        — valid cache exists and TTL not exceeded; no write.
  "refreshed"  — snapshot written (or force-rewritten with no_cache=True).
  "lock-error" — could not acquire mkdir-lock within 10s timeout.
  "gh-error"   — gh search failed or returned empty; cache left stale.
  "unscoped"   — no repo scope resolvable (roster null + no git remote); refused
                 rather than search account-wide; cache left stale (#50 privacy).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from enginelib import gh, roster, snapshot
from enginelib.paths import ensure_dir, snapshot_path_for_advisor

# owner/repo out of an ssh (git@host:owner/repo.git) or https URL, .git optional.
_REMOTE_SLUG_RE = re.compile(r"[:/]([^/:]+/[^/:]+?)(?:\.git)?/?$")


def _parse_remote_slug(url: str) -> str:
    """Extract 'owner/repo' from a git remote URL, or '' if it doesn't match."""
    match = _REMOTE_SLUG_RE.search(url.strip())
    return match.group(1) if match else ""


def _git_remote_slug() -> str:
    """'owner/repo' of the local origin remote, or '' if unavailable.

    Offline and deterministic (no network, unlike `gh repo view`). The cwd seam
    keeps the refuse-path test hermetic without shelling out to a real repo.
    """
    cwd = os.environ.get("CONCLAVE_GIT_REMOTE_CWD") or None
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=cwd,
        )
    except OSError:
        return ""
    if result.returncode != 0:
        return ""
    return _parse_remote_slug(result.stdout)


def resolve_repos(owner: str) -> list[str]:
    """Repo scope for the GH search, layered: roster → git remote → empty.

    Layer 1: github.ai_repo / github.main_repo from roster.yaml (bare names get
             owner-prefixed; already-qualified 'owner/repo' slugs pass through).
    Layer 2: the local origin remote's 'owner/repo'.
    Layer 3: empty — caller must refuse (fail-closed), never account-wide (#50).
    """
    repos: list[str] = []
    for key in ("github.ai_repo", "github.main_repo"):
        value = roster.roster_get(key).strip()
        if value:
            repos.append(value if "/" in value else f"{owner}/{value}")
    if repos:
        return repos
    slug = _git_remote_slug()
    return [slug] if slug else []


def _merge_issue_json(open_json: str, closed_json: str) -> str:
    """Concatenate two gh JSON arrays, de-duped by issue number (open wins on clash)."""
    seen: dict[int, dict] = {}
    for raw in (closed_json, open_json):  # open applied last → open wins on dup number
        try:
            for issue in json.loads(raw):
                seen[issue["number"]] = issue
        except (ValueError, KeyError, TypeError):
            continue
    return json.dumps(list(seen.values()))


def run(advisor: str, no_cache: bool = False) -> str:
    """Snapshot GH issues for an advisor to a TTL-cached .md file.

    Returns a status string: "hit", "refreshed", "lock-error", "gh-error", or "unscoped".
    """
    ttl = int(os.environ.get("SNAPSHOT_GH_TTL", "900"))
    owner = roster.roster_get("github.owner")
    cache_path = snapshot_path_for_advisor("gh", advisor)
    ensure_dir(cache_path.parent)

    # First hit check (no lock needed — read-only).
    if not no_cache and not snapshot.snapshot_is_stale(cache_path, ttl):
        return "hit"

    # Resolve the repo scope BEFORE taking the lock or hitting gh. Fail-closed:
    # with no scope we refuse rather than search account-wide (#50 privacy leak).
    repos = resolve_repos(owner)
    if not repos:
        return "unscoped"

    # Acquire mkdir-lock before fetch to prevent concurrent double-fetch.
    lock_dir = Path(f"{cache_path}.lock")
    if not snapshot.acquire_lock(lock_dir, 10):
        return "lock-error"

    try:
        # Re-check after acquiring lock: another writer may have refreshed while we waited.
        if not no_cache and not snapshot.snapshot_is_stale(cache_path, ttl):
            return "hit"

        # Map canonical advisor id (e.g. kai-cto) → GH label stem (advisor:kai).
        stem = advisor.split("-")[0]

        try:
            issues_json = gh.search_issues(stem, repos)
        except RuntimeError:
            return "gh-error"

        # Distinguish a gh failure from a genuine empty result: a failed call yields
        # an empty string; a successful empty query yields the literal "[]". On failure,
        # exit WITHOUT writing — never mask an error as "no issues".
        if not issues_json.strip():
            return "gh-error"

        # Keep CLOSED issues carrying an instance-configured sticky label (e.g.
        # grants) visible in the snapshot (#7). Best-effort: a failed closed fetch
        # must never sink the open snapshot. Empty config → no gh call, raw open
        # JSON preserved byte-for-byte (no reserialization for the common path).
        sticky_labels = roster.roster_get_list("github.sticky_labels")
        if sticky_labels:
            try:
                closed_json = gh.search_closed_by_labels(stem, repos, sticky_labels)
            except (RuntimeError, ValueError):
                closed_json = "[]"
            issues_json = _merge_issue_json(issues_json, closed_json)

        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        issues_json = issues_json.rstrip("\n")

        body = (
            f"---\n"
            f"type: gh-snapshot\n"
            f"schema_version: 1\n"
            f"tags: [op/gh-snapshot]\n"
            f"advisor: {advisor}\n"
            f'captured_at: "{now_iso}"\n'
            f"ttl_seconds: {ttl}\n"
            f"source: gh search issues\n"
            f"---\n"
            f"\n"
            f"# GH Snapshot — {advisor}\n"
            f"\n"
            f"```json\n"
            f"{issues_json}\n"
            f"```\n"
        )

        snapshot.snapshot_write(cache_path, body)
        return "refreshed"
    finally:
        snapshot.release_lock(lock_dir)
