---
description: |
  Universal end-of-session / end-of-dispatch work-review emission for ALL agents.
  Walks the agent through the Review schema, scaffolds the review file, instructs
  honest item filling (cap 3-5, evidence mandatory, minimum-item rule), then flips
  _draft: false. Invoked by /conclave:done (advisors) and by exec.* at dispatch end.
  Any agent can invoke it directly. No exceptions.
---

!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/feedback-protocol.md`

# /conclave:feedback — Universal Work Review Emission

> **MANDATORY** at the end of every session or dispatch. Works independently — no
> facilitator role required. Replaces the old `emit.sh` path entirely.

## Data classification

Before filling `observation` or `evidence` fields, verify the content does not include
any of the following forbidden patterns (source: spec 077 §"Data classification"):

- wallet addresses (`0x[a-fA-F0-9]{40}`)
- private keys / tx-hashes (`0x[a-fA-F0-9]{64}`)
- GH tokens (`gh[ps]_[A-Za-z0-9_]{36,}`)
- RPC URLs containing `alchemy|infura|quicknode|drpc`
- invoice URL fragments (`#N4Ig`, `#H4sI`)
- `?og=` params
- social URLs (`t.me|twitter.com|x.com|farcaster.xyz|warpcast.com`)
- IP addresses, email addresses
- paths under the knowledge wiki outside `_bridges/`

Use reference IDs and file excerpts instead of raw sensitive values.
The emitted file also carries a machine-readable DATA CLASSIFICATION WARNING HTML comment
(injected by `feedback_emit.py`) — do not remove it.

## Multi-advisor meetings

In a facilitated multi-advisor meeting, each participating advisor emits their own
review covering their own friction and ideas. The facilitator additionally emits a meeting-level
review covering workflow/process observations. Overlapping fingerprints across the
per-advisor reviews are expected and resolved by dedup (`hit_count`).

## Step 1 — Determine your `agent_type`

| Value | Who |
|-------|-----|
| `advisor` | Any `team.*` agent — the instance's hired advisor slugs, plus the engine's own `forge`, `retro`, `start`, `processing`, `done`, `handoff` |
| `executor` | Any `exec.*` agent: exec.atlas-dev, exec.iris-test |
| `other` | Any other agent invoked via a team command that does not fit the above buckets |

## Step 2 — Capture the skill version

```bash
SKILL_VER="sha256:$(shasum -a 256 .claude/skills/<your-skill>/SKILL.md | cut -c1-12)"
```

Replace `<your-skill>` with the primary skill you ran this session (e.g. `exec.atlas-dev`, or
`team.<advisor-id>`). For sessions spanning multiple skills, use the entry-point skill.

## Step 3 — Scaffold the review file

Run from the repo root (the `.ai/` directory):

```bash
cd /path/to/.ai   # CONCLAVE_AI_ROOT must resolve here
uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_emit.py \
  --agent <your-agent-slug> \
  --agent-type <advisor|executor|other> \
  --session-ref <session-id-or-dispatch-id> \
  --skill-version "$SKILL_VER" \
  [--no-op]
```

The script writes `ops/feedback/<today>/<agent>-<session>.md` with `_draft: true` and
prints the path. Pass `--no-op` **only** when the session had zero mutations and zero
side-effecting tool calls (structural no-op — empty `items[]` is then legitimate).

## Step 4 — Fill in the review

Open the scaffolded file. The frontmatter contains every required field. Fill them in
according to the schema below.

### File-level fields

| Field | Guidance |
|-------|---------|
| `summary` | Replace the TODO placeholder with one neutral sentence framing the session — what was attempted and what happened. Always present. |
| `items[]` | See per-item schema below. Cap: **3–5 highest-value items** only. |
| `below_threshold_count` | Count of minor items that did not make the cap (can be 0). If `> 0`, `items[]` must be non-empty. |
| `_draft` | Do not hand-edit. Finalize via `--finalize` (Step 5) — it validates then flips to `false`. While `true` the aggregator skips the file. |

### Minimum-item rule

`items[]` **must contain at least one item** unless the session is a structural no-op
(`--no-op` flag). `below_threshold_count > 0` with an empty `items[]` is a schema
violation — the index rejects it. A self-assessed "nothing notable" that omits items
while having real side effects is the exact sycophancy loophole the evidence gate
exists to close.

### Per-item schema (closed enums — no free-form values)

| Field | Required | Values / rule |
|-------|----------|---------------|
| `id` | yes | short slug, e.g. `it-1` |
| `category` | yes | `script-defect` · `doc-contradiction` · `naming-inconsistency` · `skill-inaccuracy` · `skill-gap` · `process-friction` · `data-access` · `idea` |
| `layer` | yes | `infra` · `skill` · `contract` · `memory` · `workflow` |
| `location` | yes | typed object: `{file: "path/to/file.py", line?: N, skill?: "name", section?: "heading"}` — at least one of `file`, `skill`, or `section` must be set |
| `observation` | yes | What the agent witnessed — a concrete output, error, or missing field. NOT an opinion. |
| `suggested_fix` | yes | One concrete change, ≤ 2 sentences. |
| `severity` | yes | `low` · `medium` · `high` · `critical` |
| `frequency` | yes | `first-time` · `occasional` · `every-dispatch` |
| `evidence` | yes | Tool-call id, file excerpt, or test output reference. **Missing ⇒ item rejected at ingest.** |
| `interpretation` | optional | Why it caused friction (root cause). |
| `occurrence_count` | optional | Raw count when known, alongside `frequency`. |
| `notes` | optional | Free-form — the only open-ended field. |

### Evidence examples

```
evidence: "tool_call:read_file:abc123 — file was absent at expected path"
evidence: "bash exit=1: command not found: uv (line 42 of emit.sh)"
evidence: "test output: AssertionError at tests/test_emit.py:55"
evidence: "file excerpt: .claude/skills/exec.atlas-dev/SKILL.md:L88 — emit.sh still referenced"
```

### Routing hint (informational — triage sets the final owner)

`layer` → fix owner at triage time: `skill` / `contract` / `memory` / `infra` → Forge;
`workflow` → the facilitator role; `category: idea` → both.

## Step 5 — Finalize (validates, then flips `_draft: false`)

Do **not** hand-edit `_draft`. Finalize via the validating gate:

```bash
uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_emit.py \
  --finalize ops/feedback/<today>/<your-file>.md
```

It validates the review against the schema and flips `_draft: false` **only if it
passes**. On a schema violation (e.g. a free-form `layer`/`frequency`, or an untyped
`location`) it prints the exact error and leaves `_draft: true` — fix the field and
re-run. This is what prevents a malformed review from hard-aborting the triage cadence.
The aggregator (`feedback_index.py`) skips all `_draft: true` files; only finalized
reviews enter triage.

## Complete example (frontmatter fragment)

```yaml
feedback_id: fb-1748900000-abc123
agent: exec.atlas-dev
agent_type: executor
session_ref: dispatch-086-g4
skill_version: sha256:abcdef012345
created: "2026-05-22T17:00:00Z"
updated_at: "2026-05-22T17:10:00Z"
summary: "Implemented T9+T10 SKILL.md files for spec 086; two commits, all green."
_draft: false
below_threshold_count: 1
items:
  - id: it-1
    category: skill-gap
    layer: skill
    location:
      skill: exec.atlas-dev
      section: "Before Exit"
    observation: "emit.sh path still referenced in Before Exit block after channel B deletion"
    suggested_fix: "Replace emit.sh reference with /conclave:feedback invocation in T12."
    severity: medium
    frequency: every-dispatch
    evidence: "grep result: .claude/skills/exec.atlas-dev/SKILL.md:L88 contains emit.sh"
    interpretation: "T12 is scheduled but not yet landed; agents following the skill would fail."
```

## Anti-patterns

| Pattern | Why bad |
|---------|---------|
| Skipping emission because "nothing broke" | Minimum-item rule — non-zero sessions always have signal |
| `evidence: "my observation"` | Evidence must be a concrete artifact reference, not a restatement |
| Filling 5 items with minor variants of the same finding | One item per unique `fingerprint`; aggregate in `below_threshold_count` |
| Setting `_draft: false` before filling items | Submits an empty/incomplete review to the index |
| Free-form `category` or `layer` values | Closed enums only — arbitrary strings cause ingest rejection |
