---
description: >-
  Opens an advisor session with its context already loaded — the advisor's briefing, live
  cross-agent state, open GitHub issues, and any interrupted work offered for resume — then
  sizes the task and routes it to the right skill chain. Use at the start of every advisor
  session, before doing any work.
---

!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/agent-data-policy.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/github-issues-protocol.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/session-lifecycle.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/first-launch-protocol.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/decision-framework.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/quality-loop.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/advisor-anti-patterns.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/feedback-protocol.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/output-formatting.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/output-discipline.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/state-report.md`
!`cat ${CLAUDE_PLUGIN_ROOT}/skills/advisor-contracts/references/question-shape.md`

# /conclave:start — Session Initialization

> **MANDATORY** for every advisor session. Works independently — no Quorum required.
>
> **Cardinal Rule**: GitHub Issues = source of truth for tasks. The auto-generated briefing is a dashboard cache that references issues (AI#N, GH#N). When they conflict, GH wins.

## Question shape

Every user choice in this skill follows the **prose-context + condensed-Ask** pattern —
see `question-shape.md` (auto-imported). Applies here to: resume-vs-fresh (Step 1b),
tier override + skill-chain pick (Step 7), briefing-conflict resolution (Step 3c).

## Process

### 0. Self-heal SessionStart hook

!`python3 "${CLAUDE_PLUGIN_ROOT}/engine/scripts/init/reconcile_hook.py" 2>&1 || true`

Best-effort repair of the SessionStart hook's command path + `CONCLAVE_ENGINE_ROOT` in
`.claude/settings.json`, in case they still point at a plugin cache dir removed by a prior
`/plugin update` (099 followups B1). Runs before session-init below, which needs a valid
engine root.

### 0b. Provision engine deps

!`python3 "${CLAUDE_PLUGIN_ROOT}/engine/scripts/init/provision_deps.py" 2>&1 || true`

Best-effort install of the engine's third-party deps (PyYAML/pydantic/python-frontmatter/
ruamel.yaml) into `${CLAUDE_PLUGIN_DATA}/venv`, so `python -m engine <cmd>` (used throughout
this skill and others) has its deps available on a fresh consumer or right after a
`/plugin update` wiped the in-tree `.venv` (099 followups B4). Idempotent; never blocks
session start.

### 1. Load briefing

1. Detect the advisor from the `/conclave-<id>` router invocation (the router binds
   `advisor=<id>` and passes it to session-init). For `forge-chro`, this is `/conclave-forge-chro`.
2. Run session-init (Steps 1/1b/1c + Overlay in one call):
   ```bash
   python3 engine/scripts/lifecycle/session_init.py --advisor <advisor>
   ```
   Exit codes: 0 = cache-hit / briefing content unchanged, 2 = briefing regenerated, 1 = error
   (the briefing could not be built). A failed gh-fetch is non-fatal (#76): the run
   continues and prints a `degraded: gh-data-unavailable` line — board-derived
   sections come from the stale cache, the rest of the briefing is current.
   The script handles: gh-fetch (TTL=900s), briefing build-and-compare (always rebuilds; writes
   only if content differs), resume-scan (ops/specs/*/resume-prompt.md + ops/handoffs/*-<advisor>-*.md),
   reflexion extract (last-3 sessions), overlay scan, and feedback cadence check.
   If a line starting with `  feedback:` appears in the output, triage is due — include it in
   the session-start summary and suggest running `/conclave:triage` this session.
   A `WARNING: CONCLAVE_ENGINE_ROOT points at …` line on stderr means the environment named a
   different checkout than the one the script lives in; it runs its own copy's helpers and
   tells you so (GH#187). Treat it as a signal that the hook and the tree have drifted apart.
3. Read `.conclave/agent-memory/advisors/briefings/<advisor>.md` into context.
4. Load `hot.md` **once** separately (AC8 — no longer embedded in briefings):
   ```bash
   cat .conclave/agent-memory/hot.md
   ```
   Read the Now / Recent decisions / Watch sections for live cross-agent state.
5. The briefing and hot.md are auto-generated; do not edit either directly.

### 1b. Resume Check

The session-init script (Step 1) prints resume findings prefixed `resume:`. Read its output:

- Lines starting `  spec-resume:` — interrupted spec worktree; path + age in hours shown.
- Lines starting `  handoff:` — filed handoff for this advisor; filename + age shown.

If found → apply **Question shape** (above):

1. **Prose first** — describe each found item: title, path, last-update mtime, what was in progress (one-line from resume-prompt header), and what "resume" vs "start new" means (resume = load original skill chain + reuse session id; start new = current request takes over, old resume-prompt stays unconsumed on disk for later).
2. **`AskUserQuestion`** — `label`s: "Resume" / "Start new" / "Skip" (≤ 5 words each); `description`s ≤ 1 sentence each.

If user picks Resume → read resume-prompt, load required skills from it, skip to Step 5.
If Start new → leave the file in place; mention in `/conclave:done` Lifecycle Retrospective if it's been stale > 3 days.

### 1c. Reflexion Context

The session-init script (Step 1) prints reflexion findings prefixed `reflexion:`. Read its output:

- Lines starting `  - [<session-file>]` — non-empty reflexion value from that session.
- If `reflexion: none` → skip silently (no signal, no noise).

If any reflexions were surfaced, apply them as priors for this session:

> "Recent reflexions for ${ADVISOR}:
> - {reflexion-1}
> - {reflexion-2}
> Apply these as priors for this session."

### 2. Tier Detection

> **Forge (meta-advisor) carve-out:** if the advisor is `forge`, skip domain
> tier-detection and the GitHub issue-board step — forge has no domain board and
> follows the `forge-operations` flow, not domain tiers. Run only the lifecycle
> steps session-init performs for meta-advisors (briefing / resume / reflexion /
> overlays); see the spec §3.3 step matrix.

Classify user request by scale:

| Signal | Tier | Ceremony |
|--------|------|----------|
| Quick question, opinion, <30 min | **Quick** | Minimal GH check (Step 3a), skip steps 4-5 |
| Feature work, 1-4 hours, clear scope | **Feature** | Full init (Steps 3b-6) |
| Multi-session, worktree, epic scope | **Epic** | Full init + checkpoint plan |

### 3. GH Issue Check (MANDATORY — all tiers)

> **GH Issues = source of truth.** Always check before working.
> The instance's repos feed into its configured **roadmap project board** (owner/repos/board from `roster.yaml`).

#### 3a. Quick Tier (minimal)

```bash
# Repo scope comes from the resolver, never from raw roster keys: an instance with a single repo
# has ai_repo null, and `-R "$OWNER/$(roster.py github.ai_repo)"` builds the malformed slug
# `owner/`. `gh-repos` applies the same roster → git-remote → refuse layering gh-fetch uses, and
# exits 1 rather than printing an empty list.
ROOT="${CONCLAVE_ENGINE_ROOT:-${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/engine}}"
: "${ROOT:?no engine root — export CONCLAVE_ENGINE_ROOT (the engine/ dir) or CLAUDE_PLUGIN_ROOT}"
ADVISOR="<advisor>"   # the slug this session is bound to
for REPO in $(PYTHONPATH="$ROOT/scripts" python3 -m engine lifecycle gh-repos); do
  gh issue list -R "$REPO" --label "advisor:$ADVISOR" --state open \
    --json number,title --jq 'length' &
done
wait
```

Show: "You have N open issues (AI: X, Code: Y). P0 blockers: [list or none]."
If user's question relates to an open issue — mention it. Then answer directly.

#### 3b. Feature/Epic Tier (full)

```bash
# Same resolver as 3a — one repo or two, the loop adapts; an unscoped instance exits 1 here
# instead of silently iterating nothing.
ROOT="${CONCLAVE_ENGINE_ROOT:-${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/engine}}"
: "${ROOT:?no engine root — export CONCLAVE_ENGINE_ROOT (the engine/ dir) or CLAUDE_PLUGIN_ROOT}"
ADVISOR="<advisor>"
for REPO in $(PYTHONPATH="$ROOT/scripts" python3 -m engine lifecycle gh-repos); do
  gh issue list -R "$REPO" --label "advisor:$ADVISOR" --state open &
  # P0 blockers, including ones assigned to other advisors
  gh issue list -R "$REPO" --label p0 --state open &
  # Possibly mis-routed: open p1 carrying SOMEONE ELSE'S advisor label. The p0 line above
  # already reads cross-advisor; p1 did not, and that is the whole blind spot.
  gh issue list -R "$REPO" --label p1 --state open --limit 200 \
    --json number,title,labels,updatedAt \
    --jq "[.[] | select([.labels[].name] | index(\"advisor:$ADVISOR\") | not)]
          | sort_by(.updatedAt) | reverse
          | \"possibly mis-routed p1: \\(length) open\",
            (.[:5][] | \"  #\\(.number) \\(.title[:72])\")" &
done
wait
```

Present open items in a compact table with source repo prefix (AI#N / GH#N).
**Match user's request to an existing issue.** If matched → reference it throughout the session.

**Mis-routing is invisible by construction.** The first query asks only for issues already
labelled `advisor:$ADVISOR`, so an issue in this advisor's domain that was filed under someone
else's label appears in no queue at all — it is not late, it is unseen, and nothing in the
lifecycle ever surfaces it. The third query above is the join the first two never make.

Render it as **a count plus the five most recently updated**, never the full list. The count is
what makes the blind spot visible; the full table would be tens of rows of other advisors' work
every session, and a wall nobody reads restores the invisibility it was meant to cure. Scan the
five titles: if one is plainly this advisor's domain, say so and propose a relabel — do not
silently adopt it, and do not relabel another advisor's queue without saying which issue and why.
Widen the query (drop `--limit`, add `--label p2`) only when chasing a specific suspicion.

**Alternative** — single Project Board query (shows both repos + all custom fields):
```bash
gh project item-list "$(python3 engine/scripts/lib/roster.py github.board_number)" --owner "$(python3 engine/scripts/lib/roster.py github.owner)" --format json --limit 100 | \
  python3 engine/scripts/lifecycle/gh_board_query.py \
    --mode advisor-open --advisor <advisor>
```

#### 3c. BRIEFING ↔ GH Reconciliation (Feature/Epic)

Compare briefing Action Items (from the regenerated `.conclave/agent-memory/advisors/briefings/<advisor>.md`) with `gh issue list` results from **both repos**:

| Mismatch | Action |
|----------|--------|
| Briefing has AI#N / GH#N but issue is closed | Flag: "AI#N closed in GH but still in briefing — will clean up in /conclave:done" |
| GH has open issue for this advisor not in briefing | Flag: "AI#N / GH#N exists in GH but missing from briefing" |
| Briefing status differs from Project Board status | Flag drift, use GH as truth |

Present mismatches (if any) before proceeding. Don't fix now — `/conclave:done` handles cleanup.

### 4. Startup Audit (Feature/Epic only)

Two lists are not an audit. Printing the worktrees and printing the PRs leaves the join — *is
this branch's work already upstream?* — to a human who is not reading. Do the join here.

```bash
DEFAULT_BRANCH="$(git symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null | sed 's#^origin/##')"
DEFAULT_BRANCH="${DEFAULT_BRANCH:-master}"
git fetch --quiet --prune origin 2>/dev/null || true

# Compare against the REMOTE-tracking ref, not the local branch. `git fetch` advances
# origin/<default>; it does not advance the local <default>, and in a worktree the local one is
# often days behind. Comparing against it reports every branch merged since as unshipped — which
# is precisely the branches most likely to be removable.
BASE="origin/$DEFAULT_BRANCH"
git rev-parse --verify --quiet "$BASE" >/dev/null || BASE="$DEFAULT_BRANCH"

# The DATA root is a sibling of the CODE checkout, not of the cwd — from inside a
# worktree `cd .conclave` finds nothing and the DATA repo goes unchecked in silence.
DATA_ROOT="${CONCLAVE_AI_ROOT:-$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null | sed 's#/\.git$##')/.conclave}"
if [ -d "$DATA_ROOT/.git" ]; then
  (cd "$DATA_ROOT" && git status --short)
else
  echo "DATA root not found at $DATA_ROOT — set CONCLAVE_AI_ROOT"
fi

# ONE network call for every PR, then join locally. A `gh pr list` per branch is N round-trips
# at every session start, and the audit that is slow is the audit that gets skipped.
gh pr list --state all --limit 300 --json number,state,headRefName \
  --jq '.[] | "\(.headRefName)\t#\(.number):\(.state)"' | sort -u > /tmp/pr-by-branch.tsv

# Which branches have a worktree checked out
git worktree list --porcelain | awk '/^branch /{sub("refs/heads/","",$2); print $2}' | sort > /tmp/wt-branches.txt

git for-each-ref --format='%(refname:short)' refs/heads | while read -r BRANCH; do
  [ "$BRANCH" = "$DEFAULT_BRANCH" ] && continue
  LEFT=$(git cherry "$BASE" "$BRANCH" 2>/dev/null | grep -c '^+')
  PR=$(awk -F'\t' -v b="$BRANCH" '$1==b{printf "%s%s", sep, $2; sep=","}' /tmp/pr-by-branch.tsv)
  WT=$(grep -qxF "$BRANCH" /tmp/wt-branches.txt && echo worktree || echo bare)
  AGE=$(git log -1 --format=%cr "$BRANCH" 2>/dev/null)
  printf '%-46s %-9s unshipped=%-4s pr=%-22s %s\n' "$BRANCH" "$WT" "$LEFT" "${PR:-none}" "$AGE"
done
```

Read the columns **together** — each signal is wrong on its own, in a different direction:

| `unshipped` (`git cherry`) | PR state | Verdict |
|---|---|---|
| `0` | merged | **Fully shipped.** Every patch is upstream by patch-id and the PR landed. `git worktree remove` (if any), then `git branch -D` — `-d` **refuses** on a squash-merged branch however conclusive the evidence, so the capital `-D` is not recklessness here, it is the join above being what makes it safe. |
| `>0` | merged | **Look before removing.** Either commits landed *after* the merge (real work — keep), or `git cherry` cannot see the squash: its patch-id matches none of the branch's own commits when the PR squashed more than one, and it can miss even a single-commit squash once the base has moved under it. Read the log; do not guess. |
| `>0` | open | Live work in flight. Leave it. |
| `0` | none | The branch holds no patch of its own. Use the age column: minutes old = a worktree just created and not yet written in (**keep**); days old = work that landed by some other route (**stale**). |
| `>0` | none | Unshipped and unproposed — the branch nobody is waiting on. Flag it with its age. |

The `worktree` / `bare` column is the second join, and it is the one that answers *how* to clean up:
a `bare` row needs only the branch delete, a `worktree` row needs `git worktree remove` first or the
delete refuses for a second, unrelated reason. A `bare` row whose PR merged weeks ago is the ordinary
residue of squash-merge, and `git branch -d` refuses on it forever — which is why such rows
accumulate silently and why this table exists to license the `-D`. (`git branch -d --dry-run` is not
an option that exists; the refusal itself is the only preview.)

Why three signals and not the obvious one: `git log $BASE..$BRANCH` counts commits, and for
a squash-merged branch it counts commits that are already upstream — which is why `git branch -d`
refuses on branches whose work has demonstrably shipped. `git cherry` fixes that by comparing
patch-ids, but a squash of *N > 1* commits produces a patch-id matching none of its parts, so
`cherry` reports the whole branch unshipped. Even a *single*-commit squash can slip past it: the
patch-ids stay equal, but only if the comparison base is the ref that actually received the merge —
which is why `BASE` above is `origin/<default>` and not the local branch of the same name.
Neither signal reads correctly alone; the PR state is what disambiguates, and the PR state alone
would call a branch removable while it carries commits pushed after its merge.

Show the joined result as a compact table. Skip it only when every row is live work in flight —
never because the list is long. A long list *is* the finding.

### 4.5. Wiki Domain Context (Feature/Epic only)

Load domain context from the wiki for richer advisory. Which areas to load is **derived, not
tabulated** — the roster is instance data and so are the vault's areas:

1. Take the bound advisor's domain from its responsibilities (its agent-def frontmatter, or
   `roster.yaml`) — the same `<advisor>` Step 1 bound this session to.
2. List the vault's areas — the top-level folders under the wiki path:
   ```bash
   ls "$(python3 engine/scripts/lib/roster.py knowledge.wiki_path)"
   ```
3. `/wiki:browse <area>` the one or two whose names match that domain. Two is the ceiling —
   this is context loading, not research.

Skip the step (and say so) when no area matches the advisor's domain, or when the context it
would load is already in the session via `@import`.

Optional: `/wiki:query "topic"` for task-specific context.

### 5. Skill Routing

Detect task type → load required skill chain. Every external target carries its plugin prefix, so a
missing one is visible as a missing plugin rather than as silence — except the two rows marked †
below and the `find-skills` fallback itself, which are unprefixed by design: user-level skills in
the operator's private `~/.claude/skills`, shipped by no plugin. On a fresh install those three
will not resolve, and that silence is not caught by anything — know it going in.

> **Provenance, not dependency.** The `superpowers:*` and `marketing-skills:*` rows are third-party
> prior art carried until spec 108 P2 authors Conclave-owned procedures for the stages that earn
> one. They are cited here, never `Skill()`-ed from engine code.

| Task Type | Skill Chain |
|-----------|-------------|
| New feature | superpowers:brainstorming → superpowers:writing-plans |
| Bug fix | superpowers:systematic-debugging |
| Content | marketing-skills:product-marketing-context → marketing-skills:copywriting → marketing-skills:copy-editing |
| Grant | grant-proposal-assistant † |
| Code review | superpowers:requesting-code-review |
| Security | senior-security † |
| Meeting | the instance's facilitator slot, if one was hired — see the roster |
| Plan execution | superpowers:subagent-driven-development |

† unprefixed on purpose — user-level, not shipped by any plugin, absent on a fresh install.

If no matching skill exists:
1. Search with `find-skills` — also user-level, same caveat
2. If found installed → invoke
3. If found remote → recommend install to user
4. If not found → work best-effort, log gap in /conclave:done

### 6. Create Session Tasks (Feature/Epic only)

**MANDATORY**: Create tasks via TaskCreate for the current work session. Always include `/conclave:done` as the final task so it is never forgotten.

Example:
```
TaskCreate: "Load context and check resume state"       → in_progress
TaskCreate: "[Main work description from user request]" → pending
TaskCreate: "Run /conclave:done completion checklist"       → pending
```

The `/conclave:done` task MUST be the last task. It ensures: commits, GH issues sync, BRIEFING update, wiki capture, and handoff if incomplete.

### 7. Present & Confirm (Feature/Epic only)

Render the start-summary using the ▍-framed format (per `output-formatting.md` Per-skill instantiation table):

▍ **{persona-emoji} {advisor} · session-start · {date}**
▍
▍ **focus**       {current focus from briefing}
▍ **queue**       {N} open issues ({AI: x, GH: y}) · {P0_count} P0
▍ **briefing**    `agent-memory/advisors/briefings/{advisor}.md` ({unchanged | regenerated})
▍ ⚠ **interrupted** {title} ({path})              ← OMIT if none
▍ **tier**        {Quick | Feature | Epic}
▍ **skills**      {chain → e.g. superpowers:brainstorming → superpowers:writing-plans}
▍
▍ **next →** {first concrete action from the chain}

Then apply **Question shape** (above) to the approval gate:

1. **Prose first** — name the tier you picked (Quick / Feature / Epic) and *why* (which signal from §2 fired), the skill chain you're about to load and what each skill in it costs (rough context budget / time-on-task), and the first concrete action you'd take. State explicit alternatives if the tier-pick was borderline ("could also run as Feature if you want spec.md upfront").
2. **`AskUserQuestion`** — labels: "Proceed" / "Switch tier" / "Different skill chain" / "Abort" (≤ 5 words). Descriptions ≤ 1 sentence.

For Quick tier the render above is **mid-run**, not terminal: the Ask gate is skipped and the work
proceeds inside the same operator turn, so a block here plus the work's own report would be two
terminal objects for one run — `output-discipline.md` R1. Do not render a start-summary for Quick
tier.

Carry `focus` and `queue` into slot 2 (`required / assumed`) of the run's terminal block, and the
first concrete action into slot 5. Nothing is lost: the same three facts arrive once, attached to
the result they framed, instead of ahead of it.

If the request is ambiguous, the run does not proceed on a guess — that is R7 case 1, so ask with
`AskUserQuestion` and end the run there. The block above stays exactly as written for Feature and
Epic, where the Ask gate that follows it makes it terminal under R8.

## Overlay loading

After loading base contracts, session-init (Step 1) prints overlay findings prefixed `overlays:`.
Read its output:

- Lines starting `  overlay:` — path to an advisor-specific contract override.
- If `overlays: none` → no overrides; base contracts apply as-is.

Apply each listed overlay. Overlay semantics (`constraint` / `extension` / `replacement`) per
`${CLAUDE_PLUGIN_ROOT}/skills/forge-operations/references/aspects/contract-overlays.md`.

To run overlay scan in isolation:
```bash
python3 engine/scripts/lifecycle/session_init.py --advisor <advisor>
```

> Vault setup: see `${CLAUDE_PLUGIN_ROOT}/skills/forge-operations/references/obsidian-vault-setup.md`
