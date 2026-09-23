"""Competition evaluation case definitions.

Each category carries an evidence level and a list of cases.
Cases are executed by ``competition.py`` and scored honestly.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Evidence levels
# ---------------------------------------------------------------------------
EVIDENCE_LEVELS = ("LIVE", "INTEGRATION", "UNIT", "STATIC")


# ---------------------------------------------------------------------------
# Case dataclass
# ---------------------------------------------------------------------------
@dataclass
class EvalCase:
    name: str
    category: str
    evidence_level: str
    description: str
    expected: Any
    actual: Any = None
    passed: bool = False
    detail: str = ""
    provenance: str = ""


# ---------------------------------------------------------------------------
# Category result container
# ---------------------------------------------------------------------------
@dataclass
class CategoryResult:
    name: str
    evidence_level: str
    passed: int = 0
    failed: int = 0
    not_available: int = 0
    cases: List[EvalCase] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)
    notes: str = ""
    _total_override: Optional[int] = field(default=None, repr=False, compare=False)

    @property
    def total(self) -> int:
        if self._total_override is not None:
            return self._total_override
        return len(self.cases)


# ---------------------------------------------------------------------------
# Industrial golden cases (10 criteria from evaluate.py)
# ---------------------------------------------------------------------------
INDUSTRIAL_GOLDEN_CASES = [
    EvalCase(
        name="temperature_breach_detected",
        category="industrial_golden",
        evidence_level="INTEGRATION",
        description="Temperature threshold breach must be detected for R-1001",
        expected=True,
    ),
    EvalCase(
        name="pressure_breach_detected",
        category="industrial_golden",
        evidence_level="INTEGRATION",
        description="Pressure threshold breach must be detected",
        expected=True,
    ),
    EvalCase(
        name="vibration_breach_detected",
        category="industrial_golden",
        evidence_level="INTEGRATION",
        description="Vibration threshold breach must be detected",
        expected=True,
    ),
    EvalCase(
        name="catalyst_hotspot_detected",
        category="industrial_golden",
        evidence_level="INTEGRATION",
        description="Catalyst hotspot inspection finding must be detected",
        expected=True,
    ),
    EvalCase(
        name="thermowell_drift_detected",
        category="industrial_golden",
        evidence_level="INTEGRATION",
        description="Thermowell drift inspection finding must be detected",
        expected=True,
    ),
    EvalCase(
        name="gasket_weep_detected",
        category="industrial_golden",
        evidence_level="INTEGRATION",
        description="Gasket weep inspection finding must be detected",
        expected=True,
    ),
    EvalCase(
        name="vendor_recommendation_detected",
        category="industrial_golden",
        evidence_level="INTEGRATION",
        description="Vendor recommendation must be detected",
        expected=True,
    ),
    EvalCase(
        name="controlled_shutdown_recommended",
        category="industrial_golden",
        evidence_level="INTEGRATION",
        description="Controlled shutdown must be recommended",
        expected=True,
    ),
    EvalCase(
        name="corrective_maintenance_recommended",
        category="industrial_golden",
        evidence_level="INTEGRATION",
        description="Corrective maintenance must be recommended",
        expected=True,
    ),
    EvalCase(
        name="approval_required",
        category="industrial_golden",
        evidence_level="INTEGRATION",
        description="Approval required flag must be set",
        expected=True,
    ),
]

# ---------------------------------------------------------------------------
# RAG benchmark queries (6 categories from rag_evaluation.md)
# ---------------------------------------------------------------------------
RAG_BENCHMARK_QUERIES = [
    {
        "query": "What are the high-temperature limits for R-1001?",
        "asset_tag": "R-1001",
        "acceptable_document_types": {"equipment_manual", "operating_sop", "sensor_dataset"},
        "top_k": 5,
        "primary_acceptable": {"equipment_manual", "operating_sop", "sensor_dataset"},
    },
    {
        "query": "What does the maintenance SOP require when reactor temperature exceeds the high-high threshold?",
        "asset_tag": "R-1001",
        "acceptable_document_types": {"preventive_maintenance_sop", "operating_sop"},
        "top_k": 5,
        "primary_acceptable": {"preventive_maintenance_sop", "operating_sop"},
    },
    {
        "query": "What abnormal conditions were observed during the latest inspection?",
        "asset_tag": "R-1001",
        "acceptable_document_types": {"inspection_report"},
        "top_k": 5,
        "primary_acceptable": {"inspection_report"},
    },
    {
        "query": "What parts did the vendor recommend?",
        "asset_tag": "R-1001",
        "acceptable_document_types": {"vendor_correspondence"},
        "top_k": 5,
        "primary_acceptable": {"vendor_correspondence"},
    },
    {
        "query": "Does the sensor data show a threshold breach?",
        "asset_tag": "R-1001",
        "acceptable_document_types": {"sensor_dataset"},
        "top_k": 5,
        "primary_acceptable": {"sensor_dataset"},
    },
    {
        "query": "Should R-1001 be shut down?",
        "asset_tag": "R-1001",
        "acceptable_document_types": {"operating_sop", "preventive_maintenance_sop", "inspection_report"},
        "top_k": 5,
        "primary_acceptable": {"operating_sop", "preventive_maintenance_sop"},
    },
]

# ---------------------------------------------------------------------------
# Asset identity safety matrix (12 cases)
# ---------------------------------------------------------------------------
IDENTITY_SAFETY_CASES = [
    EvalCase(name="known_exact_asset", category="asset_identity", evidence_level="UNIT",
             description="Known exact asset resolves", expected="VERIFIED_TEXT_ONLY"),
    EvalCase(name="case_whitespace_normalization", category="asset_identity", evidence_level="UNIT",
             description="Case/whitespace normalization resolves safely", expected="VERIFIED_TEXT_ONLY"),
    EvalCase(name="ocr_confusable_not_corrected", category="asset_identity", evidence_level="UNIT",
             description="OCR-confusable tag is NOT corrected", expected="UNKNOWN_ASSET"),
    EvalCase(name="production_unknown_R1002", category="asset_identity", evidence_level="UNIT",
             description="Production registry does not contain R-1002 -> UNKNOWN_ASSET", expected="UNKNOWN_ASSET"),
    EvalCase(name="temp_registry_known_R1002", category="asset_identity", evidence_level="UNIT",
             description="Temp registry containing R-1002 resolves R-1002 -> VERIFIED_TEXT_ONLY", expected="VERIFIED_TEXT_ONLY"),
    EvalCase(name="p2104a_p2104b_distinct", category="asset_identity", evidence_level="UNIT",
             description="P-2104A and P-2104B stay distinct", expected=True),
    EvalCase(name="vision_exact_match_allows", category="asset_identity", evidence_level="UNIT",
             description="Vision exact match allows workflow", expected="VERIFIED"),
    EvalCase(name="related_tags_no_conflict", category="asset_identity", evidence_level="UNIT",
             description="Related tags do not create conflict", expected="VERIFIED"),
    EvalCase(name="vision_asset_missing_blocks", category="asset_identity", evidence_level="UNIT",
             description="Vision asset missing causes block", expected="CONFLICT"),
    EvalCase(name="unknown_requested_asset_blocks", category="asset_identity", evidence_level="UNIT",
             description="Unknown requested asset blocks retrieval", expected="UNKNOWN_ASSET"),
    EvalCase(name="empty_asset_tag_blocks", category="asset_identity", evidence_level="UNIT",
             description="Empty asset tag is rejected", expected="MISSING_ASSET"),
    EvalCase(name="identity_blocked_skips_retrieval", category="asset_identity", evidence_level="INTEGRATION",
             description="Identity-blocked graph does NOT call search_knowledge_base", expected="RETRIEVAL_BLOCKED"),
    EvalCase(name="identity_blocked_no_artifact", category="asset_identity", evidence_level="INTEGRATION",
             description="Identity-blocked graph does NOT generate artifact", expected="IDENTITY_BLOCKED"),
    EvalCase(name="retrieval_uses_canonical_tag", category="asset_identity", evidence_level="INTEGRATION",
             description="Retrieval uses canonical tag only", expected=True),
    EvalCase(name="foreign_vision_tag_not_primary", category="asset_identity", evidence_level="INTEGRATION",
             description="Foreign vision tag is NOT used as primary RAG query", expected=True),
    EvalCase(name="foreign_asset_hit_dropped", category="asset_identity", evidence_level="INTEGRATION",
             description="Foreign-asset retrieval hit is dropped", expected=True),
    EvalCase(name="raw_vision_tags_preserved", category="asset_identity", evidence_level="UNIT",
             description="Raw vision tags remain preserved for provenance", expected=True),
    EvalCase(name="identity_no_network_call", category="asset_identity", evidence_level="UNIT",
             description="Identity resolution needs no network", expected="VERIFIED_TEXT_ONLY"),
]

# ---------------------------------------------------------------------------
# Routing scorecard cases (10+ cases)
# ---------------------------------------------------------------------------
ROUTING_SCORECARD_CASES = [
    EvalCase(name="coding_task_routes_to_coder", category="routing", evidence_level="UNIT",
             description="Python coding task routes to qwen-coder", expected="qwen-coder"),
    EvalCase(name="vision_task_routes_to_vision", category="routing", evidence_level="UNIT",
             description="Image/P&ID inspection routes to vision", expected="vision"),
    EvalCase(name="rag_task_routes_to_general", category="routing", evidence_level="UNIT",
             description="R-1001 SOP question routes to general with RAG", expected="general"),
    EvalCase(name="multimodal_routes_to_vision_general", category="routing", evidence_level="UNIT",
             description="P&ID + knowledge base routes to vision + general", expected=True),
    EvalCase(name="general_text_routes_to_general", category="routing", evidence_level="UNIT",
             description="General text question routes to general", expected="general"),
    EvalCase(name="explicit_code_override_routes_to_coder", category="routing", evidence_level="UNIT",
             description="Explicit requires_code override routes to coder", expected="qwen-coder"),
    EvalCase(name="explicit_vision_override_routes_to_vision", category="routing", evidence_level="UNIT",
             description="Explicit requires_vision override routes to vision", expected="vision"),
    EvalCase(name="local_only_enforcement", category="routing", evidence_level="UNIT",
             description="Local-only enforcement rejects external endpoints", expected=True),
    EvalCase(name="missing_capability_raises", category="routing", evidence_level="UNIT",
             description="Missing local capability raises NoLocalModelAvailable", expected=True),
    EvalCase(name="coding_with_tools_requires_tools", category="routing", evidence_level="UNIT",
             description="Coding + tools sets requires_tools", expected=True),
]

# ---------------------------------------------------------------------------
# Runtime resilience cases
# ---------------------------------------------------------------------------
RESILIENCE_CASES = [
    EvalCase(name="coder_unavailable_503", category="runtime_resilience", evidence_level="INTEGRATION",
             description="Coder unavailable -> 503", expected=503),
    EvalCase(name="coder_transport_503", category="runtime_resilience", evidence_level="INTEGRATION",
             description="Coder transport failure -> 503", expected=503),
    EvalCase(name="coder_timeout_504", category="runtime_resilience", evidence_level="INTEGRATION",
             description="Coder timeout -> 504", expected=504),
    EvalCase(name="coder_malformed_payload", category="runtime_resilience", evidence_level="INTEGRATION",
             description="Coder malformed payload -> controlled failure", expected="CONTROLLED_FAILURE"),
    EvalCase(name="coder_recovery_after_failure", category="runtime_resilience", evidence_level="INTEGRATION",
             description="Coder recovery after failure -> 200", expected=200),
    EvalCase(name="vision_unavailable_503", category="runtime_resilience", evidence_level="INTEGRATION",
             description="Vision unavailable -> 503", expected=503),
    EvalCase(name="vision_transport_503", category="runtime_resilience", evidence_level="INTEGRATION",
             description="Vision transport failure -> 503", expected=503),
    EvalCase(name="vision_timeout_504", category="runtime_resilience", evidence_level="INTEGRATION",
             description="Vision timeout -> 504", expected=504),
    EvalCase(name="vision_malformed_upstream_502", category="runtime_resilience", evidence_level="INTEGRATION",
             description="Vision malformed upstream -> 502", expected=502),
    EvalCase(name="vision_invalid_input_400", category="runtime_resilience", evidence_level="INTEGRATION",
             description="Vision invalid input -> 400", expected=400),
    EvalCase(name="vision_recovery_after_failure", category="runtime_resilience", evidence_level="INTEGRATION",
             description="Vision recovery after failure -> 200", expected=200),
    EvalCase(name="gpu_admission_busy_429", category="runtime_resilience", evidence_level="INTEGRATION",
             description="GPU admission busy -> 429", expected=429),
    EvalCase(name="gpu_admission_retry_after", category="runtime_resilience", evidence_level="INTEGRATION",
             description="GPU admission 429 includes Retry-After", expected="5"),
    EvalCase(name="gpu_lock_recovers", category="runtime_resilience", evidence_level="INTEGRATION",
             description="GPU lock recovers after request", expected=True),
]

# ---------------------------------------------------------------------------
# Sovereignty / security cases
# ---------------------------------------------------------------------------
SOVEREIGNTY_CASES = [
    EvalCase(name="network_guard_blocks_external", category="sovereignty_security", evidence_level="INTEGRATION",
             description="NetworkGuard blocks public external socket", expected=True),
    EvalCase(name="loopback_allowed", category="sovereignty_security", evidence_level="INTEGRATION",
             description="Loopback allowed through guard", expected=True),
    EvalCase(name="private_local_endpoint_valid", category="sovereignty_security", evidence_level="UNIT",
             description="Private/local endpoint validation works", expected=True),
    EvalCase(name="malicious_public_endpoint_rejected", category="sovereignty_security", evidence_level="UNIT",
             description="Malicious public model endpoint rejected", expected=True),
    EvalCase(name="vision_path_allowlist_rejects_unauthorized", category="sovereignty_security", evidence_level="UNIT",
             description="Vision path allow-list rejects unauthorized path", expected=True),
    EvalCase(name="sandbox_network_import_blocked", category="sovereignty_security", evidence_level="INTEGRATION",
             description="Sandbox network import blocked", expected=True),
    EvalCase(name="sandbox_out_of_tree_write_blocked", category="sovereignty_security", evidence_level="INTEGRATION",
             description="Sandbox out-of-tree write blocked", expected=True),
    EvalCase(name="local_embedding_local_files_only", category="sovereignty_security", evidence_level="UNIT",
             description="Local embedding uses local_files_only", expected=True),
    EvalCase(name="flagship_external_calls_zero", category="sovereignty_security", evidence_level="LIVE",
             description="Flagship evidence external_calls = 0", expected=True),
    EvalCase(name="identity_no_network", category="sovereignty_security", evidence_level="UNIT",
             description="Identity resolution needs no network", expected=True),
    EvalCase(name="general_missing_no_cloud_fallback", category="sovereignty_security", evidence_level="UNIT",
             description="General missing does not trigger cloud fallback", expected=True),
    EvalCase(name="model_routing_local_only", category="sovereignty_security", evidence_level="UNIT",
             description="Model routing only accepts local endpoints", expected=True),
]

# ---------------------------------------------------------------------------
# Artifact / sandbox cases
# ---------------------------------------------------------------------------
ARTIFACT_SANDBOX_CASES = [
    EvalCase(name="sandbox_executes_local_calculation", category="artifact_sandbox", evidence_level="INTEGRATION",
             description="Sandbox executes basic local calculation", expected=True),
    EvalCase(name="sandbox_network_import_blocked", category="artifact_sandbox", evidence_level="INTEGRATION",
             description="Sandbox network import blocked", expected=True),
    EvalCase(name="sandbox_timeout_safe", category="artifact_sandbox", evidence_level="INTEGRATION",
             description="Sandbox timeout behaves safely", expected=True),
    EvalCase(name="flagship_sandbox_used_true", category="artifact_sandbox", evidence_level="LIVE",
             description="Flagship sandbox_used = true from live report", expected=True),
    EvalCase(name="flagship_artifact_exists", category="artifact_sandbox", evidence_level="LIVE",
             description="Flagship artifact exists in saved live result", expected=True),
    EvalCase(name="artifact_verifier_passed", category="artifact_sandbox", evidence_level="LIVE",
             description="Artifact verifier passed (verification.ok)", expected=True),
    EvalCase(name="expected_asset_tag_present", category="artifact_sandbox", evidence_level="LIVE",
             description="Expected asset tag present in artifact", expected=True),
    EvalCase(name="source_references_present", category="artifact_sandbox", evidence_level="LIVE",
             description="Source references present in artifact", expected=True),
    EvalCase(name="disclaimer_present", category="artifact_sandbox", evidence_level="LIVE",
             description="Disclaimer present in artifact", expected=True),
    EvalCase(name="draft_pending_human_present", category="artifact_sandbox", evidence_level="LIVE",
             description="DRAFT/pending-human state present", expected=True),
    EvalCase(name="false_final_approval_absent", category="artifact_sandbox", evidence_level="LIVE",
             description="False final approval absent", expected=True),
]

# ---------------------------------------------------------------------------
# Flagship live evidence cases (read from committed JSON)
# ---------------------------------------------------------------------------
FLAGSHIP_LIVE_CASES = [
    EvalCase(name="asset_R1001", category="flagship_live", evidence_level="LIVE",
             description="Asset is R-1001", expected="R-1001"),
    EvalCase(name="identity_verified", category="flagship_live", evidence_level="LIVE",
             description="Identity status is VERIFIED", expected="VERIFIED"),
    EvalCase(name="retrieval_hybrid", category="flagship_live", evidence_level="LIVE",
             description="Retrieval mode is hybrid", expected="hybrid"),
    EvalCase(name="chunks_36", category="flagship_live", evidence_level="LIVE",
             description="Chunk count is 36", expected=36),
    EvalCase(name="sandbox_used_true", category="flagship_live", evidence_level="LIVE",
             description="Sandbox used is true", expected=True),
    EvalCase(name="approval_required_true", category="flagship_live", evidence_level="LIVE",
             description="Approval required is true", expected=True),
    EvalCase(name="artifact_verified_true", category="flagship_live", evidence_level="LIVE",
             description="Artifact verification ok is true", expected=True),
    EvalCase(name="external_calls_zero", category="flagship_live", evidence_level="LIVE",
             description="External calls is 0", expected=0),
    EvalCase(name="validation_14_14", category="flagship_live", evidence_level="LIVE",
             description="Validation checks are 14/14", expected=14),
]
