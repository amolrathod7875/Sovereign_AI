"""RETRIEVE_EVIDENCE node: focused hybrid retrieval + targeted full-document reads."""
import logging
import os
import time
from typing import Dict, Any, List

from agent.tools.search_kb import search_knowledge_base
from agent.tools.read_document import read_document
from agent.config import ASSETS_DIR
from agent.utils import trace_entry, elapsed_ms

logger = logging.getLogger(__name__)

_DOC_PATHS = {
    "sensor_dataset": ASSETS_DIR / "sensors" / "sensor_dataset.csv",
    "equipment_manual": ASSETS_DIR / "manual" / "manual.docx",
    "operating_sop": ASSETS_DIR / "sop" / "operating_sop.docx",
    "preventive_maintenance_sop": ASSETS_DIR / "sop" / "pm_sop.docx",
    "inspection_report": ASSETS_DIR / "inspection" / "inspection_report.pdf",
    "vendor_correspondence": ASSETS_DIR / "correspondence" / "vendor_correspondence.eml",
    "canonical_profile": ASSETS_DIR / "profile.json",
    "maintenance_approval_note": ASSETS_DIR / "approvals" / "approval_note.docx",
}


def _build_evidence(plan_item: Dict[str, Any], hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ev: List[Dict[str, Any]] = []
    for h in hits[:2]:
        ev.append({
            "claim": plan_item["category"],
            "value": (h.get("text") or "")[:800],
            "source_file": h.get("source_file", ""),
            "document_type": h.get("document_type", ""),
            "asset_tag": h.get("asset_tag", ""),
            "confidence": round(min(1.0, max(0.0, float(h.get("score", 0.0)))), 3),
        })
    return ev


def run(state: dict) -> dict:
    start = time.time()
    asset_tag = state["asset_tag"]
    plan = state["plan"]

    chunks: List[Dict[str, Any]] = []
    docs: List[Dict[str, Any]] = []
    evidence: List[Dict[str, Any]] = []
    errors: List[str] = []

    for item in plan:
        dt = item["document_type"]
        q = item["query"]
        try:
            hits = search_knowledge_base(q, asset_tag=asset_tag, document_type=dt, top_k=6)
            for h in hits:
                chunks.append(h)
            evidence.extend(_build_evidence(item, hits))
        except Exception as e:
            logger.error("retrieval failed for %s: %s", dt, e)
            errors.append(f"retrieve:{dt}:{e}")

        # Targeted full read for precise extraction (inspection / vendor / SOP / profile / sensors).
        # This MUST run for every planned document type: the ANALYZE_EVIDENCE node
        # extracts inspection findings / vendor parts / SOP requirements from these
        # full documents, and everything downstream (findings, required_actions,
        # approval_required, the approval-note artifact) is grounded in them.
        path = _DOC_PATHS.get(dt)
        if path and os.path.exists(str(path)):
            try:
                parsed = read_document(str(path))
                docs.append({
                    "document_type": dt,
                    "source_file": parsed["source_file"],
                    "content": parsed["content"],
                    "num_blocks": parsed["num_blocks"],
                    "asset_tag": asset_tag,
                })
            except Exception as e:
                logger.error("read failed for %s: %s", path, e)
                errors.append(f"read:{dt}:{e}")

    # Vision-grounded RAG: use equipment tags the VLM extracted from the drawing
    # to pull the matching local knowledge-base documents (vision -> RAG).
    vision_tags = state.get("vision_tags") or []
    if vision_tags:
        for tag in vision_tags[:5]:
            try:
                hits = search_knowledge_base(
                    f"{tag} equipment specification operating parameters",
                    asset_tag=asset_tag, top_k=4,
                )
                for h in hits:
                    chunks.append(h)
                evidence.extend(_build_evidence(
                    {"category": "vision_rag", "document_type": ""},
                    hits,
                ))
            except Exception as e:
                logger.error("vision-grounded retrieval failed for %s: %s", tag, e)
                errors.append(f"retrieve:vision_rag:{tag}:{e}")

    return {
        "retrieved_chunks": chunks,
        "retrieved_documents": docs,
        "evidence": evidence,
        "errors": errors,
        "status": "RETRIEVED",
        "trace": [trace_entry("retrieve_evidence", "hybrid_retrieve+read",
                              "search_knowledge_base,read_document",
                              elapsed_ms(start), "SUCCESS",
                              chunks=len(chunks), docs=len(docs), evidence=len(evidence),
                              vision_tags=len(vision_tags))],
    }
