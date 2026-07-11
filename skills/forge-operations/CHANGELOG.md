# team.forge changelog

All notable changes to the skill.

## Persona Voice — Three Layers — 2026-05-08 (third pass same day)

Restructured the contract into three explicit layers after Ignat flagged
that advisors should hallucinate from their own biography (not generic motifs)
and each should have a distinct voice fingerprint.

### Changed

- `contracts/persona-voice.md` v1.1.0 → v1.2.0:
  - **Layer 1 — emoji prefix** (unchanged, hard rule).
  - **Layer 2 — Voice signature** (NEW): per-advisor linguistic fingerprint. Sentence rhythm, default response shape, vocabulary tells, pet phrases, what this voice never does. The layer Ignat reads to recognise who's speaking without checking the prefix.
  - **Layer 3 — Biographical wells** (NEW): vignettes are drawn from the advisor's `memory/personality.md`, not from generic professional motifs. Hallucinations should sound like *this specific person's life*. Off-topic personal questions answered in character — biography is always live. Don't poach other advisors' wells.
- Per-advisor `## Persona Voice` blocks renamed `## Voice Signature` and rewritten across kai/nexus/shade/spark — with denser content drawn from each advisor's existing personality.md (152/198/136/120 lines respectively).
- Quorum's `## Voice Signature` updated, but `memory/personality.md` is still 10 lines (vs 120-198 for others). Left as a self-update task for Quorum per Ignat (GH issue under `advisor:quorum`).
- `references/agent-model-version.md` 1.2.0 → 1.3.0.
- Stamps: kai/nexus/shade/quorum 1.2.0 → 1.3.0, spark 1.3.0 → 1.4.0.

### Why

Previous "motif pool" approach gave advisors topical references but no biographical depth and no voice fingerprint — they sounded like the same LLM with different topic lists. Three-layer model anchors each advisor in a specific *life* with a specific *speaking style*.

## Persona Voice Relaxed — 2026-05-08 (same day, later)

Loosened the v1.0.0 contract after Ignat flagged it as too strict.

### Changed

- `contracts/persona-voice.md` v1.0.0 → v1.1.0:
  - Removed hard cap (`≤ 1 vignette per 5 replies`) — saturation is taste, not arithmetic.
  - Removed strict trigger gate — Layer 2 is now "encouraged on natural moments", not "ONLY on these 4".
  - Motif pools downgraded from "fence (drift = audit finding)" to "examples that establish texture".
  - Suppression rules became "soft mute" (judgement) instead of "MUST suppress" (ban).
  - New section: **Friendly business etiquette (non-negotiable)** — 6 firm rules covering real-name citations, invented metrics, persona-as-deflection, dropping frame when asked.
  - Quorum nuance reframed: warmth welcome, side-taking still forbidden — same line, friendlier framing.
- Per-advisor `## Persona Voice` blocks rewritten in the new register across kai/nexus/shade/spark/quorum — added "self-deprecating beats", "honest moments", "dry humour" textures.
- `references/agent-model-version.md` 1.1.0 → 1.2.0.
- Stamps: kai/nexus/shade/quorum 1.1.0 → 1.2.0, spark 1.2.0 → 1.3.0.

### Why

Original strictness made advisors theatrical at best, sterile at worst. New register: friendly colleague with a history, business-ethical guardrails firm, taste over rules.

## Persona Voice — 2026-05-08

Hybrid persona expression for all 5 advisors. Spec: ad-hoc evolve via `/team.forge`, no formal spec file.

### Added

- `contracts/persona-voice.md` (v1.0.0) — shared contract: Layer 1 (always-on `<emoji> <name>:` prefix) + Layer 2 (contextual vignettes on 4 triggers: greeting / subjective judgement / closing summary / divergence). Per-advisor motif pools, suppression rules, user overrides, audit hooks.
- `## Persona Voice` block in all 5 advisor SKILL.md (kai, nexus, shade, spark, quorum) — references the contract + lists 4-5 motifs + lists per-advisor suppression contexts.

### Changed

- `references/agent-model-version.md` bumped 1.0.0 → 1.1.0 (MINOR — new required behaviour, no structural break).
- `forge.model-version` stamps:
  - kai-cto: 1.0.0 → 1.1.0
  - nexus-ceo: 1.0.0 → 1.1.0
  - shade-ciso: 1.0.0 → 1.1.0
  - spark-cmo: 1.1.0 → 1.2.0 (was already ahead of standard)
  - quorum: 1.0.0 → 1.1.0
- `last-evolve` set to `2026-05-08` for all 5 advisors.

### Quorum nuance

Quorum's Cardinal Rule #1 ("never express personal opinions") is preserved — vignettes for Quorum are constrained to procedural / facilitative anecdotes only, with explicit "if unsure → drop" guidance.

### Known follow-ups

- `protocols/audit.md` does not yet enforce the audit hooks listed in `persona-voice.md` (prefix presence, vignette saturation, motif drift). Adding these is a separate evolve.
- Persona-mode propagation to `templates/SKILL.md.template` for future-hire defaults — tracked separately.

## Feedback Loop — 2026-04-27

Added the advisor feedback journal under `agent-memory/advisors/feedback/`. Spec: `ops/specs/052-advisor-feedback-loop/spec.md`.

### Added

- `lib/feedback.sh` — vocabularies (scope/severity/type), `mkdir`-based locking, ISO8601 ts + `fb-<unix>-<6hex>` id generators, JSONL line builder with `jq`-safe escaping.
- `report-issue.sh` — writer CLI with auto-commit; validates enums and canonical advisor inventory + `lifecycle` sentinel; survives crash without `/team.done`.
- `summarize-feedback.sh` — grouped triage report (severity / skill / advisor / scope+type), `--since` / `--advisor` / `--severity` / `--include-archive` filters.
- `archive-feedback.sh` — moves resolved entries from `journal.jsonl` to monthly `archive/YYYY-MM.jsonl`, refuses re-archive, auto-commits.
- `contracts/feedback-protocol.md` — schema, vocabularies, reaction policy (blocker halts, high explicit-workaround, medium/low silent).
- 6 new bats files: `lib-paths-feedback.bats`, `lib-advisors-lifecycle.bats`, `lib-feedback.bats`, `report-issue.bats`, `summarize-feedback.bats`, `archive-feedback.bats` (43 tests total, all green).

### Changed

- `lib/paths.sh` — added `feedback_dir()` and `feedback_archive_dir()` helpers.
- `lib/advisors.sh` — `is_canonical_advisor` now accepts an optional `--allow-lifecycle` flag (lets the literal string `lifecycle` pass for infra-skill self-reports).
- All 5 lifecycle SKILL.md (`team.start`, `team.processing`, `team.done`, `team.handoff`, `team.forge`) reference `feedback-protocol.md` and carry a one-line "Feedback Rule".
- `agent-memory/advisors/README.md` — layout table now documents `feedback/journal.jsonl` and `feedback/archive/YYYY-MM.jsonl`.
- `.ai/.claude/CLAUDE.md` — Conditional Context table references `feedback-protocol.md`.

### Intentional deviations from existing pattern

- `report-issue.sh` and `archive-feedback.sh` auto-commit per call (one entry / one batch). `mention.sh` and `file-decision.sh` leave commits to callers; this is approved in spec §"Commit Cadence" because feedback must survive crash without a follow-up `/team.done`.
- No `flock(1)` dependency — uses `mkdir feedback/.journal.lock` retry loop (3s cap). `flock` is absent on stock macOS.

## [1.0.0] — 2026-04-18

Initial release. Unified advisor-model meta-skill replacing `team.hire`.

### Added

**Protocols:**
- `protocols/hire.md` (v2.2.0) — advisor creation via deterministic script + LLM enrichment.
- `protocols/evolve.md` (v1.0.0) — composable aspect-based mutation, 8 stages.
- `protocols/audit.md` (v1.0.0) — 7-category drift detection.

**Aspects (8 composable refs):** identity, responsibilities, toolbox, memory-structure, lifecycle, shared-rules, agent-frontmatter, contract-overlays.

**Top-level refs:** agent-model-version (1.0.0 baseline), color-palette (16-color pool), quality-checks (Internal Quality Loop), commit-conventions.

**Scripts (11 total, each with paired test + `set -euo pipefail`):**
- `verify-skill.sh` — resolve skill name to SKILL.md path (reject phantoms).
- `find-references.sh` — grep-based usage scanner.
- `create-advisor.sh` — scaffolds new advisor from 4 templates with `$VAR` substitution.
- `register-advisor.sh` — discovery-driven CLAUDE.md + Quorum registry rebuild.
- `bump-model-version.sh` — stamps `forge.model-version` in advisor frontmatter.
- `apply-overlay.sh` — creates per-advisor contract overlay scaffold.
- `audit-versions.sh`, `audit-phantom-skills.sh`, `audit-bloat.sh`, `audit-registry-consistency.sh`, `audit-overlays.sh`.

**Templates (4):** `skill-frontmatter.md`, `agent-frontmatter.md`, `briefing-awaiting.md`, `personality.md`.

**Contracts (7 shared, advisor-only):** session-lifecycle, first-launch-protocol, decision-framework, quality-loop, advisor-anti-patterns, agent-data-policy, github-issues-protocol.

**Overlays (2):**
- `team.kai-cto/contracts/session-lifecycle.md` — constraint: no code editing (delegates to /exec.atlas-dev).
- `team.nexus-ceo/contracts/github-issues-protocol.md` — extension: cross-advisor visibility.

### Changed

- All 7 advisors (kai, nexus, shade, spark, vox, dev, quorum) stamped at `forge.model-version: 1.0.0`.
- 5 advisors (kai, nexus, shade, spark, vox) thin-refactored: process logic moved to `team.forge/contracts/`, only identity + domain content kept in SKILL.md.
- `team.hire` deprecated — replaced with redirect stub pointing to `team.forge`. Removal date: 2026-04-24.

### Known follow-ups (not blocking merge)

**Spec-text drift (Phase 5):**
- `protocols/evolve.md` references `SKILL.md Section 7.3/7.4` — anchors don't exist yet; content is present in spec 049 §7.3/7.4.
- `references/aspects/lifecycle.md` uses YAML brace-expansion `team.{start,processing,...}` that won't expand as a literal string.
- `references/aspects/memory-structure.md` mixes `.claude/` prefix with bare `skills/` paths.

**Script hardening (Phase 6):**
- `bump-model-version.sh`: add `trap 'rm -f "${tmp:-}"' EXIT` after `mktemp`. Also: script silently no-ops when advisor lacks `forge:` block (must be added manually — as done for exec.atlas-dev + team.quorum in Phase 8).
- `register-advisor.sh`: strip `|` from role before emitting Markdown table row.
- `register-advisor.test.sh`: assert on section header, not on live advisor name.
- `audit-phantom-skills.sh`: regex over-broad; matches English words like `any`, `to`, `name` as skill names. Scope to structured skill references only.
- `audit-phantom-skills.test.sh` / `audit-bloat.test.sh`: inject known-bad fixture so tests verify detection (currently only assert exit 0).
- `apply-overlay.sh`: replace `${TYPE^}` (bash 4+) with POSIX `tr` substitution.

**Bloat budget (Phase 7):**
- All 5 refactored advisors exceed the 100-line target (106-134). Content is genuine identity/domain per DONE_WITH_CONCERNS — further trim-pass optional.
- `team.quorum` at 299 lines (CRIT per `audit-bloat.sh`) — candidate for dedicated thin-refactor pass.

**Registry (Phase 9):**
- CLAUDE.md has no Custom Agents table. Either add one or update `audit-registry-consistency.sh` expectation.

**Overlay content:**
- Nexus `github-issues-protocol` overlay: spec §4.7 provided no verbatim template; content written from spirit of the spec description.

### Smoke-test deferred

Plan Phase 9 Task 9.2 requires fresh-session smoke-tests for 3 advisors (Kai code-delegation constraint, Nexus cross-advisor visibility, Shade default session-lifecycle). User to run manually.

### Cleanup deferred

Plan Phase 12 schedules deletion of `team.hire/` directory on 2026-04-24.
