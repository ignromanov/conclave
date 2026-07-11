#!/usr/bin/env python3
"""Conclave SessionStart hook — idempotent verify/repair + dashboard inject.

Registered DATA-side by /conclave.init into the consumer .claude/settings.json with a
resolved path (098 F-001). The engine root comes from CONCLAVE_ENGINE_ROOT (persisted
by init); the hook must not depend on the plugin-root interpolation variable, which is
empty at SessionStart (CC #27145 / #39550).
"""
import os, sys, pathlib

data = pathlib.Path(os.environ.get("CONCLAVE_AI_ROOT")
    or os.path.join(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()), ".conclave"))
if not data.exists():
    print("Conclave not initialized here — run `/conclave:init`")   # nudge only, no scaffold
    sys.exit(0)

# verify/repair: add missing dirs idempotently (never create the whole tree from scratch)
for sub in ["agent-memory/advisors/briefings", "agent-memory/advisors/sessions",
            "ops/specs", "ops/handoffs"]:
    (data / sub).mkdir(parents=True, exist_ok=True)

# dashboard: add the engine scripts package to sys.path and render via session_init.
engine = os.environ.get("CONCLAVE_ENGINE_ROOT", "")
sys.path.insert(0, os.path.join(engine, "scripts"))
try:
    from lifecycle import session_init           # render_dashboard added in D-5b
    print(session_init.render_dashboard(data))   # advisor-agnostic: briefing/resume/reflexion/cadence/roster
except Exception as e:
    print(f"Conclave dashboard unavailable ({e}); run `/conclave:start` manually.")
