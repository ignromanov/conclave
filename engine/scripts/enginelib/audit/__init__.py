"""enginelib/audit — audit modules. Findings dataclass shared by all sibling audits."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Findings:
    crit: list[str] = field(default_factory=list)
    warn: list[str] = field(default_factory=list)
