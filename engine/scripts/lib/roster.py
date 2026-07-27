#!/usr/bin/env python3
"""lib/roster.py — thin re-export shim; retained — consumed by lifecycle/gh_board_query.py.

Consumers:
  - lib/roster.sh  runs `python3 lib/roster.py <key>` (CLI via main())
  - lifecycle/gh_board_query.py does `import roster; roster.get(...)`

The real parser lives in enginelib/roster.py (I/O-free).
"""
import os
import sys

# Interpreter floor, enforced before the first thing that can fail below it — here,
# `enginelib.roster` and its `ruamel` dependency, which a sub-floor interpreter reports as
# `ModuleNotFoundError: ruamel`, naming neither Python nor a version. /conclave:start,
# github-issues-protocol.md and lib/roster.sh all launch this file directly.
# Inert when imported by gh_board_query.py, which carries the same guard.
# Measured, not declared; see engine/__main__.py for the full note.
if sys.version_info < (3, 11):  # noqa: UP036 — see engine/__main__.py
    sys.stderr.write(
        f"Conclave requires Python 3.11 or newer.\n"
        f"This is Python {sys.version.split()[0]} at {sys.executable}.\n"
        f"Install a newer interpreter (e.g. `uv python install 3.13`) and re-run.\n"
    )
    sys.exit(1)

# enginelib lives one level up from lib/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from enginelib.roster import roster_get  # noqa: E402

# Expose the name the existing consumer (gh_board_query.py) uses.
get = roster_get


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: roster.py <dotted.key>", file=sys.stderr)
        return 2
    val = get(sys.argv[1])
    if val != "":
        print(val)
    return 0


if __name__ == "__main__":
    sys.exit(main())
