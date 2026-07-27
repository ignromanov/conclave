---
description: |
  MANDATORY session completion checklist for ALL advisors (with or without Quorum).
  3 mandatory + 5 conditional items (1-8), DO-CONFIRM format.
  Every advisor session MUST end with this skill. No exceptions.
  Conditional items 4-9 fire situationally — rarely all at once (WHO Checklist research favours ≤7 active per run).
---

!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/agent-data-policy.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/github-issues-protocol.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/session-lifecycle.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/advisor-anti-patterns.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/feedback-protocol.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/output-formatting.md`

# /conclave:done — Completion Checklist

> **MANDATORY** for every advisor session. Works independently — no Quorum required.

## Closing the session

### Phase: Feedback emission

**MANDATORY** — every advisor emits a work review via `/conclave:feedback` before filing
session artifacts. This is the single feedback channel (spec 086).

```bash
python engine/scripts/feedback/feedback_emit.py \
  --agent <advisor-slug> \
  --agent-type advisor \
  --session-ref <session-id> \
  --skill-version sha256:<12-hex>
```

Fill `items[]` (cap 3–5, `evidence` mandatory), then set `_draft: false`.
A zero-mutation session may use `--no-op` (empty `items[]` + summary line).
See `${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/feedback-protocol.md` §How-to-emit for full schema.

### Mandatory emission gate (AC12)

Before proceeding past the Feedback emission phase, run the enforcement gate to
verify a non-draft emission file exists for this session:

```bash
CONCLAVE_AI_ROOT="$(pwd)" \
TODAY="$(date +%Y-%m-%d)" \
ADVISOR_NAME="<advisor-slug>" \
SESSION_ID="<session-ref>" \
  python -m engine session emission-gate
```

If the gate exits non-zero, the emission is missing or still `_draft: true`.
Complete `/conclave:feedback` before continuing. The gate is the
`engine session emission-gate` command (tested by
`engine/scripts/tests/cmd/test_session_close.py`).

---

1. Compose artifacts into /tmp/:
   - `/tmp/session-body-<ts>.md` (always)
   - `/tmp/decision-<slug>.md` per decision made (if any)
   - `/tmp/mention-<i>.md` per mention sent (if any)
   - `/tmp/handoff-<slug>.md` (if handing off)

2. For each decision, call:
   ```bash
   python -m engine file decision \
     --slug <slug> --by <advisor> --date <ISO-date> \
     --body-file /tmp/decision-<slug>.md \
     [--meeting <ref>] [--session <pre-computed-session-id>]
   ```

3. For each mention, call:
   ```bash
   python -m engine mention create \
     --from <advisor> --to <recipient> \
     --body-file /tmp/mention-<i>.md \
     [--priority p0|p1|p2|fyi] \
     [--ref-session <session-id>] [--ref-decision <slug>] [--ref-issue AI#N]
   ```

4. Close the session:
   ```bash
   python -m engine session close \
     --advisor <advisor> --slug <session-slug> --date <date> \
     --body-file /tmp/session-body-<ts>.md \
     [--decisions <slug,slug>] \
     [--resolves-mentions <id,id>] \
     [--handoff-file /tmp/handoff-<slug>.md \
      --handoff-to <advisor> --handoff-priority <p0|p1|p2|p3> \
      --handoff-title <title> --handoff-slug <slug>] \
     [--issues-touched AI#N,AI#N] \
     [--reflexion "<one-sentence post-mortem; '—' if nothing notable>"]
   ```

   The `--reflexion` arg is **mandatory**. If genuinely nothing to reflect on, pass `"—"`.
   It is persisted to `session.md` frontmatter and read by `/conclave:start` for the next 3 sessions
   of this advisor. See `${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/output-formatting.md` for the sidecar lane spec.

   The `--handoff-file` arg files a **new** handoff inline — it requires all four
   companions (`--handoff-to`, `--handoff-priority`, `--handoff-title`, `--handoff-slug`);
   omitting any one aborts the call. If the handoff was already created separately via
   `file-handoff.sh`, omit `--handoff-file` entirely and reference the handoff path in
   the session body prose.

5. One aggregate commit:
   ```bash
   cd "$CONCLAVE_AI_ROOT"   # the .ai root
   git add agent-memory/advisors ops/handoffs
   git commit -m "session: <advisor> <slug> (decisions:N, mentions:M, handoff:Y/N)"
   ```

6. GH issues sync: for every `AI#N` in `--issues-touched`, run `gh issue comment <N> --body "..."` as usual (not script-wrapped).

## Checklist

### Mandatory (always)

1. ☐ **All changes committed** (both repos if applicable)
   - Run: `git status` in both `/` and `.ai/`
   - If uncommitted changes → commit or explain why not
   - Gate: **Auto**

2. ☐ **GH Issues synced** (both repos)
   - **Worked on issue** → comment with session result + update Project Board status
   - **Issue complete** → close it + archive project item:
     ```bash
     gh issue close NUMBER -R REPO --comment "Done in session YYYY-MM-DD"
     ```
   - **New actionable task discovered** → recommend creating GH issue (Ignat confirms)
   - **Hit blocker** → set Project Board status → `Blocked` + comment explaining blocker
   - Gate: **Auto** (comment/status) / **Notify** (close — show user after)

3. ☐ **Session artifacts filed** (scripted flow above)
   - Decisions → `file-decision.sh`
   - Mentions → `mention.sh`
   - Session record + handoff → `close-session.sh`
   - Single aggregate commit under `agent-memory/advisors` + `ops/handoffs`
   - (Briefing regenerates on next `/conclave:start`; no manual action here.)
   - Gate: **Auto**

### Conditional

4. ☐ **IF session produced new knowledge** → wiki updated
   - Preferred: invoke `/wiki:capture --clipboard "Title"` with session summary
   - For web sources discovered: `/wiki:capture <url>`
   - Architecture registries (`.ai/architecture/`) — update directly (code-coupled)
   - Gate: **Auto** — always capture if knowledge was produced

5. ☐ **IF new slice/component** → architecture registries updated
   - `architecture/fsd-registry.md`
   - `architecture/ui-index.md`
   - `architecture/types-registry.md`

6. ☐ **IF spec deviation** → spec.md updated
   - Compare implementation vs spec
   - Gate: **Approve** — AskUserQuestion before modifying spec

7. ☐ **IF work incomplete** → invoke `/conclave:handoff`
   - Creates structured resume-prompt for next session

8. ☐ **IF skill gap found** → log for creation
   - What was needed but didn't exist
   - Gate: **Notify** — recommend invoking `writing-skills`

9. ☐ **IF the agent holds duties** → discharge check (spec 091 §4)

   Record what became of each duty that activated this session, then report what is still
   owed. `condition` is prose **you** evaluate in context — the check cannot decide it for
   you, which is exactly why an unanswered conditional is surfaced instead of assumed in
   either direction.

   ```bash
   # one per duty that activated
   # outcome ∈ discharged | deferred | skipped | errored | condition-unmet
   python -m engine duty record --advisor <id> --duty <duty_id> \
     --session <session_id> --outcome <outcome> [--note "..."]

   python -m engine duty discharge --advisor <id> --session <session_id>
   ```

   Exit 0 = nothing owed → omit the row. Exit 2 = something deferred or unevaluated, which
   is **not** a failure: surface the `DEFERRED:` / `UNEVALUATED:` lines as a ⚠ **duties**
   row in the Session Summary and let the operator decide. Suppressing them is precisely
   what turns a duty model back into documentation.

   Record the unhappy outcomes as readily as the happy one. A ledger holding only
   discharges lets a duty that errors every time read as healthy, and the §5 health sweep
   has nothing else to read.

   Executors use `--executor <slug>` and run this at dispatch end, not session end — they
   have no session lifecycle (`executor-protocol.md`).
   - Gate: **Auto** (record) / **Notify** (anything owed)

## Risk-Adaptive Gates

| Gate | Meaning |
|------|---------|
| **Auto** | Agent does it, mentions in summary |
| **Notify** | Agent does it, shows user after |
| **Approve** | AskUserQuestion before action |
| **Escalate** | Explicit user "yes" required |

## Summary Format

The `/conclave:done` chat output is the `▍`-framed Session Summary block. Its render rules,
examples, severity source-of-truth, and the `/conclave:done` key set are defined **once** in
`output-formatting.md` (auto-imported above) — §Render format, §Per-skill instantiation,
§Severity source-of-truth. Do not restate the contract here; follow it.

## Retro trigger (optional)

After every 3rd `/conclave:done` invocation (or after major spec merge), suggest:

> "Last 3 sessions closed. Run `/conclave:retro`?" (AskUserQuestion: yes / not now)

If yes → invoke `team.retro` skill. If no → carry counter to next session.

## Phase: Study (Phase 2 E14)

Knowledge-graduation step. Runs after artifact filing, before session-close commit.
**Non-blocking per ADR-0003 `wiki_failure_policy: defer`** — failures log + continue.
**P0-blocking exception** per ADR-0003 `wiki_p0_policy: block` — see step 4 below.

Run all 6 steps in one call:

```bash
python3 engine/scripts/lifecycle/study_phase.py --advisor <advisor>
```

- Exit 0 → all clean; omit study row from Summary
- Exit 2 → non-blocking findings (captures / P1 stale / link violations); emit `⚠ study` row
- Exit 3 → **P0 BLOCKING** (wiki-audit-stale contradictions / canonical-ref drift) — must triage before close-session commit; emit `✗ study` row
- Exit 1 → orchestration error; treat as P1

Steps orchestrated (in order): capture-suggest → promote-decision (per candidate) →
bridge-rebuild (if ≥1 promoted) → audit-stale (P0-blocking) → hot-sync (always) → link-check.

`study_phase.py` is the single orchestrator for all six steps — there is no per-step shell
entrypoint. For direct wiki operations (capture, audit, link-check) use the `/wiki:*` plugin
commands (e.g. `/wiki:capture`, `/wiki:audit`), which own the vault after the wiki extraction.

### Aggregate Study summary

Collapsed into one row inside the ▍-block (inline, no sidecar lane):

```
▍ ⚠ **study**    link:violations {N} open · capture:{N} · promoted:{N} · stale:P0:{N}/P1:{N}
```

Render rules (per `output-formatting.md` silence-on-success):
- All Study steps exit 0 → **omit the row entirely** (clean = absent)
- Step 4 P1 stale OR step 6 wikilink violations → emit row with `⚠` (informational)
- Step 4 exit 3 (P0 BLOCKING) → emit row with `✗` (must triage before close-session commit)

Drop zero counters from the row text — show only fields that have non-zero values.

### Anti-patterns

- Skipping Study because "tests pass, ship it" → defeats knowledge graduation
- Promoting every candidate (bypassing 5-test filter) → wiki signal degrades
- Treating Study exit codes as blocking (except step 4 P0) → violates `wiki_failure_policy: defer`
- Running Study INSIDE close-session.sh → must run BEFORE close-session for failures to be visible in the session record

---

## Phase: Infra (run-log surface)

Surfaces telemetry that `lib/run-log.sh` is already writing to
`agent-memory/run-log/<YYYY-MM-DD>.jsonl` on every script invocation. Zero new instrumentation —
the data exists; we just render it.

### When

After Study phase, before Reflexion. Non-blocking.

### Script

```bash
python -m engine lifecycle runlog-summary --advisor <advisor> --date <YYYY-MM-DD>
```

Output: one row body ready for the Summary column block. Examples:

- Clean session (all exit 0) → script emits a clean signal; **row is OMITTED from Summary**
- One failure → `1 script · gh-fetch.sh exit=2`
- P0 failure → row prefixed with `✗` instead of `⚠`

### Severity → render

- All scripts exit 0 → **omit the row entirely**
- Any non-zero exit, none P0 → emit row with `⚠`
- Any P0 script failed (`briefing-build.sh`, `close-session.sh`, `file-decision.sh`) → emit row with `✗`

### Inline render

```
▍ ⚠ **infra**    {script_count} scripts · {first_failing_script} exit={code}
```

Drop `total_ms` from default render — surface only on `--verbose` or when a script blew through
a perf budget (future). Time-on-success is vanity per the output-formatting contract.

---

## Phase: Lifecycle Retrospective

Structured self-review of the **lifecycle infrastructure itself** through the lens of *this* session. Distinct from Reflexion (one-sentence advisor post-mortem about the work) and from the passive feedback rule (report-on-encounter). This phase asks the agent to actively scan five lenses for improvement signals — even when nothing visibly "broke".

Inspired by Toyota's *hansei* (反省): explicit reflection on what could be better, expected even when outcomes were good. Maps each finding to the `/conclave:feedback` channel (spec 086).

### When

**Execution order**: Study → Infra → **Lifecycle Retrospective** → Reflexion → hot.md → `close-session.sh`. Runs every session — non-blocking.

Rationale for slot: Infra's exit-codes are needed as inputs to the **broke** lens; Reflexion (the one-sentence post-mortem persisted to session frontmatter) can then quote the highest-leverage Retrospective finding. Documentation order matches execution order — Study → Infra → Lifecycle Retrospective → Reflexion → hot.md.

### Five lenses (+ open-ended)

For each lens, ask: "Did this session produce a signal here? If yes, what's the smallest concrete improvement?" Empty lenses → skip silently. Don't fabricate findings.

| Lens | Prompt | Typical `category` for `/conclave:feedback` |
|------|--------|----------------------------------------|
| **broke** | What failed outright? (script exit ≠ 0, missing file, contract violation, wrong output that the agent had to work around) | `script-defect`, severity `high\|medium` |
| **unexpected** | What returned different from what the SKILL.md / contract / briefing said it would? (output shape drift, naming mismatch, docs out of sync with reality) | `doc-contradiction` or `naming-inconsistency`, severity `medium\|low` |
| **script-improvement** | Which `team.*` script could be cleaner, faster, or smarter? (manual retry that should auto-retry, brittle parse, missing `--dry-run`, opaque error message) | `skill-gap` or `process-friction`, severity `low` |
| **automation** | What work did *I* (the LLM) do by hand this session that a script could do deterministically? (file pattern, JSON shape transform, repeated gh query, briefing reconciliation) | `idea`, severity `low` |
| **context-reduction** | Where did context get wasted? (re-read of a file already loaded, large file pulled for one fact, missing skill that would have shortened the chain, contract @import that wasn't actually needed for this session) | `process-friction` or `skill-gap`, severity `low` |
| **other** | Anything else the agent found useful — friction, ergonomics, naming, ordering, missing checks. Single line, the agent picks the closest mapping. | agent's call |

### How (per finding)

Collect each finding as a `/conclave:feedback` item in the **Feedback emission** phase (at the start of `/conclave:done`). Use `observation` to record what happened (with lens prefix, e.g. `automation: gh issue list re-run 3× — cache for session duration`), `evidence` to cite the tool-call or file ref, and the lens-to-category mapping above to set `category`. The lens prefix in `observation` makes triage faster than re-deriving intent from free text.

Cap: **MAX_RETRO_FINDINGS_PER_SESSION=5**. If the agent has more than 5, pick the highest-leverage 5 and note the count in the reflexion sentence. The retro is signal, not exhaustive coverage.

### Inline render

One row inside the ▍-block when ≥ 1 finding was filed:

```
▍ ⚠ **retro**    {N} findings — {lens-counts e.g. "broke:1 · automation:2 · context-reduction:1"} · in /conclave:feedback items
```

If zero findings → omit the row entirely (clean is silent). If any finding has `severity=high|blocker` → use `✗` instead of `⚠`.

### Anti-patterns

| Pattern | Why bad |
|---------|---------|
| Fabricating findings to fill all 5 lenses | Filler degrades the journal — same failure mode as filler reflexions |
| Repeating the same finding 5 times in different lenses | One finding, one entry — pick best lens |
| Skipping the phase because "session went smoothly" | Hansei: smooth ≠ unimprovable; at least one of the 5 lenses usually has signal |
| Writing findings as a chat-rant instead of `/conclave:feedback` items | Defeats triage — items must be in `ops/feedback/` for `feedback_index.py` to surface them |
| Severity inflation (`high` for suggestions) | Reaction policy keys on severity; mis-tagging triggers user surfacing for non-blockers |

---

## Phase: Reflexion

Per-session verbal post-mortem. Written by the advisor at close-session time; persisted to
`session.md` frontmatter; read by `/conclave:start` Step 1c for the next 3 sessions of this advisor.

Inspired by the Reflexion paper (Shinn et al., NeurIPS 2023) — episodic verbal feedback that
improves next-session performance without retraining (+11% accuracy on HumanEval).

### When

After the Lifecycle Retrospective phase, before `close-session.sh` is invoked.

### What

One sentence (≤ 280 chars). Format: *"what surprised me / what I'd do differently"*.

Good reflexions are:
- **Specific** — names a file, function, decision, or pattern (not "the work went well")
- **Actionable** — implies a behavior change for next session ("add error-channel before next || fallback")
- **Honest** — failures and false starts welcome; we want signal, not vanity
- **Retro-aware** — if the Lifecycle Retrospective phase (above) filed any findings, the single highest-leverage one is a strong default candidate for the sentence; quote the lens tag (e.g., `automation: gh issue re-run ×3 — script it`)

If genuinely nothing notable: pass `--reflexion "—"`. Forbidden anti-pattern: filler reflexions
like *"good session"* — those degrade the buffer faster than blanks.

### Where

`--reflexion "..."` arg → `close-session.sh` → `session.md` frontmatter field `reflexion:`.
Read back via `/conclave:start` Step 1c (last 3 sessions for this advisor; concatenated into briefing context).

### Inline render

One row inside the ▍-block (no sidecar lane):

```
▍ **reflexion**  "{reflexion_text}"
```

No severity glyph (qualitative, not pass/fail). If reflexion = `"—"` → omit the row entirely.
Filler reflexions ("good session") are forbidden — they degrade the buffer faster than blanks.

---

## Phase: hot.md reconciliation

If session involved Quorum (or current advisor is Quorum):

1. `grep -c "\[!contradiction\]" .ai/agent-memory/hot.md` — count contradiction markers
2. If count > 0:
   - Display each marker block to founder
   - AskUserQuestion: "Resolve <marker> as: keep A / keep B / merge / archive both"
   - Apply resolution by editing hot.md directly (sed)
3. If count == 0: skip silently

Reconciliation only by Quorum (not by every closing advisor) to avoid race conditions in concurrent sessions.
