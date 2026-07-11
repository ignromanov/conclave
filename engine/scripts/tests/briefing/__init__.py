# Make scripts/lifecycle/ importable for Phase-4 test modules (spec 085).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "lifecycle"))
