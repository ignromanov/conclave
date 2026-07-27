"""enginelib.roster — the deontic duty registry (spec 091).

Roles ⨉ missions ⨉ norms, composed from an engine-owned base plus each agent's self-written
duties, projected into a compact COMPUTED-DUTIES.md list.

I/O-free by contract (the 099 split): no stdout, no argparse, no sys.exit. The adapter in
engine/cmd/duty.py owns the process contract.
"""
