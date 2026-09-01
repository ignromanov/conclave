---
description: >-
  Works through the backlog of accumulated work reviews — groups duplicates, decides what is
  accepted, rejected or deferred, opens GitHub issues for the accepted items, and archives what
  is resolved. Use when /conclave:start reports that triage is due.
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
cd /path/to/.conclave
uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_triage.py \
  --digest --status open
```

`--status open` is the part that matters: bare `--digest` renders **every** index row
regardless of status, which on 2026-08-18 was 265 rows against the 66 that needed
classifying. `--json` emits the same rows machine-readably, with the `feedback_id` /
`item_id` pairs Step 3 needs.

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
cd /path/to/.conclave
PYTHONPATH=engine/scripts \
  uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_verify.py
```

Prints `auto-close=N candidates=M nominations=K`.

- **auto-close items**: predicate-passing items confirmed resolved on disk. Re-run with `--apply` to write `status=resolved` via `feedback_triage.py --set` (no duplicate writer — routes through the audited path).
- **candidates** (`_verify/verify-candidates-<date>.md`): LLM-judge each — is the fix present on disk? For each confirmed: run `feedback_triage.py --set <feedback_id> <item_id> resolved`.
- **nominations** (`ops/feedback/nominations/<slug>-<fingerprint>.md`): recurring high-frequency
  clusters, one file per cluster. The consumer is **spec 091 L1** (Forge-evolve, operator approves
  each) — 090's oracle route is blocked on 089 and cannot act on them. Forge assigns the target
  (skill | contract | briefing). An existing nomination file is never rewritten: the operator's
  notes on it are the work product.

Apply after review:

```bash
PYTHONPATH=engine/scripts \
  uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_verify.py --apply
```

### Step 3.6 — Attach a `verify:` predicate to each item just accepted (#165)

Step 3.5 can only drain items that carry a predicate. Nothing before this step ever wrote
one, which is why coverage sat at 2 of 171 accepted items on 2026-08-31 and the sweep closed
nothing for seven weeks. **This step is what feeds the loop; the sweep only reads what it left.**

For each item moved to `accepted`, attach the predicate that will become true when the fix
lands — or record why none can exist:

```bash
PYTHONPATH=engine/scripts \
  uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_verify.py \
  --set-verify <feedback_id> <item_id> <kind> --file <path> --pattern <regex>
```

Three kinds, all file-reading and exec-free:

| kind | resolved when | use for |
|------|---------------|---------|
| `grep-absent` | `--file` exists and `--pattern` is **gone** | the offending line is deleted or rewritten |
| `file-contains` | `--file` exists and `--pattern` is **present** | the fix leaves a marker: a new function, flag, test name |
| `file-absent` | `--path` no longer exists | the whole file is the defect |

**Write the predicate against the fix, not against the symptom.** `grep-absent` on a line
that any refactor would move closes the item when nobody fixed anything; `file-contains` on
the name of the regression test that will prove the fix is the strongest shape available.

`--set-verify` evaluates the predicate before attaching it and refuses two verdicts:

- **already passes** — the next sweep would close the item with nothing fixed. Either the
  predicate is wrong, or the item is genuinely resolved: resolve it explicitly with
  `--set ... resolved`, or pass `--force` to let the sweep close it on the record.
- **cannot be evaluated** — the target is unreadable or escapes the checkout root. The item
  would report `BROKEN` on every sweep and never close.

Predicate paths are **checkout-relative** (siblings of `.conclave/`, e.g.
`engine/scripts/...`), not DATA-root-relative.

**When no mechanical predicate is possible** — the item is a judgement call, a naming
decision, a "be more careful" — say so in the item rather than leaving the field empty, so
the gap is a recorded decision instead of an omission:

```yaml
  verify_waiver: "no file-readable oracle: the fix is a judgement about tone, not a diff"
```

An accepted item with neither `verify:` nor `verify_waiver:` is the loop's starvation, one
item at a time.

### Step 4 — Open GH Issues for accepted items

**First, check for an existing issue.** Step 4 has no built-in guard, and filing blind is
how conclave#47 duplicated conclave#46:

```bash
gh issue list -R <code-repo> --state open --limit 300 --json number,title,body,labels \
  > /tmp/open-issues.json
```

**Pass `-R` explicitly.** Issues live in the **CODE** repo; the DATA repo has never held
one. Run from inside `.conclave/` without `-R` and `gh` resolves to DATA, returns an empty
list, and every item reads as "no existing issue" — a dedup guard that always passes is
worse than none, because it is believed (#162).

Match each accepted item against that set **by root cause, read from the issue body** —
not by title keywords, which collide constantly here (several distinct defects all read as
"the rename" or "pytest"). The test: would fixing the linked issue, as that issue describes
the work, also fix this item? If yes, bind the item to it with `--issue` and open nothing.
If it only overlaps, open a new issue and cross-reference.

Then, for each accepted item with no existing issue, open one in the **CODE** repo:

```bash
gh issue create -R <code-repo> \
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

**Bind the issue back to the item** — this is not optional bookkeeping:

```bash
uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_triage.py \
  --set <feedback_id> <item_id> accepted --owner <owner> --issue <N>
```

`--issue` writes a real `issue:` field on the item (the older `--owner "forge:AI#N"`
string hack is superseded — it put a number in a name field where nothing could read it).

An item with no issue link is a defect the next session re-observes, re-emits, and
triage re-accepts as new — the feedback index dedups on `fingerprint` within itself and
knows nothing about GitHub. Measured 2026-08-18: at least 11 of 41 accepted items already
had an open issue (#87, #89, #99, #111, #109, #116, #69, #34, #26, #45, #86).

### Step 5 — Archive resolved reviews

After all `--set` calls, run:

```bash
uv run --project engine/scripts/feedback \
  python engine/scripts/feedback/feedback_archive.py \
  [--note "triage YYYY-MM-DD"]
```

`feedback_archive.py` archives at **two granularities**, because the lifecycle unit is
the item and the review is only its container:

- **Whole review** — every item is `resolved`/`rejected`: the review row goes to
  `_archive/YYYY-MM.jsonl` (append-only), the source `.md` is removed, and a one-line
  finding lands in `agent-memory/hot.md` for cross-agent visibility.
- **Partially closed review** — its closed items are archived individually as
  `kind: item` rows. **Nothing is removed**: the item stays in the review verbatim and
  only gains `archived_at`, which is what makes `feedback_index.py` drop it from the
  working set. No hot.md line (a per-item append would evict the capped decisions list).

Both refuse to re-archive: reviews key on `feedback_id`, items on
`(feedback_id, item_id)`.

Without the item granularity Step 5 archives nothing at all — a single lingering
`accepted` item pins its whole review, and a multi-item review effectively never
reaches all-closed. Measured 2026-08-18: 60 live reviews, 0 fully closed.

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
