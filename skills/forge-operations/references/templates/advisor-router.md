---
name: conclave-${ID}
description: |
  Advisory session with the ${ID} advisor. Routes into the mandatory Conclave
  session lifecycle (/conclave:start) bound to ${ID}.
  Triggers: /conclave-${ID}, "session with ${ID}", "ask ${ID}".
---

You are being invoked as the **${ID}** advisor.

Immediately begin the mandatory Conclave session by entering the `/conclave:start`
lifecycle bound to advisor **${ID}** — pass `--advisor ${ID}` to session-init:

```bash
ROOT="${CLAUDE_PLUGIN_ROOT:-.}"   # installed plugin → plugin dir; in-place engine checkout → cwd
PYTHONPATH="$ROOT/engine/scripts" python3 "$ROOT/engine/scripts/lifecycle/session_init.py" --advisor ${ID}
```

Then follow the full `/conclave:start` protocol as advisor `${ID}`.
