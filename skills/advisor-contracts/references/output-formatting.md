---
type: contract
name: output-formatting
schema_version: 4.1
applies_to: [team.done, team.start, team.processing, team.handoff, team.retro, team.forge, all advisor SKILL.md]
supersedes: schema_version 1 (Render-B table + 27-glyph palette, 2026-05-18 5e63a34), schema_version 3 (bare-text minimalism — sections блекли), schema_version 3.1 (persona emoji вместе с decorative были излишне удалены), schema_version 3.2 (не покрывал fan-out / batch lists — advisor fan-out скатился к box-drawing), schema_version 3.4 (render grammar only — carried no slot contract, so a report could render perfectly and still omit its evidence)
stages: [clarify, design, implement, verify, deliver]
tiers: [quick, work]
task_types: [dev, content, research, review, advisory]
binding: required
last_reviewed: "2026-08-31"
---

# Output Formatting Contract — Session Summary (▍-framed minimalism)

> Version is tracked in frontmatter `schema_version` + the Changelog below — never in
> this heading or in prose, so consumers cannot cite a stale number.

> **Purpose**: single canonical spec for the Session Summary render produced by `/conclave:done`.
> v3 supersedes v1 (Render-B table + advisor-overlay palette) after the operator's `слишком пестро`
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

### 1. Silence on success, signal on exception — session-summary scope only

A row is shown ONLY when it has content. Severity glyph (⚠ or ✗) appears ONLY on the row that
deviates from "ok". A clean session has no ⚠/✗ anywhere — the absence IS the green signal.

**Scope**: this rule governs the session summary and other *exception surfaces*, where the reader
asks "did anything go wrong". It does NOT govern a **state report** — an *inventory surface*,
where the reader asked for the successes too and "9 specs done" is load-bearing information. State
reports state their positive claims in words and render zeros; see `state-report.md` (spec 115).

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

The *mapping* is **instance data**, not engine canon: each agent's emoji is set at hire time in its
agent-def frontmatter (`emoji:`) and is whatever that instance's roster chose. Read it from the
agent-def; never assume a name-to-emoji table. The engine ships exactly one fixed entry, because
Forge is the one agent present in every instance:

| Agent | Emoji | Type |
|---|---|---|
| Forge | 🔨 | lifecycle-with-persona |

The binding rules are engine canon and apply to every instance regardless of the mapping:
one emoji per agent, stable across all its sessions, and used only in the two positions below.

Persona emoji is allowed in TWO places only:
1. **Header line** — speaker's own emoji: `▍ **🔨 forge · session-end · {date}**`
2. **Cross-reference value cells** — when the row's value points to another agent
   (`**mention →** 🔷 architect`, `**dispatched** 🛠️ builder T3-T7`, `**filed** 🛡️ security decisions/...`)

Forbidden (still rules from v3):
- Decorative semantic glyphs in data rows (📦 commit, 💬 mention, 📜 decision) — they belong in
  commit messages and prose, not summaries
- Advisor specialty overlay (🛡️🐛, 🏗️📜) — two-glyph stacks read as two signals
- Persona emoji as decoration on every row (e.g., `🔷 **committed** ...` when the speaker IS 🔷 —
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

### 7. No bare identifiers — the referent travels with the pointer

A GH issue number, spec number, slug, or SHA is a *pointer*, not a message. The operator does not
hold the registry in memory (verbatim: «я не в контексте названия каждой, мне номер ни о чем не
говорит»). Every identifier outside the header and `recorded`/`committed` rows carries an inline
gloss in the same cell:

```
▍ **gh-bind**   #142 (102 чартерит поля, которых нет)     ← not: #142
▍ **next →**    file GH#57 (engine status) cost comment    ← not: comment on #57
```

The unit is the screen, not the document — terminal output scrolls, so the gloss repeats per
block (the `git log --oneline` model: the subject rides on every line). This applies to the
`Concepts:` footer tags and to any glyph outside the functional four: a symbol is an identifier
and gets a word beside it on first use per block. Evidence: curse-of-knowledge (Camerer 1989),
GitHub hover-cards / git 50/72 / Bluebook 10.9 convergence — spec 115 `research/`.

### 8. The voice is always named

Every ▍-block opens with the speaker anchor — persona emoji + agent id (the header line §2 already
mandates for summaries, generalized): an advisor's conclusions are never unattributed. Prose
outside a ▍-block is working narration, not a finding; anything the reader is meant to act on
arrives inside an attributed block. (Operator directive 2026-08-31: «адвайзер всегда должен
напоминать что он работает в роли».)

## Example: clean session

> The roster in these examples is **illustrative**. Your instance's advisor ids and emoji come from
> its own agent-defs; only 🔨 forge is the same everywhere.

▍ **🔨 forge · session-end · 2026-05-18**
▍
▍ **committed**  `.conclave 5e63a34` feat + `9ef7aa9` session
▍ **filed**      `decisions/output-formatting-contract-v3.2.md`
▍ **updated**    hot.md (recent-decisions)
▍ **changed**    2 files
▍ **recorded**   `sessions/forge-summary-v3.2.md` ~25m
▍ **reflexion**  "The v1 contract was stale the day it shipped — research before canonizing would have saved a commit."
▍
▍ **next →** wire the run-log EXIT trap into `engine file decision` · add a test for --reflexion
▍
▍ **Concepts**: advisor:forge, process, output-formatting, lifecycle

## Example: session with exceptions + cross-agent refs

▍ **🛡️ security-ciso · session-end · 2026-05-18**
▍
▍ **committed**  `.conclave f3a8e21`
▍ **filed**      `mentions/architect-gh-fetch-fix.md`
▍ **mention →**  🔷 architect (gh_fetch.py:89 advisor label query)
▍ **dispatched** 🛠️ builder (T3-T7 implementation, completed)
▍ **updated**    hot.md (open-threads)
▍ **recorded**   `sessions/security-mention-sweep.md` ~45m
▍ ⚠ **study**    link:violations 3 open · capture:0
▍ ⚠ **infra**    1 script · gh-fetch exit=2
▍ **reflexion**  "Deserialiser bias confirmed — add an error channel before the next `||` fallback."
▍
▍ **next →** triage gh_fetch.py:89 advisor label query · file low/test-gap
▍
▍ **Concepts**: advisor:security-ciso, security, audit, infrastructure

Reader instantly sees: 🛡️ as speaker in header, 🔷 and 🛠️ as referenced agents in body, 2 warnings
stand out from ▍-wrapped frame. Identity continuity preserved without per-row decoration noise.

## Severity source-of-truth (prevents false ⚠/✗ AND false-clean)

- ⚠ / ✗ may ONLY be emitted from a real signal: script exit code ≠ 0, gh operation returned
  failure, audit script returned non-zero, link-check flagged violations.
- Omitting a row is a STRONGER claim than emitting `key  value` — it asserts "no signal here".
  Only omit when you actually know the row's underlying check passed cleanly. If unsure → emit
  the row with a brief reason and ⚠.
- LLM impressions ("session went well") may NEVER cause a row to be omitted on the optimistic side.

## Report slots (spec 113 §6)

The ▍-render grammar above says how a block looks. This says what must be in it.

**Lead with requirements and assumptions, never with a narrative of what you did.** This is
counter-intuitive and it is measured: a process-oriented presentation of an agent's work had the
*lowest* error-finding rate of the formats tested, and when readers missed an error it *raised*
their confidence. A tidy story of what happened is the worst tested format and the one an
unconstrained model produces by default.

| # | Slot | Binding |
|---|---|---|
| 1 | **verdict** — one line + a token from `done · done-with-caveats · blocked · failed` | MUST |
| 2 | **required / assumed** — what was asked, what you assumed to proceed | MUST |
| 3 | **changed** — files, commands, resources. Facts, not adjectives | MUST |
| 4 | **evidence** — test output, measurements, quotations with locations | MUST |
| 5 | **actions** — numbered, owner-attributed, independently actionable | MUST when non-empty |
| 6 | **not checked** — paths not executed, cases not covered, assumptions unverified | MUST |
| 7 | **confidence** — from a fixed scale, plus what would change the verdict | SHOULD |
| 8 | **where** — paths, IDs, branches. The re-entry points | MUST |

**Slot 6 is the hardest to drop, not the easiest.** It is the slot compression deletes first and
the one with the strongest evidence behind it: omission of observed detail, not invention, is the
dominant failure of summarization. If a length budget bites, it bites slots 2 and 3. It may never
bite 4 or 6.

**The report body has a budget.** A `quick`-tier report body targets one screen (~30 lines)
without scrolling; a `work`-tier body targets two. Past the budget, slots 1–2 lead and slot 4/6
detail moves to a file at a stable path, cited from slot 8 — progressive disclosure, not deletion
(the rustc `--explain` model). Without this ceiling, "cut slots 2 and 3 first" never fires: R6
caps every field *except* the one the operator reads, and the structure-costs-length tension its
own research flagged (04-report-structure.md:127-129) was resolved by nobody. Evidence and
not-checked are still never cut — they *move*, with their address left behind.

**Do not perform effort on a bad outcome.** On success keep the effort summary brief and let the
result carry it. On partial failure or low confidence, lead with what is unknown. Showing effort
alongside an unfavourable outcome rates *worse* than having shown nothing.

**The report is not the only copy.** Slot 8 carries a stable path. A block that exists only in
scrollback fails as a record.

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
| Showing zero-state rows (`mentions: 0`, `defects: 0`) | terraform/npm convention — zeros aren't surfaced. **Session-summary scope only**: on a state report zeros are load-bearing and render (see `state-report.md`) |
| Bare identifiers (`#142`, `spec 109`, naked SHA) in any row the operator reads | violates rule 7 — a pointer without its referent reads as noise to anyone not holding the registry |
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
▍ **filed**       1 — defer-backend-rewrite (active, kill-criteria inline)
▍ **mention →**   2 — 🔷 architect (P1, api) · ⚖️ chair (P2, funding)
▍ **resolved**    4 — 🔷 architect ×3 (api-v2 P1, spec-054, sync FYI) · ⚡ growth (copy-correction P2)
▍ **defect**      1 — mention.py:164 (low) → fb-1779083181
```

Rules:
- Count is the leading number for grep-ability
- Em-dash (`—`) separates count from items
- `·` (middle dot) separates items within a category
- Same-recipient grouping: `🔷 architect ×3 (item1, item2, item3)` — count + recipient + parenthesized items
- Persona emoji + name for cross-references (`🔷 architect`, `⚖️ chair`)
- Priority/severity inline in parentheses where relevant

### Pattern C (fallback) — chevron detail when row would overflow

Switch to two-level chevron rendering when ANY of:
- item-description average > 40 chars (long titles)
- items per category > 5 (more than the line can hold)
- mixed priorities/types within one category obscure the count
- Pattern B would push the line past ~120 chars

```
▍ **resolved**    8 cleared
▍                 › 🔷 architect · api-v2 (P1, refs decision)
▍                 › 🔷 architect · spec-054 FYI (out-of-scope deferred)
▍                 › ⚖️ chair · sync-cadence FYI
▍                 › ⚖️ chair · funding-admin (P2, awaits external reply)
▍                 › ⚡ growth · copy-correction (P2, copy-only)
▍                 › ⚡ growth · launch-window-shift (P1, founder-input pending)
▍                 › 🛡️ security · audit-gh-fetch (low, fixed in this session)
▍                 › 🛠️ builder · T7-fixture-mismatch (P3, deferred)
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
▍   1  filed       defer-backend-rewrite (active)
▍   2  mention →   🔷 architect (P1, api)
▍   3  mention →   ⚖️ chair (P2, funding)
▍   4  resolved    🔷 architect · api-v2 (P1)
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
markdown headings as they always have; chat blocks use this contract — the version is in
frontmatter and the Changelog, never cited inline, so a reader cannot pick up a stale one.

## See also

- `state-report.md` — the *inventory surface* contract (state questions); scoped against this
  file's §1 — spec 115
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

- **v4.1** (2026-08-31) — closes the three legibility holes the operator named (spec 115): rule 7
  (no bare identifiers — the referent travels with the pointer), rule 8 (the voice is always
  named), a report-body length budget in Report slots (one screen quick / two work, overflow moves
  to a file — R6 capped everything except what the operator reads), and explicit session-summary
  scoping on §1 + the zero-rows anti-pattern so the new `state-report.md` (inventory surface) and
  this file no longer contradict. Render grammar otherwise unchanged.
- **v4.0** (2026-08-21) — adds the slot contract (spec 113 §6). v3.4 governed the render and nothing else, so a report could render perfectly and still omit its evidence. Slots 4 and 6 are non-negotiable; the ordering leads with requirements and assumptions rather than with process, which is the measured direction. Render grammar unchanged.
- **v3.4** (2026-05-20) — forbid HTML entities (`&nbsp;`, `&mdash;`) for ▍-row column alignment after advisors' 2026-05-18 Session Summaries rendered literal `&nbsp;` strings in chat. Adds anti-pattern row + explicit ASCII-spaces-only rule to §3. Closes fb-1779131089-1c86b3.
- **v3.3** (2026-05-18) — add List rendering section (Patterns A/B/C/D) after an advisor's fan-out output reverted to a box-drawing table for 8 ops. Pattern B (grouped count + inline detail) is default; C (chevron) is fallback for long lists; D (numbered) reserved for ordered pipelines. Box-drawing tables explicitly forbidden in anti-patterns. Per-skill table gains `fan-out` row for batch-op summaries.
- **v3.2** (2026-05-18 a24ff9f) — restore persona emoji as identity-anchors after the operator's "эмоджи адвайзеров, исполнителей и других агентов системы мы можем показывать, потому что они как раз создают визуальную связь" feedback. Header now leads with speaker emoji; cross-references to other agents keep their emoji in value cells. Per-row decorative emoji still forbidden.
- **v3.1** (2026-05-18 f497713) — wrap whole Summary in ▍ gutter + bold keys after the operator's "итог сливается с остальным выводом, секции и ключевые слова не выделяются" feedback.
- **v3** (2026-05-18 ae66f5d) — full rewrite to Variant C minimalism after the operator's "слишком пестро" feedback + web research diagnosis. Removed 27-glyph palette, sidecar lane, table layout, box-frames. Exception-only severity.
- **v1** (2026-05-18 5e63a34) — initial contract with Render-B table + advisor overlay. Outdated within the same day.
