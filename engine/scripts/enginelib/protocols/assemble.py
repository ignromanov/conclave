"""assemble.py — select and order protocols for one session (spec 108 §6).

OR within an axis, AND across axes — the semantics every surveyed selection system
(Kubernetes, ESLint) uses; none uses cross-axis OR. Deduplication is structural: a file
cannot enter the assembled context twice, which is what makes the measured 93,000 bytes
of duplication impossible by construction rather than by discipline.
"""
from __future__ import annotations

from enginelib.protocols.model import ProtocolFile


def select(files: list[ProtocolFile], tier: str, task_type: str) -> list[ProtocolFile]:
    seen: set = set()
    chosen: list[ProtocolFile] = []
    for f in files:
        if tier not in f.meta.tiers:
            continue
        if task_type not in f.meta.task_types:
            continue
        key = f.path.resolve() if f.path.exists() else f.path
        if key in seen:
            continue
        seen.add(key)
        chosen.append(f)
    chosen.sort(key=lambda p: (p.meta.earliest_stage_index(), str(p.path)))
    return chosen
