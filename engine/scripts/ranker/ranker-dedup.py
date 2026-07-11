"""ranker-dedup.py — n-gram similarity matrix + diversity guard (Stage 0, mandatory per D20/AC10).

Computes pairwise character-level n-gram Jaccard similarity between candidate texts; emits a
similarity matrix and a WARN if max similarity exceeds the diversity threshold (default 0.85).
Greedy dedup produces the max-diverse subset when collapse is detected.

CLI:
    python ranker-dedup.py --candidates-json <path>
                           [--threshold 0.85]
                           [--ngram-size 3]
                           [--output-json <path>]

candidates-json schema: [{id: str, text: str}, ...]

Output JSON schema:
    {
      "similarity_matrix": [[float, ...]],   # NxN, index matches candidates order
      "candidate_ids": [str, ...],
      "similarity_max": float,
      "threshold": float,
      "diversity_collapse": bool,            # True if similarity_max > threshold
      "diverse_subset_ids": [str, ...],      # max-diverse subset (kept candidates)
      "dedup_triggered": bool                # True if subset != all candidates
    }

Diversity warrant: 2 diverse candidates >= 16 homogeneous (Yang 2602.03794).
Ranking clones is meaningless — this guard is mandatory (D20).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def _ngram_set(text: str, n: int = 3) -> set[str]:
    """Return the set of character-level n-grams for a text."""
    normalized = " ".join(text.lower().split())
    return {normalized[i : i + n] for i in range(len(normalized) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two n-gram sets."""
    if not a and not b:
        return 1.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def _similarity_matrix(texts: list[str], n: int = 3) -> list[list[float]]:
    """Compute pairwise Jaccard similarity; symmetric, diagonal = 1.0."""
    ngrams = [_ngram_set(t, n) for t in texts]
    size = len(ngrams)
    matrix: list[list[float]] = []
    for i in range(size):
        row: list[float] = []
        for j in range(size):
            if i == j:
                row.append(1.0)
            elif j < i:
                row.append(matrix[j][i])
            else:
                row.append(round(_jaccard(ngrams[i], ngrams[j]), 4))
        matrix.append(row)
    return matrix


def _max_off_diagonal(matrix: list[list[float]]) -> float:
    """Return the maximum pairwise similarity between distinct candidates."""
    size = len(matrix)
    if size < 2:
        return 0.0
    return max(matrix[i][j] for i in range(size) for j in range(size) if i != j)


def _greedy_diverse_subset(
    candidate_ids: list[str],
    matrix: list[list[float]],
    threshold: float,
) -> list[str]:
    """Greedy max-diverse subset: remove the most-redundant candidate at each step.

    Iteratively removes the candidate with the highest mean similarity to others until
    no pair exceeds the threshold (or only 1 candidate remains).
    """
    n = len(candidate_ids)
    if n <= 1:
        return list(candidate_ids)

    kept = list(range(n))

    while len(kept) > 1:
        max_sim = 0.0
        max_pair = (-1, -1)
        for ii in range(len(kept)):
            for jj in range(ii + 1, len(kept)):
                sim = matrix[kept[ii]][kept[jj]]
                if sim > max_sim:
                    max_sim = sim
                    max_pair = (kept[ii], kept[jj])

        if max_sim <= threshold:
            break

        # Remove the candidate more similar to the rest (more redundant)
        i_idx, j_idx = max_pair
        i_mean = sum(matrix[i_idx][k] for k in kept if k != i_idx) / (len(kept) - 1)
        j_mean = sum(matrix[j_idx][k] for k in kept if k != j_idx) / (len(kept) - 1)
        remove = i_idx if i_mean >= j_mean else j_idx
        kept.remove(remove)

    return [candidate_ids[k] for k in kept]


def run(
    candidates: list[dict[str, str]],
    threshold: float = 0.85,
    ngram_size: int = 3,
) -> dict[str, Any]:
    """Core dedup logic — importable by ranker-staged-prune.py.

    Args:
        candidates: list of {id: str, text: str}
        threshold: similarity above which diversity_collapse is flagged (default 0.85)
        ngram_size: character n-gram width (default 3)

    Returns:
        dict matching the output JSON schema documented in the module docstring.
    """
    if not candidates:
        return {
            "similarity_matrix": [],
            "candidate_ids": [],
            "similarity_max": 0.0,
            "threshold": threshold,
            "diversity_collapse": False,
            "diverse_subset_ids": [],
            "dedup_triggered": False,
        }

    ids = [c["id"] for c in candidates]
    texts = [c["text"] for c in candidates]
    matrix = _similarity_matrix(texts, n=ngram_size)
    sim_max = _max_off_diagonal(matrix)
    collapse = sim_max > threshold

    diverse_ids = _greedy_diverse_subset(ids, matrix, threshold) if collapse else ids
    dedup_triggered = len(diverse_ids) < len(ids)

    if collapse:
        print(
            f"WARN diversity_collapse: similarity_max={sim_max:.4f} > threshold={threshold}. "
            f"Deduped {len(ids)} → {len(diverse_ids)} candidates.",
            file=sys.stderr,
        )

    return {
        "similarity_matrix": matrix,
        "candidate_ids": ids,
        "similarity_max": round(sim_max, 4),
        "threshold": threshold,
        "diversity_collapse": collapse,
        "diverse_subset_ids": diverse_ids,
        "dedup_triggered": dedup_triggered,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Stage 0 diversity guard: n-gram similarity matrix + collapse detection"
    )
    parser.add_argument(
        "--candidates-json",
        required=True,
        metavar="PATH",
        help="JSON file with list of {id, text} objects",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        metavar="FLOAT",
        help="Similarity threshold for diversity collapse (default 0.85)",
    )
    parser.add_argument(
        "--ngram-size",
        type=int,
        default=3,
        metavar="N",
        help="Character n-gram width (default 3)",
    )
    parser.add_argument(
        "--output-json",
        metavar="PATH",
        help="Write result JSON to this path (default: stdout)",
    )
    args = parser.parse_args(argv)

    input_path = Path(args.candidates_json)
    if not input_path.exists():
        print(f"ERROR: candidates-json not found: {input_path}", file=sys.stderr)
        return 1

    try:
        raw = json.loads(input_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"ERROR: invalid JSON in {input_path}: {exc}", file=sys.stderr)
        return 1

    if not isinstance(raw, list):
        print("ERROR: candidates-json must be a JSON array", file=sys.stderr)
        return 1

    for item in raw:
        if "id" not in item or "text" not in item:
            print(
                "ERROR: each candidate must have 'id' and 'text' fields", file=sys.stderr
            )
            return 1

    result = run(raw, threshold=args.threshold, ngram_size=args.ngram_size)
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
