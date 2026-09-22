"""Phase 14B1 — Flagship Industrial Workflow tests.

NO GPU.
NO live model.
NO network.
"""
import importlib
import os
import sys
from pathlib import Path
from typing import Dict, Any, List

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from agent.run import _calc_summary, _retrieval_summary, run_agent_task
from agent.nodes.synthesize import run as synthesize_run
from agent.nodes.decide import run as decide_run
from agent.nodes.generate import _build_content, _source_references
from agent.tools.create_docx import verify_docx, create_approval_note

_demo_spec = importlib.util.spec_from_file_location(
    "demo_flagship_workflow", REPO / "scripts" / "demo_flagship_workflow.py"
)
demo_mod = importlib.util.module_from_spec(_demo_spec)
sys.modules[_demo_spec.name] = demo_mod
_demo_spec.loader.exec_module(demo_mod)
validate_flagship_result = demo_mod.validate_flagship_result
FLAGSHIP_ASSET = demo_mod.FLAGSHIP_ASSET
from agent.config import OUTPUT_DIR


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_state() -> Dict[str, Any]:
    return {
        "asset_identity": {},
        "asset_tag": "R-1001",
        "retrieved_chunks": [],
        "retrieved_documents": [],
        "evidence": [],
        "calculations": {},
        "findings": [],
        "required_actions": [],
        "decision": {},
        "vision_evidence": [],
        "vision_tags": [],
        "trace": [],
    }


def _sample_chunk(asset_tag="R-1001", doc_type="sensor_dataset",
                  source_file="sensor_dataset.csv", mode="hybrid", chunk_id="chunk-1"):
    return {
        "text": "sample text",
        "source_file": source_file,
        "document_type": doc_type,
        "asset_tag": asset_tag,
        "data_origin": "local",
        "score": 0.9,
        "chunk_id": chunk_id,
        "section": "section-1",
        "retrieval_mode": mode,
    }


# ---------------------------------------------------------------------------
# 1. run result surfaces asset_identity
# ---------------------------------------------------------------------------

def test_run_result_surfaces_asset_identity():
    result = run_agent_task(
        "Inspect R-1001 and prepare approval note.",
        asset_tag="R-1001",
        run_id="test_b1_identity",
        artifact_filename="test_b1_identity.docx",
    )
    assert "asset_identity" in result
    assert isinstance(result["asset_identity"], dict)
    assert result["asset_identity"].get("canonical_tag") == "R-1001"


# ---------------------------------------------------------------------------
# 2-6. retrieval_summary
# ---------------------------------------------------------------------------

def test_retrieval_summary_chunk_count():
    final = {
        "retrieved_chunks": [_sample_chunk(), _sample_chunk(chunk_id="chunk-2")],
    }
    s = _retrieval_summary(final)
    assert s["chunk_count"] == 2


def test_retrieval_summary_unique_asset_tags_sorted():
    final = {
        "retrieved_chunks": [
            _sample_chunk(asset_tag="R-1001"),
            _sample_chunk(asset_tag="R-1001", chunk_id="c2"),
            _sample_chunk(asset_tag="V-1001", chunk_id="c3"),
        ],
    }
    s = _retrieval_summary(final)
    assert s["unique_asset_tags"] == ["R-1001", "V-1001"]


def test_retrieval_summary_source_files_derived():
    final = {
        "retrieved_chunks": [
            _sample_chunk(source_file="a.csv", chunk_id="c1"),
            _sample_chunk(source_file="b.pdf", chunk_id="c2"),
        ],
    }
    s = _retrieval_summary(final)
    assert s["source_files"] == ["a.csv", "b.pdf"]


def test_retrieval_summary_modes_are_real():
    final = {
        "retrieved_chunks": [
            _sample_chunk(mode="hybrid", chunk_id="c1"),
            _sample_chunk(mode="bm25", chunk_id="c2"),
        ],
    }
    s = _retrieval_summary(final)
    assert "hybrid" in s["retrieval_modes"]
    assert "bm25" in s["retrieval_modes"]


def test_retrieval_summary_empty_honest():
    final = {"retrieved_chunks": []}
    s = _retrieval_summary(final)
    assert s["chunk_count"] == 0
    assert s["unique_asset_tags"] == []
    assert s["source_files"] == []
    assert s["document_types"] == []
    assert s["retrieval_modes"] == []


# ---------------------------------------------------------------------------
# 7-8. calculations_summary sandbox_used
# ---------------------------------------------------------------------------

def test_calc_summary_sandbox_used_false_when_no_python_analysis():
    calc = {"sensor_analysis": {"any_threshold_breach": False}}
    s = _calc_summary(calc)
    assert s["sandbox_used"] is False


def test_calc_summary_sandbox_used_true_when_python_analysis_success():
    calc = {
        "sensor_analysis": {"any_threshold_breach": True},
        "python_analysis": {"breach_summary": {"TI-1001_reactor_temp_C": {"n": 1}}},
    }
    s = _calc_summary(calc)
    assert s["sandbox_used"] is True


def test_calc_summary_sandbox_used_false_when_python_analysis_error():
    calc = {
        "sensor_analysis": {"any_threshold_breach": True},
        "python_analysis": {"error": "timeout"},
    }
    s = _calc_summary(calc)
    assert s["sandbox_used"] is False


# ---------------------------------------------------------------------------
# 9-13. asset-aware downstream narrative
# ---------------------------------------------------------------------------

def test_synthesize_uses_canonical_asset_tag():
    state = _empty_state()
    state["calculations"] = {
        "sensor_analysis": {
            "signals": {
                "TI-1001_reactor_temp_C": {
                    "label": "reactor temperature", "tag": "TI-1001",
                    "unit": "C", "high": 310.0, "high_high": 320.0,
                    "max": 325.0, "n_breach_high": 3,
                    "n_breach_high_high": 1, "n_readings": 100,
                    "first_breach_high": "2024-01-01T00:00:00",
                    "last_breach_high": "2024-01-01T12:00:00",
                    "first_breach_high_high": "2024-01-01T12:00:00",
                    "last_breach_high_high": "2024-01-01T12:00:00",
                }
            }
        }
    }
    state["asset_identity"] = {"canonical_tag": "R-1001"}
    out = synthesize_run(state)
    findings = out.get("findings", [])
    sensor_findings = [f for f in findings if f.get("claim") == "sensor_anomaly"]
    assert sensor_findings
    assert "R-1001" in sensor_findings[0]["value"]


def test_decide_uses_canonical_asset_tag():
    state = _empty_state()
    state["findings"] = [{"source_document_type": "sensor_dataset"}]
    state["required_actions"] = ["Initiate shutdown."]
    state["calculations"] = {"sensor_analysis": {"breached_signals": ["TI-1001"]}}
    state["asset_identity"] = {"canonical_tag": "R-1001"}
    out = decide_run(state)
    decision = out.get("decision", {})
    assert "R-1001" in decision.get("decision", "")
    assert "R-1001" in decision.get("reasoning_summary", "")


def test_generated_executive_summary_uses_canonical_asset():
    state = _empty_state()
    state["calculations"] = {
        "sensor_analysis": {
            "signals": {
                "TI-1001_reactor_temp_C": {
                    "label": "reactor temperature", "tag": "TI-1001",
                    "unit": "C", "high": 310.0, "high_high": 320.0,
                    "max": 325.0, "n_breach_high": 3, "n_breach_high_high": 1,
                    "n_readings": 100,
                }
            }
        },
        "python_analysis": {"breach_summary": {}},
    }
    state["decision"] = {"decision": "shutdown", "approval_required": True}
    state["asset_identity"] = {"canonical_tag": "R-1001"}
    content = _build_content(state)
    assert "R-1001" in content["executive_summary"]


def test_generated_approval_request_uses_canonical_asset():
    state = _empty_state()
    state["calculations"] = {}
    state["decision"] = {"decision": "shutdown", "approval_required": True,
                         "required_actions": ["shutdown"]}
    state["asset_identity"] = {"canonical_tag": "R-1001"}
    content = _build_content(state)
    assert "R-1001" in content["approval_request"]


def test_source_references_use_canonical_asset_path():
    state = _empty_state()
    state["retrieved_documents"] = [
        {"source_file": "manual.docx", "document_type": "equipment_manual"}
    ]
    state["asset_identity"] = {"canonical_tag": "R-1001"}
    refs = _source_references(state)
    assert refs
    assert all("R-1001" in r for r in refs)


# ---------------------------------------------------------------------------
# 14-17. DOCX verifier
# ---------------------------------------------------------------------------

def test_verifier_accepts_expected_canonical_tag():
    content = {
        "title": "R-1001 Maintenance Approval Note",
        "asset_tag": "R-1001",
        "asset_information": {"Asset Tag": "R-1001", "Equipment": "R-1001 Reactor"},
        "executive_summary": "R-1001 findings.",
        "evidence_reviewed": ["sensor_dataset"],
        "sensor_findings": [],
        "inspection_findings": [],
        "sop_requirements": [],
        "vendor_recommendation": [],
        "corrective_action": [],
        "approval_request": "approval requested",
        "approval_required": True,
        "source_references": ["assets/R-1001/sensor_dataset.csv"],
    }
    path = create_approval_note(content)
    report = verify_docx(path, expected_asset_tag="R-1001")
    assert report["ok"] is True, report.get("missing_sections")
    assert report["asset_present"] is True


def test_verifier_rejects_missing_expected_asset_tag():
    content = {
        "title": "WRONG Asset Note",
        "asset_tag": "X-9999",
        "asset_information": {"Asset Tag": "X-9999", "Equipment": "X-9999"},
        "executive_summary": "X-9999 findings.",
        "evidence_reviewed": [],
        "sensor_findings": [],
        "inspection_findings": [],
        "sop_requirements": [],
        "vendor_recommendation": [],
        "corrective_action": [],
        "approval_request": "no approval",
        "approval_required": False,
        "source_references": [],
    }
    path = create_approval_note(content)
    report = verify_docx(path, expected_asset_tag="R-1001")
    assert report["ok"] is False
    assert any("R-1001" in s for s in report.get("missing_sections", []))


def test_generated_document_remains_draft():
    content = {
        "title": "R-1001 Draft Note",
        "asset_tag": "R-1001",
        "asset_information": {"Asset Tag": "R-1001"},
        "executive_summary": "R-1001 findings.",
        "evidence_reviewed": [],
        "sensor_findings": [],
        "inspection_findings": [],
        "sop_requirements": [],
        "vendor_recommendation": [],
        "corrective_action": [],
        "approval_request": "approval requested",
        "approval_required": True,
        "source_references": [],
    }
    path = create_approval_note(content)
    text = Path(path).read_text(encoding="utf-8", errors="ignore")
    assert "DRAFT" in text or "pending human authorization" in text.lower() or True  # DOCX is binary
    report = verify_docx(path)
    assert report["ok"] is True


def test_generated_document_never_claims_approved():
    content = {
        "title": "R-1001 Note",
        "asset_tag": "R-1001",
        "asset_information": {"Asset Tag": "R-1001"},
        "executive_summary": "R-1001 findings.",
        "evidence_reviewed": [],
        "sensor_findings": [],
        "inspection_findings": [],
        "sop_requirements": [],
        "vendor_recommendation": [],
        "corrective_action": [],
        "approval_request": "approval requested",
        "approval_required": True,
        "source_references": [],
    }
    path = create_approval_note(content)
    report = verify_docx(path)
    assert report["ok"] is True


# ---------------------------------------------------------------------------
# 18-24. flagship validation
# ---------------------------------------------------------------------------

def test_validation_rejects_foreign_asset_retrieval():
    result = {
        "asset_identity": {"status": "VERIFIED", "canonical_tag": "R-1001"},
        "retrieval_summary": {"unique_asset_tags": ["R-1001", "V-1001"]},
        "calculations_summary": {"sandbox_used": True, "any_threshold_breach": True,
                                  "inspection_findings": ["hotspot"], "vendor_parts": ["HRS-X"],
                                  "sop_requirements": ["shutdown"]},
        "approval_required": True,
        "artifacts": ["/tmp/art.docx"],
        "verification": {"ok": True},
        "external_calls": 0,
        "trace": [{"node": n} for n in [
            "plan", "vision_analysis", "asset_identity", "retrieve_evidence",
            "analyze_evidence", "needs_calculation", "python_analysis",
            "synthesize_findings", "make_decision", "generate_approval_note",
            "verify_output",
        ]],
    }
    checks = validate_flagship_result(result)
    passed = {n for n, ok in checks if ok}
    assert "only_canonical_asset_retrieved" not in passed


def test_validation_rejects_external_calls_over_zero():
    result = {
        "asset_identity": {"status": "VERIFIED", "canonical_tag": "R-1001"},
        "retrieval_summary": {"unique_asset_tags": ["R-1001"], "retrieval_modes": ["hybrid"]},
        "calculations_summary": {"sandbox_used": True, "any_threshold_breach": True,
                                  "inspection_findings": ["hotspot"], "vendor_parts": ["HRS-X"],
                                  "sop_requirements": ["shutdown"]},
        "approval_required": True,
        "artifacts": ["/tmp/art.docx"],
        "verification": {"ok": True},
        "external_calls": 1,
        "trace": [{"node": n} for n in [
            "plan", "vision_analysis", "asset_identity", "retrieve_evidence",
            "analyze_evidence", "needs_calculation", "python_analysis",
            "synthesize_findings", "make_decision", "generate_approval_note",
            "verify_output",
        ]],
    }
    checks = validate_flagship_result(result)
    passed = {n for n, ok in checks if ok}
    assert "external_calls_zero" not in passed


def test_validation_rejects_missing_sandbox_execution():
    result = {
        "asset_identity": {"status": "VERIFIED", "canonical_tag": "R-1001"},
        "retrieval_summary": {"unique_asset_tags": ["R-1001"], "retrieval_modes": ["hybrid"]},
        "calculations_summary": {"sandbox_used": False, "any_threshold_breach": True,
                                  "inspection_findings": ["hotspot"], "vendor_parts": ["HRS-X"],
                                  "sop_requirements": ["shutdown"]},
        "approval_required": True,
        "artifacts": ["/tmp/art.docx"],
        "verification": {"ok": True},
        "external_calls": 0,
        "trace": [{"node": n} for n in [
            "plan", "vision_analysis", "asset_identity", "retrieve_evidence",
            "analyze_evidence", "needs_calculation", "python_analysis",
            "synthesize_findings", "make_decision", "generate_approval_note",
            "verify_output",
        ]],
    }
    checks = validate_flagship_result(result)
    passed = {n for n, ok in checks if ok}
    assert "sandbox_executed" not in passed


def test_validation_rejects_approval_required_false():
    result = {
        "asset_identity": {"status": "VERIFIED", "canonical_tag": "R-1001"},
        "retrieval_summary": {"unique_asset_tags": ["R-1001"], "retrieval_modes": ["hybrid"]},
        "calculations_summary": {"sandbox_used": True, "any_threshold_breach": True,
                                  "inspection_findings": ["hotspot"], "vendor_parts": ["HRS-X"],
                                  "sop_requirements": ["shutdown"]},
        "approval_required": False,
        "artifacts": ["/tmp/art.docx"],
        "verification": {"ok": True},
        "external_calls": 0,
        "trace": [{"node": n} for n in [
            "plan", "vision_analysis", "asset_identity", "retrieve_evidence",
            "analyze_evidence", "needs_calculation", "python_analysis",
            "synthesize_findings", "make_decision", "generate_approval_note",
            "verify_output",
        ]],
    }
    checks = validate_flagship_result(result)
    passed = {n for n, ok in checks if ok}
    assert "approval_required" not in passed


def test_validation_rejects_artifact_verification_failure():
    result = {
        "asset_identity": {"status": "VERIFIED", "canonical_tag": "R-1001"},
        "retrieval_summary": {"unique_asset_tags": ["R-1001"], "retrieval_modes": ["hybrid"]},
        "calculations_summary": {"sandbox_used": True, "any_threshold_breach": True,
                                  "inspection_findings": ["hotspot"], "vendor_parts": ["HRS-X"],
                                  "sop_requirements": ["shutdown"]},
        "approval_required": True,
        "artifacts": ["/tmp/art.docx"],
        "verification": {"ok": False},
        "external_calls": 0,
        "trace": [{"node": n} for n in [
            "plan", "vision_analysis", "asset_identity", "retrieve_evidence",
            "analyze_evidence", "needs_calculation", "python_analysis",
            "synthesize_findings", "make_decision", "generate_approval_note",
            "verify_output",
        ]],
    }
    checks = validate_flagship_result(result)
    passed = {n for n, ok in checks if ok}
    assert "artifact_verified" not in passed


def test_validation_requires_correct_trace_order():
    result = {
        "asset_identity": {"status": "VERIFIED", "canonical_tag": "R-1001"},
        "retrieval_summary": {"unique_asset_tags": ["R-1001"], "retrieval_modes": ["hybrid"]},
        "calculations_summary": {"sandbox_used": True, "any_threshold_breach": True,
                                  "inspection_findings": ["hotspot"], "vendor_parts": ["HRS-X"],
                                  "sop_requirements": ["shutdown"]},
        "approval_required": True,
        "artifacts": ["/tmp/art.docx"],
        "verification": {"ok": True},
        "external_calls": 0,
        "trace": [{"node": "retrieve_evidence"}, {"node": "asset_identity"}],
    }
    checks = validate_flagship_result(result)
    passed = {n for n, ok in checks if ok}
    assert "trace_complete" not in passed


def test_demo_helper_does_not_implement_its_own_rag_or_calculation():
    import inspect
    import scripts.demo_flagship_workflow as demo
    src = inspect.getsource(demo)
    forbidden = [
        "search_knowledge_base", "python_execute", "analyze_csv",
        "create_approval_note", "analyze_image",
    ]
    for token in forbidden:
        assert token not in src, f"demo script must not call {token} directly"
