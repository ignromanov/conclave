"""status/ — the canonical state projection (GH#57) and its arithmetic.

I/O-free by contract: the model and the reduction live here, the gathering lives in
the adapters (briefing scans, gh cache, git). Spec 115 rule 11 — one model, three
printers; nothing in this package knows about any of them.
"""
