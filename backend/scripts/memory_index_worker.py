#!/usr/bin/env python3
"""M5 memory outbox worker CLI.

Processes memory_index_outbox events into the local embedded Qdrant semantic index.

Examples:
  python scripts/memory_index_worker.py --once
  python scripts/memory_index_worker.py --loop --poll-seconds 5 --batch-size 25
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Ensure backend/ is importable when run directly from scripts/
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


def configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def _run_once(batch_size: int, max_attempts: int, processing_timeout: int) -> int:
    from app.memory.indexer import OutboxProcessor
    processor = OutboxProcessor(
        batch_size=batch_size,
        max_attempts=max_attempts,
        processing_timeout_seconds=processing_timeout,
    )
    try:
        summary = await processor.run_batch()
        print(f"Processed: {summary}")
        return 0 if not summary["failed"] else 1
    finally:
        await processor.close()


async def _run_loop(poll_seconds: float, batch_size: int, max_attempts: int, processing_timeout: int) -> int:
    from app.memory.indexer import OutboxProcessor
    processor = OutboxProcessor(
        batch_size=batch_size,
        max_attempts=max_attempts,
        processing_timeout_seconds=processing_timeout,
    )
    try:
        await processor.run_loop(poll_seconds=poll_seconds)
        return 0
    except KeyboardInterrupt:
        print("Interrupted.")
        return 0
    finally:
        await processor.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="M5 memory index outbox worker")
    parser.add_argument("--once", action="store_true", help="Run one batch and exit")
    parser.add_argument("--loop", action="store_true", help="Run continuously")
    parser.add_argument("--poll-seconds", type=float, default=5.0, help="Poll interval in loop mode")
    parser.add_argument("--batch-size", type=int, default=25, help="Outbox batch size")
    parser.add_argument("--max-attempts", type=int, default=5, help="Max retry attempts for failed events")
    parser.add_argument("--processing-timeout", type=int, default=300, help="Stale PROCESSING recovery timeout seconds")
    parser.add_argument("--verbose", action="store_true", help="Debug logging")
    args = parser.parse_args()

    configure_logging(args.verbose)
    if args.once:
        return asyncio.run(_run_once(args.batch_size, args.max_attempts, args.processing_timeout))
    if args.loop:
        return asyncio.run(_run_loop(args.poll_seconds, args.batch_size, args.max_attempts, args.processing_timeout))
    parser.error("Specify --once or --loop")


if __name__ == "__main__":
    sys.exit(main())
