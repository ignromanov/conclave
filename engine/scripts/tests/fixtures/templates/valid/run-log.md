---
type: run-log
schema_version: 1
tags: [op/run-log]
---

# Run Log — fixture

Sample JSONL rows as produced by `run_log_append` (from `lib/run-log.sh`, T2).

```jsonl
{"type":"run-log","schema_version":1,"ts":"2026-05-16T10:00:01Z","script":"briefing-build.sh","args_hash":"b1c2d3e4","exit_code":0,"duration_ms":1102,"advisor":"shade-ciso"}
{"type":"run-log","schema_version":1,"ts":"2026-05-16T10:02:44Z","script":"gh-fetch.sh","args_hash":"","exit_code":0,"duration_ms":876,"advisor":"shade-ciso"}
{"type":"run-log","schema_version":1,"ts":"2026-05-16T10:05:30Z","script":"hot-md-append.sh","args_hash":"f9e8d7c6","exit_code":0,"duration_ms":45,"advisor":""}
```
