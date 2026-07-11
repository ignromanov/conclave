"""ranker-prm-harness.py — decompose artifact into steps + score per domain (Stage 2 PRM).

Implements the AgentPRM step-scoring approach for each supported domain:
  code       → AST top-level functions/classes (via stdlib ast; falls back to block split)
  prose      → markdown sections / paragraph blocks
  long-chain → structured tool-call step boundaries (regex; falls back to block split)

Each step is scored heuristically vs AC sub-criteria extracted from the contract text.
In production, a Sonnet call scores each step vs the full AC context; the heuristic
provides the deterministic floor used in tests and cost-capped runs.

Reference: AgentPRM (2511.08325) — 88.1% vs 65.7% end-judge accuracy on multi-step tasks.

CLI:
    python ranker-prm-harness.py
        --artifact-path <path>
        --domain code|prose|long-chain
        --ac-contract-ref <path>
        [--output-json <path>]

Output JSON schema:
    {
      "domain": "code|prose|long-chain",
      "steps": [
        {"step_id": str, "step_label": str, "score": float, "ac_criterion": str},
        ...
      ],
      "prm_aggregate": float
    }
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Step decomposition
# ---------------------------------------------------------------------------

def _decompose_code(text: str) -> list[dict[str, str]]:
    """Decompose code into top-level function/class definitions via AST.

    Falls back to blank-line-separated blocks for non-Python text.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return _decompose_blocks(text, prefix="block")

    steps: list[dict[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            lineno = node.lineno
            end_lineno = getattr(node, "end_lineno", lineno)
            body_lines = text.splitlines()[lineno - 1 : end_lineno]
            steps.append({
                "step_id": f"fn:{node.name}",
                "step_label": node.name,
                "body": "\n".join(body_lines),
            })

    return steps if steps else _decompose_blocks(text, prefix="block")


def _decompose_prose(text: str) -> list[dict[str, str]]:
    """Decompose prose into markdown sections; falls back to paragraph blocks."""
    steps: list[dict[str, str]] = []
    current_heading = "preamble"
    current_lines: list[str] = []

    for line in text.splitlines():
        if line.startswith("#"):
            body = "\n".join(current_lines).strip()
            if body:
                steps.append({
                    "step_id": f"section:{current_heading[:30]}",
                    "step_label": current_heading,
                    "body": body,
                })
            current_heading = line.lstrip("#").strip() or "untitled"
            current_lines = []
        else:
            current_lines.append(line)

    body = "\n".join(current_lines).strip()
    if body:
        steps.append({
            "step_id": f"section:{current_heading[:30]}",
            "step_label": current_heading,
            "body": body,
        })

    return steps if steps else _decompose_blocks(text, prefix="para")


_TOOL_CALL_RE = re.compile(
    r"(?:tool_call|tool:|step\s+\d+|\[tool:|\baction:)", re.IGNORECASE
)


def _decompose_long_chain(text: str) -> list[dict[str, str]]:
    """Decompose long-chain artifact on tool-call step boundaries.

    Splits on lines matching structured log markers; falls back to block split.
    """
    steps: list[dict[str, str]] = []
    current_step: list[str] = []
    step_idx = 0

    for line in text.splitlines():
        if _TOOL_CALL_RE.search(line) and current_step:
            steps.append({
                "step_id": f"step:{step_idx}",
                "step_label": current_step[0][:60],
                "body": "\n".join(current_step),
            })
            step_idx += 1
            current_step = [line]
        else:
            current_step.append(line)

    if current_step:
        steps.append({
            "step_id": f"step:{step_idx}",
            "step_label": (current_step[0][:60] if current_step else f"step_{step_idx}"),
            "body": "\n".join(current_step),
        })

    return steps if len(steps) > 1 else _decompose_blocks(text, prefix="step")


def _decompose_blocks(text: str, prefix: str = "block") -> list[dict[str, str]]:
    """Fallback: split on double newlines into paragraph blocks."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    return [
        {
            "step_id": f"{prefix}:{i}",
            "step_label": blocks[i][:60],
            "body": blocks[i],
        }
        for i in range(len(blocks))
    ]


# ---------------------------------------------------------------------------
# Step scoring
# ---------------------------------------------------------------------------

def _extract_ac_keywords(ac_text: str, max_keywords: int = 5) -> list[str]:
    """Extract short keyword phrases from AC contract list items."""
    keywords: list[str] = []
    for line in ac_text.splitlines():
        stripped = line.strip().lstrip("-").strip()
        if stripped and len(stripped) > 5:
            # Take the first 4 words as a keyword phrase
            phrase = " ".join(stripped.split()[:4]).lower()
            keywords.append(phrase)
            if len(keywords) >= max_keywords:
                break
    return keywords


def _score_step(step_body: str, ac_text: str) -> tuple[float, str]:
    """Heuristic score for a single step vs AC sub-criteria.

    Returns (score in [0.0, 1.0], matched_criterion_label).

    Three sub-checks (equal weight):
      1. non-trivial length — proxy for substance
      2. no blocker markers (TODO/FIXME/NOT IMPLEMENTED)
      3. AC-keyword proximity — at least one AC phrase appears in the step
    """
    if not step_body.strip():
        return 0.0, "empty step"

    checks = 3
    score = 0.0
    matched_criterion = "heuristic"

    # 1. Length proxy (saturates at 200 chars)
    score += min(1.0, len(step_body) / 200)

    # 2. No blocker markers
    has_blocker = any(
        marker.lower() in step_body.lower()
        for marker in ["todo", "fixme", "not implemented", "pass  #", "raise NotImplementedError"]
    )
    score += 0.0 if has_blocker else 1.0

    # 3. AC-keyword proximity
    ac_keywords = _extract_ac_keywords(ac_text)
    if ac_keywords:
        body_lower = step_body.lower()
        matched = [kw for kw in ac_keywords if kw in body_lower]
        score += len(matched) / len(ac_keywords)
        if matched:
            matched_criterion = matched[0]
    else:
        score += 0.5  # no keywords extractable — neutral

    return round(score / checks, 4), matched_criterion


# ---------------------------------------------------------------------------
# Public API (imported by ranker-staged-prune.py)
# ---------------------------------------------------------------------------

def score_steps(
    artifact_text: str,
    domain: str,
    ac_text: str,
) -> list[dict[str, Any]]:
    """Decompose artifact into steps and score each vs AC sub-criteria.

    Returns list of dicts matching PrmStepScore schema:
      {step_id: str, step_label: str, score: float, ac_criterion: str}
    """
    if domain == "code":
        steps = _decompose_code(artifact_text)
    elif domain == "prose":
        steps = _decompose_prose(artifact_text)
    elif domain == "long-chain":
        steps = _decompose_long_chain(artifact_text)
    else:
        steps = _decompose_blocks(artifact_text)

    results: list[dict[str, Any]] = []
    for step in steps:
        score, criterion = _score_step(step["body"], ac_text)
        results.append({
            "step_id": step["step_id"],
            "step_label": step["step_label"],
            "score": score,
            "ac_criterion": criterion,
        })

    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="PRM step-scoring harness — decompose artifact + score per domain"
    )
    parser.add_argument("--artifact-path", required=True, metavar="PATH")
    parser.add_argument(
        "--domain",
        required=True,
        choices=["code", "prose", "long-chain"],
    )
    parser.add_argument("--ac-contract-ref", required=True, metavar="PATH")
    parser.add_argument("--output-json", metavar="PATH")
    args = parser.parse_args(argv)

    artifact_path = Path(args.artifact_path)
    if not artifact_path.exists():
        print(f"ERROR: artifact-path not found: {artifact_path}", file=sys.stderr)
        return 1

    ac_path = Path(args.ac_contract_ref)
    ac_text = ac_path.read_text(encoding="utf-8") if ac_path.exists() else ""
    if not ac_text:
        print(f"WARN: ac-contract-ref empty or not found: {ac_path}", file=sys.stderr)

    artifact_text = artifact_path.read_text(encoding="utf-8")
    steps = score_steps(artifact_text, args.domain, ac_text)
    prm_aggregate = (
        round(sum(s["score"] for s in steps) / len(steps), 4) if steps else 0.0
    )

    result = {"domain": args.domain, "steps": steps, "prm_aggregate": prm_aggregate}
    output_json = json.dumps(result, indent=2)

    if args.output_json:
        out_path = Path(args.output_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_json + "\n", encoding="utf-8")
        print(f"Written: {out_path}")
    else:
        print(output_json)

    return 0


if __name__ == "__main__":
    sys.exit(main())
