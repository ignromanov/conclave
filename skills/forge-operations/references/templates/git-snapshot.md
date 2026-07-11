---
type: git-snapshot
schema_version: 1
tags: [op/git-snapshot]
advisor: <advisor-slug>
captured_at: <ISO-8601 timestamp>
ttl_seconds: 300
branch: <current branch>
worktree: <worktree path or "main">
---

# Git Snapshot — {{advisor}}

## Schema

| Field | Type | Required | Description |
|---|---|---|---|
| type | string | yes | Always `git-snapshot` |
| schema_version | integer | yes | Always `1`; consumers reject unknown versions |
| tags | list | yes | Always `[op/git-snapshot]`; no status/ tag (write-once data) |
| advisor | string | yes | Advisor slug that requested this snapshot, e.g. `kai-cto` |
| captured_at | string | yes | ISO-8601 UTC timestamp of when `git status` / `git worktree list` ran |
| ttl_seconds | integer | yes | Seconds until snapshot is considered stale; default 300 (5 min) |
| branch | string | yes | Active branch at capture time |
| worktree | string | yes | Worktree path if in a worktree, otherwise `"main"` |

## Producer

`git-fetch.sh` (T5) — the sole `git status` / `git worktree list` caller in the forge-vault runtime.
Emits a single repo-global snapshot file via atomic write with mkdir-lock for refresh coalescing
(first writer wins; others sleep 0.5s and re-read if now fresh). Snapshot TTL is shorter than
`gh-snapshot` (5 min vs 15 min) because worktree state changes more frequently.

No other script may call `git status` or `git worktree` directly. Enforcement: CI grep on `scripts/**/*.sh`.

## Path

`agent-memory/git-cache/state.md`

This is a repo-global single file (not per-advisor), because git state is shared across all advisors.

## Example

```markdown
---
type: git-snapshot
schema_version: 1
tags: [op/git-snapshot]
advisor: nexus-ceo
captured_at: "2026-05-16T15:00:00Z"
ttl_seconds: 300
branch: master
worktree: main
---

# Git Snapshot

- Branch: master
- Worktree: main (not in a worktree)
- Status: clean (no uncommitted changes)

## Active worktrees

| Path | Branch | HEAD |
|------|--------|------|
| /path/to/project | master | 744bfc4 |
| /path/to/project/worktrees/NNN-feature | feat/NNN-feature | a3c21d0 |
```
