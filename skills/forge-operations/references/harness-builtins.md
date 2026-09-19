---
kind: harness-builtins
version: 1.0.0
last_measured: "2026-09-19"
harness: "Claude Code 2.1.278"
---

# Harness built-in skills

Skills the harness provides with **no SKILL.md anywhere on disk**. They are compiled into the
Claude Code binary, listed in the session, and invocable via the Skill tool all the same.

`enginelib.skill.classify` reads this file. A name listed here is `BUILTIN`, not `PHANTOM`:
`engine skill verify` stops exiting non-zero over it, and `engine audit phantom-skills`
(Cat 12, BLOCKING) stops flagging an advisor that lists it in a Toolbox.

Before this file existed, `verify()` searched five on-disk roots and its callers printed the
resulting `None` as "phantom skill" — a claim about the world made from a search of one
filesystem. The cost was not noise. An advisor on the reference instance deleted a working
entry from its own toolbox and wrote the reason down (#168):

> `dataviz` is deliberately **not** listed: it is a harness-builtin and `engine skill verify`
> reports it PHANTOM, which would fail audit Cat 12 on every run.

## Harness built-ins

- `artifact-components`
- `batch`
- `claude-in-chrome`
- `debug`
- `design-sync`
- `doctor`
- `explain-usage`
- `fewer-permission-prompts`
- `keybindings-help`
- `run`
- `run-skill-generator`
- `setup-claude`
- `update-config`

Only entries under that heading count. Prose may say anything; a name becomes declared by
appearing in that one list, exactly as `skill-sources.md` works for the install allowlist.

## Why this list is declared and not discovered

There is no session skill listing reachable from a process — not in `~/.claude/`, not in
`settings.json`. The names live only inside the CLI binary, and the only structural handle
there is a **minified identifier renamed on essentially every build**:

| Installed binary | Registration spelling | a scan keyed on `Do({name:` reads |
|---|---|---|
| 2.1.270 | `_o({name:"keybindings-help"` | 0 built-ins |
| 2.1.273 | `Po({name:"keybindings-help"` | 0 built-ins |
| 2.1.277 | `Do({name:"keybindings-help"` | 14 built-ins |
| 2.1.278 | `Do({name:"keybindings-help"` | 14 built-ins |

Four builds in four days, three distinct spellings. A scraper keyed on today's spelling reads
fourteen built-ins now and **zero** on last week's binary — and zero means every built-in
silently becomes a phantom again: this defect, rebuilt with a longer fuse.

Deriving the identifier from a known anchor instead of hardcoding it does work, and the command
below does exactly that. It is still not what `classify` runs, for two measured reasons:

1. **Cost.** `strings` over a 226 MB binary is ~1.6 s warm and ~8 s cold. `audit phantom-skills`
   resolves one reference at a time across every advisor-authored file; `skill verify` runs
   inside a blocking hire gate. Caching that is a cache-invalidation problem bought to avoid
   maintaining thirteen lines.
2. **Locating the binary at all.** `~/.local/bin/claude` is one install layout among several
   (npm global, homebrew, a cmux shim that re-execs the real one). A resolver that guesses wrong
   returns the empty set, which is the failure mode in the table above.

The set itself is stable: all four binaries above yield the **same fourteen names** under the
derived scan. What moves is the spelling, not the inventory — which is what makes a declared
list cheap to keep and a spelling-keyed scraper expensive to trust.

## Re-measuring it

Derive the identifier from a name known to be a built-in, then enumerate everything registered
through it:

```
BIN=$(readlink -f ~/.local/bin/claude)
FN=$(/usr/bin/strings -a "$BIN" \
  | /usr/bin/grep -o '[A-Za-z_$][A-Za-z0-9_$]*({name:"keybindings-help"' \
  | sed 's/({name:.*//' | head -1)
test -n "$FN" || echo "ANCHOR LOST — do not read this as an empty list"
/usr/bin/strings -a "$BIN" | /usr/bin/grep -o "$FN"'({name:"[a-z0-9-]*"' \
  | sed 's/.*name:"//;s/"//' | sort -u
```

Verified identical output on 2.1.270, 2.1.273, 2.1.277 and 2.1.278 (`_o`, `Po`, `Do`, `Do`).

Do **not** widen the pattern to any `({name:` — tools and slash-commands register through their
own wrappers, and the wide form returns 28 names including `bash`, `read`, `write` and `grep`.
Grouping by the one registration function is the whole point.

If `FN` comes back empty the shape has moved again. **A zero result is not an empty list** — it
is a broken instrument, and reporting it as a list is the same error one layer up
(`advisor-anti-patterns.md` item 9, "absence is a claim about an instrument").

Update `last_measured` and `harness` in the frontmatter when you re-run this.

## What is deliberately absent

`claude-api` is registered by the harness **and** ships as a plugin-cache skill
(`anthropic-agent-skills/document-skills/.../skills/claude-api/SKILL.md`). It resolves on disk,
so it needs no exemption, and
`tests/test_a_builtin_is_not_a_phantom.py::test_no_declared_builtin_resolves_on_disk` fails if
it — or any other row here — acquires a file. A skill with a file is `OK`, never `BUILTIN`:
a declaration must never shadow the real path a caller asked for.

## What this list cannot tell you

Nothing on disk reveals a **new** built-in. The next harness update ships one and no gate here
will notice; the list simply goes quiet and that skill is a phantom again until someone re-runs
the command above. That is the honest limit of a hand-kept list, stated rather than hidden —
and the reason `last_measured` is a field and not a comment.
