"""VISION_ANALYSIS node: local multimodal evidence extraction.

Runs ONLY when the request carries a vision input (image / P&ID / PDF). It calls
the local Qwen-VL tool and stores the structured result in ``vision_evidence``.
Equipment tags extracted from the vision output are forwarded to ``vision_tags``
so the RETRIEVE_EVIDENCE node can run a vision-grounded RAG search (the
"vision -> RAG" demonstration).

If there is no image, the node is a safe pass-through (status unchanged) so the
graph can be shared between text-only and multimodal tasks.
"""
import logging
import time
from typing import Dict, Any

from agent.tools.vision import analyze_image, extract_equipment_tags
from agent.utils import trace_entry, elapsed_ms

logger = logging.getLogger(__name__)


def _detect_analysis_type(request: str) -> str:
    r = (request or "").lower()
    if any(k in r for k in ("p&id", "pid", "piping", "instrumentation diagram")):
        return "pid"
    if any(k in r for k in ("scan", "document", "pdf", "page", "report")):
        return "document"
    if any(k in r for k in ("ocr", "transcribe", "text in")):
        return "ocr"
    if any(k in r for k in ("inspect", "photo", "photograph", "drawing", "diagram")):
        return "inspection"
    return "general"


def run(state: dict) -> dict:
    start = time.time()
    image_path = state.get("image_path")

    if not image_path:
        return {
            "has_vision_input": False,
            "trace": [trace_entry("vision_analysis", "skip_no_image", None,
                                  elapsed_ms(start), "SUCCESS", used=False)],
        }

    analysis_type = state.get("analysis_type") or _detect_analysis_type(state.get("user_request", ""))
    try:
        result = analyze_image(image_path, prompt=state.get("user_request"), analysis_type=analysis_type)
        tags = extract_equipment_tags(result)
        status = "VISION_ANALYZED"
        err = None
    except Exception as e:
        logger.error("vision_analysis failed: %s", e)
        result = {
            "file": image_path,
            "analysis_type": analysis_type,
            "description": "",
            "findings": [],
            "entities": [],
            "uncertain_items": [f"vision_error: {e}"],
            "confidence": 0.0,
            "model": "Qwen2.5-VL-3B-Instruct",
            "data_origin": "local",
        }
        tags = []
        status = "VISION_FAILED"
        err = str(e)

    return {
        "has_vision_input": True,
        "analysis_type": analysis_type,
        "vision_evidence": [result],
        "vision_tags": tags,
        "errors": [f"vision:{err}"] if err else [],
        "status": status,
        "trace": [trace_entry("vision_analysis", "analyze_image",
                              "agent.tools.vision", elapsed_ms(start),
                              "SUCCESS" if not err else "FAILED",
                              analysis_type=analysis_type,
                              findings=len(result.get("findings", [])),
                              uncertain=len(result.get("uncertain_items", [])),
                              tags=tags[:10])],
    }
