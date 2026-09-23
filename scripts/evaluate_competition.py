"""Phase 13A — Competition evaluation entry point.

Usage:
    python scripts/evaluate_competition.py
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
BACKEND = REPO / "backend"
sys.path.insert(0, str(BACKEND))

from evaluation.competition import main

if __name__ == "__main__":
    sys.exit(main())
