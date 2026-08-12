---
stages: [implement, verify]
tiers: [work]
task_types: [dev]
binding: required
last_reviewed: "2026-08-12"
---

# Aspect: Engine Scripts

Modify the Python engine under `engine/scripts/` — the `engine <noun> <verb>` CLI (argparse adapters in
`engine/cmd/`) over the I/O-free `enginelib/` core.

## Required model

- **enginelib-first:** put logic in an I/O-free `enginelib/<name>.py` core (no stdout, no CLI parsing, no
  process exit — file/subprocess/clock are fine). Adapters in `engine/cmd/<noun>.py` own argparse/print/
  exit and stay thin (≤ ~30 lines: marshal args → call the core → format + exit code).
- Register the verb in `engine/__main__.py`; preserve the single run-log hook site.

## Testing gate

All changes must:
- Pass `uv run ruff check` clean
- Pass `uv run mypy enginelib engine` clean
- Pass `uv run pytest` (existing + new tests for the change; keep behavior 1:1 when porting)
- Keep the `enginelib` core I/O-free (enforced by the AST gate in `tests/test_gates.py`)

## Commit convention

`feat(engine): <noun> <change>` or `fix(engine): <noun> <bugfix>`
