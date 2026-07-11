---
title: Obsidian vault setup
last-reviewed: 2026-05-16
covers-as-of-commit: 3a08af2
---

# Obsidian Vault Setup

> Vault root: `.ai/agent-memory/` — initialised by spec 076 T10.

## 1. First-time setup (humans only)

1. Open Obsidian Desktop.
2. Click "Open another vault" → "Open folder as vault".
3. Select `<repo>/.ai/agent-memory/`.
4. Accept "Trust this vault?" → click "Trust and Enable Plugins".
5. Go to Settings → Community plugins → turn off Restricted mode.
6. Install the 3 required plugins (search each by name, install, enable):
   - **Dataview** — renders live queries in the 10 MOC INDEX.md pages
   - **Folder Notes** — lets `INDEX.md` act as a clickable folder note
   - **Linter** — normalises frontmatter + heading conventions
7. Restart Obsidian once after enabling all three.

The abbreviated walkthrough lives in `agent-memory/README.md`; this document is the permanent reference that deepens it.

---

## 2. Committed vs ignored `.obsidian/` files

| Committed | Ignored |
|-----------|---------|
| `app.json` (vault display settings) | `workspace.json` (per-user open panes + UI state) |
| `core-plugins.json` (enabled built-in plugins) | `workspace-mobile.json`, `workspaces.json` |
| `community-plugins.json` (required plugin list) | `cache/`, `.cache/` (hot-reload artifacts) |
| `plugins/<plugin>/data.json` (plugin config) | `plugins/*/main.js.map`, `plugins/*/styles.css.map` |
| | `community-plugins-installed.json` (per-user enable state) |
| | `types.json` |
| | `.trash/` (Obsidian soft-delete folder) |

**Rationale:** shared config lands in git so any contributor's Obsidian session matches the baseline plugin configuration; per-user UI state (open panes, expanded folders, window size) stays local and is never committed.

Full `.gitignore` source: `agent-memory/.gitignore` (T10).

---

## 3. Plugin baseline

### Required (Phase 0 — needed for MOC pages + frontmatter integrity)

| Plugin | Why required |
|--------|-------------|
| **Dataview** | Renders the live `dataviewjs` queries inside each of the 10 `INDEX.md` MOC pages (T11). Without it, those pages show raw code blocks. |
| **Folder Notes** | Associates `INDEX.md` with its parent folder so clicking the folder in the file explorer opens the MOC page instead of expanding the tree. Pattern: set "Folder note name" to `INDEX` (no extension) in plugin settings. |
| **Linter** | Enforces YAML frontmatter structure and heading conventions on save. Catches missing required keys (`type`, `schema_version`) before they silently break Dataview queries. |

### Optional (vault evolution — add as use cases land)

| Plugin | When to add |
|--------|------------|
| **Templater** | When you need conditional template logic beyond what the bash scaffolding scripts provide (e.g., dynamic date-based filenames from within Obsidian). |
| **Tasks** | If `mention.md` op-type evolves into an interactive tasks-style query view (deferred to spec 080). |
| **Bases** (Obsidian 1.8+) | When MOC Dataview tables outgrow their current form and you want Notion-like filtered/grouped views over frontmatter fields. Drop-in replacement for Dataview table blocks. |

---

## 4. Folder-notes convention

We use `INDEX.md` as the folder note filename (not `<folder>.md`, which is the Obsidian default). This choice is intentional:

- `INDEX.md` renders correctly as plain markdown for non-Obsidian consumers (CI scripts, `cat`, GitHub's file browser).
- Folder Notes plugin auto-discovers either pattern; configure it: Settings → Folder Notes → "Folder note name pattern" → `INDEX`.

To open a folder's MOC view in Obsidian: click the folder name in the file explorer. Folder Notes renders the `INDEX.md` inline without navigating into the folder.

The 10 committed MOC pages (T11):

```
agent-memory/advisors/INDEX.md
agent-memory/executors/INDEX.md
agent-memory/audit/INDEX.md
agent-memory/reconcile/INDEX.md
agent-memory/gh-cache/INDEX.md
agent-memory/git-cache/INDEX.md
agent-memory/plans/INDEX.md
agent-memory/run-log/INDEX.md
agent-memory/advisors/sessions/INDEX.md
agent-memory/advisors/decisions/INDEX.md
```

---

## 5. Cross-vault link convention

The `agent-memory/` vault and the public knowledge wiki (the `<wiki>/` repo) are separate Obsidian vaults. Obsidian wikilinks do not cross vault boundaries by default.

For the rare case where you want the wikilink graph to span both vaults, use a relative path wikilink from the vault root:

```
[[../../../<wiki>/concepts/<concept>|Concept Label]]
```

In practice, most contributors do not need this — the wiki is browsable via `/wiki:browse` and `/wiki:query` commands directly from any advisor session. The cross-vault link is for cases where you want graph view continuity between the operational memory and the knowledge base.

---

## 6. Schema enforcement

All op-type files carry `schema_version` and `type` in YAML frontmatter (established T3+T4). The **Linter** plugin can enforce this via its "YAML required keys" feature:

1. Open Settings → Linter → YAML.
2. Under "Force YAML Escape" or "Required YAML metadata fields" (depending on plugin version), add: `type`, `schema_version`.
3. Set Linter to run on save or via the command palette.

When a file is missing these keys, Linter will flag or auto-insert placeholder values, preventing silent Dataview query breakage.

---

## 7. Troubleshooting

### "Dataview query returns no results but I know there are files"

Check that files have `type:` in their YAML frontmatter. Legacy files created before T8 may lack this field. Re-run the migration script:

```bash
python -m engine lifecycle migrate-add-type
```

After the script completes, trigger a Dataview cache rebuild: open the command palette → "Dataview: Force Refresh All Views".

### "Folder Notes plugin doesn't render INDEX.md as the folder"

Go to Settings → Folder Notes → set "Folder note name pattern" to `INDEX` (no extension). Restart Obsidian. If the setting is already correct and the issue persists, try disabling and re-enabling the plugin.

### "Sync conflict on `.obsidian/workspace.json`"

This should not happen — `workspace.json` is gitignored. If it appears in `git status`, it was accidentally committed in a prior session. Fix:

```bash
git rm --cached .ai/agent-memory/.obsidian/workspace.json
echo '.obsidian/workspace.json' >> .ai/agent-memory/.gitignore
```

### "Wikilink target shows as red (broken link)"

Verify the target file exists with the exact same name as the link text. Status-tag archival (T7) does not move files — links stay valid through archival. If you renamed a file outside Obsidian (via `mv`), Obsidian cannot auto-update wikilinks. Use Obsidian's right-click → "Rename" for safe renames that propagate to all wikilinks in the vault.

### "Plugin not loading after pulling from git"

After `git pull`, open Obsidian → Settings → Community plugins → verify each required plugin is enabled. Plugin install state (`community-plugins-installed.json`) is per-user and not committed. If a plugin is listed in `community-plugins.json` but not enabled, enable it manually and restart.

---

## See also

- `skills/forge-operations/references/loop-discipline.md` — producer/consumer contract (exit codes, cache policy, run-log)
- `ops/specs/076-lifecycle-bash-extraction/spec.md` — full spec for this vault's initialisation
- `agent-memory/README.md` — vault root readme (abbreviated first-time setup walkthrough)
