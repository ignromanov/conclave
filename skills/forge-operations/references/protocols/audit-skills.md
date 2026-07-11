---
protocol: audit-skills
version: 1.0.0
description: |
  Inventories all installed Claude Code skills + plugins, clusters them by domain,
  detects dead/redundant/wrong-stack/duplicate clusters, and routes per-cluster
  decisions (quarantine | disable | uninstall) through AskUserQuestion gates.
  Reversible by default. Read-only without --apply.
inherits:
  - contracts/decision-framework.md
  - contracts/quality-loop.md
trigger:
  cadence: quarterly OR post-pivot OR after-major-release OR on-context-bloat
  signals:
    - "audit skills" / "проверь скиллы" / "очисти плагины"
    - skill-list line count > 250 (proxy for sprawl)
    - product roadmap pivot (e.g., dropped feature group)
    - new advisor created (may obsolete predecessors)
---

# audit-skills protocol

> Sister-protocol to `protocols/audit.md`. That one audits advisor model drift; this one audits external skill/plugin sprawl. Both share contracts/decision-framework + AskUserQuestion gates.

## Why this exists

Claude Code accumulates skills + plugins faster than they leave. Sprawl costs:
- **Context tokens** — every session loads the available-skills list (~5-15KB)
- **Discovery noise** — overlapping triggers compete; LLM picks suboptimal skill
- **Mental cache** — Ignat (or any operator) must remember what does what
- **Marketplace bytes** — installed plugins occupy `~/.claude/plugins/cache/`

Periodic audit re-aligns inventory with current project reality (the host project's roadmap, active advisors, completed/dropped features).

## Categories of skill/plugin defect

| # | Category | Heuristic | Default action | Severity |
|---|----------|-----------|----------------|----------|
| **S1** | **Stale-task** | Skill tied to a completed/dropped spec (e.g., `remotion-best-practices` after spec 035 dropped) | quarantine loose; disable plugin | WARN |
| **S2** | **Wrong-stack** | Targets tech the host project does NOT use (e.g. Farcaster MiniKit, SOC2/HIPAA, enterprise observability) | quarantine / uninstall | WARN |
| **S3** | **Duplicate-canon** | ≥2 skills with overlapping `description:` trigger keywords (e.g., token×5, bash×3) | keep 1 canonical, quarantine rest | INFO |
| **S4** | **Advisor-mimic** | Loose skill imitates a `team.*` advisor (`cto-advisor`, `c-level-advisor`) | quarantine — `/conclave-*` is canon | INFO |
| **S5** | **Orchestration-dupe** | Skill/plugin duplicates Quorum's role (cognitive-orchestration, agent-orchestration, conductor, full-stack-orchestration, team-collaboration) | disable plugin | INFO |
| **S6** | **Solo-mismatch** | Assumes team-of-N workflow (agile/Scrum, standup automation, project-management) for solo founder | disable plugin | INFO |
| **S7** | **Wrong-audience** | Skill for personas operator is not (`interview-assist` for job-seekers, `claude-cost-optimization` for API-SDK builders) | disable plugin / quarantine | INFO |
| **S8** | **Sleeping plugin** | Installed but absent from `enabledPlugins` map AND > 30 days unused | uninstall (frees marketplace) | INFO |
| **S9** | **Cold loose skill** | In `~/.claude/skills/` or `.ai/.claude/skills/` but never appeared in transcripts last 30 days | flag for review (don't auto-remove — passive cost is low) | INFO |
| **S10** | **Project-scoped duplicate** | Same plugin installed as both `project` AND `user` scope | uninstall project-scoped (keep user) | WARN |

## Discovery sources

```bash
# (A) User-level loose skills
ls ~/.claude/skills/ | grep -v "^_quarantine"

# (B) Project-level loose skills
ls .claude/skills/ | grep -v "^_quarantine"

# (C) Installed plugins (with scope)
cat ~/.claude/plugins/installed_plugins.json | jq '.plugins | keys[]'

# (D) Enabled vs installed delta
cat ~/.claude/settings.json | jq '.enabledPlugins | to_entries[] | "\(.value) \(.key)"'

# (E) Plugin-bundled skills (via skill-list system reminder — captured by hook)
# Available only inside live session; capture once via `engine audit skills` (Stage 1 discovery run)
```

## Procedure

### Stage 1 — INVENTORY

Run discovery command:
```bash
engine audit skills
```
Output: `agent-memory/advisors/audits/YYYY-MM-DD-skills.md` with sections:
- All loose user skills (count, names)
- All loose project skills (count, names)
- All installed plugins (count, enabled/disabled state, scope, marketplace)
- Suspected duplicates (by SKILL.md description token-overlap > 60%)

### Stage 2 — CLUSTER

For each candidate, classify into S1-S10 categories. Manual review supported by dispatched agent:

```
Agent(subagent_type="general-purpose", prompt="
  Read SKILL.md for each of [N] suspected duplicates.
  Compare scope, trigger keywords, unique value-add.
  Recommend keep-1 canonical + quarantine list.
  Report under 600 words.
")
```

Pattern: when ≥4 skills overlap, ALWAYS dispatch agent — manual reading consumes too much main context.

### Stage 3 — PROPOSE

Build matrix:

| Cluster | Members | Category | Recommendation | Reversibility |
|---------|---------|----------|----------------|---------------|
| <name> | a, b, c | S3 | keep `a`, quarantine `b, c` | `mv _quarantine` ↔ `mv back` |

Render via ▍-framed format (per `contracts/output-formatting.md`).

### Stage 4 — APPROVE (AskUserQuestion gate)

**MANDATORY** — never silent-remove. Apply Question-shape from `team.start` Step 1b:
1. Prose context per cluster (what gets removed, why, blast radius)
2. AskUserQuestion: labels ≤ 5 words, options for *batch-approve* / *per-item* / *skip-cluster*

Three batch modes:
- **Conservative**: only quarantine loose skills (zero plugin changes)
- **Standard**: quarantine + disable plugins
- **Aggressive**: quarantine + disable + uninstall (S8)

### Stage 5 — APPLY

Per cluster, in order:

| Action | Mechanism | Reversibility |
|--------|-----------|---------------|
| Quarantine loose skill | `mv ~/.claude/skills/<x> ~/.claude/skills/_quarantine/YYYY-MM-DD/user-skills/` | `mv` back |
| Quarantine project skill | `mv .claude/skills/<x> .claude/skills/_quarantine/YYYY-MM-DD/project-skills/` | `mv` back |
| Disable plugin | Edit `~/.claude/settings.json` → `enabledPlugins.<name>: false` | edit `true` |
| Uninstall plugin | `claude plugin uninstall <name>@<marketplace>` (or via `/plugin` UI) | `claude plugin install ...` |
| Archive stale spec resume-prompt | `mv ops/specs/<n>/resume-prompt.md archive/YYYY-MM-DD-skills-audit/` | `mv` back |

**Known blocker**: editing `~/.claude/settings.json` may be hard-blocked by Claude Code's self-modification classifier. Fallback: instruct user to:
- Run `/plugin disable <name>` interactively, OR
- Add explicit `Bash(Edit ~/.claude/settings.json)` permission, OR
- Manual edit before next session restart.

Document blocked actions in audit log with `BLOCKED: needs manual confirmation`.

### Stage 6 — VERIFY

```bash
# Confirm quarantine moves
diff <(ls ~/.claude/skills/) <(ls ~/.claude/skills/_quarantine/YYYY-MM-DD/user-skills/)

# Confirm settings.json delta
git diff ~/.claude/settings.json  # if git-tracked, else jq before/after

# Confirm available-skill-list shrunk (next session)
# Note from log: "restart required for plugin disables to take effect in available-skill list"
```

### Stage 7 — LOG

Write audit report to `agent-memory/advisors/audits/YYYY-MM-DD-skills.md`:

```markdown
---
date: YYYY-MM-DD
operator: <advisor or "ignat-direct">
mode: standard | aggressive | conservative
---

# Skills/Plugins Audit YYYY-MM-DD

## Before
- Loose user skills: N
- Loose project skills: M
- Enabled plugins: P / installed Q

## Removed
[table cluster → action → status]

## Blocked
[list of items needing manual intervention]

## After (post-restart)
[re-run inventory after Claude Code restart]
```

### Stage 8 — COMMIT

Single commit per audit (per spec 051 batch principle):
```
chore(skills-audit): YYYY-MM-DD — quarantine N loose, disable P plugins, uninstall Q
```

## Anti-patterns

| Pattern | Why bad |
|---------|---------|
| Auto-remove without AskUserQuestion gate | Violates Cardinal Rule #2 (mandatory approval) |
| Hard-delete loose skill (`rm -rf`) | Loses reversibility — always `mv` to `_quarantine/` |
| Uninstall plugin without checking dependents | `plugin-dev:agent-development` may be referenced by other skills |
| Edit `enabledPlugins` for plugin not in map | `enabledPlugins` map ≠ `installed`; absence = de-facto disabled, no action needed |
| Quarantine `team.*` lifecycle skills | Forbidden — those are infrastructure (`LIFECYCLE_SKILLS` invariant in SKILL.md §Shared invariants) |
| Run without inventory snapshot | Can't roll back if you don't know what state you started from |
| Skip restart-confirmation | settings.json changes don't reflect in available-skill-list until restart |

## Decision boundaries

| Situation | Owner | Rationale |
|-----------|-------|-----------|
| Quarterly audit cadence | team.forge (auto-trigger via cron-style reminder) | infra hygiene |
| Mid-session "this skill conflicts with what I want" | team.quorum delegates to forge audit-skills | Quorum routes infra requests to Forge |
| New advisor created — check for predecessor skills | Forge hire protocol invokes audit-skills as sub-call | prevent dual canon |
| Post-spec-archive — drop related skills | Spec close hook triggers audit-skills with `--spec <id>` filter | scoped audit |
| Operator on the fly: "remove that skill" | Direct quarantine, log retroactively in next audit | trust operator, but record |

## Reference cluster taxonomy (living)

Build over time as new defect-classes emerge. Initial set from audit `2026-05-19`:

- Video / Remotion (S1, dropped feature group)
- Interview prep (S7, wrong audience for solo founder)
- Project-delivery / Agile (S6, solo mismatch)
- Cognitive-orchestration (S5, duplicates Quorum)
- Advisor-mimics (S4, replaced by `team.*`)
- Token/context optimizers (S3, 5-way overlap → kept `context-management` v3.0)
- Bash scripting (S3 — Ignat override: kept ALL 3, operator preference > heuristic)
- Skill/agent creators (S3, replaced by `superpowers:writing-skills` + `plugin-dev`)
- Wrong-stack: Farcaster MiniKit (S2), SOC2 compliance (S2), enterprise observability (S2)
- claude-code-workflows sprawl (S5/S6/S7, ~14 plugins recommended uninstall)

## Sub-routine: agent-dispatched analysis

For deep clusters (≥4 overlapping skills or ≥10 plugins), dispatch a `general-purpose` agent in **background**:

```
Agent(
  description="Analyze <cluster> sprawl",
  subagent_type="general-purpose",
  run_in_background=true,
  prompt="...read SKILL.md / plugin.json for each / classify / recommend keep-1..."
)
```

While agent runs, the operator can apply other approved batches in parallel. Pattern proven in audit `2026-05-19` — 110s agent runtime + parallel file-system removals.

## See also

- `protocols/audit.md` — advisor-model drift audit (sister protocol)
- `contracts/decision-framework.md` — AskUserQuestion patterns
- `engine audit skills` — discovery runner (implements Stage 1)
- `agent-memory/advisors/audits/` — past audit reports
