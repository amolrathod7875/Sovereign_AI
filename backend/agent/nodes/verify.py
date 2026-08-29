"""VERIFY_OUTPUT node: validate the generated DOCX artifact.

If verification fails, it requests regeneration (graph loops back to generate up
to MAX_GENERATION_RETRIES). This provides iteration / error recovery.
"""
import logging
import time
from typing import Dict, Any

from agent.tools.create_docx import verify_docx
from agent.config import MAX_GENERATION_RETRIES
from agent.utils import trace_entry, elapsed_ms

logger = logging.getLogger(__name__)


def run(state: dict) -> dict:
    start = time.time()
    artifacts = state.get("artifacts", [])
    path = artifacts[-1] if artifacts else None
    errors: list = list(state.get("errors", []))

    if not path:
        verification = {"ok": False, "error": "no artifact produced", "missing_sections": ["artifact"]}
        errors.append("verify:no_artifact")
    else:
        verification = verify_docx(path)
        if not verification.get("ok"):
            errors.append("verify:missing_sections:" + ",".join(verification.get("missing_sections", [])))

    iterations = int(state.get("iterations", 0)) + (0 if verification.get("ok") else 1)
    status = "VERIFIED" if verification.get("ok") else "VERIFY_FAILED"

    return {
        "verification": verification,
        "iterations": iterations,
        "errors": errors,
        "status": status,
        "trace": [trace_entry("verify_output", "validate_docx", "verify_docx",
                              elapsed_ms(start), "SUCCESS" if verification.get("ok") else "FAILED",
                              ok=verification.get("ok"), iterations=iterations)],
    }


def route(state: dict) -> str:
    if state.get("verification", {}).get("ok"):
        return "end"
    if int(state.get("iterations", 0)) < MAX_GENERATION_RETRIES:
        return "retry"
    return "end"
