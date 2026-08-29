"""Tests for the agent's local tools (RAG, document reading, CSV analysis, sandbox, DOCX)."""
import os
from pathlib import Path

import pytest

from agent.tools import (
    search_knowledge_base, read_document, analyze_csv,
    python_execute, create_approval_note, verify_docx,
)
from agent.config import ASSETS_DIR

ASSET = str(ASSETS_DIR)


def test_search_knowledge_base_returns_required_fields():
    res = search_knowledge_base("R-1001 temperature threshold breach", asset_tag="R-1001",
                                document_type="sensor_dataset", top_k=4)
    assert isinstance(res, list) and res, "expected non-empty retrieval"
    for r in res:
        for k in ("text", "source_file", "document_type", "asset_tag", "data_origin", "score"):
            assert k in r, f"missing field {k}"
    # asset_tag filter must be honoured
    assert all(r["asset_tag"] == "R-1001" for r in res)


def test_search_knowledge_base_document_type_filter():
    res = search_knowledge_base("vendor recommended spare parts", asset_tag="R-1001",
                                document_type="vendor_correspondence", top_k=3)
    assert res, "vendor correspondence should be retrievable"
    assert all(r["document_type"] == "vendor_correspondence" for r in res)


def test_read_document_all_formats():
    specs = [
        ("sensors/sensor_dataset.csv", "csv"),
        ("profile.json", "json"),
        ("manual/manual.docx", "docx"),
        ("inspection/inspection_report.pdf", "pdf"),
        ("maintenance/maintenance_history.xlsx", "xlsx"),
        ("correspondence/vendor_correspondence.eml", "eml"),
    ]
    for rel, kind in specs:
        path = os.path.join(ASSET, rel)
        assert os.path.exists(path), path
        out = read_document(path)
        assert out["content"], f"no content extracted from {rel}"
        assert out["num_blocks"] > 0


def test_analyze_csv_detects_breaches():
    r = analyze_csv()
    assert r["any_threshold_breach"] is True
    assert "TI-1001_reactor_temp_C" in r["breached_signals"]
    assert "PI-1001_reactor_pressure_bar" in r["breached_signals"]
    assert "VI-1001_reactor_vibration_mm_s" in r["breached_signals"]
    sig = r["signals"]["TI-1001_reactor_temp_C"]
    assert sig["max"] >= 320.0
    assert sig["n_breach_high"] > 0
    assert sig["first_breach_high"] and sig["last_breach_high"]
    assert sig["min"] <= sig["max"]


def test_python_execute_runs_and_returns_stdout():
    res = python_execute("print('hello'); RESULT = {'x': 1+1}")
    assert res["exit_code"] == 0, res.get("stderr")
    assert "hello" in res["stdout"]
    assert res["result"] == "{\"x\": 2}"


def test_python_execute_blocks_network_import():
    res = python_execute("import socket\nprint('should not happen')")
    assert res["exit_code"] != 0
    assert "Blocked module" in res["stderr"] or "ImportError" in res["stderr"]


def test_python_execute_blocks_out_of_dir_write():
    res = python_execute("open(r'C:\\Windows\\System32\\x.txt', 'w').write('x')")
    assert res["exit_code"] != 0
    assert "PermissionError" in res["stderr"] or "outside allowed" in res["stderr"].lower()


def test_create_and_verify_docx():
    content = {
        "title": "TEST Approval Note",
        "asset_tag": "R-1001",
        "purpose": "test",
        "evidence_summary": ["e1", "e2"],
        "findings": [{"claim": "c", "value": "v"}],
        "threshold_breaches": ["temp breach"],
        "inspection_findings": ["hotspot"],
        "vendor_recommendation": ["HRS-CAT-22"],
        "corrective_action": ["replace catalyst"],
        "approval_request": "approval requested",
        "approval_required": True,
        "source_references": ["assets/R-1001/sensor_dataset.csv"],
    }
    path = create_approval_note(content)
    assert os.path.exists(path)
    report = verify_docx(path)
    assert report["ok"], report["missing_sections"]
    assert report["asset_present"]
    assert report["disclaimer_present"]
    assert report["sources_present"]
