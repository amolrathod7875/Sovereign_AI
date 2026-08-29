"""Ingestion entry point. Run from the backend/ directory:
    python -m rag.run_ingest
"""
import json
import logging
import sys
from rag.ingestion.ingest import run_ingest

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")


def main():
    stats = run_ingest()
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    sys.exit(main())
