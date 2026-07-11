---
type: gh-snapshot
schema_version: 1
tags: [op/gh-snapshot]
advisor: <advisor-slug>
captured_at: <ISO-8601 timestamp>
ttl_seconds: 900
source: gh issue list
---

# GH Snapshot — {{advisor}}

## Schema

| Field | Type | Required | Description |
|---|---|---|---|
| type | string | yes | Always `gh-snapshot` |
| schema_version | integer | yes | Always `1`; consumers reject unknown versions |
| tags | list | yes | Always `[op/gh-snapshot]`; no status/ tag (write-once data) |
| advisor | string | yes | Advisor slug, e.g. `kai-cto`, `nexus-ceo` |
| captured_at | string | yes | ISO-8601 UTC timestamp of when `gh issue list` ran |
| ttl_seconds | integer | yes | Seconds until snapshot is considered stale; default 900 (15 min) |
| source | string | yes | Always `gh issue list`; records the external command that produced this data |

## Producer

`gh-fetch.sh` (T5) — the sole `gh` caller in the forge-vault runtime. Runs `gh issue list` filtered
by advisor label, emits one atomic write to the snapshot file. Display reads (briefing, dashboard)
use the cached snapshot; mutation-feeding reads pass `--no-cache` to force a fresh fetch.

No other script may call `gh` directly. Enforcement: CI grep on `scripts/**/*.sh`.

## Path

`agent-memory/gh-cache/<advisor>.md`

Example: `agent-memory/gh-cache/kai-cto.md`

## Example

```markdown
---
type: gh-snapshot
schema_version: 1
tags: [op/gh-snapshot]
advisor: kai-cto
captured_at: "2026-05-16T14:30:00Z"
ttl_seconds: 900
source: gh issue list
---

# GH Snapshot — kai-cto

| # | Title | Labels | State |
|---|-------|--------|-------|
| 42 | Upgrade Next.js to v16 | p1, kai | open |
| 38 | Implement run-log JSONL | p0, kai | open |
| 31 | Rust/WASM codec prototype | p2, kai | open |
```
