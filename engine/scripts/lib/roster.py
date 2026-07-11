#!/usr/bin/env python3
"""lib/roster.py — thin re-export shim; retained — consumed by lifecycle/gh_board_query.py.

Consumers:
  - lib/roster.sh  runs `python3 lib/roster.py <key>` (CLI via main())
  - lifecycle/gh_board_query.py does `import roster; roster.get(...)`

The real parser lives in enginelib/roster.py (I/O-free).
"""
import os
import sys

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
