import os
import sys
from pathlib import Path

# Ensure the backend package root is importable when pytest runs from anywhere.
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# Force offline model loading for any test that touches the rag package.
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
