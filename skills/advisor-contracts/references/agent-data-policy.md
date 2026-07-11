---
contract: agent-data-policy
version: 2.0.0
appliers: [team.quorum, all advisors]
propagation: hire-template
---

# Agent Data Policy

> **Purpose**: Where data lives and how agents read/write it.
> **Approved**: 2026-03-17 (Meeting #6). **v2.0** 2026-05-22 — spec 085: stripped
> sections obsoleted by spec 051 (auto-generated briefings) and spec 074
> (foundations + domain knowledge migrated to the wiki).

---

## Where data lives

| Data | Home | Access |
|------|------|--------|
| Dev tasks, bugs, features, strategy, grants, ops | GitHub Issues (both repos) | per `github-issues-protocol.md` |
| Advisor briefings | `agent-memory/advisors/briefings/<id>.md` | **auto-generated** by `briefing-build.sh` — read-only, never hand-edited (spec 051) |
| Sessions / decisions / mentions | `agent-memory/advisors/{sessions,decisions,mentions}/` | written only via `engine session close` / `engine file decision` / `engine mention create` |
| Cross-agent live state | `agent-memory/hot.md` | `hot-md-append.sh` / `wiki-hot-sync.sh` |
| Architecture registries | `.ai/architecture/*.md` | code-coupled — edited directly after code changes |
| Process artifacts | `.ai/ops/` (specs, meetings, decisions, handoffs) | edited directly |
| Domain knowledge (architecture trade-offs, strategy, security findings, competitive analysis) | **wiki** (the knowledge wiki, `knowledge.wiki_path` in roster.yaml) | `/wiki:capture`, `/wiki:browse`, `/wiki:query` |

**Rule**: domain knowledge belongs in the wiki, not `.ai/`. `.ai/` holds only process
artifacts + code-coupled architecture registries. Writing research / strategy / security
narratives into `.ai/` is an anti-pattern (see CLAUDE.md).

---

## `.ai/` Repository Privacy

`.ai/` (the private ops repo, `github.ai_repo` in roster.yaml) is a **private**
repository. Strategic, competitive, and grant information can live here safely.

**Never in `.ai/` (regardless of repo visibility)**:
- API keys, RPC endpoint URLs with auth tokens, private keys
- Exploit PoC code, decompression bomb payloads
- Bypass technique details → use GitHub Security Advisories (GHSA)
- PII (wallet addresses linked to real identities)

---

## Architecture Staleness Detection

Every file in `.ai/architecture/` carries a header on line 3:

```markdown
> **Last updated**: YYYY-MM-DD — [what changed]
```

After code changes, the validation workflow checks:
- Component added/removed → `ui-index.md` update required
- Slice added/removed → `fsd-registry.md` update required
- Store added/modified → `data-flow.md` update required

Flag if an architecture file's `Last updated` is older than the current commit.
Non-blocking, but visible in the `/conclave:done` checklist (item 5).

---

## INDEX.md Convention

Every top-level `.ai/` directory has an `INDEX.md`:
- Adding a file → update INDEX.md. Removing a file → update INDEX.md.
- INDEX.md = lightweight table of contents, not documentation.
- The owner of the directory owns its INDEX.md.

---

## KB Updates routing (post-meeting)

After writing meeting minutes, Quorum appends a `## KB Updates Required` section
tagging the responsible advisor:

```markdown
## KB Updates Required
- [ ] architecture/data-flow.md — [decision summary] ← @kai
- [ ] wiki: strategy/positioning — [decision summary] ← @nexus
```

On the next session, the tagged advisor executes the update — architecture registries
directly, domain knowledge via `/wiki:capture`. Ignat confirms via commit.
