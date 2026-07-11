---
kind: color-palette
version: 1.0.0
---

# Color palette

## Available colors (pool)
red, orange, yellow, green, teal, blue, indigo, purple, pink, magenta, cyan, amber, lime, emerald, rose, slate

## Discovery

```bash
# Compute taken colors:
grep -h "^color:" .claude/agents/team.*.md | awk '{print $2}' | sort -u

# Free = pool minus taken.
```

## Hire Phase 3 uses
1. Run the grep above.
2. Subtract from pool.
3. Suggest 3 free colors to the user via AskUserQuestion.

## Reserved (in-use)

| Agent | Emoji | Color |
|-------|-------|-------|
| Nexus 🔮 (CEO) | 🔮 | purple |
| Kai 🔷 (CTO) | 🔷 | cyan |
| Shade 🛡️ (CISO) | 🛡️ | red |
| Spark ⚡ (CMO) | ⚡ | orange |
| Quorum ⚖️ (Secretary) | ⚖️ | blue |
| Dev 🛠️ (legacy) | 🛠️ | #F97316 (orange-500) |
| atlas 🧱 (executor) | 🧱 | teal |
| iris 🌈 (executor) | 🌈 | violet |

> **Note**: Dev's reservation expires when `exec.atlas-dev` is archived in Phase D.1 — its emoji 🛠️ becomes available for future executors.
>
> **Rename note (2026-05-08)**: `argus 👁️ violet` → `iris 🌈 violet`. Color slot stable; persona swap from masculine sentinel (Argus Panoptes) to feminine messenger (Iris). See `ops/handoffs/2026-05-08-create-argus-test-agent.md`.

## Reserved emojis (do not use without freeing)
🔷 🔮 ⚡ 🛡️ 🛠️ ⚖️ 🧱 🌈

## Invariants
- No color hardcoded in Hire or scripts. Pool lives here only.
- Pool updated via Evolve (aspect: `agent-frontmatter` + `shared-rules`).
