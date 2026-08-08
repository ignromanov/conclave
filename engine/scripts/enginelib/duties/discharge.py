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

from enginelib.duties.derive import derive, load_duties
from enginelib.duties.ledger import read_entries
from enginelib.duties.model import AgentKind, Manifest
from enginelib.duties.validate import compose


@dataclass
class DischargeResult:
    agent_id: str
    session_id: str
    discharged: list[str] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    condition_unmet: list[str] = field(default_factory=list)
    unevaluated: list[str] = field(default_factory=list)
    norms_in_force: int = 0
    """How many obligations were checked. The denominator: without it, `0 deferred` reads the
    same whether the agent owed nothing or owed everything and did it all."""

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
    duties_dir: Path | None = None,
    kind: AgentKind = "advisor",
) -> DischargeResult:
    """`duties_dir` is what makes a written duty reachable here at all: the agent's own
    duties derive advice norms, which an operator norm can then elevate to an obligation.
    Omit it and only the manifests are in play — the pre-P2 behaviour, kept so callers that
    genuinely have no duty files (the unit tests below) need not invent one."""
    duties = load_duties(duties_dir)
    composed = compose([base, agent_manifest, derive(duties, agent_id, kind)])
    obligations = [n for n in composed.for_role(agent_id) if n.type == "obligation"]

    this_session = {
        e.duty_id: e.outcome
        for e in read_entries(agent_dir)
        if e.session_id == session_id
    }

    result = DischargeResult(agent_id=agent_id, session_id=session_id,
                             norms_in_force=len(obligations))
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
