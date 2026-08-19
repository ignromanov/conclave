---
type: architecture
schema_version: 1
title: "Instance Contract — the CODE/DATA two-root boundary"
created: 2026-06-25
status: current
scope: plugin ↔ consumer boundary (how Conclave installs into and runs against any repo)
see_also:
  - overview.md
  - lifecycle.md
  - ../specs/098-conclave-plugin-packaging.md
  - ../specs/096-engine-manifest.md
---

# Instance Contract — the CODE/DATA two-root boundary

> **Single question this doc answers:** "When Conclave is installed into a repo, what is CODE
> (shipped by the plugin, shared, read-only) versus DATA (per-project, written by sessions), and how
> do the two roots resolve at runtime?"
>
> This is the contract every consumer — including the `conclave-self` self-instance — obeys. It was
> crystallized at spec **098** (plugin packaging) and the **`1af117c`** path-convention unification.
>
> **Verified section-by-section against disk on 2026-07-09** (#84), by executing the resolvers rather
> than reading them. Six of eight sections were false or stale; §3 and §4 held. Claims that remain
> aspirational are marked ⚠ and carry the issue that tracks them.

---

## 1. Two roots, never crossed

| Root | Env var | Resolves to | Holds | Mutability |
|------|---------|-------------|-------|------------|
| **CODE** | `CONCLAVE_ENGINE_ROOT` | the plugin's `engine/` dir (`${CLAUDE_PLUGIN_ROOT}/engine`) | scripts the commands call (`engine/scripts/…`) | read-only, shared |
| **DATA** | `CONCLAVE_AI_ROOT` | the consumer's `.conclave/` (`${CLAUDE_PROJECT_DIR}/.conclave`) | `roster.yaml`, `agent-memory/`, `ops/`, `wiki/` | written by sessions, per-project |

**Cardinal invariant:** a session writes only under the DATA root. CODE is never mutated by a running
advisor — engine evolution goes through Forge (`/conclave:forge`) against the engine's *own* instance,
not as a side effect of a consumer session. The `code-data-gate` enforces the read-side of this.

## 2. Canonical path convention (`1af117c` — do not reintroduce a dual convention)

`CONCLAVE_ENGINE_ROOT` is the **`engine/` directory itself**, not the plugin root:

- scripts live at `_engine_root()/scripts` (e.g. `engine/scripts/lifecycle/session_init.py`);
- plugin skills live at `_engine_root().parent/skills` (e.g. `skills/advisor-contracts/references/…`).

Defaults are **`:+`-guarded** on the Claude Code env vars so that in-repo / test runs (where the CC
vars are empty) fall back to a filesystem walk instead of a broken interpolation. Expressed in shell
notation (the rule; the implementation is Python):

```
CONCLAVE_AI_ROOT     := ${CLAUDE_PROJECT_DIR:+${CLAUDE_PROJECT_DIR}/.conclave}   # else: walk up
CONCLAVE_ENGINE_ROOT := ${CLAUDE_PLUGIN_ROOT:+${CLAUDE_PLUGIN_ROOT}/engine}      # else: walk up
```

Implemented once, in `enginelib/paths.py` (`_plugin_data_default` / `_plugin_engine_default`).
`briefing/paths.py` re-exports it — the names stay for its twelve importers, the answers come from
one place. The bash original `engine/scripts/lib/paths.sh` **no longer exists** — spec 099 ported
the whole tree to Python; only its docstring reference survives at `enginelib/paths.py:1`.

> The two implementations used to disagree on five counts — the env names honoured, whether the
> answer was `.resolve()`d, whether the walk started from `cwd` or `__file__`, whether a symlinked
> `.claude/` passed, and a module cache only one of them had. On macOS every path either produced
> differed from the other's by a `/private` prefix, so `==` between two spellings of one directory
> was false. `tests/test_root_resolver_agreement.py` runs both across seven scenarios and fails if
> they part again; it was written red (4 of 6 failing) before the collapse.

> The walk's marker was also self-confirming: the engine checkout carries `ops/` (for
> `ops/SCHEMA.md`) beside `.claude/`, so with no env set the resolver answered with the CODE tree
> and DATA was written into it. A candidate now needs a `roster.yaml` — what `conclave init` writes
> at a DATA root and nothing writes into CODE. The reproduction recorded here and in #29 now raises
> instead of answering.

> ⚠ History: a dead `_engine_root()/skills` lookup (overlay base) silently disabled contract overlays
> in production; the fix unified everything on the rule above. Don't anchor plugin-skill lookups on the
> engine subtree.

## 3. What the plugin ships (CODE)

| Location | Content |
|----------|---------|
| `commands/*.md` | the `/conclave:<verb>` lifecycle (`start`, `processing`, `done`, `forge`, `hire`, `handoff`, `feedback`, `retro`, `triage`, `init`) |
| `agents/*.md` | `forge` (always-present meta-role) + the `exec-*` executors (flat agent-defs) |
| `skills/*` | shared skills: `advisor-contracts` (the contract reference bundle) + `forge-operations` |
| `hooks/sessionstart-conclave.py` | the SessionStart dashboard/verify-repair hook (registered DATA-side, see §5) |
| `.claude-plugin/{plugin.json,marketplace.json}` | the manifest + local/git marketplace entry |

## 4. What the consumer holds (DATA)

Created by `/conclave:init` (idempotent):

- `<repo>/.conclave/` — `roster.yaml` (096 nested schema), `agent-memory/advisors/{briefings,sessions,decisions,audits}`, `agent-memory/executors/`, `ops/{specs,handoffs,decisions}`, `wiki/`.
- `<repo>/.claude/agents/<id>.md` — **hired domain advisors**, flat agent-defs (discovery = filename stem). Advisor inventory is *discovered, not hardcoded*: `_known_advisors` globs this dir and excludes `forge` + `exec-*`.
- `<repo>/.claude/settings.json` — machine-local wiring written by init: the two env vars (resolved absolute) + the SessionStart hook entry.

## 5. Wiring (machine-local, never committed)

The SessionStart hook is registered **DATA-side** with a **resolved absolute path** — never the literal
`${CLAUDE_PLUGIN_ROOT}`, which is empty at SessionStart (098 F-001).

`/conclave:init` writes this wiring to `<repo>/.claude/settings.json` (`init/conclave_init.py:197`,
`init/reconcile_hook.py:35`). It never writes `settings.local.json` — that filename appears in the
engine only as a scanner exclusion (`audit/agent_configs.py::SECRET_EXCLUDES`). Because the resolved
paths are machine-specific, **both** `settings.json` and `settings.local.json` are gitignored (#83). A
fresh clone re-creates wiring by re-running `/conclave:init` (or mirroring its `register_hook`).

The committed footprint of an instance is **DATA + docs only**. ⚠ The engine repo currently violates
this: `.claude/agents/{advisor,sage-cto,testx}.md` and two `.claude/skills/` files are tracked in the
CODE tree. Tracked as **#82**; relocation is spec 103 W3.

## 6. Two instantiations of the contract

1. **Normal consumer** — plugin installed globally; DATA at `<repo>/.conclave/`; `CLAUDE_PROJECT_DIR`
   set by CC → `CONCLAVE_AI_ROOT` resolves automatically.
2. **`conclave-self`** (the engine's self-improvement instance) — DATA root is `<repo>/.conclave/`,
   exactly like a normal consumer; it is a nested **private git repo** (`conclave-ai`). Both resolvers
   return it when `CLAUDE_PROJECT_DIR` is set. Env + hook live in `.claude/settings.json` (gitignored).
   Its hired advisors live in `.conclave/.claude/`, and `.claude/{agents,skills}` in the CODE checkout
   hold per-item symlinks back to them (spec 103 §3.2) — gitignored, so CODE tracks no instance data.
   The `test_instance_data_not_tracked_in_code` gate enforces that.

## 7. Back-compat alias (retired)

`VOIDPAY_AI_ROOT` was a fallback alias for `CONCLAVE_AI_ROOT`, from the instance this engine was
extracted from. **No reader honours it any more.** Set without `CONCLAVE_AI_ROOT`, it now stops the
command with an error naming the current variable; set alongside it, it is ignored.

It was retired rather than deprecated because the six sites that read it did not agree on whether
it counted, and the seventh — `enginelib/paths.py`, the resolver everything else was meant to
defer to — ignored it entirely. A process could therefore honour the alias in one subsystem and
ignore it in the next, writing feedback into one tree while reading advisors from another, with
every individual call succeeding. A deprecation warning does not fix a split brain; it narrates it.

The guard is `enginelib.paths.check_legacy_data_root_env()`, called by every site that resolves a
DATA root. It lives beside `repo_root()` rather than inside it because five of the six readers
never call `repo_root()` — they read `os.environ` directly, and a check inside the resolver would
have covered one of six.

| File | Before | Now |
|------|--------|-----|
| `enginelib/paths.py` | ignored the alias | raises the guard, then reads `CONCLAVE_AI_ROOT` |
| `briefing/paths.py` | honoured it | re-exports `enginelib/paths.py` |
| `enginelib/roster.py` | honoured it | guard + `CONCLAVE_AI_ROOT` |
| `lifecycle/session_init.py` | honoured it | guard + `CONCLAVE_AI_ROOT` |
| `lifecycle/study_phase.py` | honoured it | guard + `CONCLAVE_AI_ROOT` |
| `lifecycle/gh_board_query.py` | honoured it | guard + `CONCLAVE_AI_ROOT` |
| `engine/cmd/session.py` | honoured it | guard + `CONCLAVE_AI_ROOT` |

## 8. Boundary invariants (checklist)

Each invariant names the test that enforces it. An unenforced invariant is a wish, not a contract.

| Invariant | Enforced by | Status |
|-----------|-------------|--------|
| Sessions write only under `CONCLAVE_AI_ROOT` (DATA); CODE is read-only | `test_root_resolver_agreement.py::test_a_code_shaped_tree_is_not_taken_for_a_data_root` | ✅ with env unset the walk now refuses a rosterless tree (#29) |
| The two `repo_root()` spellings answer alike | `test_root_resolver_agreement.py` (7 scenarios) | ✅ `briefing.paths` re-exports `enginelib.paths` |
| Plugin tree carries zero instance literals | `test_grep_gate_no_instance_literals` | ✅ |
| Public surface carries zero operator-absolute paths | `test_publication_gate_no_operator_abs_paths` | ✅ (#83) |
| Hook command is a resolved absolute path, no `${CLAUDE_PLUGIN_ROOT}` literal | — | ⚠ unenforced |
| Advisor inventory is discovered (`.claude/agents/*.md` stem), never hardcoded | `session_init.py::_known_advisors` | ✅ |
| Machine-specific wiring stays gitignored | `test_machine_local_settings_are_gitignored` | ✅ (#83) |
| Committed instance = DATA + docs | — | ⚠ violated (#82) |
| No CODE resource read via the DATA `.claude/` namespace | `test_code_data_gate_no_claude_namespace_reads` | ✅ |
