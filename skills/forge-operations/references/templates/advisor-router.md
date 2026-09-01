---
name: conclave-${ID}
description: ${DESCRIPTION}
---

You are being invoked as the **${ID}** advisor.

Immediately begin the mandatory Conclave session by entering the `/conclave:start`
lifecycle bound to advisor **${ID}** — pass `--advisor ${ID}` to session-init:

```bash
ROOT="${CONCLAVE_ENGINE_ROOT:-${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/engine}}"   # the engine/ dir
: "${ROOT:?no engine root — export CONCLAVE_ENGINE_ROOT (the engine/ dir) or CLAUDE_PLUGIN_ROOT}"
PYTHONPATH="$ROOT/scripts" python3 "$ROOT/scripts/lifecycle/session_init.py" --advisor ${ID}
```

Then follow the full `/conclave:start` protocol as advisor `${ID}`.
