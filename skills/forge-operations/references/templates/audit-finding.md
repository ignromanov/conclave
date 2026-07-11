---
type: audit-finding
schema_version: 1
tags: [op/audit-finding, status/open]
id: <YYYY-MM-DD>-<scope>-<slug>
severity: p0
found_at: <ISO-8601 timestamp>
found_by: <script-name or advisor-slug>
affects: <comma-separated list of affected paths or components>
---

# Audit Finding — {{id}}

## Schema

| Field | Type | Required | Description |
|---|---|---|---|
| type | string | yes | Always `audit-finding` |
| schema_version | integer | yes | Always `1`; consumers reject unknown versions |
| tags | list | yes | `[op/audit-finding, status/open]` initially; status transitions to `resolved` or `archived` via tag-change (not file-move) |
| id | string | yes | Unique ID: `<YYYY-MM-DD>-<scope>-<slug>`, e.g. `2026-05-16-briefing-stale-snapshot` |
| severity | string | yes | One of `p0`, `p1`, `p2`; p0 findings block `/conclave:start` |
| found_at | string | yes | ISO-8601 UTC timestamp when the finding was detected |
| found_by | string | yes | Script name (e.g. `startup-audit.sh`) or advisor slug that raised the finding |
| affects | string | yes | Comma-separated paths/components affected, e.g. `agent-memory/advisors/kai-cto/BRIEFING.md` |

## Producer

`startup-audit.sh` and `hot-md-contradictions.sh` — audit scripts that run during `/conclave:start`.
A finding is emitted when a structural invariant is violated (stale snapshot, schema drift,
contradictory hot.md entries, orphaned files). Each finding is written atomically to its own file.
p0 findings cause `/conclave:start` to halt with a prominent error.

Resolution: `resolve-finding.sh` (T6) transitions `status/open` → `status/resolved` and adds a
`resolved_at` frontmatter field. Files are never moved; wikilinks stay valid.

## Path

`agent-memory/audit/open/<date>-<scope>-<slug>.md`

Example: `agent-memory/audit/open/2026-05-16-briefing-stale-snapshot.md`

## Example

```markdown
---
type: audit-finding
schema_version: 1
tags: [op/audit-finding, status/open]
id: 2026-05-16-briefing-stale-snapshot
severity: p0
found_at: "2026-05-16T09:15:00Z"
found_by: startup-audit.sh
affects: agent-memory/advisors/kai-cto/BRIEFING.md
---

# Audit Finding — 2026-05-16-briefing-stale-snapshot

**Summary**: BRIEFING.md for `kai-cto` is 48 hours old (threshold: 24h). GH snapshot
also stale (captured_at 47h ago). `/conclave:start` blocked until resolved.

**Evidence**: mtime of `BRIEFING.md` = 2026-05-14T09:00:00Z; now 2026-05-16T09:15:00Z; delta = 48h.

**Resolution**: Run `briefing-build.sh kai-cto` to regenerate, then run `resolve-finding.sh
2026-05-16-briefing-stale-snapshot`.

**Related**: [[2026-05-14-kai-session]], [[2026-05-16-hot-md]]
```
