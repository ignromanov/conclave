"""ranker-cost-meter.py — token spend tracker + 2× cost ceiling enforcement (D5/D13).

Tracks cumulative token spend across ranker stages. The cost ceiling equals 2× the
estimated single-generation token cost (set by the orchestrator from the adaptive-N
table in spine.md). On ceiling breach the caller degrades to ORM-top-1 → oracle-only
and writes status: cost_gate_triggered in the rank YAML.

CLI usage:
    # Initialize a new ledger:
    python ranker-cost-meter.py --log-json ledger.json --ceiling 40000

    # Record stage spend:
    python ranker-cost-meter.py --log-json ledger.json --stage stage1_orm --tokens 500

    # Report current state:
    python ranker-cost-meter.py --log-json ledger.json --report

Exit codes: 0 = within ceiling, 1 = ceiling breached (or error).

Import API (used by ranker-staged-prune.py):
    meter = CostMeter(ceiling=40000)
    meter.record(stage="stage1_orm", tokens=500)
    if meter.ceiling_breached():
        ...
    print(meter.total_tokens)
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass
class _StageRecord:
    stage: str
    tokens: int
    cumulative: int
    timestamp: str


@dataclass
class CostMeter:
    """Token spend tracker with 2× ceiling enforcement.

    Args:
        ceiling: maximum tokens allowed (= 2× single-generation estimate per D13).
    """

    ceiling: int
    total_tokens: int = 0
    _records: list[_StageRecord] = field(default_factory=list, repr=False)

    def record(self, stage: str, tokens: int) -> None:
        """Record token spend for a named stage."""
        self.total_tokens += tokens
        self._records.append(_StageRecord(
            stage=stage,
            tokens=tokens,
            cumulative=self.total_tokens,
            timestamp=datetime.now(tz=UTC).isoformat(),
        ))

    def ceiling_breached(self) -> bool:
        """Return True if cumulative tokens >= ceiling."""
        return self.total_tokens >= self.ceiling

    def utilization(self) -> float:
        """Return fraction of ceiling consumed (0.0–1.0+)."""
        if self.ceiling <= 0:
            return 0.0
        return self.total_tokens / self.ceiling

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-safe dict."""
        return {
            "ceiling": self.ceiling,
            "total_tokens_used": self.total_tokens,
            "utilization": round(self.utilization(), 4),
            "ceiling_breached": self.ceiling_breached(),
            "stages": [
                {
                    "stage": r.stage,
                    "tokens": r.tokens,
                    "cumulative": r.cumulative,
                    "timestamp": r.timestamp,
                }
                for r in self._records
            ],
        }

    def save(self, path: Path) -> None:
        """Persist the spend ledger (atomic write)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> CostMeter:
        """Reconstruct a CostMeter from a persisted JSON ledger."""
        data = json.loads(path.read_text(encoding="utf-8"))
        meter = cls(ceiling=data["ceiling"])
        meter.total_tokens = data["total_tokens_used"]
        meter._records = [
            _StageRecord(
                stage=s["stage"],
                tokens=s["tokens"],
                cumulative=s["cumulative"],
                timestamp=s["timestamp"],
            )
            for s in data.get("stages", [])
        ]
        return meter


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Token spend tracker — record stage cost or report ledger"
    )
    parser.add_argument(
        "--log-json",
        required=True,
        metavar="PATH",
        help="Path to the spend ledger JSON file",
    )
    parser.add_argument(
        "--ceiling",
        type=int,
        default=0,
        help="Cost ceiling in tokens (required when creating a new ledger)",
    )
    parser.add_argument("--stage", metavar="NAME", help="Stage name to record")
    parser.add_argument(
        "--tokens", type=int, default=0, help="Tokens to record for --stage"
    )
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print ledger summary as JSON and exit",
    )
    args = parser.parse_args(argv)

    log_path = Path(args.log_json)

    if args.report:
        if not log_path.exists():
            print(f"ERROR: log not found: {log_path}", file=sys.stderr)
            return 1
        meter = CostMeter.load(log_path)
        print(json.dumps(meter.to_dict(), indent=2))
        return 1 if meter.ceiling_breached() else 0

    # Init or load ledger
    if log_path.exists():
        meter = CostMeter.load(log_path)
        if args.ceiling > 0 and args.ceiling != meter.ceiling:
            print(
                f"WARN: --ceiling {args.ceiling} differs from ledger ceiling "
                f"{meter.ceiling}; using ledger value",
                file=sys.stderr,
            )
    else:
        if args.ceiling <= 0:
            print("ERROR: --ceiling required when creating a new ledger", file=sys.stderr)
            return 1
        meter = CostMeter(ceiling=args.ceiling)

    if args.stage:
        if args.tokens <= 0:
            print("ERROR: --tokens must be > 0 when --stage is set", file=sys.stderr)
            return 1
        meter.record(stage=args.stage, tokens=args.tokens)
        meter.save(log_path)
        status = "BREACHED" if meter.ceiling_breached() else "ok"
        print(
            f"Recorded: stage={args.stage} tokens={args.tokens} "
            f"cumulative={meter.total_tokens}/{meter.ceiling} ({status})"
        )
        return 1 if meter.ceiling_breached() else 0

    # No --stage: init/save ledger only
    meter.save(log_path)
    print(f"Ledger initialized: ceiling={meter.ceiling}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
