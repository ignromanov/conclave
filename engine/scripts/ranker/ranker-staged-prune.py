"""ranker-staged-prune.py — orchestrate 3-stage ranking + write rank-*.yaml (spec 089 P6).

Stages:
  0  diversity guard   (ranker-dedup.py, mandatory — D20/AC10)
  1  ORM prune        fast AC-binary checklist; keep orm_score >= ORM_PRUNE_THRESHOLD
  2  PRM step-scoring  ranker-prm-harness.py; weighted-mean aggregate per candidate
  3  oracle gate       code→exec.iris-test ref; prose→deterministic scripts; long-chain→PRM-traj

Writes: <output-dir>/rank-<task-slug>-<YYYYMMDD-HHMMSS>.yaml

CLI:
    python ranker-staged-prune.py
        --task-slug <str>
        --ac-contract-ref <path>
        --domain code|prose|long-chain
        --candidates-json <path>      # [{id, generator, artifact_path, text}]
        --cost-ceiling <int>          # tokens; 2× single-generation estimate
        [--output-dir artifacts/]
        [--orm-threshold 0.50]
        [--diversity-threshold 0.85]
        [--prm-finalist-gap 0.15]

Output YAML schema (R6 I/O spec, field-for-field):
    schema_version, task_slug, ac_contract_ref, domain, n_candidates,
    diversity_guard{triggered, similarity_max},
    candidates[]{id, generator, orm_score, orm_pruned,
      prm_step_scores[]{step_id, step_label, score, ac_criterion},
      prm_aggregate, oracle_pass, oracle_blockers[], oracle_warnings[],
      final_rank, selected, selection_rationale},
    selected_id, status(ok|escalate|cost_gate_triggered),
    cost_tokens_used, cost_ceiling
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Pydantic output schema — field-for-field per R6 I/O spec
# ---------------------------------------------------------------------------

class PrmStepScore(BaseModel):
    step_id: str
    step_label: str
    score: float = Field(ge=0.0, le=1.0)
    ac_criterion: str


class CandidateResult(BaseModel):
    id: str
    generator: str
    orm_score: float = Field(ge=0.0, le=1.0)
    orm_pruned: bool
    prm_step_scores: list[PrmStepScore] = Field(default_factory=list)
    prm_aggregate: float = Field(ge=0.0, le=1.0, default=0.0)
    oracle_pass: bool = False
    oracle_blockers: list[str] = Field(default_factory=list)
    oracle_warnings: list[str] = Field(default_factory=list)
    final_rank: int | None = None
    selected: bool = False
    selection_rationale: str = ""


class DiversityGuard(BaseModel):
    triggered: bool
    similarity_max: float


class RankOutput(BaseModel):
    schema_version: int = 1
    task_slug: str
    ac_contract_ref: str
    domain: Literal["code", "prose", "long-chain"]
    n_candidates: int
    diversity_guard: DiversityGuard
    candidates: list[CandidateResult]
    selected_id: str
    status: Literal["ok", "escalate", "cost_gate_triggered"]
    cost_tokens_used: int
    cost_ceiling: int


# ---------------------------------------------------------------------------
# Dynamic sibling-script loader
# ---------------------------------------------------------------------------

_SCRIPTS_DIR = Path(__file__).resolve().parent


def _load_sibling(name: str, filename: str) -> Any:
    """Load a sibling .py script from the same directory as this file."""
    path = _SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


# ---------------------------------------------------------------------------
# ORM score (Stage 1)
# ---------------------------------------------------------------------------

def _orm_score(candidate: dict[str, Any], ac_text: str) -> float:
    """Heuristic ORM score vs AC binary criteria — deterministic, no LLM calls.

    Three equal-weight checks:
      1. Non-trivial content length (>= 50 chars)
      2. No explicit blocker markers (TODO / FIXME / placeholder)
      3. AC-keyword presence (up to 5 phrases from the contract list items)

    In production a single-pass Sonnet call adds LLM scoring on top of this floor.
    Returns score in [0.0, 1.0].
    """
    text = candidate.get("text", "")
    if not text.strip():
        return 0.0

    checks = 3
    score = 0.0

    # 1. Length
    score += 1.0 if len(text) >= 50 else 0.0

    # 2. No blockers
    blockers = ["todo", "fixme", "not implemented", "placeholder"]
    score += 0.0 if any(b in text.lower() for b in blockers) else 1.0

    # 3. AC-keyword presence
    ac_keywords: list[str] = []
    for line in ac_text.splitlines():
        stripped = line.strip().lstrip("-").strip()
        if stripped and len(stripped) > 5:
            ac_keywords.append(" ".join(stripped.split()[:4]).lower())
        if len(ac_keywords) >= 5:
            break

    if ac_keywords:
        body_lower = text.lower()
        matched = sum(1 for kw in ac_keywords if kw in body_lower)
        score += matched / len(ac_keywords)
    else:
        score += 0.5

    return round(score / checks, 4)


# ---------------------------------------------------------------------------
# Oracle gate helpers (Stage 3)
# ---------------------------------------------------------------------------

def _oracle_gate_prose(
    candidate: dict[str, Any],
    ac_text: str,
) -> tuple[bool, list[str], list[str]]:
    """Deterministic oracle for prose: section presence + citation check + AC-grep."""
    text = candidate.get("text", "")
    blockers: list[str] = []
    warnings: list[str] = []

    if not text.strip():
        blockers.append("empty artifact")
        return False, blockers, warnings

    # Section presence
    headers = [ln.strip() for ln in text.splitlines() if ln.strip().startswith("#")]
    if not headers:
        warnings.append("no section headers found — structure unclear")

    # Citation markers
    has_citations = any(
        m in text
        for m in ["[", "(20", "(19", "et al", "doi:", "arXiv", "http"]
    )
    if not has_citations:
        warnings.append("no citations detected — factual claims may be unverifiable")

    # AC-grep: top-3 AC criteria phrases present?
    ac_lines = []
    for line in ac_text.splitlines():
        stripped = line.strip().lstrip("-").strip()
        if stripped and len(stripped) > 10:
            ac_lines.append(stripped)
        if len(ac_lines) >= 3:
            break

    for ac_line in ac_lines:
        key = ac_line[:30].lower()
        if key and key not in text.lower():
            warnings.append(f"AC criterion may be unaddressed: '{ac_line[:40]}'")

    return len(blockers) == 0, blockers, warnings


def _oracle_gate_long_chain(
    prm_step_scores: list[PrmStepScore],
) -> tuple[bool, list[str], list[str]]:
    """PRM-trajectory gate for long-chain: aggregate floor + critical-step check."""
    blockers: list[str] = []
    warnings: list[str] = []

    if not prm_step_scores:
        blockers.append("no PRM step scores for trajectory gate")
        return False, blockers, warnings

    aggregate = sum(s.score for s in prm_step_scores) / len(prm_step_scores)
    if aggregate < 0.40:
        blockers.append(f"PRM aggregate {aggregate:.3f} below floor 0.40")

    critical = [s for s in prm_step_scores if s.score < 0.20]
    if critical:
        warnings.append(
            f"critically low PRM steps: {', '.join(s.step_label for s in critical)}"
        )

    return len(blockers) == 0, blockers, warnings


# ---------------------------------------------------------------------------
# Cost-gate degraded output
# ---------------------------------------------------------------------------

def _cost_gate_output(
    task_slug: str,
    ac_contract_ref: str,
    domain: str,
    candidates_raw: list[dict[str, Any]],
    diversity_guard: DiversityGuard,
    tokens_used: int,
    cost_ceiling: int,
    partial_results: list[CandidateResult] | None = None,
) -> RankOutput:
    """Return a cost_gate_triggered RankOutput — degrade to top-1 ORM selection."""
    print(
        f"WARN cost_gate_triggered: tokens_used={tokens_used} >= ceiling={cost_ceiling}",
        file=sys.stderr,
    )
    results = partial_results or [
        CandidateResult(
            id=c["id"],
            generator=c.get("generator", "unknown"),
            orm_score=0.0,
            orm_pruned=False,
        )
        for c in candidates_raw
    ]

    non_pruned = [r for r in results if not r.orm_pruned]
    selected_id = ""
    if non_pruned:
        best = max(non_pruned, key=lambda r: r.orm_score)
        best.selected = True
        best.selection_rationale = "cost_gate degraded: top-1 ORM"
        selected_id = best.id

    return RankOutput(
        schema_version=1,
        task_slug=task_slug,
        ac_contract_ref=ac_contract_ref,
        domain=domain,  # type: ignore[arg-type]
        n_candidates=len(candidates_raw),
        diversity_guard=diversity_guard,
        candidates=results,
        selected_id=selected_id,
        status="cost_gate_triggered",
        cost_tokens_used=tokens_used,
        cost_ceiling=cost_ceiling,
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(
    task_slug: str,
    ac_contract_ref: str,
    domain: str,
    candidates_raw: list[dict[str, Any]],
    cost_ceiling: int,
    orm_threshold: float = 0.50,
    diversity_threshold: float = 0.85,
    prm_finalist_gap: float = 0.15,
) -> RankOutput:
    """Execute the 3-stage ranking pipeline. Returns a RankOutput pydantic model."""

    dedup_mod = _load_sibling("ranker_dedup", "ranker-dedup.py")
    prm_mod = _load_sibling("ranker_prm_harness", "ranker-prm-harness.py")
    cost_mod = _load_sibling("ranker_cost_meter", "ranker-cost-meter.py")

    meter = cost_mod.CostMeter(ceiling=cost_ceiling)

    ac_path = Path(ac_contract_ref)
    ac_text = ac_path.read_text(encoding="utf-8") if ac_path.exists() else ""
    if not ac_text:
        print(f"WARN: ac_contract_ref empty or not found: {ac_contract_ref}", file=sys.stderr)

    # -------------------------------------------------------------------
    # Stage 0 — diversity guard (mandatory)
    # -------------------------------------------------------------------
    dedup_input = [{"id": c["id"], "text": c.get("text", "")} for c in candidates_raw]
    dedup_result = dedup_mod.run(dedup_input, threshold=diversity_threshold)

    diversity_guard = DiversityGuard(
        triggered=dedup_result["diversity_collapse"],
        similarity_max=dedup_result["similarity_max"],
    )

    diverse_ids: set[str] = set(dedup_result["diverse_subset_ids"])
    active_candidates = [c for c in candidates_raw if c["id"] in diverse_ids]

    meter.record(stage="stage0_dedup", tokens=len(candidates_raw) * 10)
    if meter.ceiling_breached():
        return _cost_gate_output(task_slug, ac_contract_ref, domain, candidates_raw,
                                 diversity_guard, meter.total_tokens, cost_ceiling)

    # -------------------------------------------------------------------
    # Stage 1 — ORM prune
    # -------------------------------------------------------------------
    candidate_results: list[CandidateResult] = []

    for cand in active_candidates:
        orm = _orm_score(cand, ac_text)
        candidate_results.append(CandidateResult(
            id=cand["id"],
            generator=cand.get("generator", "unknown"),
            orm_score=orm,
            orm_pruned=orm < orm_threshold,
        ))

    survivors = [r for r in candidate_results if not r.orm_pruned]

    # orm_floor_bypass: never return an empty survivor set
    if not survivors:
        top = max(candidate_results, key=lambda r: r.orm_score)
        top.orm_pruned = False
        top.oracle_warnings.append(
            "orm_floor_bypass: promoted top-1 despite below-threshold ORM score"
        )
        survivors = [top]
        print("WARN orm_floor_bypass: all candidates pruned; promoted top-1", file=sys.stderr)

    # Candidates removed by diversity guard — mark as pruned
    pruned_by_dedup = {c["id"] for c in candidates_raw} - {c["id"] for c in active_candidates}
    for cid in pruned_by_dedup:
        orig = next((c for c in candidates_raw if c["id"] == cid), {})
        candidate_results.append(CandidateResult(
            id=cid,
            generator=orig.get("generator", "unknown"),
            orm_score=0.0,
            orm_pruned=True,
            oracle_warnings=["pruned by Stage 0 diversity guard"],
        ))

    meter.record(stage="stage1_orm", tokens=len(active_candidates) * 50)
    if meter.ceiling_breached():
        return _cost_gate_output(task_slug, ac_contract_ref, domain, candidates_raw,
                                 diversity_guard, meter.total_tokens, cost_ceiling,
                                 partial_results=candidate_results)

    # -------------------------------------------------------------------
    # Stage 2 — PRM step-scoring on survivors
    # -------------------------------------------------------------------
    for cand_result in survivors:
        raw_cand = next((c for c in candidates_raw if c["id"] == cand_result.id), {})
        raw_steps = prm_mod.score_steps(
            artifact_text=raw_cand.get("text", ""),
            domain=domain,
            ac_text=ac_text,
        )
        cand_result.prm_step_scores = [PrmStepScore(**s) for s in raw_steps]
        if cand_result.prm_step_scores:
            cand_result.prm_aggregate = round(
                sum(s.score for s in cand_result.prm_step_scores)
                / len(cand_result.prm_step_scores),
                4,
            )
        meter.record(
            stage=f"stage2_prm_{cand_result.id}",
            tokens=len(raw_cand.get("text", "")) // 4 + 100,
        )
        if meter.ceiling_breached():
            return _cost_gate_output(task_slug, ac_contract_ref, domain, candidates_raw,
                                     diversity_guard, meter.total_tokens, cost_ceiling,
                                     partial_results=candidate_results)

    # Top-K finalists by PRM aggregate (K = min(2, survivors))
    K = min(2, len(survivors))
    finalists = sorted(survivors, key=lambda r: r.prm_aggregate, reverse=True)[:K]

    # -------------------------------------------------------------------
    # Stage 3 — oracle/deterministic gate on finalists
    # -------------------------------------------------------------------
    for cand_result in finalists:
        raw_cand = next((c for c in candidates_raw if c["id"] == cand_result.id), {})

        if domain == "code":
            # Code oracle = exec.iris-test (p6-floor sub-phase).
            # Ranker references but does NOT reimplement the 4+1 pipeline inline.
            # The orchestrator dispatches exec.iris-test as a separate p6-floor step.
            # Here we note the oracle dependency; oracle_pass is provisional (True).
            cand_result.oracle_pass = True
            cand_result.oracle_warnings.append(
                "code domain: exec.iris-test is the authoritative oracle — "
                "dispatched by orchestrator as p6-floor (after this ranker run)"
            )

        elif domain == "prose":
            ok, blockers, warnings = _oracle_gate_prose(raw_cand, ac_text)
            cand_result.oracle_pass = ok
            cand_result.oracle_blockers = blockers
            cand_result.oracle_warnings.extend(warnings)

        elif domain == "long-chain":
            ok, blockers, warnings = _oracle_gate_long_chain(cand_result.prm_step_scores)
            cand_result.oracle_pass = ok
            cand_result.oracle_blockers = blockers
            cand_result.oracle_warnings.extend(warnings)

        meter.record(
            stage=f"stage3_oracle_{cand_result.id}",
            tokens=len(raw_cand.get("text", "")) // 4 + 200,
        )
        if meter.ceiling_breached():
            return _cost_gate_output(task_slug, ac_contract_ref, domain, candidates_raw,
                                     diversity_guard, meter.total_tokens, cost_ceiling,
                                     partial_results=candidate_results)

    # -------------------------------------------------------------------
    # Selection
    # -------------------------------------------------------------------
    passing = [r for r in finalists if r.oracle_pass]

    if not passing:
        _assign_ranks(finalists)
        return RankOutput(
            schema_version=1,
            task_slug=task_slug,
            ac_contract_ref=ac_contract_ref,
            domain=domain,  # type: ignore[arg-type]
            n_candidates=len(candidates_raw),
            diversity_guard=diversity_guard,
            candidates=candidate_results,
            selected_id="",
            status="escalate",
            cost_tokens_used=meter.total_tokens,
            cost_ceiling=cost_ceiling,
        )

    best = max(passing, key=lambda r: r.prm_aggregate)
    if len(passing) > 1:
        others = sorted(passing, key=lambda r: r.prm_aggregate, reverse=True)
        gap = best.prm_aggregate - others[1].prm_aggregate
        best.selection_rationale = (
            f"max PRM aggregate {best.prm_aggregate:.4f} among oracle-passing finalists "
            f"(gap={gap:.4f} vs next)"
        )
    else:
        best.selection_rationale = (
            f"sole oracle-passing finalist; PRM aggregate {best.prm_aggregate:.4f}"
        )
    best.selected = True
    _assign_ranks(finalists)

    return RankOutput(
        schema_version=1,
        task_slug=task_slug,
        ac_contract_ref=ac_contract_ref,
        domain=domain,  # type: ignore[arg-type]
        n_candidates=len(candidates_raw),
        diversity_guard=diversity_guard,
        candidates=candidate_results,
        selected_id=best.id,
        status="ok",
        cost_tokens_used=meter.total_tokens,
        cost_ceiling=cost_ceiling,
    )


def _assign_ranks(finalists: list[CandidateResult]) -> None:
    """Assign final_rank to finalists sorted by PRM aggregate descending."""
    for rank, result in enumerate(
        sorted(finalists, key=lambda r: r.prm_aggregate, reverse=True), start=1
    ):
        result.final_rank = rank


# ---------------------------------------------------------------------------
# YAML serialization
# ---------------------------------------------------------------------------

def _write_rank_yaml(output: RankOutput, output_dir: Path) -> Path:
    """Write RankOutput to rank-<slug>-<ts>.yaml using ruamel round-trip I/O."""
    ts = datetime.now(tz=UTC).strftime("%Y%m%d-%H%M%S")
    out_path = output_dir / f"rank-{output.task_slug}-{ts}.yaml"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    data = json.loads(output.model_dump_json())

    try:
        from ruamel.yaml import YAML

        yaml = YAML()
        yaml.default_flow_style = False
        yaml.width = 120
        stream = io.StringIO()
        yaml.dump(data, stream)
        out_path.write_text(stream.getvalue(), encoding="utf-8")
    except ImportError:
        # Fallback: JSON-as-YAML-compatible (valid YAML superset)
        out_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Staged best-of-N ranker — orchestrate 3 stages + write rank-*.yaml"
    )
    parser.add_argument("--task-slug", required=True)
    parser.add_argument("--ac-contract-ref", required=True, metavar="PATH")
    parser.add_argument(
        "--domain", required=True, choices=["code", "prose", "long-chain"]
    )
    parser.add_argument(
        "--candidates-json",
        required=True,
        metavar="PATH",
        help="JSON: [{id, generator, artifact_path, text}]",
    )
    parser.add_argument("--cost-ceiling", required=True, type=int)
    parser.add_argument(
        "--output-dir", default="artifacts", metavar="DIR",
        help="Directory to write rank-*.yaml (default: artifacts/)",
    )
    parser.add_argument("--orm-threshold", type=float, default=0.50)
    parser.add_argument("--diversity-threshold", type=float, default=0.85)
    parser.add_argument("--prm-finalist-gap", type=float, default=0.15)
    args = parser.parse_args(argv)

    cands_path = Path(args.candidates_json)
    if not cands_path.exists():
        print(f"ERROR: candidates-json not found: {cands_path}", file=sys.stderr)
        return 1

    candidates_raw: list[dict[str, Any]] = json.loads(
        cands_path.read_text(encoding="utf-8")
    )

    output = run_pipeline(
        task_slug=args.task_slug,
        ac_contract_ref=args.ac_contract_ref,
        domain=args.domain,
        candidates_raw=candidates_raw,
        cost_ceiling=args.cost_ceiling,
        orm_threshold=args.orm_threshold,
        diversity_threshold=args.diversity_threshold,
        prm_finalist_gap=args.prm_finalist_gap,
    )

    out_path = _write_rank_yaml(output, Path(args.output_dir))
    print(f"Written: {out_path}")
    print(f"Status:  {output.status}")
    print(f"Selected: {output.selected_id or '(none)'}")

    return 0 if output.status == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
