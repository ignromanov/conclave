---
type: run-log
schema_version: 1
tags: [op/run-log]
---

# Run Log — JSONL Row Schema

This template documents the **JSONL row format** written to `agent-memory/run-log/<YYYY-MM-DD>.jsonl`
by every lifecycle script via `lib/run-log.sh`'s `run_log_append` function (T2).

Each invocation appends exactly one JSON object (single line) to the day's log file. The file itself
is append-only; no row is ever modified after write.

## Schema

| Field | Type | Required | Description |
|---|---|---|---|
| type | string | yes | Always `run-log`; identifies the row type for consumers |
| schema_version | integer | yes | Always `1`; consumers skip rows with unknown versions |
| ts | string | yes | ISO-8601 UTC timestamp of script invocation start |
| script | string | yes | Basename of the script that appended the row, e.g. `briefing-build.sh` |
| args_hash | string | yes | SHA-256 (first 8 hex chars) of the space-joined argument list; empty string `""` if no args |
| exit_code | integer | yes | Exit code of the script; 0 = success, non-zero = failure |
| duration_ms | integer | yes | Wall-clock duration of the script in milliseconds |
| advisor | string | yes | Advisor slug context for the invocation; `""` (empty string) if not advisor-scoped |

## Producer

Every lifecycle script in `scripts/lifecycle/` and `scripts/` sources `lib/run-log.sh` and calls
`run_log_append` in its EXIT trap (installed by `run_log_init`). This means the row is always
written — even on error or signal termination — because it fires on EXIT.

The single append point (`lib/run-log.sh`) is the sole writer for run-log rows. No script writes
raw JSON to the JSONL file directly.

## Path

`agent-memory/run-log/<YYYY-MM-DD>.jsonl`

One file per calendar day (UTC). Each line is a complete JSON object. Consumers use `jq -s '.'`
to parse the file as an array, or stream line-by-line with `while IFS= read -r line`.

## Example

```jsonl
{"type":"run-log","schema_version":1,"ts":"2026-05-16T14:30:01Z","script":"briefing-build.sh","args_hash":"a3f2c1b0","exit_code":0,"duration_ms":1423,"advisor":"kai-cto"}
{"type":"run-log","schema_version":1,"ts":"2026-05-16T14:31:55Z","script":"gh-fetch.sh","args_hash":"","exit_code":0,"duration_ms":987,"advisor":"kai-cto"}
{"type":"run-log","schema_version":1,"ts":"2026-05-16T15:02:10Z","script":"startup-audit.sh","args_hash":"","exit_code":1,"duration_ms":234,"advisor":""}
```
