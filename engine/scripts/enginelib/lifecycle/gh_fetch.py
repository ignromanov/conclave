"""enginelib.lifecycle.gh_fetch — TTL-cached GH issue snapshot writer.

Contract: no stdout, no argparse, no sys.exit. Subprocess (via enginelib.gh) + clock +
file I/O are allowed, as is a stderr diagnostic — `resolve_repos()` names a malformed
roster key whenever one occurs, whether that leaves the scope refused outright or just
missing that one key, and the *reason* is the whole point: neither an empty return nor a
scope quietly short one key lets a caller reconstruct it from the return value alone.
Port of lifecycle/gh-fetch.sh.

run(advisor, no_cache=False) -> "hit" | "refreshed" | "lock-error" | "gh-error" | "unscoped"
  "hit"        — valid cache exists and TTL not exceeded; no write.
  "refreshed"  — snapshot written (or force-rewritten with no_cache=True).
  "lock-error" — could not acquire mkdir-lock within 10s timeout.
  "gh-error"   — gh search failed or returned empty; cache left stale.
  "unscoped"   — no usable repo scope (roster declared none and no git remote, or
                 roster declared one that resolve_repos refused as malformed); refused
                 rather than search account-wide; cache left stale (#50 privacy).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from enginelib import gh, roster, snapshot
from enginelib.paths import consumer_git_cwd, ensure_dir, snapshot_path_for_advisor


def _label_for(advisor: str) -> str:
    """The id this advisor's issues are labelled with.

    Was `advisor.split("-")[0]`. GitHub matches labels exactly, so querying
    `advisor:kai` for `kai-cto` returned nothing, forever, without an error —
    the snapshot then cached that empty result as fact.
    """
    return advisor

# owner/repo out of an ssh (git@host:owner/repo.git) or https URL, .git optional.
_REMOTE_SLUG_RE = re.compile(r"[:/]([^/:]+/[^/:]+?)(?:\.git)?/?$")

# A usable GH scope: exactly two non-empty, slash-free halves. Guards the half the
# verb did not cover — a null `github.owner` made `f"{owner}/{repo}"` yield "/app",
# which gh accepts as a search target and no caller could tell apart from a real slug.
_SLUG_RE = re.compile(r"^[^/\s]+/[^/\s]+$")


def _parse_remote_slug(url: str) -> str:
    """Extract 'owner/repo' from a git remote URL, or '' if it doesn't match."""
    match = _REMOTE_SLUG_RE.search(url.strip())
    return match.group(1) if match else ""


def _git_remote_slug() -> str:
    """'owner/repo' of the local origin remote, or '' if unavailable.

    Offline and deterministic (no network, unlike `gh repo view`). The cwd seam
    keeps the refuse-path test hermetic without shelling out to a real repo.

    The default is CLAUDE_PROJECT_DIR, not the process cwd: this fallback layer must
    read the CONSUMER project's origin, and a caller inheriting an arbitrary shell cwd
    would read whatever checkout the operator happened to stand in. Defaulting inside
    `consumer_git_cwd()` rather than at a call site covers every caller by construction —
    `engine lifecycle gh-repos` is invoked straight from advisor command prose and pins
    nothing itself. `git-fetch` reads the same resolver, so the two cannot drift.
    """
    cwd = consumer_git_cwd()
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
    Layer 2: the local origin remote's 'owner/repo' — consulted ONLY when layer 1
             declared nothing at all.
    Layer 3: empty — caller must refuse (fail-closed), never account-wide (#50).

    Every slug is shape-checked before it leaves: a null `github.owner` prefixes a bare
    repo name into "/app", which is not a repo and must not reach gh. Dropping it here
    rather than at a caller keeps both consumers — `run()` and `gh-repos` — on one rule.

    **Declared-nothing, declared-and-unusable, and declared-mixed are three different facts.**
    A roster naming no repo keys falls through to the git remote — silently, since there is
    nothing to report. A roster that names one or more keys and NONE survive the shape check
    is an operator TYPO with no usable scope at all: refuse (return `[]`) and name every key
    and value that failed, rather than substituting the git remote and hiding the typo behind
    a scope that happens to work. A roster that names two keys where only one is malformed is
    ALSO a typo, but not a fatal one — the working sibling is real and gets used, so the run
    is not refused; the malformed key is still named on stderr, because a sibling that happens
    to work must not let a typo travel silently. Fail-closed only when nothing declared
    survives; the stderr diagnostic fires whenever a declared key is malformed, independent of
    whether another declared key is usable.
    """
    owner = owner.strip()
    declared: list[tuple[str, str, str]] = []  # (roster key, raw value, built slug)
    for key in ("github.ai_repo", "github.main_repo"):
        value = roster.roster_get(key).strip()
        if value:
            declared.append((key, value, value if "/" in value else f"{owner}/{value}"))

    usable = [slug for _, _, slug in declared if _SLUG_RE.match(slug)]
    malformed = [(key, value, slug) for key, value, slug in declared if not _SLUG_RE.match(slug)]

    for key, value, slug in malformed:
        # A bare name depends on github.owner, so say what owner was when it failed —
        # that is the actual typo in the common case, and it is not in `key`.
        detail = "" if "/" in value else (
            f" with github.owner {'unset' if not owner else repr(owner)}"
        )
        if usable:
            # A sibling key survived: not a refusal, so the sentence must say what actually
            # happens next, not the all-malformed wording — that would claim a refusal that
            # did not occur.
            sys.stderr.write(
                f"roster: {key}: {value!r}{detail} yields {slug!r}, which is not a repo — "
                f"ignoring it and continuing with the usable scope {', '.join(usable)}. "
                f"Fix roster.yaml.\n"
            )
        else:
            sys.stderr.write(
                f"roster: {key}: {value!r}{detail} yields {slug!r}, which is not a repo — "
                f"refusing the declared scope rather than substituting your git remote, "
                f"which would hide the typo. Fix roster.yaml.\n"
            )

    if usable:
        return usable

    if declared:
        return []

    slug = _git_remote_slug()
    return [slug] if _SLUG_RE.match(slug) else []


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


def _hit_the_cap(issues_json: str) -> bool:
    """True when the open-issue search returned exactly as many rows as it asked for.

    That is the only signal available that more exist: `gh search` reports no total. The
    answer can be a false positive on a queue of exactly SEARCH_LIMIT, which is the safe
    direction — over-disclosing a cap costs one line, under-disclosing it hides work."""
    try:
        return len(json.loads(issues_json)) >= gh.SEARCH_LIMIT
    except (json.JSONDecodeError, TypeError):
        return False


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

        label_id = _label_for(advisor)

        try:
            issues_json = gh.search_issues(label_id, repos)
        except RuntimeError:
            return "gh-error"
        open_json = issues_json

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
                closed_json = gh.search_closed_by_labels(label_id, repos, sticky_labels)
            except (RuntimeError, ValueError):
                closed_json = "[]"
            issues_json = _merge_issue_json(issues_json, closed_json)

        now_iso = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        issues_json = issues_json.rstrip("\n")

        # #204 — a cap that is never disclosed is indistinguishable from a complete list.
        # Computed on the OPEN search alone, before any sticky-closed merge, because that
        # is the query the limit applies to.
        body_extra = "truncated: true\n" if _hit_the_cap(open_json) else ""

        body = (
            f"---\n"
            f"type: gh-snapshot\n"
            f"schema_version: 1\n"
            f"tags: [op/gh-snapshot]\n"
            f"advisor: {advisor}\n"
            f'captured_at: "{now_iso}"\n'
            f"ttl_seconds: {ttl}\n"
            f"source: gh search issues\n"
            f"{body_extra}"
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
