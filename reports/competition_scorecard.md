# Sovereign AI — Competition Evaluation Scorecard

- Commit: `b2ce3cc03db9358a834303a826cec655ab33397e`
- Generated: 2026-09-23T01:58:46Z

## Summary

| Area | Evidence | Metric | Result |
|---|---|---|---|
| Regression | UNIT | ... | passed=304 failed=2 skipped=14 |
| Industrial Golden | INTEGRATION | ... | 10/10 passed |
| Rag Retrieval | INTEGRATION | ... | Hit@1=2 Hit@3=4 Hit@5=6 MRR=0.5556 primary@1=2 |
| Asset Identity | UNIT | ... | 18/18 cases |
| Routing | UNIT | ... | 10/10 correct, runtime=UNAVAILABLE |
| Runtime Resilience | INTEGRATION | ... | 14/14 cases |
| Sovereignty Security | UNIT | ... | 12/12 controls |
| Artifact Sandbox | LIVE | ... | 11/11 passed |
| Flagship Live | LIVE | ... | 14/14 validation checks |

## Details

### Regression

- Evidence level: UNIT
- Passed: 304 / 320
- Failed: 2
- Not available: 0
- Notes: Regression: 304 passed, 2 failed, 14 skipped

### Industrial Golden

- Evidence level: INTEGRATION
- Passed: 10 / 10
- Failed: 0
- Not available: 0
- Notes: Reuses backend/agent/evaluation/evaluate.py against committed live evidence. Ground truth NEVER exposed to agent.

| Case | Result | Detail | Provenance |
|---|---|---|---|
| temperature_breach_detected | PASS | breached_signals=['TI-1001_reactor_temp_C', 'PI-1001_reactor_pressure_bar', 'VI-1001_reactor_vibration_mm_s'] |  |
| pressure_breach_detected | PASS | pressure signal referenced with breach language |  |
| vibration_breach_detected | PASS | vibration signal referenced with breach language |  |
| catalyst_hotspot_detected | PASS | inspection_findings=['catalyst_hotspot', 'thermowell_drift', 'gasket_weep'] |  |
| thermowell_drift_detected | PASS | inspection_findings=['catalyst_hotspot', 'thermowell_drift', 'gasket_weep'] |  |
| gasket_weep_detected | PASS | inspection_findings=['catalyst_hotspot', 'thermowell_drift', 'gasket_weep'] |  |
| vendor_recommendation_detected | PASS | vendor_parts=['HRS-CAT-22', 'HRS-GSK-1001', 'HRS-TW-1001'] |  |
| controlled_shutdown_recommended | PASS | shutdown language present |  |
| corrective_maintenance_recommended | PASS | corrective action language present |  |
| approval_required | PASS | approval_required=True |  |

### Rag Retrieval

- Evidence level: INTEGRATION
- Passed: 6 / 6
- Failed: 0
- Not available: 0
- Notes: Real local HybridRetriever queries. No mocks. Hit@K and MRR calculated from actual rankings.

| Case | Result | Detail | Provenance |
|---|---|---|---|
| query_What_are_the_high-temperature_limits_for | PASS | rank1=sensor_dataset rank2=operating_sop rank3=inspection_report first_relevant=1 primary_at_1=True RR=1.0 mode=hybrid |  |
| query_What_does_the_maintenance_SOP_require_wh | PASS | rank1=preventive_maintenance_sop rank2=operating_sop rank3=vendor_correspondence first_relevant=1 primary_at_1=True RR=1.0 mode=hybrid |  |
| query_What_abnormal_conditions_were_observed_d | PASS | rank1=canonical_profile rank2=sensor_dataset rank3=operating_sop first_relevant=4 primary_at_1=False RR=0.25 mode=hybrid |  |
| query_What_parts_did_the_vendor_recommend? | PASS | rank1=canonical_profile rank2=vendor_correspondence rank3=canonical_profile first_relevant=2 primary_at_1=False RR=0.5 mode=hybrid |  |
| query_Does_the_sensor_data_show_a_threshold_br | PASS | rank1=operating_sop rank2=plant_context rank3=sensor_dataset first_relevant=3 primary_at_1=False RR=0.3333 mode=hybrid |  |
| query_Should_R-1001_be_shut_down? | PASS | rank1=maintenance_approval_note rank2=sensor_dataset rank3=maintenance_approval_note first_relevant=4 primary_at_1=False RR=0.25 mode=hybrid |  |

### Asset Identity

- Evidence level: UNIT
- Passed: 18 / 18
- Failed: 0
- Not available: 0
- Notes: Uses real deterministic resolver. Temp registries used only where required.

| Case | Result | Detail | Provenance |
|---|---|---|---|
| known_exact_asset | PASS | expected='VERIFIED_TEXT_ONLY' actual='VERIFIED_TEXT_ONLY' |  |
| case_whitespace_normalization | PASS | expected='VERIFIED_TEXT_ONLY' actual='VERIFIED_TEXT_ONLY' |  |
| ocr_confusable_not_corrected | PASS | expected='UNKNOWN_ASSET' actual='UNKNOWN_ASSET' |  |
| production_unknown_R1002 | PASS | expected='UNKNOWN_ASSET' actual='UNKNOWN_ASSET' |  |
| temp_registry_known_R1002 | PASS | expected='VERIFIED_TEXT_ONLY' actual='VERIFIED_TEXT_ONLY' |  |
| p2104a_p2104b_distinct | PASS | expected=True actual=True |  |
| vision_exact_match_allows | PASS | expected='VERIFIED' actual='VERIFIED' |  |
| related_tags_no_conflict | PASS | expected='VERIFIED' actual='VERIFIED' |  |
| vision_asset_missing_blocks | PASS | expected='CONFLICT' actual='CONFLICT' |  |
| unknown_requested_asset_blocks | PASS | expected='UNKNOWN_ASSET' actual='UNKNOWN_ASSET' |  |
| empty_asset_tag_blocks | PASS | expected='MISSING_ASSET' actual='MISSING_ASSET' |  |
| identity_blocked_skips_retrieval | PASS | expected='RETRIEVAL_BLOCKED' actual='RETRIEVAL_BLOCKED' |  |
| identity_blocked_no_artifact | PASS | expected='IDENTITY_BLOCKED' actual='IDENTITY_BLOCKED' |  |
| retrieval_uses_canonical_tag | PASS | expected=True actual=True |  |
| foreign_vision_tag_not_primary | PASS | expected=True actual=True |  |
| foreign_asset_hit_dropped | PASS | expected=True actual=True |  |
| raw_vision_tags_preserved | PASS | expected=True actual=True |  |
| identity_no_network_call | PASS | expected='VERIFIED_TEXT_ONLY' actual='VERIFIED_TEXT_ONLY' |  |

### Routing

- Evidence level: UNIT
- Passed: 10 / 10
- Failed: 0
- Not available: 0
- Notes: Routing decision accuracy only. Does not imply model server availability.

| Case | Result | Detail | Provenance |
|---|---|---|---|
| coding_task_routes_to_coder | PASS | expected='qwen-coder' actual='qwen-coder' |  |
| vision_task_routes_to_vision | PASS | expected='vision' actual='vision' |  |
| rag_task_routes_to_general | PASS | expected='general' actual='general' |  |
| multimodal_routes_to_vision_general | PASS | expected=True actual=True |  |
| general_text_routes_to_general | PASS | expected='general' actual='general' |  |
| explicit_code_override_routes_to_coder | PASS | expected='qwen-coder' actual='qwen-coder' |  |
| explicit_vision_override_routes_to_vision | PASS | expected='vision' actual='vision' |  |
| local_only_enforcement | PASS | expected=True actual=True |  |
| missing_capability_raises | PASS | expected=True actual=True |  |
| coding_with_tools_requires_tools | PASS | expected=True actual=True |  |

### Runtime Resilience

- Evidence level: INTEGRATION
- Passed: 14 / 14
- Failed: 0
- Not available: 0
- Notes: Uses existing tests via subprocess. No live model servers required.

| Case | Result | Detail | Provenance |
|---|---|---|---|
| coder_unavailable_503 | PASS | verified by test suite |  |
| coder_transport_503 | PASS | verified by test suite |  |
| coder_timeout_504 | PASS | verified by test suite |  |
| coder_malformed_payload | PASS | verified by test suite |  |
| coder_recovery_after_failure | PASS | verified by test suite |  |
| vision_unavailable_503 | PASS | verified by test suite |  |
| vision_transport_503 | PASS | verified by test suite |  |
| vision_timeout_504 | PASS | verified by test suite |  |
| vision_malformed_upstream_502 | PASS | verified by test suite |  |
| vision_invalid_input_400 | PASS | verified by test suite |  |
| vision_recovery_after_failure | PASS | verified by test suite |  |
| gpu_admission_busy_429 | PASS | verified by test suite |  |
| gpu_admission_retry_after | PASS | verified by test suite |  |
| gpu_lock_recovers | PASS | verified by test suite |  |

### Sovereignty Security

- Evidence level: UNIT
- Passed: 12 / 12
- Failed: 0
- Not available: 0
- Notes: Evaluates implemented controls only. Not whole-machine air-gap certification.

| Case | Result | Detail | Provenance |
|---|---|---|---|
| network_guard_blocks_external | PASS | expected=True actual=True |  |
| loopback_allowed | PASS | expected=True actual=True |  |
| private_local_endpoint_valid | PASS | expected=True actual=True |  |
| malicious_public_endpoint_rejected | PASS | expected=True actual=True |  |
| vision_path_allowlist_rejects_unauthorized | PASS | expected=True actual=True |  |
| sandbox_network_import_blocked | PASS | expected=True actual=True |  |
| sandbox_out_of_tree_write_blocked | PASS | expected=True actual=True |  |
| local_embedding_local_files_only | PASS | expected=True actual=True |  |
| flagship_external_calls_zero | PASS | expected=True actual=True |  |
| identity_no_network | PASS | expected=True actual=True |  |
| general_missing_no_cloud_fallback | PASS | expected=True actual=True |  |
| model_routing_local_only | PASS | expected=True actual=True |  |

### Artifact Sandbox

- Evidence level: LIVE
- Passed: 11 / 11
- Failed: 0
- Not available: 0
- Notes: Uses committed flagship evidence where available. Checks marked LIVE_LOCAL_ARTIFACT require the locally retained DOCX and are not fully reproducible from a clean repository clone.

| Case | Result | Detail | Provenance |
|---|---|---|---|
| sandbox_executes_local_calculation | PASS | expected=True actual=True | COMMITTED_TEST |
| sandbox_network_import_blocked | PASS | expected=True actual=True | COMMITTED_TEST |
| sandbox_timeout_safe | PASS | expected=True actual=True | COMMITTED_TEST |
| flagship_sandbox_used_true | PASS | expected=True actual=True | COMMITTED_JSON |
| flagship_artifact_exists | PASS | expected=True actual=True | COMMITTED_JSON |
| artifact_verifier_passed | PASS | expected=True actual=True | COMMITTED_JSON |
| expected_asset_tag_present | PASS | expected=True actual=True | COMMITTED_JSON |
| source_references_present | PASS | expected=True actual=True | COMMITTED_JSON |
| disclaimer_present | PASS | expected=True actual=True | COMMITTED_JSON |
| draft_pending_human_present | PASS | expected=True actual=True | LIVE_LOCAL_ARTIFACT |
| false_final_approval_absent | PASS | expected=True actual=True | LIVE_LOCAL_ARTIFACT |

### Flagship Live

- Evidence level: LIVE
- Passed: 9 / 9
- Failed: 0
- Not available: 0
- Notes: Read-only from committed reports/flagship_workflow_latest.json. Not re-executed. No new GPU inference.

| Case | Result | Detail | Provenance |
|---|---|---|---|
| asset_R1001 | PASS | expected='R-1001' actual='R-1001' |  |
| identity_verified | PASS | expected='VERIFIED' actual='VERIFIED' |  |
| retrieval_hybrid | PASS | expected='hybrid' actual='hybrid' |  |
| chunks_36 | PASS | expected=36 actual=36 |  |
| sandbox_used_true | PASS | expected=True actual=True |  |
| approval_required_true | PASS | expected=True actual=True |  |
| artifact_verified_true | PASS | expected=True actual=True |  |
| external_calls_zero | PASS | expected=0 actual=0 |  |
| validation_14_14 | PASS | expected=14 actual=14 |  |


## Limitations

- Full industrial corpus currently centers on R-1001.
- Flagship live workflow validated one real P&ID scenario, not all industrial diagrams.
- Qwen2.5-VL 3B may misread small/dense tags.
- General reasoning model is registered in the router but its local runtime is currently unavailable because no general model server is running on localhost:8001 and no local general weights are present.
- RAG currently has hybrid dense + BM25 but no validated active reranker.
- Hybrid retrieval recovers all expected primary evidence within top-5, but some queries rank secondary/context documents above the primary source at rank 1. No reranker is currently active.
- Security controls demonstrate application-level sovereignty; whole-machine physical air-gap depends on deployment/network environment.
- Human approve/reject is not implemented yet.
- Artifact remains DRAFT pending human authorization.
- GPU flagship run used very tight VRAM headroom; do not generalize to arbitrary workloads.
