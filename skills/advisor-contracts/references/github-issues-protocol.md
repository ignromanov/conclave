---
contract: github-issues-protocol
version: 1.1.0
appliers: [team.start, team.processing, team.done, team.handoff]
propagation: hire-template
stages: [clarify, design, implement, deliver]
tiers: [quick, work]
task_types: [dev, content, research, review, advisory]
binding: required
last_reviewed: "2026-08-12"
---

# GitHub Issues Protocol

> **Purpose**: Source of truth for task management
> **Repos**: `${OWNER}/${MAIN_REPO}` (public, code) + `${OWNER}/${AI_REPO}` (private, ops)
> **Approved**: 2026-03-17, updated 2026-04-28 (v1.1 — explicit `-R` enforcement)

> **Roster placeholders**: `${OWNER}`, `${MAIN_REPO}`, `${AI_REPO}` are per-instance
> values from `roster.yaml` (`github.owner`, `github.main_repo`, `github.ai_repo`).
> Before running any `gh` command below, resolve them:
> ```bash
> OWNER=$(python3 engine/scripts/lib/roster.py github.owner); MAIN_REPO=$(python3 engine/scripts/lib/roster.py github.main_repo); AI_REPO=$(python3 engine/scripts/lib/roster.py github.ai_repo)
> ```

---

## ⚠️ MANDATORY: Always pass `-R <repo>` when creating issues

`gh issue create` without `-R` uses the current git remote — which in the main worktree points to **public** `${MAIN_REPO}`. Agents have leaked private (strategy/grant/content/agent-infra) tasks into the public repo this way. **Never rely on git context.**

```bash
# ✅ CORRECT — explicit target repo
gh issue create -R ${OWNER}/${AI_REPO}   --title "[grant] ..." --label "grant,p1,advisor:${ADVISOR}"
gh issue create -R ${OWNER}/${MAIN_REPO} --title "[bug] ..."   --label "bug,p1,advisor:${ADVISOR}"

# ❌ WRONG — leaks private tasks into public repo
gh issue create --title "[strategy] ..." --label "strategy,advisor:${ADVISOR}"
```

A `PreToolUse` hook (`.claude/hooks/gh-issue-repo-guard.sh`) blocks `gh issue create` without `-R` and rejects label-vs-repo mismatches.

---

## Source of Truth

| Data | Location |
|------|----------|
| Dev tasks, bugs, features, tech-debt | GH Issues (`${MAIN_REPO}`) |
| Grants, content, strategy, research, ops | GH Issues (`${AI_REPO}`) |
| Security vulnerabilities | GHSA only (never public Issues) |
| Advisor-private notes | GH Issues (`advisor:<name>` label) — surfaced in the auto-generated briefing |
| Roadmap | GitHub Milestones + progress.md |

**Visibility rule**: Grantor reads it → helps → `${MAIN_REPO}`. Competitor reads it → hurts → `${AI_REPO}`.

**Reference format**: `GH#N` = ${MAIN_REPO} (public), `AI#N` = ${AI_REPO} (private).

---

## Repo Routing — Decision Tree

Pick the target repo from the **type label** *before* running `gh issue create`:

| Type label | Repo | Why |
|------------|------|-----|
| `bug` · `feature` · `task` · `tech-debt` · `refactor` | `${OWNER}/${MAIN_REPO}` | Code reality — useful to outside contributors |
| `security:hardening` · `security:audit` (high-level only) | `${OWNER}/${MAIN_REPO}` | Public hardening (CSP, rate-limit policy). PoC/exploit details → GHSA |
| `area:*` — the instance's own subsystems, see §Area | `${OWNER}/${MAIN_REPO}` | Always paired with code-side type label |
| `strategy` · `content` · `grant` · `research` · `ops` · `agent-infra` · `meeting-action` | `${OWNER}/${AI_REPO}` | Strategic / competitor-sensitive / internal process |
| `documentation` (advisor-private docs, BRIEFINGs, topic-READMEs) | `${OWNER}/${AI_REPO}` | Internal authoring — public docs land in repo via PR commits, not issues |

**Conflict resolution**: when an issue mixes both (e.g. "security audit results that need a code fix") → split into two issues, one per repo, cross-referenced (`see AI#N` / `see GH#N`).

**Quick check before creating**:

```bash
# Determine target from intended type
case "$TYPE" in
  bug|feature|task|tech-debt|refactor|security:hardening|security:audit) REPO=${OWNER}/${MAIN_REPO} ;;
  strategy|content|grant|research|ops|agent-infra|meeting-action|documentation) REPO=${OWNER}/${AI_REPO} ;;
  *) echo "Unknown type '$TYPE' — pick one from the routing table"; exit 1 ;;
esac
gh issue create -R "$REPO" --title "[$TYPE] ..." --label "$TYPE,p1,advisor:NAME"
```

---

## Labels

### Both repos

| Category | Labels |
|----------|--------|
| Priority | `p0` (critical) · `p1` (must-have) · `p2` (nice-to-have) |
| Advisor | `advisor:<id>` — one per hired advisor. **Instance data**: the set is whatever the roster holds, never a fixed list. Discover it, don't hardcode it: `ls .claude/agents/*.md` (or `python -m engine register advisor --dry-run`). |

### Type labels

| ${MAIN_REPO} | ${AI_REPO} |
|---------|------------|
| `bug` · `feature` · `task` · `tech-debt` · `security:hardening` · `security:audit` | `strategy` · `content` · `grant` · `research` · `ops` · `agent-infra` · `meeting-action` |

Type labels are **engine schema** — they drive the repo-routing decision tree above and are the
same in every instance.

### Area (${MAIN_REPO} only)

`area:*` is **instance data**: one label per subsystem the instance's code actually has, e.g.
`area:ui` · `area:deploy` · `area:api`. Define the set once when the board is created and keep it
stable; always pair an `area:*` label with a code-side type label.

---

## Milestones

Milestones are **instance data** — release trains, grant cycles, and campaign windows belong to the
project, not to the engine. Create them on the board and reference them by exact title:

```bash
gh issue list --milestone "<exact milestone title>" --state open
```

The only convention the engine assumes is that a catch-all `Backlog` milestone with no due date
exists, so an issue is never milestone-less.

---

## Project Board

**Roadmap project board** — an instance may run one board spanning its repos. The board's concrete
identity is **instance config, not engine canon**: `owner`, `main_repo`, `ai_repo`, `board_number`
come from the instance's `roster.yaml` `github:` block; the GitHub-minted project node-ID and the
field/option GUIDs below are placeholders the instance resolves **once per deployment** (GitHub mints
them per project — they are never shared across instances).

```
Project ID:  ${PROJECT_ID}      # gh project view ${PROJECT_NUM} --owner ${OWNER} --format json → .id
Project #:   ${PROJECT_NUM}     # roster.yaml github.board_number
Owner:       ${OWNER}           # roster.yaml github.owner
Columns:     Backlog → Ready → In Progress (max 3) → Blocked → Done
```

### Mandatory Fields (ALL REQUIRED — no exceptions)

Every item on the board MUST have all 5 fields set. Missing fields = protocol violation. Field IDs and
per-option IDs are instance-specific; resolve them once with
`gh project field-list ${PROJECT_NUM} --owner ${OWNER} --format json`.

| Field | Field ID | Options |
|-------|----------|---------|
| Status | `${STATUS_FIELD_ID}` | Backlog · Ready · In Progress · Blocked · Done |
| Advisor | `${ADVISOR_FIELD_ID}` | one option per hired advisor (from the instance roster) |
| Priority | `${PRIORITY_FIELD_ID}` | P0 · P1 · P2 |
| Type | `${TYPE_FIELD_ID}` | Dev · Strategy · Content · Grant · Agent-Infra · Meeting-Action · Research · Ops |
| Source Repo | `${REPO_FIELD_ID}` | ${MAIN_REPO} · ${AI_REPO} |

### Full Field IDs (for `gh project item-edit`)

Resolve once per deployment and export — values are instance-specific:

```
P="${PROJECT_ID}"
STATUS="${STATUS_FIELD_ID}"
ADVISOR="${ADVISOR_FIELD_ID}"
PRIORITY="${PRIORITY_FIELD_ID}"
TYPE="${TYPE_FIELD_ID}"
REPO="${REPO_FIELD_ID}"
```

### Status Transitions

```
Backlog → Ready → In Progress → Done
Any → Blocked → Ready (when unblocked)
Done → reopen issue (never reverse Done directly)
```

---

## CLI Commands (token-efficient)

### List issues (compact output)

```bash
# Both repos — advisor's issues
gh issue list -R ${OWNER}/${AI_REPO} --label advisor:NAME --state open \
  --json number,title,labels \
  --template '{{range .}}AI#{{.number}} | {{.title}} | {{pluck "name" .labels | join ", "}}{{"\n"}}{{end}}'

gh issue list -R ${OWNER}/${MAIN_REPO} --label advisor:NAME --state open \
  --json number,title,labels \
  --template '{{range .}}GH#{{.number}} | {{.title}} | {{pluck "name" .labels | join ", "}}{{"\n"}}{{end}}'

# Blockers
gh issue list -R ${OWNER}/${MAIN_REPO} --label p0 --state open \
  --json number,title --template '{{range .}}GH#{{.number}} {{.title}}{{"\n"}}{{end}}'

gh issue list -R ${OWNER}/${AI_REPO} --label p0 --state open \
  --json number,title --template '{{range .}}AI#{{.number}} {{.title}}{{"\n"}}{{end}}'

# By milestone (exact title from the instance's board)
gh issue list --milestone "<milestone title>" --state open \
  --json number,title --template '{{range .}}#{{.number}} {{.title}}{{"\n"}}{{end}}'

# By type
gh issue list -R ${OWNER}/${AI_REPO} --label grant --state open \
  --json number,title,labels \
  --template '{{range .}}AI#{{.number}} | {{.title}} | {{pluck "name" .labels | join ", "}}{{"\n"}}{{end}}'
```

### Project Board audit (check missing fields)

```bash
gh project item-list ${PROJECT_NUM} --owner ${OWNER} --limit 100 --format json \
  | python3 engine/scripts/lifecycle/gh_board_query.py \
      --mode missing-fields
```

### Create issue (auto-synced to Project via GH Actions)

```bash
# Always start with -R <repo>. Pick repo from the Decision Tree above.
gh issue create -R ${OWNER}/${AI_REPO} \
  --title "[type] Title" --body "Description" \
  --label "type,priority,advisor:name" \
  --milestone "Milestone Name"
```

**Required labels**: type + priority + `advisor:name`. GH Actions sets Project fields from labels automatically.

**Required flag**: `-R ${OWNER}/<repo>` — enforced by `gh-issue-repo-guard.sh` PreToolUse hook. Commands without `-R` are blocked.

### Transfer issue (when one was created in the wrong repo)

```bash
gh issue transfer <number> ${OWNER}/<correct-repo> -R ${OWNER}/<wrong-repo>
# Returns the new URL with the new issue number. Old URL auto-redirects.
# History, comments, original creator are preserved.
```

### Close issue

```bash
gh issue close N -R REPO --comment "Done in session YYYY-MM-DD"
```

### Set Project field manually

```bash
gh project item-edit --project-id $P --id ITEM_ID \
  --field-id $FIELD_ID --single-select-option-id OPTION_ID
```

---

## Agent Protocol (MANDATORY)

### At `/conclave:start`

1. List open issues for your advisor label in **both repos** (use compact template)
2. Compare with BRIEFING.md — flag drift
3. If picking up an issue → Status: **In Progress**

### During work

| Event | Action |
|-------|--------|
| Start working on issue | Status → In Progress |
| Hit external blocker | Status → Blocked + comment |
| Prerequisite completed | Dependent issues Blocked → Ready |
| New issue discovered | Create with ALL labels → Project auto-syncs ALL fields |

### At `/conclave:done`

1. **Completed** → Status: Done + `gh issue close` + archive item
2. **Partial** → Keep In Progress + comment with progress
3. **New issues** → Create with ALL required labels AND `-R <repo>` flag
4. **Verify**: ALL issues touched this session have ALL 5 Project fields set
5. **Routing audit** — for any issue created this session, confirm:
   - Type label matches the repo (per Decision Tree above)
   - If a private-only label (`strategy`/`content`/`grant`/`research`/`ops`/`agent-infra`/`meeting-action`/`documentation`) ended up in `${MAIN_REPO}`, transfer it: `gh issue transfer N ${OWNER}/${AI_REPO} -R ${OWNER}/${MAIN_REPO}`

### Mandatory Fields Enforcement

> GH Projects does NOT enforce required fields. Enforcement is protocol-level.

When creating issues, agents MUST include labels for: **type + priority + advisor**. GH Actions auto-maps these to Project fields.

When doing Board triage, agents MUST check and fill ALL 5 fields for their assigned issues.

---

## Issue reference convention

Briefings and session records reference issues **by number only** (`GH#N` / `AI#N`) —
never duplicate issue title/body content. The briefing is auto-generated (spec 051);
`briefing-build.sh` pulls the open-issue list from the gh-cache snapshot.

---

## Security Rules

### NEVER in public Issues

Auth-bypass techniques, API key patterns or formats, exploit payloads, tolerance/threshold values an
attacker could tune against, and internals of any endpoint that moves money or credentials. The test
is not "is it sensitive" but "does publishing it shorten an attack".

### OK in public Issues

Hardening work whose value does not depend on secrecy: CSP config, rate limiting at policy level,
input-bounds checking described without a PoC, and the existence and deadlines of grants.

### Vulnerabilities → GHSA only

Use GitHub Security Advisories for vuln reports — never public Issues.

---

## Naming Convention

```
[area] Short imperative description

[api] Implement the request encoder/decoder
[grant] Apply to <programme> before <deadline>
[security] Add CSP headers to the deploy config
```
