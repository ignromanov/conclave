---
schema_version: "1.0.0"
applies-to: advisors+executors
spec: 051
status: active
---

# Memory invariants (spec 051)

- No direct `Edit`/`Write` on `.ai/agent-memory/advisors/**` — use scripts under `engine/scripts/`.
- Inbox = GH Issues (`gh issue list --label "advisor:<name>"`). `topics/inbox.md` no longer exists.
- Don't duplicate facts from `.ai/product.md` / `.ai/architecture/*` — reference with pointers.
- Cross-advisor communication: `mention.sh` (not free-form edits).
