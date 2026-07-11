---
type: query
schema_version: 1
tags: [op/query]
---

# Query — Inter-Script Request Envelope

This template documents the **query envelope** written when a lifecycle script logs an auditable
inter-script request. Envelopes are write-once — no `status/` lifecycle tag.

A query pairs 1:1 with a later `result` record via `id` ↔ `query_id`.

## Schema

| Field | Type | Required | Description |
|---|---|---|---|
| type | string | yes | Always `query`; identifies the envelope type for consumers |
| schema_version | integer | yes | Always `1`; consumers skip records with unknown versions |
| id | string | yes | Unique ID for this query (e.g. `q-<ts>-<rand8>`); referenced by result.query_id |
| from_advisor | string | yes | Slug of the advisor/script that issued the request (e.g. `kai-cto`) |
| intent | string | yes | Human-readable description of what is being asked (≤280 chars) |
| params | object | no | Structured parameters passed with the request; omit if none |
| output_path | string | no | Expected output file path if the result will be written to disk; omit if inline |
| session_id | string | yes | Session identifier linking this query to a particular advisor session |
| writer_pid | integer | yes | PID of the process that wrote this record; used to correlate with run-log rows |

## Producer

Any lifecycle script that needs an auditable trail of an inter-script request. The script constructs
a query record (YAML frontmatter + body) and appends or writes it to the envelope path. The
corresponding `result.md` is written by the script that fulfils the request, referencing this `id`
via `query_id`.

Unlike snapshot types, query envelopes are self-contained files — not rows in a JSONL stream.

## Path

`agent-memory/envelopes/<YYYY-MM-DD>/<id>-query.md`

One file per query. The date component is the UTC date of issuance.

## Example

```yaml
---
type: query
schema_version: 1
tags: [op/query]
id: q-20260516-a3f2c1b0
from_advisor: kai-cto
intent: "What is the target launch date for onboarding-kit (spec 039)?"
params:
  spec: "039-onboarding-kit"
output_path: "agent-memory/envelopes/2026-05-16/q-20260516-a3f2c1b0-result.md"
session_id: sess-20260516-kai-001
writer_pid: 12345
---

Kai is querying Spark for the committed launch date for the onboarding-kit spec (039)
so it can be reflected in the v1.2 roadmap dependency graph.
```
