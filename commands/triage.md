---
description: |
  Weekly cadence triage pipeline for the facilitator role + Forge. Five-step pipeline: dedup digest,
  classify clusters, write status/owner back to review files, open GH Issues for
  accepted items, archive resolved reviews. Run when /conclave:start signals "Triage due".
  Monthly: zombie pass for items open > 90 days.
---

!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/feedback-protocol.md`

# /conclave:triage — Cadence Triage Pipeline

> **Run by the facilitator role + Forge.** Triggered when `/conclave:start` surfaces:
> `"Triage due: N reviews pending, last triage X days ago"`.
> Pure cadence (weekly) — no mid-week escalation carve-outs.

## Cadence trigger

`/conclave:start` (via `session_init.py`) fires the triage-due notice when:

```
now − last_triage > 7 days   OR   new reviews since last triage ≥ 15
```

The `_index/last-triage` marker file's **mtime** is the cadence signal. It is touched
by `feedback_triage.py --set` after each triage session completes.

## Five-step triage pipeline

### Step 0 — Validation gate (automatic)

`feedback_triage.py` rebuilds the index before any subcommand runs. If any
`_draft:false` (author-complete) review fails schema validation, triage **aborts
immediately** with a non-zero exit code and prints:

```
DROPPED N author-complete reviews (schema-invalid): <paths>
ERROR: triage aborted — one or more author-complete (_draft:false) reviews
failed schema validation. Fix the DROPPED files shown above, then re-run.
```

Fix the listed files (coerce types to match schema — see `schema.py`) and re-run.
Do NOT skip this gate by editing the index directly.

### Step 1 — Run the dedup digest

```bash
cd /path/to/.ai
uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_triage.py \
  --digest
```

`feedback_triage.py` always rebuilds the index first (defensive), then deduplicates
index rows on the emission-time `fingerprint`. Duplicate items increment `hit_count`
instead of adding rows. The digest renders three columns:

| Column | Content |
|--------|---------|
| **WHAT** | `observation` + `location` |
| **WHY** | `category` + `layer` |
| **URGENCY** | `severity` × `frequency` quadrant + `hit_count` |

`critical`-severity items sort to the top of every digest. The quadrant labels are
ordering signals within the weekly window — not timing bypasses (pure cadence, decision #5).

### Step 2 — Classify each cluster

For each cluster in the digest, choose one of:

| Decision | Meaning |
|----------|---------|
| `accepted` | Actionable, worth a fix. Assign an owner by `layer`. |
| `rejected` | Not actionable or already covered elsewhere. |
| `deferred` | Valid but not this sprint. Re-surfaces in the next triage. |

**Owner routing by `layer`** (informational — override as needed):

| `layer` | Default owner |
|---------|---------------|
| `infra` | forge |
| `skill` | forge |
| `contract` | forge |
| `memory` | forge |
| `workflow` | quorum |
| *(any, `category: idea`)* | both forge + quorum |

### Step 3 — Write status + owner back to review files

For each classified item:

```bash
uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_triage.py \
  --set <feedback_id> <item_id> <accepted|rejected|deferred> \
  [--owner <forge|quorum|advisor-slug>]
```

`--set` writes `status` and `owner` back into the review markdown file
(comment-preserving via `frontmatter_io.read_commented` + `write`), bumps `updated_at`,
and touches `_index/last-triage` to reset the cadence clock. The command takes exactly
one `(feedback_id, item_id, status)` triple — run it once per item.

**zsh-safe batching** (GH#13): the default shell is zsh, where `status` is a reserved
**read-only** variable and unquoted expansions do **not** word-split. A loop using
`status` as its variable, or with unquoted `$fb`/`$item`, aborts mid-batch. Use a
non-reserved loop variable and quote every expansion:

```bash
# one row per item: "<feedback_id> <item_id> <accepted|rejected|deferred>"
while read -r fb item state; do
  [ -z "$fb" ] && continue
  uv run --project engine/scripts/feedback \
    python engine/scripts/feedback/feedback_triage.py --set "$fb" "$item" "$state"
done <<'ROWS'
fb-1780599200-e77a3b it-1 accepted
fb-1780599200-e77a3b it-6 accepted
ROWS
```

**`resolved_at` lifecycle:** when `status → resolved`, `feedback_triage.py --set`
writes `resolved_at` automatically. `resolved_at − created` is the feedback-loop MTTR
for the item. Track this metric across triages to measure whether the loop is closing.

### Step 3.5 — Self-healing verify pass (spec 093)

Run the verify sweep (dry-run first):

```bash
cd /path/to/.ai
PYTHONPATH=engine/scripts \
  uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_verify.py
```

Prints `auto-close=N candidates=M nominations=K`.

- **auto-close items**: predicate-passing items confirmed resolved on disk. Re-run with `--apply` to write `status=resolved` via `feedback_triage.py --set` (no duplicate writer — routes through the audited path).
- **candidates** (`_verify/verify-candidates-<date>.md`): LLM-judge each — is the fix present on disk? For each confirmed: run `feedback_triage.py --set <feedback_id> <item_id> resolved`.
- **nominations** (`ops/feedback/nominations/<slug>.md`): recurring high-frequency clusters flagged for spec 090 durable mutation. Forge assigns target (skill | contract | briefing).

Apply after review:

```bash
PYTHONPATH=engine/scripts \
  uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_verify.py --apply
```

### Step 4 — Open GH Issues for accepted items

For each `accepted` item, open a GitHub Issue in the `.ai` repo:

```bash
gh issue create \
  --title "<observation, ≤ 72 chars>" \
  --body "$(cat <<'EOF'
**Source:** ops/feedback/<date>/<agent>-<session>.md · item <item_id>
**Category / Layer:** <category> / <layer>
**Severity:** <severity> · **Frequency:** <frequency>
**Observation:** <observation>
**Suggested fix:** <suggested_fix>
**Evidence:** <evidence>
EOF
)" \
  --label "feedback,agent-infra,<priority>,advisor:<owner>"
```

**Label derivation** — the four labels are fixed keys, not the body's `<layer>`
(`infra`/`skill`/`contract`/`memory`/`workflow` are metadata, **not** real repo
labels — passing one fails with `could not add label: <layer> not found`):

| Label | Value |
|-------|-------|
| `feedback` | always |
| `agent-infra` | always — the canonical agent-system label |
| `<priority>` | `p1` if `severity` ∈ {high, critical}, else `p2` |
| `advisor:<owner>` | owner from the Step-2 layer→owner table (e.g. `advisor:forge`) |

Record the issue number in the `--set` call's owner note if useful
(e.g. `--owner "forge:AI#N"`).

### Step 5 — Archive resolved reviews

After all `--set` calls, run:

```bash
uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_archive.py \
  [--note "triage YYYY-MM-DD"]
```

`feedback_archive.py` moves every review whose items are **all** `resolved` or
`rejected` into `_archive/YYYY-MM.jsonl` (append-only), removes the source `.md`
file, and appends a one-line finding to `agent-memory/hot.md` for cross-agent
visibility. It refuses to re-archive an id already in any archive file.

An item's lifecycle state is always readable from the live review file
(`ops/feedback/<date>/<agent>-<session>.md`) until archival. The archive is the
closed-item ledger; the review file is the single source of truth while open.

## Monthly: zombie pass

Once a month, Forge runs:

```bash
uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_triage.py \
  --monthly
```

This lists all items with `status` in `{open, deferred}` older than 90 days
("zombie items"). For each: either advance to `accepted` (if still relevant),
`rejected` (if stale), or `deferred` again with a note. A zombie item that survives
three monthly passes should be promoted to a spec or closed.

## Check triage status without running a triage

```bash
uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_triage.py \
  --check
```

Prints `triage_due=<true|false>` and `open_items=<N>` without mutating anything.
Used by `/conclave:start` cadence guard.

## Summary format

After completing the triage pipeline, emit a ▍-framed block:

```
▍ ⚖️ quorum · feedback-triage · <date>
▍
▍ **reviews**       <N> reviewed · <N> clusters after dedup
▍ **accepted**      <N> items → GH Issues opened: AI#N, AI#N
▍ **rejected**      <N> items
▍ **deferred**      <N> items
▍ **archived**      <N> reviews moved to _archive/
▍ **mttr-signal**   oldest open item: <age> days (fb-<id>)
```

Omit rows with zero counts. Include `mttr-signal` only when oldest open item age is
notable (> 14 days).

## Anti-patterns

| Pattern | Why bad |
|---------|---------|
| Running triage outside the weekly window for a single "urgent" item | Pure cadence (decision #5) — all routing waits for the window; live blocking → surface to user directly in session |
| Skipping `--set` and only opening GH Issues | Status lives in the review file; the archive step depends on it; GH Issues alone are not the source of truth |
| Archiving before `--set` completes | Archive moves files — items with stale status become invisible |
| Accepting everything to keep the digest short | Acceptance rate is the quality signal; inflating it defeats Goodhart-resistance |
| Closing zombie items with `rejected` to clear the backlog | Zombie pass is for genuine staleness; close only what is truly no longer applicable |
