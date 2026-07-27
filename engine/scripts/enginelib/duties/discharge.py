"""discharge.py — the /conclave:done discharge check (spec 091 §4).

At session end, answer one question: of the obligations in force for this agent, which were
addressed this session and which were not.

Three deliberate boundaries:

  - **Only obligations.** `permission` is a may and `advice` is a should; neither is owed.
    A check that demanded them would mark every session delinquent, and a signal that always
    fires is a signal nobody reads.
  - **Only this session.** An obligation discharged last session is owed again. Carrying
    credit forward would let one discharge satisfy an obligation forever.
  - **It reports, it does not decide.** A deferred obligation is a normal outcome that must
    be visible, not an error to suppress. And `condition` is prose the LLM evaluates in
    context (research §E) — so a conditional obligation with no ledger entry is surfaced as
    UNEVALUATED rather than guessed at in either direction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from enginelib.duties.ledger import read_entries
from enginelib.duties.model import Manifest
from enginelib.duties.validate import compose


@dataclass
class DischargeResult:
    agent_id: str
    session_id: str
    discharged: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    condition_unmet: list[str] = field(default_factory=list)
    unevaluated: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """Nothing owed. `unevaluated` counts as owed: the agent still has to answer it."""
        return not self.deferred and not self.unevaluated


def check_discharge(
    base: Manifest,
    agent_manifest: Manifest,
    agent_id: str,
    agent_dir: Path,
    *,
    session_id: str,
) -> DischargeResult:
    composed = compose([base, agent_manifest])
    obligations = [n for n in composed.for_role(agent_id) if n.type == "obligation"]

    this_session = {
        e.duty_id: e.outcome
        for e in read_entries(agent_dir)
        if e.session_id == session_id
    }

    result = DischargeResult(agent_id=agent_id, session_id=session_id)
    for norm in obligations:
        outcome = this_session.get(norm.mission)
        if outcome == "discharged":
            result.discharged.append(norm.mission)
        elif outcome == "condition-unmet":
            # The condition did not hold, so nothing was owed. Reporting this as deferred
            # would manufacture a debt out of a norm that never activated.
            result.condition_unmet.append(norm.mission)
        elif outcome is None and norm.condition:
            result.unevaluated.append(norm.mission)
        else:
            # No entry on an unconditional obligation, or an entry saying errored / skipped
            # / deferred. Attempting is not discharging.
            result.deferred.append(norm.mission)

    return result
