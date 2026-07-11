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

Implemented in `enginelib/paths.py` (`_plugin_data_default` / `_plugin_engine_default`) and mirrored
in `briefing/paths.py`. The bash original `engine/scripts/lib/paths.sh` **no longer exists** — spec 099
ported the whole tree to Python; only its docstring reference survives at `enginelib/paths.py:1`.

> ⚠ The two implementations **do not agree**, and the divergence is load-bearing, not cosmetic:
> `enginelib.repo_root()` walks up from **`cwd`** and requires a non-symlink `.claude/`;
> `briefing.repo_root()` walks up from **`__file__`**, memoizes, accepts a symlinked `.claude/`, and
> additionally honours the `VOIDPAY_AI_ROOT` alias (§7) that `enginelib` ignores. With no env set, the
> `briefing` walk matches the **engine repo root itself** and DATA is written into the CODE tree.
> Reproduce: `env -u CONCLAVE_AI_ROOT -u CLAUDE_PROJECT_DIR PYTHONPATH=engine/scripts python -c
> 'from briefing.paths import agent_memory_dir; print(agent_memory_dir())'`. Tracked as **#80**;
> unification is spec 103 W5. Until then, treat the "Resolves to" column of §1 as true *only when
> `CLAUDE_PROJECT_DIR` or `CONCLAVE_AI_ROOT` is set*.

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
   return it when `CLAUDE_PROJECT_DIR` is set. Env + hook live in `.claude/settings.json` (gitignored),
   and CODE comes from the installed plugin — no CODE symlinks.
   ⚠ `instances/conclave-self/` predates the convention and is a **fossil**, not the live root: its
   `ops/feedback/_index/index.jsonl` last moved 2026-06-17, while `.conclave/`'s is live. Do not write
   to it. Removal is spec 103 W3.

## 7. Back-compat alias (deprecated)

`VOIDPAY_AI_ROOT` is accepted as a fallback alias for `CONCLAVE_AI_ROOT` (origin: VoidPay was the
dogfooding instance). It is **deprecated** — new instances set `CONCLAVE_AI_ROOT`. The alias survives
only for the in-place VoidPay `.ai/` during migration and should be dropped once that instance is
re-homed.

Resolution points (enumerated 2026-07-09; `lib/paths.sh`, `create-advisor.sh` and `register-advisor.sh`
were listed here but no longer exist — retired by spec 099):

| File | Reads the alias |
|------|-----------------|
| `enginelib/roster.py` | yes |
| `briefing/paths.py` | yes |
| `lifecycle/session_init.py` | yes |
| `lifecycle/study_phase.py` | yes |
| `lifecycle/gh_board_query.py` | yes |
| `engine/cmd/session.py` | yes |
| `enginelib/paths.py` | **no** — reads only `CONCLAVE_AI_ROOT` (part of the #80 split-brain) |

## 8. Boundary invariants (checklist)

Each invariant names the test that enforces it. An unenforced invariant is a wish, not a contract.

| Invariant | Enforced by | Status |
|-----------|-------------|--------|
| Sessions write only under `CONCLAVE_AI_ROOT` (DATA); CODE is read-only | — | ⚠ unenforced; violated when env is unset (#80) |
| Plugin tree carries zero instance literals | `test_grep_gate_no_instance_literals` | ✅ |
| Public surface carries zero operator-absolute paths | `test_publication_gate_no_operator_abs_paths` | ✅ (#83) |
| Hook command is a resolved absolute path, no `${CLAUDE_PLUGIN_ROOT}` literal | — | ⚠ unenforced |
| Advisor inventory is discovered (`.claude/agents/*.md` stem), never hardcoded | `session_init.py::_known_advisors` | ✅ |
| Machine-specific wiring stays gitignored | `test_machine_local_settings_are_gitignored` | ✅ (#83) |
| Committed instance = DATA + docs | — | ⚠ violated (#82) |
| No CODE resource read via the DATA `.claude/` namespace | `test_code_data_gate_no_claude_namespace_reads` | ✅ |
