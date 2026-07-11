---
type: audit-finding
schema_version: 1
tags: [op/audit-finding, status/open]
id: 2026-05-16-briefing-stale-snapshot
severity: p1
found_at: "2026-05-16T09:30:00Z"
found_by: startup-audit.sh
affects: agent-memory/advisors/nexus-ceo/BRIEFING.md
---

# Audit Finding — 2026-05-16-briefing-stale-snapshot

**Summary**: BRIEFING.md for `nexus-ceo` is 26 hours old (threshold: 24h). Snapshot may
not reflect current GH issue state.

**Evidence**: mtime of `BRIEFING.md` = 2026-05-15T07:00:00Z; captured_at in gh-snapshot =
2026-05-15T07:05:00Z; now 2026-05-16T09:30:00Z; delta = 26.4h.

**Resolution**: Run `briefing-build.sh nexus-ceo` to regenerate, then run
`resolve-finding.sh 2026-05-16-briefing-stale-snapshot`.

**Related**: [[2026-05-15-nexus-session]]
