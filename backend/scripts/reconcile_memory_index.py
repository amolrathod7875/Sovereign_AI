#!/usr/bin/env python3
"""M5 memory index reconciliation CLI.

Detects drift between PostgreSQL canonical memories and Qdrant sovereign_memory.

Examples:
  python scripts/reconcile_memory_index.py --dry-run
  python scripts/reconcile_memory_index.py --repair
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def _reconcile(dry_run: bool, repair: bool) -> int:
    from app.memory.reconciliation import MemoryReconciliation
    reconciler = MemoryReconciliation()
    try:
        delta = await reconciler.diff()
    finally:
        await reconciler.close()

    print("Delta:")
    print(f"  missing:      {len(delta.missing)}")
    print(f"  orphan:       {len(delta.orphan)}")
    print(f"  stale_version:{len(delta.stale_version)}")
    print(f"  inactive_present: {len(delta.inactive_present)}")
    print(f"  expired_present:  {len(delta.expired_present)}")

    if not repair or dry_run:
        return 0

    summary = await reconciler.repair(delta)
    print(f"Repair: {summary}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="M5 memory index reconciliation")
    parser.add_argument("--dry-run", action="store_true", help="Show drift without mutating Qdrant")
    parser.add_argument("--repair", action="store_true", help="Repair drift toward PostgreSQL state")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()
    configure_logging(args.verbose)
    if not args.dry_run and not args.repair:
        parser.error("Specify --dry-run or --repair")
    return asyncio.run(_reconcile(dry_run=args.dry_run, repair=args.repair))


if __name__ == "__main__":
    sys.exit(main())
