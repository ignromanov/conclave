---
type: result
schema_version: 1
tags: [op/result]
---

# Result — Inter-Script Response Envelope

This template documents the **result envelope** written when a lifecycle script responds to a
`query` record. Envelopes are write-once — no `status/` lifecycle tag.

A result pairs 1:1 with its originating `query` via `query_id` ↔ `id`.

## Schema

| Field | Type | Required | Description |
|---|---|---|---|
| type | string | yes | Always `result`; identifies the envelope type for consumers |
| schema_version | integer | yes | Always `1`; consumers skip records with unknown versions |
| id | string | yes | Unique ID for this result (e.g. `r-<ts>-<rand8>`) |
| query_id | string | yes | ID of the originating query record this result answers |
| exit_code | integer | yes | 0 = success, non-zero = the responder encountered an error |
| payload | object | no | Inline result data; omit if result is written to a file |
| payload_path | string | no | Path to a file containing the result; omit if payload is inline |
| summary | string | yes | Human-readable one-line summary of the result (≤280 chars) |

Note: `payload` and `payload_path` are mutually exclusive; exactly one should be present when
the result carries data. Both may be absent for acknowledgement-only results.

## Producer

Any lifecycle script that fulfils an inter-script query. The script reads the originating query
record, executes the requested work, then writes a result record referencing `query_id`. The
result is written once and never modified.

## Path

`agent-memory/envelopes/<YYYY-MM-DD>/<query_id>-result.md`

One file per result. The date component is the UTC date of the response, which may differ from
the query date for cross-session responses.

## Example

```yaml
---
type: result
schema_version: 1
tags: [op/result]
id: r-20260516-b7d4e2f1
query_id: q-20260516-a3f2c1b0
exit_code: 0
payload:
  launch_date: "2026-06-15"
  confidence: "medium"
  notes: "Depends on the v1.2 API landing by Jun 1"
summary: "Advisor confirms onboarding-kit target is 2026-06-15, medium confidence"
---

The advisor has reviewed spec 039. The onboarding-kit launch is targeted for 2026-06-15,
contingent on the v1.2 API landing by Jun 1 as planned.
```
