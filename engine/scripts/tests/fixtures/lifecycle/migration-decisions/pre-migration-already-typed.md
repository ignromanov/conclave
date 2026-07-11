---
type: audit-finding
schema_version: 1
tags: [op/audit-finding, status/open]
id: 2026-05-02-already-typed
made_at: "2026-05-02T10:00:00Z"
made_by: kai-cto
---

# Audit Finding — Already Typed

This file already has a `type:` field. The migration must leave it byte-identical.
Idempotency target: running migrate-add-type.sh on this file must produce 0 injections.
