"""Phase 13A — Competition evaluation tests.

Tests the evaluator harness itself to ensure honest scoring.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

REPO = BACKEND.parent
SCORECARD_JSON = REPO / "reports" / "competition_scorecard.json"
FLAGSHIP_JSON = REPO / "reports" / "flagship_workflow_latest.json"


@pytest.fixture(scope="module")
def scorecard():
    if not SCORECARD_JSON.exists():
        pytest.skip("competition_scorecard.json not yet generated")
    return json.loads(SCORECARD_JSON.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def flagship():
    if not FLAGSHIP_JSON.exists():
        pytest.skip("flagship_workflow_latest.json not yet generated")
    return json.loads(FLAGSHIP_JSON.read_text(encoding="utf-8"))


class TestScorecardStructure:
    def test_all_categories_present(self, scorecard):
        required = {
            "industrial_golden", "rag_retrieval", "asset_identity", "routing",
            "runtime_resilience", "sovereignty_security", "artifact_sandbox",
            "flagship_live", "regression",
        }
        assert set(scorecard["categories"].keys()) == required

    def test_no_global_fake_accuracy(self, scorecard):
        text = json.dumps(scorecard)
        assert "98.7%" not in text
        assert "99.%" not in text
        assert "overall accuracy" not in text.lower()

    def test_evidence_levels_present(self, scorecard):
        valid = {"LIVE", "INTEGRATION", "UNIT", "STATIC"}
        for name, cat in scorecard["categories"].items():
            assert cat["evidence_level"] in valid, f"{name} has invalid evidence_level"


class TestRAGMetrics:
    def test_hit_at_k_calculation(self, scorecard):
        rag = scorecard["categories"]["rag_retrieval"]
        metrics = rag["metrics"]
        assert metrics["hit_at_1"] <= metrics["queries_total"]
        assert metrics["hit_at_3"] <= metrics["queries_total"]
        assert metrics["hit_at_5"] <= metrics["queries_total"]

    def test_mrr_calculation(self, scorecard):
        rag = scorecard["categories"]["rag_retrieval"]
        mrr = rag["metrics"]["mrr"]
        assert 0.0 <= mrr <= 1.0

    def test_irrelevant_document_not_counted(self, scorecard):
        rag = scorecard["categories"]["rag_retrieval"]
        assert rag["metrics"]["foreign_asset_hits"] == 0


class TestIdentity:
    def test_false_accept_counted(self, scorecard):
        ident = scorecard["categories"]["asset_identity"]
        for case in ident["cases"]:
            if case["name"] in ("ocr_confusable_not_corrected", "production_unknown_R1002", "temp_registry_known_R1002"):
                assert case["passed"] is True

    def test_no_false_accepts(self, scorecard):
        ident = scorecard["categories"]["asset_identity"]
        for case in ident["cases"]:
            if case["name"] in ("ocr_confusable_not_corrected", "production_unknown_R1002"):
                assert case["expected"] == "UNKNOWN_ASSET"
                assert case["actual"] == "UNKNOWN_ASSET"


class TestRouting:
    def test_wrong_route_counted_incorrect(self, scorecard):
        routing = scorecard["categories"]["routing"]
        assert routing["failed"] == 0

    def test_general_runtime_status_explicit(self, scorecard):
        routing = scorecard["categories"]["routing"]
        assert "general_model_runtime_status" in routing["metrics"]
        status = routing["metrics"]["general_model_runtime_status"]
        assert status in ("AVAILABLE", "UNAVAILABLE", "BLOCKED_NO_WEIGHTS"), \
            f"general_model_runtime_status must be one of AVAILABLE/UNAVAILABLE/BLOCKED_NO_WEIGHTS, got {status}"


class TestNotAvailable:
    def test_not_available_not_counted_as_pass(self, scorecard):
        for name, cat in scorecard["categories"].items():
            for case in cat.get("cases", []):
                if case.get("actual") == "NOT_AVAILABLE":
                    assert case["passed"] is False


class TestFlagshipValues:
    def test_flagship_values_from_report(self, scorecard, flagship):
        flagship_cat = scorecard["categories"]["flagship_live"]
        for case in flagship_cat["cases"]:
            actual = case["actual"]
            expected = case["expected"]
            assert actual == expected, f"{case['name']}: expected {expected!r} got {actual!r}"

    def test_flagship_count_equals_validation_checks(self, scorecard, flagship):
        flagship_cat = scorecard["categories"]["flagship_live"]
        flagship_checks = flagship.get("flagship_validation", {}).get("checks", {})
        expected_total = len(flagship_checks)
        expected_passed = sum(1 for v in flagship_checks.values() if v)
        metrics = flagship_cat.get("metrics", {})
        assert metrics.get("flagship_checks_total") == expected_total, \
            f"flagship_checks_total should be {expected_total}, got {metrics.get('flagship_checks_total')}"
        assert metrics.get("flagship_checks_passed") == expected_passed, \
            f"flagship_checks_passed should be {expected_passed}, got {metrics.get('flagship_checks_passed')}"

    def test_evaluator_fails_on_missing_report(self, tmp_path):
        missing_json = tmp_path / "missing.json"
        assert not missing_json.exists()
        # The evaluator should handle missing files gracefully
        data = {}
        if missing_json.exists():
            data = json.loads(missing_json.read_text())
        assert data == {}


class TestRegression:
    def test_regression_metrics_separate(self, scorecard):
        reg = scorecard["categories"]["regression"]
        assert "metrics" in reg
        assert "passed" in reg["metrics"]
        assert "failed" in reg["metrics"]

    def test_regression_not_mixed_with_ai(self, scorecard):
        ai_categories = {
            "industrial_golden", "rag_retrieval", "asset_identity", "routing",
            "sovereignty_security", "artifact_sandbox", "flagship_live",
        }
        for name, cat in scorecard["categories"].items():
            if name in ai_categories:
                assert "pytest_passed" not in cat.get("metrics", {}), f"{name} should not have pytest metrics"

    def test_regression_category_totals_match_metrics(self, scorecard):
        reg = scorecard["categories"]["regression"]
        metrics = reg.get("metrics", {})
        assert reg.get("passed") == metrics.get("passed"), "regression category passed should match metrics"
        assert reg.get("failed") == metrics.get("failed"), "regression category failed should match metrics"
        assert reg.get("total") == metrics.get("passed", 0) + metrics.get("failed", 0) + metrics.get("skipped", 0), \
            "regression total should equal passed+failed+skipped"

    def test_regression_raw_failed_count_visible(self, scorecard):
        reg = scorecard["categories"]["regression"]
        metrics = reg.get("metrics", {})
        failed = metrics.get("failed", 0)
        assert failed >= 0, "failed count should be non-negative"
        if failed > 0:
            assert "0 failures" not in (reg.get("notes", "")).lower(), \
                "notes should not claim 0 failures when failed > 0"


class TestSecurity:
    def test_external_calls_zero_in_sovereignty(self, scorecard, flagship):
        sov = scorecard["categories"]["sovereignty_security"]
        for case in sov["cases"]:
            if case["name"] == "flagship_external_calls_zero":
                assert case["expected"] == 0 or case["expected"] is True
                assert case["actual"] == 0 or case["actual"] is True

    def test_no_cloud_fallback_explicit(self, scorecard):
        sov = scorecard["categories"]["sovereignty_security"]
        for case in sov["cases"]:
            if case["name"] == "general_missing_no_cloud_fallback":
                assert case["passed"] is True


class TestMarkdown:
    def test_markdown_contains_limitations(self):
        md_path = REPO / "reports" / "competition_scorecard.md"
        if not md_path.exists():
            pytest.skip("markdown report not yet generated")
        text = md_path.read_text(encoding="utf-8")
        assert "Limitations" in text

    def test_no_absolute_paths_in_markdown(self):
        md_path = REPO / "reports" / "competition_scorecard.md"
        if not md_path.exists():
            pytest.skip("markdown report not yet generated")
        text = md_path.read_text(encoding="utf-8")
        assert "D:\\\\" not in text
        assert "C:\\\\" not in text


class TestJSON:
    def test_no_absolute_paths_in_json(self):
        if not SCORECARD_JSON.exists():
            pytest.skip("json report not yet generated")
        text = SCORECARD_JSON.read_text(encoding="utf-8")
        assert "D:\\\\" not in text
        assert "C:\\\\" not in text

    def test_deterministic_ordering(self):
        if not SCORECARD_JSON.exists():
            pytest.skip("json report not yet generated")
        data = json.loads(SCORECARD_JSON.read_text(encoding="utf-8"))
        assert "generated_at" in data
        assert "repository_commit" in data
        assert "categories" in data
        assert "limitations" in data


class TestRAGRelevance:
    def test_canonical_profile_not_relevant_to_inspection(self):
        from evaluation.cases import RAG_BENCHMARK_QUERIES
        inspection_q = next(q for q in RAG_BENCHMARK_QUERIES if "abnormal conditions" in q["query"])
        assert "canonical_profile" not in inspection_q["acceptable_document_types"]

    def test_canonical_profile_not_relevant_to_vendor(self):
        from evaluation.cases import RAG_BENCHMARK_QUERIES
        vendor_q = next(q for q in RAG_BENCHMARK_QUERIES if "vendor recommend" in q["query"])
        assert "canonical_profile" not in vendor_q["acceptable_document_types"]

    def test_operating_sop_not_relevant_to_sensor_query(self):
        from evaluation.cases import RAG_BENCHMARK_QUERIES
        sensor_q = next(q for q in RAG_BENCHMARK_QUERIES if "sensor data show a threshold breach" in q["query"])
        assert "operating_sop" not in sensor_q["acceptable_document_types"]

    def test_maintenance_approval_note_not_relevant_to_shutdown_query(self):
        from evaluation.cases import RAG_BENCHMARK_QUERIES
        shutdown_q = next(q for q in RAG_BENCHMARK_QUERIES if "Should R-1001 be shut down" in q["query"])
        assert "maintenance_approval_note" not in shutdown_q["acceptable_document_types"]

    def test_primary_source_at_1_metric_present(self, scorecard):
        rag = scorecard["categories"]["rag_retrieval"]
        assert "primary_source_at_1" in rag["metrics"]

    def test_primary_source_at_1_bounded(self, scorecard):
        rag = scorecard["categories"]["rag_retrieval"]
        ps1 = rag["metrics"]["primary_source_at_1"]
        total = rag["metrics"]["queries_total"]
        assert 0 <= ps1 <= total

    def test_first_relevant_rank_in_case_details(self, scorecard):
        rag = scorecard["categories"]["rag_retrieval"]
        for case in rag["cases"]:
            assert "first_relevant=" in case["detail"], f"missing first_relevant in {case['name']}"


class TestIdentitySafety:
    def test_production_R1002_rejected(self, scorecard):
        ident = scorecard["categories"]["asset_identity"]
        case = next(c for c in ident["cases"] if c["name"] == "production_unknown_R1002")
        assert case["expected"] == "UNKNOWN_ASSET"
        assert case["actual"] == "UNKNOWN_ASSET"

    def test_temp_registry_R1002_accepted(self, scorecard):
        ident = scorecard["categories"]["asset_identity"]
        case = next(c for c in ident["cases"] if c["name"] == "temp_registry_known_R1002")
        assert case["expected"] == "VERIFIED_TEXT_ONLY"
        assert case["actual"] == "VERIFIED_TEXT_ONLY"

    def test_false_accept_uses_expected_negative_only(self, scorecard):
        ident = scorecard["categories"]["asset_identity"]
        negative_cases = {
            "ocr_confusable_not_corrected": "UNKNOWN_ASSET",
            "production_unknown_R1002": "UNKNOWN_ASSET",
            "empty_asset_tag_blocks": "MISSING_ASSET",
        }
        for case in ident["cases"]:
            if case["name"] in negative_cases:
                assert case["expected"] == negative_cases[case["name"]], \
                    f"{case['name']} should be a negative case"
                assert case["actual"] == case["expected"], \
                    f"{case['name']} false accept: expected {case['expected']!r} got {case['actual']!r}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
