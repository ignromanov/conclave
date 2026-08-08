---
name: conclave-${ID}
description: ${DESCRIPTION}
---

You are being invoked as the **${ID}** advisor.

Immediately begin the mandatory Conclave session by entering the `/conclave:start`
lifecycle bound to advisor **${ID}** — pass `--advisor ${ID}` to session-init:

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-.}"   # installed plugin → plugin dir; in-place engine checkout → cwd
PYTHONPATH="$ROOT/engine/scripts" python3 "$ROOT/engine/scripts/lifecycle/session_init.py" --advisor ${ID}
```

Then follow the full `/conclave:start` protocol as advisor `${ID}`.
