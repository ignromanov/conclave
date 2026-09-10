---
description: >-
  Closes an advisor session so nothing is silently lost — commits the work, syncs GitHub
  issues, files decisions and mentions, records what was learned, and writes a resume-prompt
  if anything is unfinished. Use as the last step of every advisor session.
---

!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/agent-data-policy.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/github-issues-protocol.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/session-lifecycle.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/advisor-anti-patterns.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/feedback-protocol.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/output-formatting.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/output-discipline.md`

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
      --handoff-title <title> --handoff-slug <slug> \
      (--handoff-issue <#N|AI#N|owner/repo#N|URL> | --handoff-no-issue "<why>")] \
     [--issues-touched AI#N,AI#N] \
     [--reflexion "<one-sentence post-mortem; '—' if nothing notable>"]
   ```

   The `--reflexion` arg is **mandatory**. If genuinely nothing to reflect on, pass `"—"`.
   It is persisted to `session.md` frontmatter and read by `/conclave:start` for the next 3 sessions
   of this advisor. See `${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/output-formatting.md` for the sidecar lane spec.

   The `--handoff-file` arg files a **new** handoff inline — it requires all four
   companions (`--handoff-to`, `--handoff-priority`, `--handoff-title`, `--handoff-slug`)
   plus exactly one of `--handoff-issue` / `--handoff-no-issue`; omitting any one aborts
   the call *before* the session document is written, so a refused handoff never leaves a
   closed session behind. A handoff has no terminal state, and the resume-scan ranks by
   mtime — a resolvable reference is what lets a later reader answer "did this ship?"
   without opening the file (#55). Free text and bare numbers are refused. If the handoff was already created separately via
   `python -m engine file handoff`, omit `--handoff-file` entirely and reference the handoff path in
   the session body prose.

5. One aggregate commit:
   ```bash
   cd "$CONCLAVE_AI_ROOT"   # the DATA root
   git add agent-memory/advisors ops/handoffs
   git commit -m "session: <advisor> <slug> (decisions:N, mentions:M, handoff:Y/N)"
   ```

6. GH issues sync: for every `AI#N` in `--issues-touched`, run `gh issue comment <N> --body "..."` as usual (not script-wrapped).

## Checklist

### Mandatory (always)

1. ☐ **All changes committed AND the PR state re-read from the remote** (both repos if applicable)
   - Run: `git status` in both `/` and `.conclave/`
   - If uncommitted changes → commit or explain why not
   - `git status` is a **local** view. It cannot tell you that the PR you believe you are still
     working on was squash-merged twenty minutes ago and its branch deleted — a session has
     closed while holding exactly that belief. Before composing the Summary, ask the remote:
     ```bash
     git fetch --quiet --prune origin
     # every branch this session pushed
     for BRANCH in <branches-pushed-this-session>; do
       gh pr list --head "$BRANCH" --state all --limit 100 --json number --jq '.[].number'
     done | sort -u | while read -r N; do
       gh pr view "$N" --json number,state,mergedAt,headRefName \
         --jq '"#\(.number) \(.state) merged=\(.mergedAt // "—") head=\(.headRefName)"'
     done
     ```
   - Report each PR as **merged / open / closed-unmerged** in the Summary, with its `mergedAt`.
     A PR that merged during the session is a *result*, not a footnote — it is the arrival
     evidence the whole checklist exists to produce.
   - If a PR merged: the branch is likely gone from the remote and the local worktree is now
     detached from anything live. Say so rather than leaving the next session to discover it.
   - If a PR is still open, name what it is waiting on (review, CI, conflict). "Opened a PR" is
     not an outcome; the state it is sitting in is.
   - Gate: **Auto** (fetch + read) / **Notify** (anything merged or closed since the session began)

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
   - Decisions → `python -m engine file decision`
   - Mentions → `python -m engine mention create`
   - Session record + handoff → `python -m engine session close`
   - Single aggregate commit under `agent-memory/advisors` + `ops/handoffs`
   - (Briefing regenerates on next `/conclave:start`; no manual action here.)
   - Gate: **Auto**

### Conditional

4. ☐ **IF session produced new knowledge** → wiki updated
   - Preferred: invoke `/wiki:capture --clipboard "Title"` with session summary
   - For web sources discovered: `/wiki:capture <url>`
   - Architecture registries (instance DATA root, e.g. `.conclave/architecture/`) — update directly
   - Gate: **Auto** — always capture if knowledge was produced

5. ☐ **IF new slice/component** → the instance's own architecture registries updated (same DATA
   root as item 4 — an instance may keep any registries it likes, or none; the engine cannot name
   them)

6. ☐ **IF spec deviation** → spec.md updated
   - Compare implementation vs spec
   - Gate: **Approve** — AskUserQuestion before modifying spec

7. ☐ **IF work incomplete** → invoke `/conclave:handoff`
   - Creates structured resume-prompt for next session

8. ☐ **IF skill gap found** → log for creation
   - What was needed but didn't exist
   - Gate: **Notify** — recommend invoking `writing-skills`

9. ☐ **IF this session resumed a handoff** → archive it
   - A handoff is a resume-prompt. `/conclave:start` surfaces every one addressed to the
     advisor, so one that is never retired resurfaces at every session forever — the
     counterpart to item 7, which only ever *creates* them. Archive it in the session that
     exhausted it, not the session that wrote it: after #202 the scan delivers to the
     RECIPIENT, so an unarchived handoff nags whoever it was sent to, not its author.
   ```bash
   python -m engine lifecycle archive-handoff <filename>.md --dry-run   # confirm first
   python -m engine lifecycle archive-handoff <filename>.md
   ```
   - Moves it to `ops/handoffs/archive/` — a move, never a delete, and it refuses to
     overwrite an existing archived copy.
   - Archive only what this session actually exhausted. Work that is still open stays
     live: an unfinished handoff that vanishes is worse than a stale one that nags.
   - Gate: **Notify** — show the user what was archived

10. ☐ **IF the agent holds duties** → discharge check (spec 091 §4)

   Record what became of each duty that activated this session, then report what is still
   owed. `condition` is prose **you** evaluate in context — the check cannot decide it for
   you, which is exactly why an unanswered conditional is surfaced instead of assumed in
   either direction.

   **Writing a duty does not create a debt.** A self-written duty is *advice*: it appears in
   `COMPUTED-DUTIES.md` tagged `[advice]` and nothing is owed for it. Only a norm in the
   operator-owned `.conclave/roster/norms.yaml` elevates one to `[obligation]`, and only
   obligations are checked here. That split is deliberate — an agent that could declare its
   own duties binding could equally soften them, and the check exists to catch exactly that
   agent (spec 091 P2 §0).

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

- Exit 0 → every step ran and was clean; omit study row from Summary
- Exit 2 → non-blocking findings (captures / P1 stale / link violations), **or** a step that
  never ran (`steps-not-run:{N}` — absent script or exit=1); emit `⚠ study` row either way.
  A step that could not run has measured nothing, so omitting the row would assert a health
  nobody checked (#56A). Since the wiki extraction the scripts live in the `/wiki:*` plugin
  and `engine/scripts/wiki/` is absent, so this is the expected state until that is resolved.
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
- Running Study INSIDE `engine session close` → must run BEFORE close-session for failures to be visible in the session record

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

- Clean session (all exit 0 or 2) → `🟢 6 scripts · 3204ms · 0 errors`; **row is OMITTED from Summary**
- One failure → `🟡 6 scripts · 3204ms · 1 errors · engine memory memory-index exit=1`
- P0 failure → `🔴 …` and the row is prefixed with `✗` instead of `⚠`

`exit=2` is a successful refresh (ADR-0003 loop-discipline §2), so an exit-2 script is never
the one named — the name always points at something that actually needs looking at.

### Severity → render

- All scripts exit 0 **or 2** (2 = refresh = success) → **omit the row entirely**
- Any non-zero exit, none P0 → emit row with `⚠`
- Any P0 script failed (`engine briefing build`, `engine session close`, `engine file decision`) → emit row with `✗`

### Inline render

```
▍ ⚠ **infra**    {script_count} scripts · {total_ms}ms · {errors} errors · {first_failing_script} exit={code}
```

`{first_failing_script} exit={code}` is appended only when something failed — on a clean session
there is nothing to name, and that row is omitted anyway. Without it the operator learned that
*something* broke and never what, which is what the row exists to tell them (GH#186).

`total_ms` is retained: on the only row a human ever sees, one that already reports a failure, the
duration distinguishes a timeout from a fast refusal. Whether to drop it is a display-contract
question owned by kosmos-cxo, not something the summariser should decide by omission.

---

## Phase: Lifecycle Retrospective

Structured self-review of the **lifecycle infrastructure itself** through this session's episodes. Distinct from Reflexion (one-sentence advisor post-mortem about the work) and from the passive feedback rule (report-on-encounter). Six prompts, answered in order; each answer is an episode or an artefact, and each finding goes to the `/conclave:feedback` channel (spec 086).

**Answer from the transcript, not from memory of it.** Every prompt below names a thing that exists in this session's record: a spec number, a command, its output, a line in a file, a step you did not have to take. The answer is that thing, quoted. Where the prompt asks for a quote and you have none, the answer is `nothing` — and `nothing` is a complete answer to every prompt here, including all six.

> **Why the prompts have this shape** (spec 117, commissioned by helm-ceo, evidence in
> `ops/specs/117-session-ledger/research/W3-agent-self-report-literature.md`): an agent's report of
> *what it did* is recoverable from its context; its report of *why* it did so is not. Reasons,
> ratings, confidence and counterfactuals come back fluent and uncorrelated with what happened —
> measured at 1–20 % verbalisation of the cue that actually drove the answer. So the prompts ask for
> episodes, and the diagnosis is left to the reader of the corpus, which is where it belonged.

### When

**Execution order**: Study → Infra → **Lifecycle Retrospective** → Reflexion → hot.md → `engine session close`. Runs every session — non-blocking.

Rationale for slot: Infra's exit-codes are the outputs the **stuck** prompt quotes; Reflexion (the one-sentence post-mortem persisted to session frontmatter) can then quote the highest-leverage Retrospective finding. Documentation order matches execution order — Study → Infra → Lifecycle Retrospective → Reflexion → hot.md.

### The six prompts

Answer in order. The middle column states what a complete answer is made of — supply those parts, or answer `nothing`.

| Prompt | What the answer consists of | Files as |
|--------|-----------------------------|----------|
| **job** | The spec or issue this session worked on, by number, each number followed by the gloss it needs to be read without opening it. Opens the phase and files nothing — it fixes which session is being described. | — |
| **stuck** | One moment: the command you ran, and the output that came back. Both quoted, verbatim, from the transcript. One moment, not a survey of the session. | `script-defect` · `process-friction` · `data-access` |
| **instead** | The thing you executed next, quoted. If you ran it more than once, the number of times — a workaround executed three times is the automation candidate, and the count is in the transcript. | `process-friction` · `skill-gap` |
| **acted-on** | A line you acted on, quoted, plus the path of the artefact that carried it. If acting on it produced something other than what the line said, both the line and what came back. | `doc-contradiction` · `naming-inconsistency` · `skill-inaccuracy` |
| **removed-step** | One artefact, and the step it removed: *"X removed Y"*, where Y is a step you can name and would otherwise have taken. Both halves, or the answer is `nothing`. | `positive` |
| **unexecuted** | One claim you made this session with no command run behind it, quoted, and the command that would decide it. If you ran that command before the session ended, the answer is both halves plus what came back — that is the same finding carried to its end, not a different one. | `idea` · `near-miss` |

`removed-step` is the only prompt that files a positive, and the named-step form is the whole of it: an artefact with no step beside it is not a finding here. Expect `nothing` often — that outcome is a measurement, not a failure of the prompt.

`unexecuted` files `idea` when the claim is still undecided and `near-miss` when you ran
the deciding command yourself: an error that did not ship, and the thing that caught it.
Both are the same prompt — filing the second as `idea` invites exploring what is already
settled, and filing it as `positive` says an artefact removed a step when what happened
is that you re-read your own claim. Measured 2026-09-10: 3 of the 6 items in the corpus
under `positive` were this, filed there because it was the only non-defect category (#250).

### Admission rules

| Rule | Form |
|------|------|
| Evidence | Every item carries `evidence`. Absent ⇒ rejected at ingest, unchanged by this phase. |
| Hypothesis | Evidence that is a quote or a re-runnable command makes a finding. Evidence that is neither ⇒ `observation` opens with `hypothesis:`, and the item is admitted at that standing. |
| Harness | An item about the tool layer rather than the engine — the CLI, tool-call behaviour, working-directory persistence between calls — opens `observation` with `harness:`. It is filed under that prefix, not dropped: roughly a third of the corpus is harness friction the engine cannot fix, and routing it keeps the denominator honest while filtering it silently inflates every engine-defect rate. |
| Fix | `suggested_fix` when you have one from what you executed. It is optional; leave it out rather than compose one. |
| Contradictions | Differences between this report and the tool log are found by a later pass over both. This phase does not ask for them. |

### How (per finding)

Collect each finding as a `/conclave:feedback` item in the **Feedback emission** phase (at the start of `/conclave:done`). `observation` opens with the prompt id and then states what happened — `stuck: gh issue list returned 30 rows for an advisor with 75 open` — carrying any `hypothesis:` or `harness:` prefix ahead of it. `evidence` holds the quote, the command, or the tool-call ref. `category` comes from the prompt's row above; where a row names several, the one the finding actually is.

The prompt id in `observation` is what makes a triage cluster readable without re-deriving intent from free text — and it is what lets a later pass count answers per prompt, which is how `removed-step`'s yield gets measured rather than assumed.

Cap: **MAX_RETRO_FINDINGS_PER_SESSION=5**. If the agent has more than 5, pick the highest-leverage 5 and note the count in the reflexion sentence. The retro is signal, not exhaustive coverage.

### Inline render

One row inside the ▍-block when ≥ 1 finding was filed:

```
▍ ⚠ **retro**    {N} findings — {prompt-counts e.g. "stuck:1 · instead:2 · removed-step:1"} · in /conclave:feedback items
```

If zero findings → omit the row entirely (clean is silent). If any finding has `severity=high|blocker` → use `✗` instead of `⚠`.

### Anti-patterns

| Pattern | Why bad |
|---------|---------|
| Composing an answer because a prompt is unanswered | `nothing` is the answer when there is no episode. A composed one is indistinguishable from a real one at triage, and it is the failure mode that produced a 244-item corpus nobody could use as research |
| Answering `stuck` with a survey of the session | One moment, one command, one output. A summary of several has no quote to check it against |
| Skipping the phase because "session went smoothly" | The prompts do not ask what broke. `job`, `acted-on` and `removed-step` are all answerable in a session where nothing failed |
| Writing findings as a chat-rant instead of `/conclave:feedback` items | Defeats triage — items must be in `ops/feedback/` for `feedback_index.py` to surface them |
| Severity inflation (`high` for suggestions) | Reaction policy keys on severity; mis-tagging triggers user surfacing for non-blockers |

---

## Phase: Reflexion

Per-session verbal post-mortem. Written by the advisor at close-session time; persisted to
`session.md` frontmatter; read by `/conclave:start` Step 1c for the next 3 sessions of this advisor.

Inspired by the Reflexion paper (Shinn et al., NeurIPS 2023) — episodic verbal feedback that
improves next-session performance without retraining (+11% accuracy on HumanEval).

### When

After the Lifecycle Retrospective phase, before `engine session close` is invoked.

### What

One sentence (≤ 280 chars). Format: *"what surprised me / what I'd do differently"*.

Good reflexions are:
- **Specific** — names a file, function, decision, or pattern (not "the work went well")
- **Actionable** — implies a behavior change for next session ("add error-channel before next || fallback")
- **Honest** — failures and false starts welcome; we want signal, not vanity
- **Retro-aware** — if the Lifecycle Retrospective phase (above) filed any findings, the single highest-leverage one is a strong default candidate for the sentence; quote the prompt id (e.g., `instead: gh issue re-run ×3`)

If genuinely nothing notable: pass `--reflexion "—"`. Forbidden anti-pattern: filler reflexions
like *"good session"* — those degrade the buffer faster than blanks.

### Where

`--reflexion "..."` arg → `engine session close` → `session.md` frontmatter field `reflexion:`.
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

1. `grep -c "\[!contradiction\]" .conclave/agent-memory/hot.md` — count contradiction markers
2. If count > 0:
   - Display each marker block to founder
   - AskUserQuestion: "Resolve <marker> as: keep A / keep B / merge / archive both"
   - Apply resolution by editing hot.md directly (sed)
3. If count == 0: skip silently

Reconciliation only by Quorum (not by every closing advisor) to avoid race conditions in concurrent sessions.
