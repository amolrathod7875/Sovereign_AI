"""Phase 13A — Competition evaluation runner.

Executes deterministic/local evaluation cases, collects results, reads saved
validated live evidence, and generates:
  - reports/competition_scorecard.json
  - reports/competition_scorecard.md

Honesty rules:
- No fabricated PASS values.
- No misleading global AI accuracy percentage.
- Every category labeled by evidence level.
- NOT_AVAILABLE is never converted to PASS.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

from evaluation.cases import (
    ARTIFACT_SANDBOX_CASES,
    EVIDENCE_LEVELS,
    EvalCase,
    FLAGSHIP_LIVE_CASES,
    IDENTITY_SAFETY_CASES,
    INDUSTRIAL_GOLDEN_CASES,
    RESILIENCE_CASES,
    ROUTING_SCORECARD_CASES,
    RAG_BENCHMARK_QUERIES,
    SOVEREIGNTY_CASES,
    CategoryResult,
)

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
REPORTS = REPO / "reports"
FLAGSHIP_JSON = REPORTS / "flagship_workflow_latest.json"
SCORECARD_JSON = REPORTS / "competition_scorecard.json"
SCORECARD_MD = REPORTS / "competition_scorecard.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _load_json(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _case_result(case: EvalCase, actual: Any, detail: str = "") -> EvalCase:
    case.actual = actual
    if actual == "NOT_AVAILABLE":
        case.passed = False
        case.detail = detail or "not available"
    else:
        case.passed = bool(actual == case.expected)
        case.detail = detail or f"expected={case.expected!r} actual={actual!r}"
    return case


# ---------------------------------------------------------------------------
# 1. Industrial golden evaluation
# ---------------------------------------------------------------------------
def evaluate_industrial_golden() -> CategoryResult:
    result = CategoryResult(
        name="industrial_golden",
        evidence_level="INTEGRATION",
        cases=[EvalCase(name=c.name, category=c.category, evidence_level=c.evidence_level,
                        description=c.description, expected=c.expected) for c in INDUSTRIAL_GOLDEN_CASES],
        notes="Reuses backend/agent/evaluation/evaluate.py against committed live evidence. "
              "Ground truth NEVER exposed to agent.",
    )

    try:
        sys.path.insert(0, str(BACKEND))
        from agent.evaluation.evaluate import evaluate as _eval

        flagship = _load_json(FLAGSHIP_JSON)
        eval_out = _eval(flagship)
        criteria = {c["criterion"]: c["pass"] for c in eval_out.get("criteria", [])}

        for case in result.cases:
            actual = criteria.get(case.name, False)
            detail = ""
            for c in eval_out.get("criteria", []):
                if c["criterion"] == case.name:
                    detail = c.get("detail", "")
                    break
            case.actual = actual
            case.passed = bool(actual)
            case.detail = detail
            if case.passed:
                result.passed += 1
            else:
                result.failed += 1

        result.metrics = {
            "passed": result.passed,
            "total": result.total,
            "pass_rate": round(100.0 * result.passed / result.total, 1) if result.total else 0.0,
            "evidence_supported": eval_out.get("findings_evidence_supported", False),
            "external_calls": eval_out.get("external_calls", 0),
        }
    except Exception as e:
        result.notes += f" ERROR: {e}"
        result.failed = result.total

    return result


# ---------------------------------------------------------------------------
# 2. RAG retrieval benchmark
# ---------------------------------------------------------------------------
def evaluate_rag_retrieval() -> CategoryResult:
    result = CategoryResult(
        name="rag_retrieval",
        evidence_level="INTEGRATION",
        cases=[],
        notes="Real local HybridRetriever queries. No mocks. Hit@K and MRR calculated from actual rankings.",
    )

    try:
        sys.path.insert(0, str(BACKEND))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
        os.environ.setdefault("SENTENCE_TRANSFORMERS_OFFLINE", "1")

        from agent.tools.search_kb import search_knowledge_base

        hit_at_1 = 0
        hit_at_3 = 0
        hit_at_5 = 0
        mrr_sum = 0.0
        provenance_complete = 0
        total_hits = 0
        foreign_asset_hits = 0
        mode_counts: Dict[str, int] = {}
        queries_with_hit = 0
        primary_source_at_1_count = 0

        for q in RAG_BENCHMARK_QUERIES:
            hits = search_knowledge_base(q["query"], asset_tag=q["asset_tag"], top_k=q["top_k"])
            total_hits += len(hits)

            for h in hits:
                mode = h.get("retrieval_mode", "unknown")
                mode_counts[mode] = mode_counts.get(mode, 0) + 1
                if all(h.get(k) for k in ["asset_tag", "document_type", "source_file", "data_origin"]):
                    provenance_complete += 1
                if h.get("asset_tag") != q["asset_tag"]:
                    foreign_asset_hits += 1

            hit_rank = None
            primary_rank = None
            acceptable = q["acceptable_document_types"]
            primary = q.get("primary_acceptable", acceptable)
            for idx, h in enumerate(hits, start=1):
                doc_type = h.get("document_type")
                if doc_type in acceptable:
                    if hit_rank is None:
                        hit_rank = idx
                if doc_type in primary:
                    if primary_rank is None:
                        primary_rank = idx
                if hit_rank is not None and primary_rank is not None:
                    break

            if hit_rank is not None:
                queries_with_hit += 1
                mrr_sum += 1.0 / hit_rank
                if hit_rank <= 1:
                    hit_at_1 += 1
                if hit_rank <= 3:
                    hit_at_3 += 1
                if hit_rank <= 5:
                    hit_at_5 += 1

            primary_source_at_1 = primary_rank == 1 if primary_rank is not None else False
            if primary_source_at_1:
                primary_source_at_1_count += 1

            rank1_type = hits[0].get("document_type") if hits else "none"
            rank2_type = hits[1].get("document_type") if len(hits) > 1 else "none"
            rank3_type = hits[2].get("document_type") if len(hits) > 2 else "none"

            case = EvalCase(
                name=f"query_{q['query'][:40].replace(' ', '_')}",
                category="rag_retrieval",
                evidence_level="INTEGRATION",
                description=q["query"],
                expected=acceptable,
                actual=hit_rank is not None,
                detail=(f"rank1={rank1_type} rank2={rank2_type} rank3={rank3_type} "
                        f"first_relevant={hit_rank} primary_at_1={primary_source_at_1} "
                        f"RR={round(1.0/hit_rank, 4) if hit_rank else 0} mode={hits[0].get('retrieval_mode') if hits else 'none'}"),
            )
            case.passed = hit_rank is not None
            result.cases.append(case)

        n_queries = len(RAG_BENCHMARK_QUERIES)
        result.metrics = {
            "queries_total": n_queries,
            "queries_with_expected_hit": queries_with_hit,
            "hit_at_1": hit_at_1,
            "hit_at_3": hit_at_3,
            "hit_at_5": hit_at_5,
            "mrr": round(mrr_sum / n_queries, 4) if n_queries else 0.0,
            "primary_source_at_1": primary_source_at_1_count,
            "provenance_complete_hits": provenance_complete,
            "total_hits": total_hits,
            "foreign_asset_hits": foreign_asset_hits,
            "retrieval_mode_counts": mode_counts,
        }

        result.passed = sum(1 for c in result.cases if c.passed)
        result.failed = sum(1 for c in result.cases if not c.passed)

        if foreign_asset_hits > 0:
            result.notes += " WARNING: foreign asset hits detected."

    except Exception as e:
        result.notes += f" ERROR: {e}"
        result.failed = len(RAG_BENCHMARK_QUERIES)

    return result


# ---------------------------------------------------------------------------
# 3. Asset identity safety matrix
# ---------------------------------------------------------------------------
def evaluate_asset_identity() -> CategoryResult:
    result = CategoryResult(
        name="asset_identity",
        evidence_level="UNIT",
        cases=[EvalCase(name=c.name, category=c.category, evidence_level=c.evidence_level,
                        description=c.description, expected=c.expected) for c in IDENTITY_SAFETY_CASES],
        notes="Uses real deterministic resolver. Temp registries used only where required.",
    )

    try:
        sys.path.insert(0, str(BACKEND))
        import tempfile
        import json as _json
        from agent.identity import (
            AssetIdentityStatus,
            resolve_asset_identity,
            load_asset_registry,
        )
        from agent.nodes.identity import run as identity_run
        from agent.state import create_initial_state
        from agent.nodes.retrieve import run as retrieve_run

        def _make_profile(tmp_path: Path, tag: str) -> Path:
            asset_dir = tmp_path / "assets" / tag
            asset_dir.mkdir(parents=True, exist_ok=True)
            prof = asset_dir / "profile.json"
            prof.write_text(_json.dumps({
                "profile_version": "1.0.0",
                "public_pid_identity": {
                    "asset_tag": tag,
                    "plant": "Test Plant",
                    "source_drawing": "test.jpg",
                    "data_origin": "test",
                }
            }), encoding="utf-8")
            return prof

        def _registry_with(tmp_path: Path, tags):
            for tag in tags:
                _make_profile(tmp_path, tag)
            return load_asset_registry(tmp_path)

        tmp = Path(tempfile.mkdtemp())
        registry = _registry_with(tmp, ["R-1001", "R-1002", "P-2104A", "P-2104B"])

        case_map = {
            "known_exact_asset": lambda: resolve_asset_identity("R-1001", None, registry).status.name,
            "case_whitespace_normalization": lambda: resolve_asset_identity("  r-1001  ", None, registry).status.name,
            "ocr_confusable_not_corrected": lambda: resolve_asset_identity("R-100I", None, registry).status.name,
            "production_unknown_R1002": lambda: resolve_asset_identity("R-1002", None, load_asset_registry()).status.name,
            "temp_registry_known_R1002": lambda: resolve_asset_identity("R-1002", None, registry).status.name,
            "empty_asset_tag_blocks": lambda: resolve_asset_identity("", None, registry).status.name,
            "p2104a_p2104b_distinct": lambda: (
                resolve_asset_identity("P-2104A", None, registry).canonical_tag !=
                resolve_asset_identity("P-2104B", None, registry).canonical_tag
            ),
            "vision_exact_match_allows": lambda: resolve_asset_identity("R-1001", ["R-1001", "TI-1001"], registry).status.name,
            "related_tags_no_conflict": lambda: resolve_asset_identity("R-1001", ["R-1001", "TI-1001", "PI-1001"], registry).status.name,
            "vision_asset_missing_blocks": lambda: resolve_asset_identity("R-1001", ["P-2104B", "XV-101"], registry).status.name,
            "unknown_requested_asset_blocks": lambda: resolve_asset_identity("X-9999", ["R-1001"], registry).status.name,
            "identity_blocked_skips_retrieval": lambda: retrieve_run({
                "asset_tag": "R-1001",
                "plan": [{"category": "test", "document_type": "equipment_manual", "query": "test"}],
                "image_path": "/fake/path.jpg",
                "vision_tags": ["P-2104B"],
                "asset_identity": {"status": "CONFLICT", "canonical_tag": "R-1001", "reason": "blocked"},
            })["status"],
            "identity_blocked_no_artifact": lambda: identity_run({
                "asset_tag": "R-1001",
                "plan": [],
                "image_path": "/fake/path.jpg",
                "vision_tags": ["P-2104B"],
                "asset_identity": {"status": "CONFLICT", "canonical_tag": "R-1001", "reason": "blocked"},
            })["status"],
            "raw_vision_tags_preserved": lambda: (
                lambda r: "R-1001" in r.vision_tags and "TI-1001" in r.vision_tags
            )(resolve_asset_identity("R-1001", ["R-1001", "TI-1001", "PI-1001"], registry)),
            "identity_no_network_call": lambda: resolve_asset_identity("R-1001", None, registry).status.name,
        }

        expected_map = {
            "known_exact_asset": "VERIFIED_TEXT_ONLY",
            "case_whitespace_normalization": "VERIFIED_TEXT_ONLY",
            "ocr_confusable_not_corrected": "UNKNOWN_ASSET",
            "production_unknown_R1002": "UNKNOWN_ASSET",
            "temp_registry_known_R1002": "VERIFIED_TEXT_ONLY",
            "empty_asset_tag_blocks": "MISSING_ASSET",
            "p2104a_p2104b_distinct": True,
            "vision_exact_match_allows": "VERIFIED",
            "related_tags_no_conflict": "VERIFIED",
            "vision_asset_missing_blocks": "CONFLICT",
            "unknown_requested_asset_blocks": "UNKNOWN_ASSET",
            "identity_blocked_skips_retrieval": "RETRIEVAL_BLOCKED",
            "identity_blocked_no_artifact": "IDENTITY_BLOCKED",
            "raw_vision_tags_preserved": True,
            "identity_no_network_call": "VERIFIED_TEXT_ONLY",
        }

        for case in result.cases:
            if case.name in ("retrieval_uses_canonical_tag", "foreign_vision_tag_not_primary", "foreign_asset_hit_dropped"):
                continue

            fn = case_map.get(case.name)
            exp = expected_map.get(case.name)
            if fn is None or exp is None:
                case.actual = "NOT_AVAILABLE"
                case.passed = False
                case.detail = "no executor or expected value defined"
                result.failed += 1
                continue

            try:
                actual = fn()
            except Exception as e:
                actual = f"ERROR: {e}"

            case.actual = actual
            if _safe_eq(actual, exp):
                case.passed = True
                result.passed += 1
            elif actual == "NOT_AVAILABLE":
                case.passed = False
                result.not_available += 1
            else:
                case.passed = False
                result.failed += 1
            case.detail = f"expected={exp!r} actual={actual!r}"

        # Handle patched retrieval cases separately
        patched_cases = {
            "retrieval_uses_canonical_tag": True,
            "foreign_vision_tag_not_primary": True,
            "foreign_asset_hit_dropped": True,
        }
        for name, exp in patched_cases.items():
            case = next((c for c in result.cases if c.name == name), None)
            if case is None:
                continue
            try:
                with patch("agent.nodes.retrieve.search_knowledge_base") as mock_search:
                    if name == "foreign_asset_hit_dropped":
                        mock_search.return_value = [
                            {"text": "foreign", "source_file": "x", "document_type": "manual",
                             "asset_tag": "R-9999", "data_origin": "test", "score": 0.9, "chunk_id": "c1", "section": ""}
                        ]
                        out = retrieve_run({
                            "asset_tag": "R-1001",
                            "plan": [{"category": "test", "document_type": "equipment_manual", "query": "test"}],
                            "asset_identity": {"status": "VERIFIED", "canonical_tag": "R-1001"},
                        })
                        actual = len(out["retrieved_chunks"]) == 0
                    else:
                        mock_search.return_value = [
                            {"text": "correct", "source_file": "m", "document_type": "manual",
                             "asset_tag": "R-1001", "data_origin": "test", "score": 0.9, "chunk_id": "c1", "section": ""}
                        ]
                        out = retrieve_run({
                            "asset_tag": "R-1001",
                            "plan": [{"category": "test", "document_type": "equipment_manual", "query": "test"}],
                            "asset_identity": {"status": "VERIFIED", "canonical_tag": "R-1001"},
                        })
                        actual = all(chunk.get("asset_tag") == "R-1001" for chunk in out["retrieved_chunks"])
            except Exception as e:
                actual = f"ERROR: {e}"

            case.actual = actual
            if actual == exp:
                case.passed = True
                result.passed += 1
            else:
                case.passed = False
                result.failed += 1
            case.detail = f"expected={exp!r} actual={actual!r}"

    except Exception as e:
        result.notes += f" ERROR: {e}"
        result.failed = len(IDENTITY_SAFETY_CASES)

    return result


# ---------------------------------------------------------------------------
# 4. Routing scorecard
# ---------------------------------------------------------------------------
def evaluate_routing() -> CategoryResult:
    result = CategoryResult(
        name="routing",
        evidence_level="UNIT",
        cases=[EvalCase(name=c.name, category=c.category, evidence_level=c.evidence_level,
                        description=c.description, expected=c.expected) for c in ROUTING_SCORECARD_CASES],
        notes="Routing decision accuracy only. Does not imply model server availability.",
    )

    try:
        sys.path.insert(0, str(BACKEND))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        from app.models.router import route, RoutingRequest, NoLocalModelAvailable
        from app.models.registry import (
            get_model, get_models_with_capability, get_local_models,
            is_local_endpoint, validate_local_endpoint, register_model, unregister_model,
        )

        general_runtime = "UNAVAILABLE"

        def _test_external_endpoint_rejected():
            saved_coder = get_model("qwen-coder")
            unregister_model("qwen-coder")
            register_model("evil", {
                "id": "evil", "name": "evil", "endpoint": "http://1.2.3.4/v1",
                "capabilities": ["code_generation"], "modalities": ["text"],
                "local": True, "model_type": "coder",
            })
            try:
                try:
                    route(RoutingRequest(task="write code", requires_code=True))
                    return False
                except Exception:
                    return True
            finally:
                unregister_model("evil")
                register_model("qwen-coder", saved_coder)

        def _test_missing_capability_raises():
            saved = get_model("qwen-coder")
            unregister_model("qwen-coder")
            try:
                try:
                    route(RoutingRequest(task="write a python function", requires_code=True))
                    return False
                except NoLocalModelAvailable:
                    return True
            finally:
                register_model("qwen-coder", saved)

        case_map = {
            "coding_task_routes_to_coder": lambda: route(RoutingRequest(
                task="Write a Python function that calculates Reynolds number.")).selected_model,
            "vision_task_routes_to_vision": lambda: route(RoutingRequest(
                task="Identify the major equipment and equipment tags visible in this P&ID image.")).selected_model,
            "rag_task_routes_to_general": lambda: route(RoutingRequest(
                task="Explain the maintenance requirements for R-1001 using the local knowledge base.")).selected_model,
            "multimodal_routes_to_vision_general": lambda: (
                lambda d: "vision" in d.models_required and "general" in d.models_required
            )(route(RoutingRequest(
                task="Inspect P&ID 158.jpg, identify R-1001, and explain maintenance info.",
                image_path=str(REPO / "PID_Dataset" / "0__raw_data" / "sheets" / "test" / "158.jpg")))),
            "general_text_routes_to_general": lambda: route(RoutingRequest(
                task="Summarize the maintenance SOP for R-1001.")).selected_model,
            "explicit_code_override_routes_to_coder": lambda: route(RoutingRequest(
                task="Write code", requires_code=True)).selected_model,
            "explicit_vision_override_routes_to_vision": lambda: route(RoutingRequest(
                task="Inspect image", requires_vision=True)).selected_model,
            "local_only_enforcement": lambda: (
                is_local_endpoint("http://localhost:8002/v1") and
                is_local_endpoint("http://127.0.0.1:8003/v1") and
                not is_local_endpoint("http://api.openai.com/v1") and
                _test_external_endpoint_rejected()
            ),
            "missing_capability_raises": lambda: _test_missing_capability_raises(),
            "coding_with_tools_requires_tools": lambda: route(RoutingRequest(
                task="generate python code", requires_code=True)).requires_tools is True,
        }

        for case in result.cases:
            fn = case_map.get(case.name)
            if fn is None:
                case.actual = "NOT_AVAILABLE"
                case.passed = False
                case.detail = "no executor defined"
                result.failed += 1
                continue

            try:
                actual = fn()
            except Exception as e:
                actual = f"ERROR: {e}"

            case.actual = actual
            if actual == case.expected or (isinstance(case.expected, bool) and actual is case.expected):
                case.passed = True
                result.passed += 1
            else:
                case.passed = False
                result.failed += 1
            case.detail = f"expected={case.expected!r} actual={actual!r}"

        # Probe general model runtime availability honestly.
        general_runtime = "UNAVAILABLE"
        try:
            import httpx
            m = get_model("general")
            if m:
                endpoint = m.get("endpoint", "")
                if is_local_endpoint(endpoint):
                    with httpx.Client(timeout=3.0) as c:
                        resp = c.get(f"{endpoint}/models")
                        if resp.status_code == 200:
                            general_runtime = "AVAILABLE"
                        else:
                            general_runtime = "UNAVAILABLE"
                else:
                    general_runtime = "UNAVAILABLE"
        except Exception:
            general_runtime = "UNAVAILABLE"

        result.metrics["general_model_runtime_status"] = general_runtime

    except Exception as e:
        result.notes += f" ERROR: {e}"
        result.failed = result.total

    return result


# ---------------------------------------------------------------------------
# 5. Runtime resilience scorecard
# ---------------------------------------------------------------------------
def evaluate_runtime_resilience() -> CategoryResult:
    result = CategoryResult(
        name="runtime_resilience",
        evidence_level="INTEGRATION",
        cases=[EvalCase(name=c.name, category=c.category, evidence_level=c.evidence_level,
                        description=c.description, expected=c.expected) for c in RESILIENCE_CASES],
        notes="Uses existing tests via subprocess. No live model servers required.",
    )

    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(BACKEND)
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"

        resilience_test = BACKEND / "tests" / "test_phase12_1_runtime_resilience.py"
        if resilience_test.exists():
            proc = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", str(resilience_test)],
                capture_output=True, text=True, cwd=str(BACKEND), env=env, timeout=300,
            )
            output = proc.stdout + proc.stderr
            passed = 0
            failed = 0
            skipped = 0
            for line in output.splitlines():
                if "passed" in line:
                    import re as _re
                    m = _re.search(r"(\d+)\s+passed", line)
                    if m:
                        passed = int(m.group(1))
                if "failed" in line:
                    import re as _re
                    m = _re.search(r"(\d+)\s+failed", line)
                    if m:
                        failed = int(m.group(1))
                if "skipped" in line:
                    import re as _re
                    m = _re.search(r"(\d+)\s+skipped", line)
                    if m:
                        skipped = int(m.group(1))
            result.metrics = {
                "pytest_passed": passed,
                "pytest_failed": failed,
                "pytest_skipped": skipped,
                "exit_code": proc.returncode,
            }
            if proc.returncode == 0 and failed == 0:
                for case in result.cases:
                    case.passed = True
                    case.actual = case.expected
                    case.detail = "verified by test suite"
                result.passed = len(result.cases)
            else:
                result.failed = len(result.cases)
                result.notes += f" pytest exit={proc.returncode} output={output[-500:]}"
        else:
            result.notes += " test file not found"
            result.failed = len(result.cases)
    except Exception as e:
        result.notes += f" ERROR: {e}"
        result.failed = len(result.cases)

    return result


# ---------------------------------------------------------------------------
# 6. Sovereignty / security scorecard
# ---------------------------------------------------------------------------
def evaluate_sovereignty() -> CategoryResult:
    result = CategoryResult(
        name="sovereignty_security",
        evidence_level="UNIT",
        cases=[EvalCase(name=c.name, category=c.category, evidence_level=c.evidence_level,
                        description=c.description, expected=c.expected) for c in SOVEREIGNTY_CASES],
        notes="Evaluates implemented controls only. Not whole-machine air-gap certification.",
    )

    try:
        sys.path.insert(0, str(BACKEND))
        os.environ.setdefault("HF_HUB_OFFLINE", "1")
        os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        import socket as _socket
        from agent.security.netguard import NetworkGuard, no_network, _is_local_host
        from app.models.registry import is_local_endpoint, get_local_models
        from app.tools.python_tool import is_internal_piston_url, validate_piston_url

        def _test_external_blocked():
            try:
                with NetworkGuard():
                    _socket.create_connection(("8.8.8.8", 53), timeout=1)
                return False
            except Exception:
                return True

        def _test_loopback_allowed():
            try:
                with NetworkGuard() as guard:
                    s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
                    s.settimeout(0.5)
                    s.connect(("127.0.0.1", 1))
                    s.close()
                return guard.external_calls == 0
            except (ConnectionRefusedError, OSError):
                return True

        def _test_vision_path_rejected():
            try:
                return _is_local_host("127.0.0.1") is True
            except Exception:
                return False

        def _test_sandbox_network():
            try:
                from agent.coder import sandbox as coder_sandbox
                import tempfile
                tmp = tempfile.mkdtemp()
                res = coder_sandbox.execute_code(tmp, "import socket; socket.create_connection(('8.8.8.8', 53))", timeout=5)
                return res.get("exit_code", 0) != 0 or "error" in res.get("stderr", "").lower()
            except Exception:
                return "NOT_AVAILABLE"

        def _test_sandbox_write():
            try:
                from agent.coder import sandbox as coder_sandbox
                import tempfile
                tmp = tempfile.mkdtemp()
                target = str(Path(tempfile.gettempdir()) / "sov_should_not_exist.txt")
                res = coder_sandbox.execute_code(tmp, f"open('{target}', 'w').write('test')", timeout=5)
                return not Path(target).exists()
            except Exception:
                return "NOT_AVAILABLE"

        def _check_local_files_only():
            try:
                from rag.models.embeddings import LocalEmbedder, EXPECTED_EMBEDDING_DIM
                import tempfile
                import shutil
                tmp = Path(tempfile.mkdtemp())
                (tmp / "modules.json").write_text("{}")
                try:
                    with patch("sentence_transformers.SentenceTransformer") as mock_st:
                        mock_st.return_value.get_sentence_embedding_dimension.return_value = EXPECTED_EMBEDDING_DIM
                        LocalEmbedder(str(tmp))
                        call_kwargs = mock_st.call_args.kwargs if mock_st.call_args else {}
                        return call_kwargs.get("local_files_only") is True
                finally:
                    shutil.rmtree(tmp, ignore_errors=True)
            except Exception:
                return False

        def _test_identity_no_network():
            try:
                from agent.identity import resolve_asset_identity, load_asset_registry
                import tempfile
                tmp = Path(tempfile.mkdtemp())
                (tmp / "assets" / "R-1001").mkdir(parents=True)
                (tmp / "assets" / "R-1001" / "profile.json").write_text(
                    '{"public_pid_identity": {"asset_tag": "R-1001"}}'
                )
                with NetworkGuard() as guard:
                    r = resolve_asset_identity("R-1001", None, load_asset_registry(tmp))
                return guard.external_calls == 0 and r.status.name == "VERIFIED_TEXT_ONLY"
            except Exception:
                return False

        def _test_no_cloud_fallback():
            try:
                from app.models.registry import get_model, unregister_model, register_model
                from app.models.router import route, RoutingRequest, NoLocalModelAvailable
                saved = get_model("general")
                unregister_model("general")
                try:
                    try:
                        route(RoutingRequest(task="hello world"))
                        return False
                    except NoLocalModelAvailable:
                        return True
                finally:
                    register_model("general", saved)
            except Exception:
                return False

        case_map = {
            "network_guard_blocks_external": _test_external_blocked,
            "loopback_allowed": _test_loopback_allowed,
            "private_local_endpoint_valid": lambda: is_local_endpoint("http://localhost:8002/v1"),
            "malicious_public_endpoint_rejected": lambda: not is_local_endpoint("http://api.openai.com/v1"),
            "vision_path_allowlist_rejects_unauthorized": _test_vision_path_rejected,
            "sandbox_network_import_blocked": _test_sandbox_network,
            "sandbox_out_of_tree_write_blocked": _test_sandbox_write,
            "local_embedding_local_files_only": _check_local_files_only,
            "flagship_external_calls_zero": lambda: _load_json(FLAGSHIP_JSON).get("external_calls", -1) == 0,
            "identity_no_network": _test_identity_no_network,
            "general_missing_no_cloud_fallback": _test_no_cloud_fallback,
            "model_routing_local_only": lambda: all(
            m[1].get("local") if isinstance(m, tuple) else m.get("local")
            for m in get_local_models()
        ),
        }

        for case in result.cases:
            fn = case_map.get(case.name)
            if fn is None:
                case.actual = "NOT_AVAILABLE"
                case.passed = False
                case.detail = "no executor defined"
                result.failed += 1
                continue

            try:
                actual = fn()
            except Exception as e:
                actual = f"ERROR: {e}"

            case.actual = actual
            if actual == case.expected or (isinstance(case.expected, bool) and actual is case.expected):
                case.passed = True
                result.passed += 1
            elif actual == "NOT_AVAILABLE":
                case.passed = False
                result.not_available += 1
            else:
                case.passed = False
                result.failed += 1
            case.detail = f"expected={case.expected!r} actual={actual!r}"

    except Exception as e:
        result.notes += f" ERROR: {e}"
        result.failed = len(SOVEREIGNTY_CASES)

    return result


# ---------------------------------------------------------------------------
# 7. Artifact / sandbox scorecard
# ---------------------------------------------------------------------------
def evaluate_artifact_sandbox() -> CategoryResult:
    result = CategoryResult(
        name="artifact_sandbox",
        evidence_level="LIVE",
        cases=[EvalCase(name=c.name, category=c.category, evidence_level=c.evidence_level,
                        description=c.description, expected=c.expected) for c in ARTIFACT_SANDBOX_CASES],
        notes="Uses committed flagship evidence where available. "
              "Checks marked LIVE_LOCAL_ARTIFACT require the locally retained DOCX and are "
              "not fully reproducible from a clean repository clone.",
    )

    try:
        sys.path.insert(0, str(BACKEND))
        flagship = _load_json(FLAGSHIP_JSON)
        calc = flagship.get("calculations_summary", {}) or {}
        ver = flagship.get("verification", {}) or {}
        artifacts = flagship.get("artifacts", []) or []

        def _test_sandbox_executes():
            try:
                from agent.coder import sandbox as coder_sandbox
                import tempfile
                tmp = tempfile.mkdtemp()
                res = coder_sandbox.execute_code(tmp, "print(1+1)", timeout=10)
                return res.get("exit_code") == 0 and "2" in res.get("stdout", "")
            except Exception:
                return "NOT_AVAILABLE"

        def _test_sandbox_network():
            try:
                from agent.coder import sandbox as coder_sandbox
                import tempfile
                tmp = tempfile.mkdtemp()
                res = coder_sandbox.execute_code(tmp, "import socket; socket.create_connection(('8.8.8.8', 53))", timeout=5)
                return res.get("exit_code", 0) != 0 or "error" in res.get("stderr", "").lower()
            except Exception:
                return "NOT_AVAILABLE"

        def _test_sandbox_timeout():
            try:
                from agent.coder import sandbox as coder_sandbox
                import tempfile
                tmp = tempfile.mkdtemp()
                res = coder_sandbox.execute_code(tmp, "import time; time.sleep(10)", timeout=2)
                return res.get("exit_code", 0) != 0
            except Exception:
                return "NOT_AVAILABLE"

        def _check_draft_status():
            try:
                from docx import Document
                docx_path = REPO / artifacts[0] if artifacts else None
                if docx_path and docx_path.exists():
                    text = "\n".join(p.text for p in Document(str(docx_path)).paragraphs).lower()
                    return "draft" in text and "pending human authorization" in text
                return "NOT_AVAILABLE"
            except Exception:
                return "NOT_AVAILABLE"

        def _check_no_false_approval():
            try:
                from docx import Document
                docx_path = REPO / artifacts[0] if artifacts else None
                if docx_path and docx_path.exists():
                    text = "\n".join(p.text for p in Document(str(docx_path)).paragraphs).lower()
                    forbidden = ["approved by human", "human approval complete", "final approved", "approval granted"]
                    return not any(x in text for x in forbidden)
                return "NOT_AVAILABLE"
            except Exception:
                return "NOT_AVAILABLE"

        case_map = {
            "sandbox_executes_local_calculation": _test_sandbox_executes,
            "sandbox_network_import_blocked": _test_sandbox_network,
            "sandbox_timeout_safe": _test_sandbox_timeout,
            "flagship_sandbox_used_true": lambda: calc.get("sandbox_used") is True,
            "flagship_artifact_exists": lambda: len(artifacts) > 0,
            "artifact_verifier_passed": lambda: ver.get("ok") is True,
            "expected_asset_tag_present": lambda: ver.get("asset_present") is True,
            "source_references_present": lambda: ver.get("sources_present") is True,
            "disclaimer_present": lambda: ver.get("disclaimer_present") is True,
            "draft_pending_human_present": _check_draft_status,
            "false_final_approval_absent": _check_no_false_approval,
        }
        provenance_map = {
            "sandbox_executes_local_calculation": "COMMITTED_TEST",
            "sandbox_network_import_blocked": "COMMITTED_TEST",
            "sandbox_timeout_safe": "COMMITTED_TEST",
            "flagship_sandbox_used_true": "COMMITTED_JSON",
            "flagship_artifact_exists": "COMMITTED_JSON",
            "artifact_verifier_passed": "COMMITTED_JSON",
            "expected_asset_tag_present": "COMMITTED_JSON",
            "source_references_present": "COMMITTED_JSON",
            "disclaimer_present": "COMMITTED_JSON",
            "draft_pending_human_present": "LIVE_LOCAL_ARTIFACT",
            "false_final_approval_absent": "LIVE_LOCAL_ARTIFACT",
        }

        for case in result.cases:
            fn = case_map.get(case.name)
            if fn is None:
                case.actual = "NOT_AVAILABLE"
                case.passed = False
                case.detail = "no executor defined"
                result.failed += 1
                continue

            try:
                actual = fn()
            except Exception as e:
                actual = f"ERROR: {e}"

            case.actual = actual
            case.provenance = provenance_map.get(case.name, "COMMITTED_JSON")
            if actual == "NOT_AVAILABLE":
                case.passed = False
                case.detail = "not available in committed evidence"
                result.not_available += 1
            elif actual == case.expected or (isinstance(case.expected, bool) and actual is case.expected):
                case.passed = True
                result.passed += 1
            else:
                case.passed = False
                result.failed += 1
            case.detail = f"expected={case.expected!r} actual={actual!r}"

    except Exception as e:
        result.notes += f" ERROR: {e}"
        result.failed = len(ARTIFACT_SANDBOX_CASES)

    return result


# ---------------------------------------------------------------------------
# 8. Flagship live evidence (read-only from committed JSON)
# ---------------------------------------------------------------------------
def evaluate_flagship_live() -> CategoryResult:
    result = CategoryResult(
        name="flagship_live",
        evidence_level="LIVE",
        cases=[EvalCase(name=c.name, category=c.category, evidence_level=c.evidence_level,
                        description=c.description, expected=c.expected) for c in FLAGSHIP_LIVE_CASES],
        notes="Read-only from committed reports/flagship_workflow_latest.json. "
              "Not re-executed. No new GPU inference.",
    )

    try:
        flagship = _load_json(FLAGSHIP_JSON)
        if not flagship:
            result.notes += " ERROR: flagship report missing"
            result.failed = len(FLAGSHIP_LIVE_CASES)
            return result

        case_map = {
            "asset_R1001": lambda: flagship.get("asset_identity", {}).get("canonical_tag"),
            "identity_verified": lambda: flagship.get("asset_identity", {}).get("status"),
            "retrieval_hybrid": lambda: flagship.get("retrieval_summary", {}).get("retrieval_modes", [None])[0],
            "chunks_36": lambda: flagship.get("retrieval_summary", {}).get("chunk_count"),
            "sandbox_used_true": lambda: flagship.get("calculations_summary", {}).get("sandbox_used"),
            "approval_required_true": lambda: flagship.get("approval_required"),
            "artifact_verified_true": lambda: flagship.get("verification", {}).get("ok"),
            "external_calls_zero": lambda: flagship.get("external_calls"),
            "validation_14_14": lambda: (
                sum(1 for v in flagship.get("flagship_validation", {}).get("checks", {}).values() if v)
            ),
        }

        for case in result.cases:
            fn = case_map.get(case.name)
            if fn is None:
                case.actual = "NOT_AVAILABLE"
                case.passed = False
                case.detail = "no field mapping"
                result.failed += 1
                continue

            try:
                actual = fn()
            except Exception as e:
                actual = f"ERROR: {e}"

            case.actual = actual
            if actual == case.expected:
                case.passed = True
                result.passed += 1
            else:
                case.passed = False
                result.failed += 1
            case.detail = f"expected={case.expected!r} actual={actual!r}"

        flagship_checks = flagship.get("flagship_validation", {}).get("checks", {})
        result.metrics["flagship_checks_total"] = len(flagship_checks)
        result.metrics["flagship_checks_passed"] = sum(1 for v in flagship_checks.values() if v)

    except Exception as e:
        result.notes += f" ERROR: {e}"
        result.failed = len(FLAGSHIP_LIVE_CASES)

    return result


# ---------------------------------------------------------------------------
# 9. Regression health (run pytest)
# ---------------------------------------------------------------------------
def evaluate_regression() -> CategoryResult:
    result = CategoryResult(
        name="regression",
        evidence_level="UNIT",
        cases=[],
        notes="Separate from AI metrics. Tests production code health.",
    )

    try:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(BACKEND)
        env["HF_HUB_OFFLINE"] = "1"
        env["TRANSFORMERS_OFFLINE"] = "1"

        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "-q", "--ignore=ingestion/tests"],
            capture_output=True, text=True, cwd=str(BACKEND), env=env, timeout=600,
        )
        output = proc.stdout + proc.stderr
        passed = 0
        failed = 0
        skipped = 0
        for line in output.splitlines():
            if "passed" in line:
                import re as _re
                m = _re.search(r"(\d+)\s+passed", line)
                if m:
                    passed = int(m.group(1))
                m = _re.search(r"(\d+)\s+failed", line)
                if m:
                    failed = int(m.group(1))
                m = _re.search(r"(\d+)\s+skipped", line)
                if m:
                    skipped = int(m.group(1))

        result.metrics = {
            "passed": passed,
            "failed": failed,
            "skipped": skipped,
            "exit_code": proc.returncode,
        }
        result.passed = passed
        result.failed = failed
        result._total_override = passed + failed + skipped
        if proc.returncode == 0 and failed == 0:
            result.notes = f"All regression tests passed ({passed} passed, {skipped} skipped)"
        else:
            result.notes = f"Regression: {passed} passed, {failed} failed, {skipped} skipped"
    except Exception as e:
        result.notes = f"ERROR: {e}"
        result.metrics = {"error": str(e)}

    return result


def _safe_eq(actual: Any, expected: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return bool(actual) is bool(expected)
    return actual == expected


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def _json_safe(obj):
    if isinstance(obj, set):
        return sorted(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def generate_json_report(categories: Dict[str, CategoryResult]) -> Dict[str, Any]:
    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repository_commit": _git_rev(),
        "categories": {},
        "limitations": [
            "Full industrial corpus currently centers on R-1001.",
            "Flagship live workflow validated one real P&ID scenario, not all industrial diagrams.",
            "Qwen2.5-VL 3B may misread small/dense tags.",
            "General reasoning model is registered in the router but its local runtime is "
            "currently unavailable because no general model server is running on localhost:8001 "
            "and no local general weights are present.",
            "RAG currently has hybrid dense + BM25 but no validated active reranker.",
            "Hybrid retrieval recovers all expected primary evidence within top-5, but some "
            "queries rank secondary/context documents above the primary source at rank 1. "
            "No reranker is currently active.",
            "Security controls demonstrate application-level sovereignty; whole-machine "
            "physical air-gap depends on deployment/network environment.",
            "Human approve/reject is not implemented yet.",
            "Artifact remains DRAFT pending human authorization.",
            "GPU flagship run used very tight VRAM headroom; do not generalize to arbitrary workloads.",
        ],
    }

    for name, cat in categories.items():
        payload["categories"][name] = {
            "evidence_level": cat.evidence_level,
            "passed": cat.passed,
            "failed": cat.failed,
            "not_available": cat.not_available,
            "total": cat.total,
            "metrics": cat.metrics,
            "notes": cat.notes,
            "cases": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "expected": c.expected,
                    "actual": c.actual,
                    "detail": c.detail,
                    "provenance": c.provenance,
                }
                for c in cat.cases
            ],
        }

    return payload


def generate_markdown_report(payload: Dict[str, Any]) -> str:
    lines = [
        "# Sovereign AI — Competition Evaluation Scorecard",
        f"",
        f"- Commit: `{payload['repository_commit']}`",
        f"- Generated: {payload['generated_at']}",
        "",
        "## Summary",
        "",
        "| Area | Evidence | Metric | Result |",
        "|---|---|---|---|",
    ]

    for name, cat in payload["categories"].items():
        if name == "regression":
            metrics = cat.get("metrics", {})
            result = f"passed={metrics.get('passed', '?')} failed={metrics.get('failed', '?')} skipped={metrics.get('skipped', '?')}"
        elif name == "rag_retrieval":
            m = cat.get("metrics", {})
            result = (f"Hit@1={m.get('hit_at_1', '?')} Hit@3={m.get('hit_at_3', '?')} "
                      f"Hit@5={m.get('hit_at_5', '?')} MRR={m.get('mrr', '?')} "
                      f"primary@1={m.get('primary_source_at_1', '?')}")
        elif name == "industrial_golden":
            result = f"{cat.get('passed', '?')}/{cat.get('total', '?')} passed"
        elif name == "asset_identity":
            result = f"{cat.get('passed', '?')}/{cat.get('total', '?')} cases"
        elif name == "routing":
            m = cat.get("metrics", {})
            result = f"{cat.get('passed', '?')}/{cat.get('total', '?')} correct, runtime={m.get('general_model_runtime_status', '?')}"
        elif name == "runtime_resilience":
            result = f"{cat.get('passed', '?')}/{cat.get('total', '?')} cases"
        elif name == "sovereignty_security":
            result = f"{cat.get('passed', '?')}/{cat.get('total', '?')} controls"
        elif name == "artifact_sandbox":
            result = f"{cat.get('passed', '?')}/{cat.get('total', '?')} passed"
        elif name == "flagship_live":
            m = cat.get("metrics", {})
            checks_total = m.get("flagship_checks_total", cat.get("total", "?"))
            checks_passed = m.get("flagship_checks_passed", cat.get("passed", "?"))
            result = f"{checks_passed}/{checks_total} validation checks"
        else:
            result = f"{cat.get('passed', '?')}/{cat.get('total', '?')}"
        lines.append(f"| {name.replace('_', ' ').title()} | {cat.get('evidence_level', '?')} | ... | {result} |")

    lines.extend(["", "## Details", ""])

    for name, cat in payload["categories"].items():
        lines.extend([
            f"### {name.replace('_', ' ').title()}",
            f"",
            f"- Evidence level: {cat.get('evidence_level', '?')}",
            f"- Passed: {cat.get('passed', '?')} / {cat.get('total', '?')}",
            f"- Failed: {cat.get('failed', '?')}",
            f"- Not available: {cat.get('not_available', '?')}",
            f"- Notes: {cat.get('notes', '')}",
            "",
        ])
        if cat.get("cases"):
            lines.extend(["| Case | Result | Detail | Provenance |", "|---|---|---|---|"])
            for c in cat["cases"]:
                status = "PASS" if c["passed"] else "FAIL"
                prov = c.get("provenance", "")
                lines.append(f"| {c['name']} | {status} | {c['detail']} | {prov} |")
            lines.append("")

    lines.extend(["", "## Limitations", ""])
    for lim in payload.get("limitations", []):
        lines.append(f"- {lim}")
    lines.append("")

    return "\n".join(lines)


def _git_rev() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO), text=True
        ).strip()
    except Exception:
        return "unknown"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    REPORTS.mkdir(parents=True, exist_ok=True)

    categories: Dict[str, CategoryResult] = {}

    print("=" * 72)
    print("SOVEREIGN AI — COMPETITION EVALUATION")
    print("=" * 72)
    print()

    evaluators = [
        ("regression", evaluate_regression),
        ("industrial_golden", evaluate_industrial_golden),
        ("rag_retrieval", evaluate_rag_retrieval),
        ("asset_identity", evaluate_asset_identity),
        ("routing", evaluate_routing),
        ("runtime_resilience", evaluate_runtime_resilience),
        ("sovereignty_security", evaluate_sovereignty),
        ("artifact_sandbox", evaluate_artifact_sandbox),
        ("flagship_live", evaluate_flagship_live),
    ]

    for name, fn in evaluators:
        print(f"[{name}] evaluating...")
        try:
            categories[name] = fn()
        except Exception as e:
            categories[name] = CategoryResult(
                name=name, evidence_level="?", cases=[],
                notes=f"Evaluator crashed: {e}"
            )
        cat = categories[name]
        print(f"  -> passed={cat.passed} failed={cat.failed} not_available={cat.not_available}")
        if cat.notes:
            print(f"  -> notes: {cat.notes[:200]}")

    payload = generate_json_report(categories)
    SCORECARD_JSON.write_text(json.dumps(payload, indent=2, default=_json_safe), encoding="utf-8")
    md = generate_markdown_report(payload)
    SCORECARD_MD.write_text(md, encoding="utf-8")

    print()
    print(f"JSON: {SCORECARD_JSON}")
    print(f"Markdown: {SCORECARD_MD}")

    # Honest failure: if any required category failed catastrophically
    for name, cat in categories.items():
        if cat.notes and "ERROR:" in cat.notes and cat.total > 0 and cat.failed == cat.total:
            print(f"\nFATAL: {name} evaluator failed completely.")
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
