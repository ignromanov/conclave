---
description: >-
  Sets Conclave up in a project for the first time — creates the data tree that holds the
  team's memory, records the project's identity, hires a first advisor, and wires the session
  hook. Use once per project, before the first /conclave:start.
version: 1.0.0
---

# /conclave:init — Bootstrap a Conclave Instance

> Run this ONCE in a fresh consumer project. It is idempotent — re-running will not
> duplicate the roster, wiki, minted advisor, or hook registration.

## 1. Gather project identity

Ask the user (or read from the invocation) for:

- **Project / roster name** → `ROSTER_NAME`
- **GitHub owner** (org or user that owns the repos) → `ROSTER_GH_OWNER`

The per-user GitHub token is declared in the manifest `userConfig` (`GH_TOKEN`, marked
`sensitive`). Because it is sensitive it is **not** interpolated into command/agent prose; the
platform exposes it to engine subprocesses as the `CLAUDE_PLUGIN_OPTION_GH_TOKEN` env var (with
`gh auth token` as the fallback). Never prompt for it inline or write it into `roster.yaml` /
`settings.json`.

## 2. Run the scaffold

```bash
ROSTER_NAME="<name>" ROSTER_GH_OWNER="<owner>" \
  python3 ${CLAUDE_PLUGIN_ROOT}/engine/scripts/init/conclave_init.py
```

If neither `CONCLAVE_AI_ROOT` nor `CLAUDE_PROJECT_DIR` is set (e.g. running this snippet
standalone, outside the plugin runtime), the DATA root defaults to `$PWD/.conclave`.

This:

- creates `<project>/.conclave/` — `agent-memory/advisors/{briefings,sessions,decisions,audits}`,
  `ops/{specs,handoffs,decisions}`, `wiki/`;
- writes `<project>/.conclave/roster.yaml` (096 nested schema: `project` / `github` / `knowledge`);
- scaffolds the wiki vault (`wiki/.obsidian/`, `wiki/wiki.config.md`);
- mints a first advisor at `<project>/.claude/agents/advisor.md` (flat agent-def);
- registers the SessionStart hook in `<project>/.claude/settings.json` with a **resolved
  absolute** command path (never a literal `${CLAUDE_PLUGIN_ROOT}` — empty at SessionStart).

## 3. Report

Show the user:

- the created `.conclave/` tree;
- the registered SessionStart hook path (from `.claude/settings.json`);
- the minted advisor;
- **next step → `/conclave:start`** to begin an advisor session.
