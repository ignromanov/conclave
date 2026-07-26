<div align="center">

# Conclave

### Your AI agents start every session from zero — no memory, no roles, no learning from past mistakes.

Conclave is a Claude Code plugin that gives a team of AI advisors and executors a persistent memory,
hard role boundaries, a mandatory session lifecycle, and a feedback loop that turns recurring mistakes
into durable edits to the agents' own skills.

[Install](#install) · [See it work](#see-it-work) · [Configuration](#configuration) · [Commands](#commands) · [Docs](#doc-set)

</div>

---

> [!IMPORTANT]
> **What it touches (local-only).** `/conclave:init` runs `python3` engine scripts that create a
> `.conclave/` data tree in your repo, write `.conclave/roster.yaml`, mint an advisor into
> `.claude/agents/`, and register a **SessionStart hook** in your project's `.claude/settings.json`.
> No telemetry. There is one outbound network call: a GitHub issue/board sync that runs
> **automatically at the start of every advisor session** — it is not opt-in. It shells out to the
> `gh` CLI, using the plugin's `GH_TOKEN` setting if you configured one and your own `gh auth`
> session otherwise. The sync happens only when a repo scope resolves: `github.ai_repo` /
> `github.main_repo` in `.conclave/roster.yaml`, falling back to your project's `origin` remote.
> With neither, it refuses and makes no call rather than searching your account. There is currently
> no switch to disable it while a scope is resolvable.
>
> **Reversibility.** Remove the SessionStart hook from `.claude/settings.json`, delete `.conclave/` and
> the minted `.claude/agents/*.md`, then `/plugin uninstall conclave`. Nothing persists outside your repo.

## Prerequisites

| Requirement | Why |
|---|---|
| **Python 3.11+** | The engine's runtime. The floor is enforced at every entrypoint, which refuses older interpreters with a plain message rather than a traceback. macOS ships 3.9 as `/usr/bin/python3`, so a system-Python run will hit this. |
| **[`uv`](https://docs.astral.sh/uv/)** | Provisions the engine's dependencies into a plugin-local venv on first run. Without it, install those four packages yourself: `PyYAML`, `python-frontmatter`, `pydantic`, `ruamel.yaml`. |
| **[`gh`](https://cli.github.com/), authenticated** | The GitHub issue/board sync shells out to it. Run `gh auth status` to confirm. On failure, session-init exits 3 (stale-fail) and reports the error in the session-start block; the cached snapshot is left untouched rather than overwritten. |
| **git** | Session state and the repo-scope fallback both read your project's git metadata. |

## Install

Conclave ships as its own marketplace, so install is two steps.

**From GitHub:**

```
/plugin marketplace add ignromanov/conclave
/plugin install conclave
```

**From a local clone** (dev loop — edit skills/agents and reinstall without pushing):

```
/plugin marketplace add .          # or an absolute path to the repo
/plugin install conclave
```

The hard dependency `agent-teams` auto-enables. Then bootstrap your project once:

```
/conclave:init
```

---

## The Problem

Most "multi-agent" systems are orchestration — they make a team of agents *busier*. They don't fix
the two failures that actually compound: agents forget everything between sessions, and they repeat
the same mistakes because nothing closes the loop on feedback.

If you've run spec-driven development or kept an engineering decision log, you already know half the
fix — durable records that survive the session. What Conclave adds is the **governance + learning**
layer on top: persona-driven advisors with hard scope boundaries run every session through a
mandatory lifecycle, write to an append-only memory, and emit structured feedback. A loop then
verifies that feedback — items already satisfied get closed, and recurring, verified patterns are
promoted into edits to the agents' own skills and contracts.

> **Honest status.** The learning loop is **human-gated (L1)** today — nominations surface for your
> approval; the agents do not yet rewrite themselves autonomously. See [`VISION.md`](VISION.md) for
> the founding intent and [`docs/architecture/`](docs/architecture/) for the corrected mechanism.

---

## See It Work

```
> /plugin marketplace add ignromanov/conclave
✓ marketplace 'conclave-marketplace' added
> /plugin install conclave
✓ conclave@0.2.0 installed   (agent-teams enabled via dependencies)

> /conclave:init
  project name? voidpay
  github owner? ignromanov
✓ created .conclave/{agent-memory,ops,wiki}/
✓ wrote   .conclave/roster.yaml
✓ minted  .claude/agents/advisor.md
✓ hook    SessionStart registered in .claude/settings.json
  next → /conclave:start

> /conclave:start
  advisor session begins — briefing loaded from .conclave/agent-memory/, lifecycle armed
```

---

## Getting Started

1. **Install** the plugin (above).
2. **`/conclave:init`** — once per project. Idempotent; re-running won't duplicate the roster, wiki,
   advisor, or hook.
3. **`/conclave:start`** — begin an advisor session. Every session flows through the lifecycle
   (`start → processing → work → done → handoff`) so work never drifts from its record.
4. **`/conclave:hire`** — grow the roster with domain advisors as the project needs them. Conclave
   ships clean: just the engine plus the always-present meta-role **Forge**; the domain roster is
   hired fresh per project.

---

## Configuration

Conclave does **not** use a `.claude/conclave.local.md` settings file. Configuration lives in two places:

| Where | What |
|-------|------|
| `userConfig.GH_TOKEN` (plugin manifest) | Optional, `sensitive`. Exposed to engine subprocesses as `CLAUDE_PLUGIN_OPTION_GH_TOKEN`; falls back to `gh auth token`. Never written into `roster.yaml` or `settings.json`. |
| `.conclave/roster.yaml` (per project) | Project identity, GitHub owner, knowledge/wiki config (096 nested schema). Written by `/conclave:init`. |

After editing the SessionStart hook or `settings.json`, restart Claude Code — hooks are not hot-swapped within a session.

---

## Dependencies

| Plugin | Role |
|--------|------|
| `agent-teams` | **Hard dependency** — auto-enabled on install (from the `claude-code-workflows` marketplace). Provides the parallel team primitives the executors dispatch onto. |
| [`llm-obsidian-wiki`](https://github.com/ignromanov/llm-obsidian-wiki) | **Companion** — the wiki vault is scaffolded by Conclave's engine at init; install the plugin if you want its curation/answer skills over the vault. |

---

## Commands

| Command | Purpose |
|---------|---------|
| `/conclave:init` | Bootstrap `.conclave/`, roster, first advisor, and the SessionStart hook. Run once. |
| `/conclave:start` | Begin an advisor session (loads briefing, arms the lifecycle). |
| `/conclave:processing` | Enter the processing phase of the lifecycle. |
| `/conclave:done` | Close out work and write the session record. |
| `/conclave:handoff` | Hand the session off with a durable summary. |
| `/conclave:hire` | Add a domain advisor to the roster. |
| `/conclave:forge` | Invoke Forge — the agent factory / self-improvement meta-role. |
| `/conclave:feedback` | Emit structured feedback into the loop. |
| `/conclave:triage` | Triage open feedback items. |
| `/conclave:retro` | Run a retrospective over recent sessions. |

---

## How It Works

Advisors and executors run as a coherent organization: persona-driven roles with distinct voices and
scope boundaries, task-scoped workers with strict file-ownership, a mandatory lifecycle, an
append-only memory under auto-generated briefings, and a feedback loop gated by an external verifier
so wrong lessons are demoted, never reinforced.

<details>
<summary><b>Architecture & design rationale</b></summary>

Start with [`VISION.md`](VISION.md), then your instance's `project-context.md` (canonical identity;
`/conclave:init` scaffolds it into `.conclave/`) and [`constitution.md`](constitution.md) (binding
governance principles). The seven architecture principles — file-as-message-bus · cache-over-truth ·
mandatory lifecycle · spec-driven · confidence-graduated authority · never-silent-delete ·
guardrails-as-first-class — are defined in `VISION.md` §6.

The engine was built in-place inside VoidPay's `.ai/` and extracted into this repo as an installable
plugin (spec 098). VoidPay remains the proving ground, not the parent.

</details>

---

## Doc-set

| Area               | Doc                                                                                                                                                                                                                                                                                       |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Architecture**   | [`overview`](docs/architecture/overview.md) · [`engine-modules`](docs/architecture/engine-modules.md) · [`roster-and-forge`](docs/architecture/roster-and-forge.md) · [`memory-and-knowledge`](docs/architecture/memory-and-knowledge.md) · [`lifecycle`](docs/architecture/lifecycle.md) |
| **Functionality**  | [`functionality`](docs/architecture/functionality.md) — end-to-end capability catalog                                                                                                                                                                                                     |
| **Contract**       | [`instance-contract`](docs/architecture/instance-contract.md) · [`SCHEMA`](docs/architecture/SCHEMA.md) — what an instance owes the engine, and the file schemas                                                                                                                          |

Working documents — specs, plans, research, product and migration notes — are **not** shipped: they
are the instance's own record and live in its private DATA tree (`.conclave/ops/`). `docs/` here
carries descriptive architecture only, and a gate enforces it
(`engine/scripts/tests/test_gates.py::test_working_docs_not_in_code`).

---

## Relationship to VoidPay

VoidPay (`~/code/vl/`) is the proving ground, not the parent. The system was born there and is
dogfooded there; Conclave is the standalone project that owns its design and productization. The same
engine is built to run on other projects (Vault, SafeUnfollow) and, per the Track-B path, on small
businesses as a product.

---

## Status & License

**Status**: packaged and installable (v0.2.0); design doc-set captured 2026-06-11.
**License**: [MIT](LICENSE).
