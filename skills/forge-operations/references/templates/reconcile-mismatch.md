---
type: reconcile-mismatch
schema_version: 1
tags: [op/reconcile-mismatch, status/open]
id: <YYYY-MM-DD>-<advisor>-<issue-ref>
advisor: <advisor-slug>
found_at: <ISO-8601 timestamp>
delta_summary: <one-line description of the mismatch>
---

# Reconcile Mismatch — {{id}}

## Schema

| Field | Type | Required | Description |
|---|---|---|---|
| type | string | yes | Always `reconcile-mismatch` |
| schema_version | integer | yes | Always `1`; consumers reject unknown versions |
| tags | list | yes | `[op/reconcile-mismatch, status/open]` initially; transitions to `resolved` via tag-change |
| id | string | yes | Unique ID: `<YYYY-MM-DD>-<advisor>-<issue-ref>`, e.g. `2026-05-16-kai-cto-gh38` |
| advisor | string | yes | Advisor slug owning the mismatch, e.g. `kai-cto` |
| found_at | string | yes | ISO-8601 UTC timestamp when the mismatch was detected by `gh-reconcile.sh` |
| delta_summary | string | yes | One-line description of what diverged, e.g. `"GH issue #38 is open but BRIEFING shows it closed"` |

## Producer

`gh-reconcile.sh` — compares the GH snapshot for an advisor against the local BRIEFING state
and emits a mismatch file when they diverge. Common causes: advisor closed an issue in GH but
didn't update the BRIEFING; or a GH issue was re-opened after the BRIEFING was last built.

Resolution: the advisor writes a decision (e.g. `file-decision.sh`) cross-linking this file,
then runs `resolve-finding.sh` (T6) to transition `status/open` → `status/resolved`. Wikilinks
in the decision reference this file's ID for backlink tracking.

## Path

`agent-memory/reconcile/open/<date>-<advisor>-<issue-ref>.md`

Example: `agent-memory/reconcile/open/2026-05-16-kai-cto-gh38.md`

## Example

```markdown
---
type: reconcile-mismatch
schema_version: 1
tags: [op/reconcile-mismatch, status/open]
id: 2026-05-16-kai-cto-gh38
advisor: kai-cto
found_at: "2026-05-16T10:45:00Z"
delta_summary: "GH issue #38 is open but BRIEFING.md lists it as closed"
---

# Reconcile Mismatch — 2026-05-16-kai-cto-gh38

**GH state**: Issue #38 "Implement run-log JSONL" — state: open, labels: p0, kai

**BRIEFING state**: Listed under "Closed recently" with note "Done in T2"

**Action required**: Verify whether issue #38 should be closed in GH or re-opened in BRIEFING.
Run `gh issue close 38` if T2 is complete and merged, then resolve this mismatch.

**Related**: [[2026-05-15-kai-session]], [[decision-2026-05-16-close-gh38]]
```
