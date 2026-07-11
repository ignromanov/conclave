---
type: contract
name: output-formatting
schema_version: 3.4
applies_to: [team.done, team.start, team.processing, team.handoff, team.retro, team.forge, all advisor SKILL.md]
supersedes: schema_version 1 (Render-B table + 27-glyph palette, 2026-05-18 5e63a34), schema_version 3 (bare-text minimalism — sections блекли), schema_version 3.1 (persona emoji вместе с decorative были излишне удалены), schema_version 3.2 (не покрывал fan-out / batch lists — Nexus fan-out скатился к box-drawing)
---

# Output Formatting Contract — Session Summary (▍-framed minimalism)

> Version is tracked in frontmatter `schema_version` + the Changelog below — never in
> this heading or in prose, so consumers cannot cite a stale number.

> **Purpose**: single canonical spec for the Session Summary render produced by `/conclave:done`.
> v3 supersedes v1 (Render-B table + advisor-overlay palette) after Ignat's `слишком пестро`
> feedback. v3.1 fixes v3's "all blends into prose" problem by wrapping the whole Summary in
> the `▍` emphasis gutter and **bold**-ing keys — re-introducing structure-cues without
> re-introducing emoji inflation.
>
> **Core principle**: silence on success, signal on exception. Density through alignment +
> bold + single ▍ visual frame, not decoration.

## Render format (canonical)

Every Summary block is wrapped in a `▍` left-gutter (U+258D, three-eighths block). Inside the
gutter: bold keys, monospace SHA/paths via backticks, exception rows still prefixed with
`⚠`/`✗` REPLACING the leading content space (gutter ▍ remains).

```
▍ **{persona-emoji} {advisor} · session-end · {date}**
▍
▍ **committed**  `{repo} {sha1}` {kind} + `{sha2}` {kind}
▍ **filed**      `{decisions_path or "—"}`
▍ **updated**    hot.md ({sections touched})
▍ **changed**    {N} files — {short_breakdown}
▍ **recorded**   `{session_record_path}` {duration}
▍ **mention →**  {persona-emoji} {recipient} ({topic})           ← cross-ref keeps recipient's emoji
▍ ⚠ **study**    {one-line if NOT clean; row omitted entirely if clean}
▍ ⚠ **infra**    {one-line if NOT clean; row omitted entirely if clean}
▍ **reflexion**  "{one-sentence post-mortem; row omitted if "—"}"
▍
▍ **next →** {primary next action} · {optional second}
▍
▍ **Concepts**: advisor:{slug}, {3-5 domain tags}
```

Key alignment: pad key + closing `**` so values start at column ~14 from the gutter. Exception
glyph `⚠`/`✗` sits BETWEEN the gutter and the bold key. Blank lines inside the block are rendered
as a lone `▍`. Persona emoji of OTHER agents appears in value cells only when the row is a
cross-reference to that agent.

## Rules

### 1. Silence on success, signal on exception

A row is shown ONLY when it has content. Severity glyph (⚠ or ✗) appears ONLY on the row that
deviates from "ok". A clean session has no ⚠/✗ anywhere — the absence IS the green signal.

| State | Render |
|---|---|
| Row has content + ok | `▍ **key**  value` |
| Row has content + warn | `▍ ⚠ **key**  value` |
| Row has content + error | `▍ ✗ **key**  value` |
| Row would be empty / no-op | omit row entirely |

This kills the v1 "everything-green" vanity grid and the false-✅ risk simultaneously.

### 2. Functional emoji set (4 max) + persona emoji (identity-anchor exception)

**Functional set** (rendering primitives):

```
⚠   warn / needs-attention
✗   error / blocking
▍   emphasis-block left bar (for Summary container, PENDING decisions, callouts)
→   next-action arrow
```

**Persona emoji** (identity-anchors — one per agent, same across all sessions, allowed):

| Agent | Emoji | Type |
|---|---|---|
| Quorum | ⚖️ | advisor |
| Kai | 🔷 | advisor |
| Shade | 🛡️ | advisor |
| Nexus | 🔮 | advisor |
| Spark | ⚡ | advisor |
| Atlas | 🛠️ | executor |
| Iris | 🌈 | executor |
| Forge | 🔨 | lifecycle-with-persona |

Persona emoji is allowed in TWO places only:
1. **Header line** — speaker's own emoji: `▍ **⚖️ quorum · session-end · {date}**`
2. **Cross-reference value cells** — when the row's value points to another agent
   (`**mention →** 🔷 kai`, `**dispatched** 🛠️ atlas T3-T7`, `**filed** 🛡️ shade decisions/...`)

Forbidden (still rules from v3):
- Decorative semantic glyphs in data rows (📦 commit, 💬 mention, 📜 decision) — they belong in
  commit messages and prose, not summaries
- Advisor specialty overlay (🛡️🐛, 🏗️📜) — two-glyph stacks read as two signals
- Persona emoji as decoration on every row (e.g., `🔷 **committed** ...` when speaker IS Kai —
  Header already establishes identity, repetition is noise)

### 3. ▍-gutter + bold keys, not table syntax

`▍` gutter on every line of the block (including blank-line spacers, rendered as lone `▍`).
Inside the gutter: **bold** keys for visual anchor, ~14-char key column (incl. `**` markers),
then value (free text or `inline code` for SHA/paths). No `|`, no `---|---`, no markdown table
syntax. Bold renders natively in every chat client; ▍ is a single unicode char with no width
issues; together they give structure without the v1 emoji noise OR the v3 "blends into prose"
problem.

Pad the key column with plain ASCII spaces only — never HTML entities (`&nbsp;`, `&mdash;`).
Claude Code renders chat output as monospace markdown and does not interpret entities; they
appear as literal 6-character strings between key and value.

### 4. Inline sidecars, not parallel lane

`study`, `infra`, `reflexion` are bold keys inside the same ▍-block as the data rows — not a
separate `— sidecar lane —` section. This collapses the v1 "two visual languages in one screen"
problem into one block.

### 5. `next →` is required, machine-readable

Single line inside the ▍-block, leading `**next →**`, dot-separated actions. Used by
`briefing-build.sh` to seed the next session's open queue. Format:

```
▍ **next →** {imperative-action} · {optional-second-action}
```

### 6. ▍-block is the universal emphasis convention

Same `▍` frame used for: (1) Session Summary container [§Render format], (2) PENDING decision
callouts, (3) important mid-session callouts. ONE visual convention — readers learn to filter
it as "this is structured advisor signal".

```
▍ **Title**
▍
▍ content line 1
▍ content line 2
```

Rules:
- ▍ appears in every line of the block (including blank-line spacer rendered as `▍` alone)
- Title in bold on first line
- For PENDING decisions / mid-session callouts: use SPARINGLY — at most one ad-hoc ▍-block
  per response. Session Summary always uses ▍ (it's the container, not an ad-hoc callout).
- NEVER use ╭─╮ box-drawing; NEVER use ▌ (heavy half-block) — too dominant
- See memory: `feedback_emphasis_frame_style.md`

## Example: clean session

▍ **⚖️ quorum · session-end · 2026-05-18**
▍
▍ **committed**  `.ai 5e63a34` feat + `9ef7aa9` session
▍ **filed**      `decisions/output-formatting-contract-v3.2.md`
▍ **updated**    hot.md (recent-decisions)
▍ **changed**    2 files
▍ **recorded**   `sessions/quorum-summary-v3.2.md` ~25m
▍ **reflexion**  "v1 контракт устарел в день ship'а — research до canonization сэкономил бы commit."
▍
▍ **next →** wire run-log EXIT trap into file-decision.sh · add bats for --reflexion
▍
▍ **Concepts**: advisor:quorum, process, output-formatting, lifecycle

## Example: session with exceptions + cross-agent refs

▍ **🛡️ shade-ciso · session-end · 2026-05-18**
▍
▍ **committed**  `.ai f3a8e21`
▍ **filed**      `mentions/kai-ciso-gh-fetch-fix.md`
▍ **mention →**  🔷 kai (gh-fetch.sh:89 advisor label query)
▍ **dispatched** 🛠️ atlas (T3-T7 implementation, completed)
▍ **updated**    hot.md (open-threads)
▍ **recorded**   `sessions/shade-mention-sweep.md` ~45m
▍ ⚠ **study**    link:violations 3 open · capture:0
▍ ⚠ **infra**    1 script · gh-fetch.sh exit=2
▍ **reflexion**  "Deserialiser bias confirmed — add error-channel before next || fallback."
▍
▍ **next →** triage gh-fetch.sh:89 advisor label query · file low/test-gap
▍
▍ **Concepts**: advisor:shade-ciso, security, audit, infrastructure

Reader instantly sees: 🛡️ as speaker in header, 🔷 and 🛠️ as referenced agents in body, 2 warnings
stand out from ▍-wrapped frame. Identity continuity preserved without per-row decoration noise.

## Severity source-of-truth (prevents false ⚠/✗ AND false-clean)

- ⚠ / ✗ may ONLY be emitted from a real signal: script exit code ≠ 0, gh operation returned
  failure, audit script returned non-zero, link-check flagged violations.
- Omitting a row is a STRONGER claim than emitting `key  value` — it asserts "no signal here".
  Only omit when you actually know the row's underlying check passed cleanly. If unsure → emit
  the row with a brief reason and ⚠.
- LLM impressions ("session went well") may NEVER cause a row to be omitted on the optimistic side.

## Anti-patterns

| Pattern | Why bad |
|---|---|
| Emitting ✅ / 🟢 on a normal-state row | v1 vanity — exception-only emphasis violated |
| Markdown table for the data block | breaks alignment on emoji + unreliable in chat renderers |
| Per-block semantic emoji (📦 commit, 📜 decision, etc.) | emoji inflation — pushes glyph count past functional 3-4 threshold |
| Advisor specialty overlay glyphs (🛡️🐛, 🏗️📜) | two glyphs read as two signals, not as modifier |
| `— sidecar lane —` as parallel block | two visual systems on one screen — kills scannability |
| `╭─ ... ─╮` box-drawing frames | requires right-side alignment, looks ASCII-art, noisy |
| Heavy `▌` left bar | dominates the text it's meant to support |
| Decorative narrative tail ("zen closing line") | violates silence-on-success and inverted-pyramid |
| Showing zero-state rows (`mentions: 0`, `defects: 0`) | terraform/npm convention — zeros aren't surfaced |
| Box-drawing tables (┌┬┐, ╔╦╗) for batch ops | Same reasons v3 rejected markdown tables: alignment fragility, ASCII-art noise. Use Pattern B/C instead |
| Mixing patterns within one ▍-block (B for one row, D for next) | One pattern per block; switch blocks if context truly changes |
| HTML entities (`&nbsp;`, `&mdash;`) for column alignment | Chat output is monospace markdown — entities render as literal 6-char strings, not spaces. Use plain ASCII spaces |

## What v3 removed from v1

- 8-glyph universal palette (📦💬📜🐛📝🔥🧩🪢)
- 3-glyph sidecar lane (🧠⚙️🪞 as visual category markers — they survive as inline keys)
- Advisor specialty overlay (🛡️🏗️🔮⚡🛠️ × 2-3 each = 12 glyphs)
- Severity grid 🟢🟡🔴⚪ — replaced by exception-only ⚠/✗ + omission for ok
- Markdown table Render-B layout
- `╭─ ... ─╮` box-drawing emphasis frames
- "Status" column (every row had one, redundant with row visibility)
- Per-advisor narrative tail (`Bug surfaced:`, zen closing) — moved into the `reflexion` row if relevant

## What v3 kept from v1

- Mandatory `--reflexion` arg on `close-session.sh` → `session.md` frontmatter field
- `/conclave:start` Step 1c reads last-3 reflexion for buffer context
- `engine lifecycle runlog-summary` as Infra sidecar producer (output reformatted to one inline row)
- Study phase wiki-script sequence (output reformatted to one inline row, omitted when clean)
- Concepts footer convention
- HTML comment advisor marker convention

## List rendering (fan-out / batch ops)

When a row's value is a LIST of N items (multiple mentions sent in one session, multiple
decisions filed, batch resolutions, fan-out operations), use one of three patterns based on
volume + item-description length. NEVER fall back to box-drawing tables (┌┬┐) — they were
rejected in v3 for the same reasons (alignment fragility, ASCII-art noise).

### Pattern B (DEFAULT) — grouped count + inline detail

One row per category, leading count, em-dash, then inline detail separated by `·`.

```
▍ **filed**       1 — solana-defer-beyond-v2 (active, kill-criteria inline)
▍ **mention →**   2 — 🔷 kai (P1, codec) · ⚖️ quorum (P2, Giveth)
▍ **resolved**    4 — 🔷 kai ×3 (v1-2-codec P1, spec-054, sync FYI) · ⚡ spark (Giveth-correction P2)
▍ **defect**      1 — mention.sh:164 (low) → fb-1779083181
```

Rules:
- Count is the leading number for grep-ability
- Em-dash (`—`) separates count from items
- `·` (middle dot) separates items within a category
- Same-recipient grouping: `🔷 kai ×3 (item1, item2, item3)` — count + recipient + parenthesized items
- Persona emoji + name for cross-references (`🔷 kai`, `⚖️ quorum`)
- Priority/severity inline in parentheses where relevant

### Pattern C (fallback) — chevron detail when row would overflow

Switch to two-level chevron rendering when ANY of:
- item-description average > 40 chars (long titles)
- items per category > 5 (more than the line can hold)
- mixed priorities/types within one category obscure the count
- Pattern B would push the line past ~120 chars

```
▍ **resolved**    8 cleared
▍                 › 🔷 kai · v1-2-codec (P1, refs decision)
▍                 › 🔷 kai · spec-054 FYI (out-of-scope deferred)
▍                 › ⚖️ quorum · sync-cadence FYI
▍                 › ⚖️ quorum · Giveth-admin (P2, awaits external reply)
▍                 › ⚡ spark · Giveth-correction (P2, copy-only)
▍                 › ⚡ spark · launch-window-shift (P1, founder-input pending)
▍                 › 🛡️ shade · audit-gh-fetch (low, fixed in this session)
▍                 › 🛠️ atlas · T7-bats-fixture-mismatch (P3, deferred)
```

Rules:
- Header row: count + qualitative word (`cleared` / `sent` / `filed`)
- Detail rows: chevron `›` after 18-char indent (aligns under value column), then full item
- Persona emoji + name + `·` + description
- Reserve for genuinely long lists; not the default

### Pattern D (rare) — numbered sequential when order is semantic

Only when the temporal/sequential ORDER matters as a property (spec task execution, gated
pipeline steps). Otherwise use Pattern B or C.

```
▍ **ops** (8)
▍   1  filed       solana-defer-beyond-v2 (active)
▍   2  mention →   🔷 kai (P1, codec)
▍   3  mention →   ⚖️ quorum (P2, Giveth)
▍   4  resolved    🔷 kai · v1-2-codec (P1)
…
```

Rules:
- Numbered 1..N with 2-space gutter inside ▍
- Reserve for `team.forge audit` findings, ordered pipeline step results, plan-execution
  traces — not for unordered fan-out

### Pattern A (avoid) — repeated key on every item

Repeating `**mention →**` row 8 times is permitted but discouraged: it inflates vertical
space without adding signal over Pattern B's count-first grouping. Only use when items truly
belong to different categories AND there are ≤3 per category (so count grouping isn't worth it).

## Per-skill instantiation

The ▍-framed bold-keys pattern applies to EVERY lifecycle skill's user-facing output block,
not just `/conclave:done`. Each skill instantiates with its own header keyword and key set:

| Skill | Header | Required keys |
|---|---|---|
| `/conclave:start` | `{persona-emoji} {advisor} · session-start · {date}` | `focus`, `queue` (open GH issue count), `briefing`, `interrupted` (if any), `tier`, `next →` |
| `/conclave:processing` | `{persona-emoji} {advisor} · routing · {date}` | `gh-bind` (matched issue or "none"), `mode`, `type`, `tier`, `skills` (chain), `next →` |
| `/conclave:done` | `{persona-emoji} {advisor} · session-end · {date}` | `committed`, `filed`, `updated`, `changed`, `recorded`, `mention →`/`dispatched` (if any), `study`/`infra` (if NOT clean), `reflexion`, `next →`, `Concepts:` |
| `/conclave:handoff` | `{persona-emoji} {advisor} · handoff · {date}` | `status`, `to` (cross-ref to recipient persona-emoji), `slug`, `file`, `gh-issue` (if any), `priority`, `next →` |
| `/conclave:retro` | `participants · retro · {date}` (no single speaker) | `worked`, `didnt`, `try-next`, `action →` (cross-ref to assignee persona-emoji), `next →` |
| `/conclave:forge` (hire) | `🔨 forge · hire · {date}` | `created`, `model-version`, `personality`, `briefing-seeded`, `next →` |
| `/conclave:forge` (evolve) | `🔨 forge · evolve · {date}` | `target`, `aspect`, `changed`, `audit`, `next →` |
| `/conclave:forge` (audit) | `🔨 forge · audit · {date}` | `scanned`, `findings` (with severity), `resolved`, `pending`, `next →` |
| advisor `fan-out` | `{persona-emoji} {advisor} · fan-out · {date}` | `filed`, `mention →` (Pattern B), `resolved` (Pattern B), `dispatched` (if any), `defect` (if any), `inbox` (delta if changed), `next →` |

All rules from §1-6 apply: ▍ on every line including spacers, bold keys, `inline code` for
identifiers, exception-only severity (⚠/✗), zero-state rows omitted, persona emoji in header
+ cross-references only.

For artifacts written to filesystem (handoff `.md` files, retro `.md` files, session.md
frontmatter) — the file format is separate from the chat output. Files use frontmatter +
markdown headings as they always have; chat blocks use v3.2.

## See also

- `team.done/SKILL.md` — invokes this contract
- `team.start/SKILL.md` — invokes this contract (Step 7 + new Start Summary)
- `team.processing/SKILL.md` — invokes this contract (Routing Result block)
- `team.handoff/SKILL.md` — invokes this contract (handoff confirmation chat-block)
- `team.retro/SKILL.md` — invokes this contract (retro confirmation chat-block)
- `skills/forge-operations/SKILL.md` — invokes this contract for hire/evolve/audit confirmations
- `skills/forge-operations/references/templates/session.md` — frontmatter schema (includes `reflexion:`)
- `engine lifecycle runlog-summary` — Infra producer
- `team.start/SKILL.md` Step 1c — Reflexion buffer reader
- Memory: `feedback_session_summary_minimalism.md` — Variant C web research outcome (now generalized to all lifecycle outputs)
- Memory: `feedback_emphasis_frame_style.md` — ▍ frame rationale
- Memory: `feedback_output_formatting_severity_frames.md` — original severity directive (frame portion superseded)

## Changelog

- **v3.4** (2026-05-20) — forbid HTML entities (`&nbsp;`, `&mdash;`) for ▍-row column alignment after advisors' 2026-05-18 Session Summaries rendered literal `&nbsp;` strings in chat. Adds anti-pattern row + explicit ASCII-spaces-only rule to §3. Closes fb-1779131089-1c86b3.
- **v3.3** (2026-05-18) — add List rendering section (Patterns A/B/C/D) after Nexus fan-out output reverted to box-drawing table for 8 ops. Pattern B (grouped count + inline detail) is default; C (chevron) is fallback for long lists; D (numbered) reserved for ordered pipelines. Box-drawing tables explicitly forbidden in anti-patterns. Per-skill table gains `fan-out` row for batch-op summaries.
- **v3.2** (2026-05-18 a24ff9f) — restore persona emoji as identity-anchors after Ignat "эмоджи адвайзеров, исполнителей и других агентов системы мы можем показывать, потому что они как раз создают визуальную связь" feedback. Header now leads with speaker emoji; cross-references to other agents keep their emoji in value cells. Per-row decorative emoji still forbidden.
- **v3.1** (2026-05-18 f497713) — wrap whole Summary in ▍ gutter + bold keys after Ignat "итог сливается с остальным выводом, секции и ключевые слова не выделяются" feedback.
- **v3** (2026-05-18 ae66f5d) — full rewrite to Variant C minimalism after Ignat "слишком пестро" feedback + web research diagnosis. Removed 27-glyph palette, sidecar lane, table layout, box-frames. Exception-only severity.
- **v1** (2026-05-18 5e63a34) — initial contract with Render-B table + advisor overlay. Outdated within the same day.
