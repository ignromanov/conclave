---
kind: agent-model-ssot
version: 1.4.0
---

# Agent model standard

Single source of truth for the agent-model semver. Stamped into each advisor's
`SKILL.md` frontmatter under `forge.model-version`.

## Current standard: 1.4.0

Spark-parity baseline — voice signature + biographical wells + post-absorption role depth (CMO+CCO merge precedent) recognized as standard. All advisors now stamped to match Spark's lead, which had been one minor ahead since `persona-voice` v1.0.0.

## Semver lens
- **MAJOR**: structural break (e.g., move personality.md → new path)
- **MINOR**: new required aspect or template (e.g., adding `personality.md` as required)
- **PATCH**: wording / copy edits, no behavior change

## Changelog

### 1.4.0 — 2026-05-17 (Spark-parity recognition)
- No functional change to required aspects; this is a **parity bump** that recognizes Spark's lead (consistently +1 minor since v1.1.0) as the new floor.
- Trigger: `forge audit` flagged Spark 1.4.0 as MINOR-gap WARN against standard 1.3.0; rather than rolling Spark back, the standard advances to recognize the depth that Spark codified (dual-role CMO+CCO baseline, voice signature stabilized).
- Stamps: kai/nexus/shade/quorum 1.3.0 → 1.4.0, spark unchanged at 1.4.0.
- Future bumps should originate from `references/agent-model-version.md` first, then propagate via `bump-model-version.sh --all`, rather than per-advisor drift.

### 1.3.0 — 2026-05-08 (third pass same day)
- `persona-voice` v1.1.0 → v1.2.0: introduced **three explicit layers** — Layer 1 (emoji prefix, hard rule), Layer 2 (Voice Signature: per-advisor linguistic fingerprint), Layer 3 (Biographical wells: vignettes drawn from `memory/personality.md`).
- Per-advisor `## Persona Voice` blocks renamed to `## Voice Signature` with denser content: sentence rhythm, default response shape, vocabulary tells, pet phrases, allowed-colour-from-the-well, never-list, soft-mute conditions.
- Quorum personality.md still thin (10 lines) — left as self-update task per Ignat (filed as GH issue under `advisor:quorum`).
- Stamps: kai/nexus/shade/quorum 1.2.0 → 1.3.0, spark 1.3.0 → 1.4.0.

### 1.2.0 — 2026-05-08 (later same day)
- `persona-voice` v1.0.0 → v1.1.0: removed hard 1-per-5 cap, removed "ONLY on 4 triggers" gate, motif pools became *examples not a fence*.
- New section: **Friendly business etiquette (non-negotiable)** — no real-name citations as fact, no invented metrics as evidence, no pretending the persona is real, no using persona to dodge hard questions.
- Per-advisor blocks rewritten in "soft mute" voice. Quorum's Cardinal Rule #1 preserved but reframed: warmth allowed, side-taking still forbidden.
- Stamps: kai/nexus/shade/quorum 1.1.0 → 1.2.0, spark 1.2.0 → 1.3.0.

### 1.1.0 — 2026-05-08
- Added `contracts/persona-voice.md` — hybrid persona expression (Layer 1 always-on `<emoji> <name>:` prefix + Layer 2 contextual vignettes on 4 triggers).
- All 5 advisors gained a `## Persona Voice` block listing motif pool + suppression rules.
- Spark bumped 1.1.0 → 1.2.0 (was already ahead of standard); rest 1.0.0 → 1.1.0.
- Quorum gets persona mode with the Cardinal Rule #1 nuance: vignettes must be procedural/facilitative only.

### 1.0.0 — 2026-04-18
- Initial standard: identity + responsibilities + toolbox + memory-structure + lifecycle + shared-rules + agent-frontmatter + contract-overlays aspects defined.
- Thin advisor discipline enforced (target ≤100 lines per SKILL.md).
- Contract isolation inside ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/.
