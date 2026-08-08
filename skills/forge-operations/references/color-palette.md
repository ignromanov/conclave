---
kind: color-palette
version: 2.0.0
---

# Color palette

## Available colors (pool)
red, blue, green, yellow, purple, orange, pink, cyan

These eight are the colours the harness renders — the `color` row of the subagent frontmatter
reference (<https://code.claude.com/docs/en/sub-agents>). The field is optional; a value outside
this set is accepted by YAML and dropped at render time, so the agent shows up with no colour at
all while its file looks configured.

Pinned in two places so neither can drift alone: `enginelib.register.VALID_AGENT_COLORS` (which
rejects an invalid `--color` at hire) and
`tests/test_executor_defs.py::test_palette_pool_matches_the_harness`, which asserts this line
equals that set.

> **v2.0.0 (2026-08-08, spec 109 Task 2).** The pool previously listed sixteen values, eight of
> them unrenderable (`teal`, `indigo`, `magenta`, `amber`, `lime`, `emerald`, `rose`, `slate`) —
> and **every shipped agent had been assigned one of those**. `amber` looked like a three-way
> collision between metron, themis and Forge; all three were in fact rendering as nothing.

## Discovery

```bash
# Colours in use across the shipped roster:
grep -h "^color:" agents/*.md | awk '{print $2}' | sort

# Plus this instance's hired advisors (DATA — a separate repo):
grep -h "^color:" .conclave/.claude/agents/*.md | awk '{print $2}' | sort

# Free = pool minus the union of both.
```

> The previous version of this block globbed `.claude/agents/team.*.md` — a path that does not
> exist, under a prefix retired on 2026-07-27. It therefore reported *every* colour as free, which
> is how three agents were handed the same one. A discovery command that cannot fail is not a
> check; re-run these greps rather than trusting a remembered answer.

## Hire uses
1. Run the greps above.
2. Subtract from the pool.
3. Offer the free colours to the operator via AskUserQuestion.
4. `engine register executor --color <name>` refuses anything outside the pool, so a typo fails
   at hire rather than at first dispatch.

**Distinctness is finite.** Eight colours, and the roster is already nine agents (seven in CODE,
two hired). Uniqueness holds *within* `agents/` — `test_agent_colours_are_valid_and_distinct`
enforces it there and fails with an explicit message once that directory exceeds eight defs.
Across tiers, repeats are expected; the emoji is the per-agent signal that does not run out.

## Reserved (in-use)

| Agent | Tier | Emoji | Colour |
|-------|------|-------|--------|
| atlas (dev executor) | executor | 🦊 | green |
| iris (quality gate) | executor | 🌈 | yellow |
| metron (ranker) | executor | 📐 | orange |
| scout (research) | executor | 🔭 | cyan |
| socra (critic) | executor | 🔍 | red |
| themis (judge) | executor | ⚖️ | blue |
| Forge (meta-advisor) | meta | 🔨 | purple |
| sage-cto | advisor (DATA) | 🦉 | — |
| keel-coo | advisor (DATA) | ⚙️ | — |

Rebuilt from the tree on 2026-08-08. The table it replaced claimed `atlas 🧱 teal` and listed a
VoidPay-era roster; atlas has been 🦊 since its rewrite. Treat this table as a cache — the greps
above are the truth.

## Reserved emojis (do not use without freeing)
🦊 🌈 📐 🔭 🔍 ⚖️ 🔨 🦉 ⚙️ 🔷 🔮 ⚡ 🛡️ 🛠️ 🧱

The tail (🔷 🔮 ⚡ 🛡️ 🛠️ 🧱) is historical: emojis of retired or foreign-instance advisors, kept
reserved so a re-read of an archived artifact never resolves to a different agent.
`enginelib.register.create_executor` reads **this line** for its collision check — one line, no
wrapping.

## Invariants
- No colour hardcoded in Hire or in scripts. The pool lives here and in `VALID_AGENT_COLORS`.
- Pool updated via Evolve (aspect: `agent-frontmatter` + `shared-rules`).
- A colour outside the pool is a hire-time error, not a style preference.
