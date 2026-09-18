"""enginelib.checkpoint — the in-flight session record (spec 117).

The half of the session lifecycle that is written *while* the session runs: one file per
session under `paths.checkpoints_dir()`, one line per event, folded into the session record
at close. `sessions/` is what a session left behind; this is what it is doing.

Named for the verb (`engine session checkpoint`) rather than for the concept, deliberately.
The concept's word is "ledger" and it is already taken: `enginelib/duties/ledger.py` is spec
091's per-session duty ledger — also only ever extended, also one entry per act, also
session-scoped. Two subsystems both called `ledger` would make every grep for one return the
other, and the two are unrelated. The design's §1 rule — a grep for the stage finds the verb —
settles it. (The phrasing avoids the two words `duties/ledger.py` itself avoids: they are one of
`evals/fixture.py`'s charter norm patterns, and a `.py` hit is a source-side reword by design.)

I/O-free by contract (the 099 split): no stdout, no argparse, no sys.exit. `record.py` is
purer still and touches no filesystem at all; the file handling lives in the adapter.
"""
