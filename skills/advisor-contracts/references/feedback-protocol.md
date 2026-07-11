# Feedback Protocol — Unified Work Reviews

> **Purpose**: Every agent emits a work review at the end of its session/dispatch.
> **Spec**: 086 — unified feedback system (a working document; it lives in the authoring
> instance's private DATA tree, not in this distribution)
> **Status**: v2 — single channel (supersedes spec 052 channel A + spec 077 channel B)

## When to emit

**Every agent emits after every session/dispatch — no exceptions.**

| Agent type | Threshold | Rule |
|------------|-----------|------|
| `exec.atlas-dev` | None — always | After every dispatch, regardless of outcome |
| `exec.iris-test` | None — always | After every dispatch, including partial verdicts |
| `team.<advisor>` | Every session | After every session (mandatory proportional emission) |

A session with zero mutations and zero side-effecting tool calls may emit an empty
`items[]` with a `summary` carrying the record — that is still a valid review.
A review with `below_threshold_count > 0` MUST have at least one item in `items[]`.

## Review schema

One review = one markdown file at `ops/feedback/YYYY-MM-DD/<agent>-<session>.md`.
Frontmatter holds structured fields; the body holds optional `notes`.

### File-level frontmatter

| Field | Notes |
|-------|-------|
| `feedback_id` | auto — `fb-<unix-ts>-<6 hex>` |
| `agent` | emitting agent (canonical slug or any agent id) |
| `agent_type` | `advisor` · `executor` · `other` |
| `session_ref` | session id / dispatch id |
| `created` | ISO8601 timestamp |
| `updated_at` | ISO8601 — bumped on every rewrite (emission or triage) |
| `skill_version` | `sha256:<12-hex>` of the primary skill |
| `summary` | one-line neutral session framing (always present) |
| `items[]` | structured feedback items — cap 3–5 |
| `below_threshold_count` | int — minor items that did not reach the cap |
| `_draft` | bool — aggregator skips while `true` |

`agent_type` buckets: `advisor` = any `team.*` slug; `executor` = any `exec.*` slug;
`other` = any other agent invoked via a team command.

### Per-item fields

| Field | Values / rule |
|-------|---------------|
| `id` | **string** (e.g. `"i1"`) — a bare YAML int (`id: 1`) is type-invalid and rejects the whole review at finalize |
| `category` | `script-defect` · `doc-contradiction` · `naming-inconsistency` · `skill-inaccuracy` · `skill-gap` · `process-friction` · `data-access` · `idea` |
| `layer` | `infra` · `skill` · `contract` · `memory` · `workflow` |
| `location` | **mandatory** — typed object: `{ file, line?, skill?, section? }`. `location.skill`, when set, is a skill-path slug matching `team.*` / `exec.*` / `workflow.*` / `util.*` (e.g. `team.sage-cto`), **not** a bare agent name |
| `fingerprint` | auto — normalized `(location, category)` hash, computed at emission time |
| `observation` | **mandatory** — what the agent witnessed (output, error, missing field) |
| `interpretation` | why it caused friction (root cause) |
| `suggested_fix` | **mandatory** — one concrete change, ≤2 sentences |
| `severity` | `low` · `medium` · `high` · `critical` |
| `frequency` | `first-time` · `occasional` · `every-dispatch` |
| `occurrence_count` | optional int — raw count when known |
| `evidence` | **mandatory** — tool-call id / file excerpt. Missing ⇒ item rejected at ingest |
| `status` | `open` · `accepted` · `in_progress` · `resolved` · `rejected` · `deferred` |
| `owner` | optional — assigned at triage when `status: accepted` |
| `resolved_at` | ISO8601 — set when `status → resolved` |
| `migrated` | bool, default `false` — legacy entries imported by `feedback_migrate.py` |
| `legacy_source` | optional — path to original channel-A/B record |
| `notes` | optional free-form |

`evidence` entries MUST cite a specific tool call or step — filler fails review.

### Routing (set by triage)

`layer` → fix owner: `skill` / `contract` / `memory` / `infra` → **Forge**;
`workflow` → **Quorum**. `category: idea` → reviewed by both.

## How to emit

Invoke `/conclave:feedback` at the end of every session or dispatch:

```bash
python engine/scripts/feedback/feedback_emit.py \
  --agent <slug> \
  --agent-type <advisor|executor|other> \
  --session-ref <id> \
  --skill-version sha256:<12-hex>
```

The script scaffolds `ops/feedback/<today>/<agent>-<session>.md` with `_draft: true`.
The agent fills `items[]` honestly (cap 3–5, `evidence` mandatory), then sets
`_draft: false`. A `--no-op` flag marks a genuinely zero-mutation session.

## Cadence triage

`/conclave:start` (via `session_init.py`) checks the `_index/last-triage` marker:

```
now − last_triage > 7 days   OR   new reviews since last triage ≥ 15
  → surface: "feedback: triage due — N open reviews, last triage X days ago"
```

When the cadence fires, the session-init output includes a `feedback:` line.
Invoke `/conclave:triage` (Quorum + Forge) to run the triage pipeline.

### `/conclave:triage` pipeline

| Step | Action |
|------|--------|
| 1 | `feedback_triage.py --digest` — dedup on `fingerprint`; render 3-column digest |
| 2 | Reviewer classifies each cluster → `accepted` / `rejected` / `deferred` |
| 3 | `feedback_triage.py --set` — writes `status` + `owner` back to review file |
| 4 | `accepted` → open GitHub Issue, record target sprint |
| 5 | `feedback_archive.py` — archive resolved reviews; append finding to `hot.md` |

Monthly: `feedback_triage.py --monthly` closes zombie items older than 90 days.

## Reaction policy

All routing waits for the weekly window (pure cadence, spec §Decision #5). An agent
genuinely blocked mid-session still surfaces that to the user live — emission and
reaction are separate concerns.

## What this is NOT

- Not a bug tracker for product code → use GH Issues.
- Not a place for advisor opinions about strategy → use mentions/decisions.
- Not a diary of what you did this session → use sessions/.
- Not a request channel to user → surface blockers to user directly AND record them here.
