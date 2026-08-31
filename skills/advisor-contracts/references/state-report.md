---
type: contract
name: state-report
schema_version: 1.0
applies_to: [all advisor SKILL.md, team.start, team.processing]
stages: [clarify, deliver]
tiers: [quick, work]
task_types: [advisory, research, review]
binding: required
last_reviewed: "2026-08-31"
---

# State Report Contract — the inventory surface

> **Purpose**: governs the surface an advisor produces when the operator asks a *state question* —
> "what is going on", "where are we", "что происходит" — across specs, tasks, queues, CI, or any
> subset. `output-formatting.md` governs the *session summary* (an exception surface: silence on
> success). This file governs the *state report* (an inventory surface: successes are load-bearing
> information). The two are injected together; this header line is the scope boundary.
>
> **Origin**: spec 115. Failing scenario on record: the 2026-08-31 state report the operator could
> not skim («информации слишком много, либо нет контекста»). Every rule below traces to evidence
> in `115-state-report-display-contract/research/` (DATA).

## The surface class test

A render is a state report iff it answers a question about **the system's state**, not about **the
run that produced the render**. Its verdict token (`done` etc., output-discipline R1) describes the
run; nothing in the report's *content* is that token — the system is never "done". A session
summary closes a run; a state report answers a question. When in doubt: if "9 specs done" is signal
rather than noise, you are on this surface.

## Shape — two layers, one answer

1. **Glance layer** — one ▍-block, ≤ 12 content lines. Readable in seconds, no scrolling assumed.
2. **Work layer** — full detail below, one `##`-section per glance row, same names, same order.
   The glance block is the table of contents. Completeness lives here, never in dialogue
   follow-ups (drill-down questions are a bonus the contract must not rely on).
3. **Proof layer** — inside each work section: the file path or command that regenerates every
   number. Exists so any count can be checked in one hop.

## Rules

### 1. The voice is always named

Line 1 of the glance block is the speaker anchor: persona emoji + advisor id + surface name +
date. An advisor speaking in role never emits an unattributed conclusion: advisor-voiced blocks
carry the ▍ gutter and open with the anchor; prose outside ▍-blocks is working narration, not a
finding. (Operator directive, 2026-08-31: «адвайзер всегда должен напоминать что он работает в
роли».)

### 2. Slot order — by what the reader must do

Fixed order, fixed names, every run (signaling beats ad-hoc ordering; fixed positions let a repeat
reader diff against memory):

| # | Slot | Carries |
|---|---|---|
| 0 | **состояние** | one counted-noun summary line, same categories in the same order every time, zeros included |
| 1 | ✗ **блокер** | what is blocked right now, with its cause and its known remedy |
| 2 | ⚠ **за вами** | decisions only the operator can make |
| 3 | ⚠ **стоит** | queues that have not moved — the staleness slot |
| 4 | **движется / чисто** | in-flight work, then explicit positive claims |
| 5 | **next →** | actions, owner-attributable, no line numbers |

Uncertainty ranks *above* known-bad within a slot (Icinga: UNKNOWN before WARNING) — "we cannot
tell" is more urgent than "we know it is degraded". ≤ 4 deviation clusters total (Cowan 4±1);
more findings than that are grouped, not flattened.

### 3. Success is stated, never implied

Every section ends in a positive claim in words when clean — the `git status` "working tree clean"
convention. On this surface, an omitted row is NOT a green signal (that rule is
`output-formatting.md` §1 and stops at the session summary's edge). Zeros render.

### 4. No bare identifiers — the referent travels with the pointer

`#142`, `spec 109`, a slug, a SHA: a pointer, not a message. Every identifier carries an inline
gloss in the same cell — `104 (конституция: запустить пилот)`, `#150 (починка hot.md)`. The unit
is the *screen*, not the document: terminal output scrolls, so the gloss repeats per block, like
the subject line in `git log --oneline`. A symbol is an identifier too — any glyph outside the
functional four gets a word beside it. (Curse of knowledge, 1989; GitHub / git 50/72 /
Bluebook 10.9 convergence. The critique of this very contract mis-dereferenced a bare spec number
while holding the registry — the rule has no exception for experts.)

### 5. Every count carries its scope noun and its one-hop path

"0/237" is a numeric bare identifier. Render "0 из 237 фидбек-записей resolved", and the work
section behind it names the file or command that reproduces the number (exemplar model: the
aggregate stays a number, the rows are one hop away). A compressed summary must preserve the
categories the reader decides on (Terraform's own filed defect: "replace" folded into add+destroy).

### 6. Absence is not zero

A measured zero renders `0`. An instrument that never ran renders `—` plus a mandatory reason in
words: `триаж — не шёл ни разу (last-triage пуст)`. The two must never render alike (SQL NULL,
aviation OFF-flag). `—` with no reason clause is a violation — it is the greyed-out chart in a new
costume. (The web dashboard renders the same primitive as `◌ unknown` per
`display-contract-liveness.md` §3.1; the terminal uses `—` because U+25CC is a combining
placeholder with unreliable standalone rendering.)

### 7. Staleness has a grammar

Every queue gets two thresholds (warn / error, dbt source-freshness model) computed from the last
**movement** of the queue, never the last read of it. Age renders beside the verdict as evidence:
`стоит · медиана 35д`. "Stale" (aged past threshold) and "absent" (rule 6) are different states
and render differently.

### 8. The glance layer carries no coordinates

No file:line, no command strings, no byte counts in the glance block. A filename may appear as a
noun (`hot.py`); a line number may not (`hot.py:6,45` is work-layer material). The glance row
states the claim; the work section under the same name carries the coordinate. This is what keeps
the 12-line promise — citations and glosses compete for the same lines, and the gloss wins in
layer 1.

### 9. Work layer grammar

- Tables are **permitted** here for ≥ 3 items sharing the same fields (specs, issues, queues) —
  a deliberate carve-out from the session-summary anti-pattern, because a fixed column position is
  what makes 20 rows scannable. Key-value ▍-rows are for heterogeneous one-off facts.
- A fact never lives inside a prose paragraph. Prose appears only in "reason" cells and wraps
  ≤ 72 columns.
- Bold marks at most one fact per section (anchor keys aside) — uniform emphasis is zero emphasis.
- A fixed **ruled out** slot discloses hypotheses investigated and falsified during the survey,
  one line each (ICD 203 analysis-of-alternatives; a silently dropped retraction biases the
  report exactly like an undisclosed forking path).
- **not checked** (output-formatting slot 6) transfers to this surface unchanged: sources not
  consulted are listed, because an incomplete answer that looks complete is this surface's worst
  failure (the 2026-08-31 report would have been "wrong by omission and confident" had one
  unprompted question not been asked).

### 10. Language is systematic, not mixed

Keys and prose in the operator's language (instance configuration). Identifiers, registry status
literals, and proper names stay in their original form (`PR`, `done`, `live lane`). The split is
predictable per token class — that is the pattern code-switching research prices at zero; a
per-row mix is not.

### 11. One model, three printers

The state projection (the counts, statuses, ages and their sources) is one canonical model. This
terminal render, the spec-102 dashboard, and a future `engine status` (GH#57, "one command
emitting the whole projection") are printers over it. A printer's formatting need never bends the
model; a display requirement that needs a missing field specifies the field and hands it to the
read-model owner — after checking the field actually exists (GH#142: four displays chartered over
phantom fields).

## Reference render (instance-language example)

```
▍ 🎨 **kosmos-cxo · состояние · 31.08**
▍ 1 блокер · 3 решения за вами · 3 очереди стоят · 9 спек готово
▍
▍ ✗ **блокер**   PR #150 (починка hot.md) красный 9 дней — фраза из чартера
▍                в докстринге триггерит анти-утечку · лечение: переписать 2 строки
▍ ⚠ **за вами**  решения: 104 (конституция: запустить пилот) ·
▍                109 (имя для executors) · 113 (чем заменить engine publish)
▍ ⚠ **стоит**    фидбек: 0 из 237 записей resolved · триаж — не шёл ни разу
▍                хендофы: 13 открыто, архив пуст · issues: 67 из 99 старше месяца
▍ **движется**   4 спеки в работе · ⚠ 110 КБ спек-работы не в коммитах DATA
▍ **чисто**      9 спек готово · CI live-линия зелёная
▍ **next →**     переписать 2 строки в hot.py · закоммитить DATA · триаж
```

Work layer follows as `## блокер`, `## за вами`, `## стоит`, `## движется / чисто` — same order —
then `## ruled out` and `## not checked`. Sample work section:

```
## стоит · фидбек

0 из 237 записей resolved — за всю историю тетради.
триаж — не шёл ни разу: _index/last-triage существует и пуст (0 байт)

статус      n     примечание
accepted    157   32 high — без issue-ссылки
deferred    56
open        23    возраст 9–12д · порог триажа: warn 7д · error 14д ✗
re-occurred 1

→ пруф: .conclave/ops/feedback/_index/index.jsonl
```

## What carries over, what does not

| From | Carries over | Does not |
|---|---|---|
| `output-formatting.md` | ▍-gutter + bold keys · functional glyph set (⚠ ✗ ▍ →) · persona emoji as identity anchors · severity source-of-truth (⚠/✗ only from a real signal) · slot 6 not-checked · `next →` | §1 silence-on-success · zero-rows anti-pattern · the 8-slot task-report skeleton (built for a reviewer verifying one run; this reader is a principal asking "what needs me") |
| `output-discipline.md` | R1 (the report is the run's one terminal object) · R7 interrupts · R8 typed questions | R3 does not apply to the report body — a state report is conclusions by design |
| `display-contract-liveness.md` | absence-vs-zero as a semantic primitive · degrade-never-lie · per-source freshness | the `◌` glyph (web-only render) · process-liveness states (that contract governs the process axis; this one governs artifacts and queues — a report mixing both cites each contract for its own axis) |

## See also

- `output-formatting.md` — the session-summary render this contract is scoped against
- `output-discipline.md` — emission discipline; R1/R7/R8 bind here too
- `.conclave/ops/specs/115-state-report-display-contract/` — spec + research evidence (DATA)
- `.conclave/ops/specs/102-engine-web-dashboard/display-contract-liveness.md` — the process axis
- GH#57 (`engine status` — the printer that makes this report cheap) · GH#142 (displays over
  phantom fields — the chartering discipline rule 11 inherits)

## Changelog

- **v1.0** (2026-08-31) — initial contract. Spec 115; commissioned by forge-chro's 2026-08-31
  handoff, redesigned against the operator's skim-failure on the first state report, five executor
  research passes, and a red-team critique whose findings are folded into rules 4, 5, 6, 8, 10.
