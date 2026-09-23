"""Judge Mode service layer.

Read-only aggregation of:
  - LIVE system state (backend/app/api/system.py)
  - LIVE_PERSISTENT governance (backend/governance/*)
  - COMMITTED_HISTORICAL_EVIDENCE (reports/flagship_workflow_latest.json)
  - FROZEN_EVALUATION_SNAPSHOT (reports/competition_scorecard.json)
"""
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
FLAGSHIP_REPORT = REPO_ROOT / "reports" / "flagship_workflow_latest.json"
SCORECARD_REPORT = REPO_ROOT / "reports" / "competition_scorecard.json"

LIVE = "LIVE"
LIVE_PERSISTENT = "LIVE_PERSISTENT"
COMMITTED_HISTORICAL_EVIDENCE = "COMMITTED_HISTORICAL_EVIDENCE"
FROZEN_EVALUATION_SNAPSHOT = "FROZEN_EVALUATION_SNAPSHOT"
UNAVAILABLE = "UNAVAILABLE"


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _git_rev_parse_head() -> Optional[str]:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip() or None
    except Exception:
        return None


def _load_json_report(path: Path) -> tuple[Optional[dict], Optional[str]]:
    try:
        if not path.is_file():
            return None, "report file not found"
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        return data, None
    except json.JSONDecodeError:
        return None, "malformed report file"
    except OSError:
        return None, "report file unreadable"
    except Exception as e:
        logger.debug("unexpected report load error: %s", e)
        return None, "report load error"


class JudgeService:
    def __init__(self) -> None:
        self.repo_root = REPO_ROOT

    async def get_overview(self) -> Dict[str, Any]:
        generated_at = _utcnow()
        repository_commit = _git_rev_parse_head()

        runtime = await self._get_runtime()
        governance = self._get_governance()
        latest_terminal = self._get_latest_terminal_run(governance)
        flagship, _ = self._get_flagship()
        evaluation, _ = self._get_evaluation()

        return {
            "generated_at": generated_at,
            "repository": {
                "commit": repository_commit,
            },
            "runtime": runtime,
            "governance": governance,
            "latest_terminal_run": latest_terminal,
            "flagship": flagship,
            "evaluation": evaluation,
            "claim_boundaries": self._get_claim_boundaries(runtime),
        }

    async def _get_runtime(self) -> Dict[str, Any]:
        from app.api.system import get_system_status
        try:
            status = await get_system_status()
            data = status.model_dump()
            components = data.get("components", [])
            repo_root = str(self.repo_root)
            for component in components:
                for key in ("detail", "endpoint"):
                    value = component.get(key)
                    if isinstance(value, str) and repo_root in value:
                        component[key] = value.replace(repo_root, "").lstrip("\\/")
            return {
                "source_type": LIVE,
                "sovereign_mode": data.get("sovereign"),
                "gpu": data.get("gpu"),
                "components": components,
                "external_api_calls": data.get("external_api_calls", 0),
                "blocked_connections": data.get("blocked_connections", 0),
                "uptime_seconds": data.get("uptime_seconds", 0),
            }
        except Exception as e:
            logger.error("runtime probe failed: %s", e)
            return {
                "source_type": LIVE,
                "error": str(e)[:200],
                "sovereign_mode": None,
                "components": [],
                "external_api_calls": 0,
                "blocked_connections": 0,
                "uptime_seconds": 0,
            }

    def _get_governance(self) -> Dict[str, Any]:
        from governance.approval import ApprovalService
        from governance.receipt_chain import ReceiptChainService

        try:
            approval_svc = ApprovalService()
            pending = approval_svc.list_pending()
            chain_svc = ReceiptChainService(db_path=approval_svc.db_path)
            chain_result = chain_svc.verify_chain()
            head = chain_svc.get_head()

            pending_summaries = []
            for r in pending[:10]:
                pending_summaries.append({
                    "run_id": r.run_id,
                    "asset_tag": r.asset_tag,
                    "decision": r.decision,
                    "status": r.status,
                    "created_at": r.created_at,
                    "artifact_sha256": r.artifact_sha256,
                    "identity_status": r.identity_status,
                    "external_calls": r.external_calls,
                })

            return {
                "source_type": LIVE_PERSISTENT,
                "pending_review_count": len(pending),
                "pending_reviews": pending_summaries,
                "chain": {
                    "entry_count": head.get("entry_count", 0),
                    "head_sequence": head.get("head_sequence"),
                    "head_run_id": head.get("head_run_id"),
                    "head_chain_sha256": head.get("head_chain_sha256"),
                    "valid": chain_result.get("valid", True),
                    "status": chain_result.get("status", "VALID"),
                    "checks": chain_result.get("checks", {}),
                    "violations": chain_result.get("violations", []),
                },
            }
        except Exception as e:
            logger.error("governance probe failed: %s", e)
            return {
                "source_type": LIVE_PERSISTENT,
                "pending_review_count": 0,
                "pending_reviews": [],
                "chain": {
                    "entry_count": 0,
                    "head_sequence": None,
                    "head_run_id": None,
                    "head_chain_sha256": None,
                    "valid": True,
                    "status": "VALID",
                    "checks": {},
                    "violations": [],
                },
                "error": str(e)[:200],
            }

    def _get_latest_terminal_run(self, governance: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        chain = governance.get("chain", {})
        head_run_id = chain.get("head_run_id")
        if not head_run_id:
            return None
        return self.get_run_detail(head_run_id)

    def _get_flagship(self) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        data, error = _load_json_report(FLAGSHIP_REPORT)
        if error:
            return {
                "source_type": UNAVAILABLE,
                "available": False,
                "reason": error,
            }, error

        checks = data.get("flagship_validation", {}).get("checks", {})
        total_checks = len(checks)
        passed_checks = sum(1 for v in checks.values() if v is True)

        return {
            "source_type": COMMITTED_HISTORICAL_EVIDENCE,
            "source_file": "reports/flagship_workflow_latest.json",
            "timestamp": data.get("timestamp"),
            "run_id": data.get("run_id"),
            "status": data.get("status"),
            "asset": data.get("asset_identity", {}).get("canonical_tag"),
            "identity_status": data.get("asset_identity", {}).get("status"),
            "retrieval_mode": self._first_or_none(data.get("retrieval_summary", {}).get("retrieval_modes")),
            "chunk_count": data.get("retrieval_summary", {}).get("chunk_count"),
            "sandbox_used": data.get("calculations_summary", {}).get("sandbox_used"),
            "approval_required": data.get("approval_required"),
            "artifact_verified": data.get("verification", {}).get("ok"),
            "external_calls": data.get("external_calls", 0),
            "validation_checks_passed": passed_checks,
            "validation_checks_total": total_checks,
            "failed_checks": [k for k, v in checks.items() if v is not True],
        }, None

    def _get_evaluation(self) -> tuple[Optional[Dict[str, Any]], Optional[str]]:
        data, error = _load_json_report(SCORECARD_REPORT)
        if error:
            return {
                "source_type": UNAVAILABLE,
                "available": False,
                "reason": error,
            }, error

        cats = data.get("categories", {})

        def _cat(name: str, include_metrics: bool = False) -> Dict[str, Any]:
            c = cats.get(name, {})
            result = {
                "passed": c.get("passed"),
                "total": c.get("total"),
            }
            if include_metrics:
                metrics = c.get("metrics")
                if metrics:
                    result["metrics"] = metrics
            return result

        def _rag_metrics(name: str) -> Dict[str, Any]:
            c = cats.get(name, {}).get("metrics", {})
            return {
                "queries_total": c.get("queries_total"),
                "hit_at_1": c.get("hit_at_1"),
                "hit_at_3": c.get("hit_at_3"),
                "hit_at_5": c.get("hit_at_5"),
                "mrr": c.get("mrr"),
                "primary_source_at_1": c.get("primary_source_at_1"),
                "provenance_complete_hits": c.get("provenance_complete_hits"),
                "total_hits": c.get("total_hits"),
                "foreign_asset_hits": c.get("foreign_asset_hits"),
            }

        flagship_metrics = cats.get("flagship_live", {}).get("metrics", {})
        flagship_passed = flagship_metrics.get("flagship_checks_passed")
        flagship_total = flagship_metrics.get("flagship_checks_total")

        regression = cats.get("regression", {})
        regression_metrics = regression.get("metrics", {})

        return {
            "source_type": FROZEN_EVALUATION_SNAPSHOT,
            "source_file": "reports/competition_scorecard.json",
            "historical_snapshot": True,
            "generated_at": data.get("generated_at"),
            "source_repository_commit": data.get("repository_commit"),
            "matches_current_head": data.get("repository_commit") == _git_rev_parse_head(),
            "industrial": _cat("industrial_golden"),
            "rag": _rag_metrics("rag_retrieval"),
            "asset_identity": _cat("asset_identity"),
            "routing": _cat("routing", include_metrics=True),
            "runtime_resilience": _cat("runtime_resilience"),
            "sovereignty_security": _cat("sovereignty_security"),
            "artifact_sandbox": _cat("artifact_sandbox"),
            "flagship": {
                "checks_passed": flagship_passed,
                "checks_total": flagship_total,
            },
            "regression_snapshot": {
                "passed": regression_metrics.get("passed"),
                "failed": regression_metrics.get("failed"),
                "skipped": regression_metrics.get("skipped"),
                "total": regression.get("total"),
                "historical_snapshot": True,
                "source_generated_at": data.get("generated_at"),
                "source_repository_commit": data.get("repository_commit"),
            },
        }, None

    def _get_claim_boundaries(self, runtime: Dict[str, Any]) -> Dict[str, Any]:
        components = runtime.get("components", [])
        general_runtime = "UNAVAILABLE"
        for c in components:
            if c.get("id") == "general":
                general_runtime = c.get("status", "UNAVAILABLE")
                break

        return {
            "reviewer_identity_authenticated": False,
            "whole_machine_airgap_certified": False,
            "receipt_chain_tamper_proof": False,
            "external_trust_anchor_present": False,
            "digital_signature_present": False,
            "general_runtime_status": general_runtime,
        }

    def get_run_detail(self, run_id: str) -> Optional[Dict[str, Any]]:
        from governance.approval import (
            ApprovalService,
            ApprovalNotFoundError,
            ApprovalStatus,
        )
        from governance.receipt import ReceiptNotFoundError, ReceiptService
        from governance.receipt_chain import ReceiptChainService

        approval_svc = ApprovalService()
        try:
            record = approval_svc.get_record(run_id)
        except ApprovalNotFoundError:
            return None

        snapshot = record.snapshot
        asset_identity = snapshot.get("asset_identity") or {}
        retrieval = snapshot.get("retrieval_summary") or {}
        calculations = snapshot.get("calculations_summary") or {}
        routing = snapshot.get("routing") or {}
        trace = snapshot.get("trace") or []
        vision_evidence = snapshot.get("vision_evidence") or []
        external_calls = record.external_calls

        executed_nodes = []
        for entry in trace:
            if isinstance(entry, dict):
                node = entry.get("node") or entry.get("name") or entry.get("step")
                if node:
                    executed_nodes.append(str(node))

        receipt = None
        receipt_available = False
        receipt_verification = {
            "valid": False,
            "checks": {"receipt_exists": False},
            "receipt_sha256": None,
        }
        model_execution = {"recorded_models": [], "status": "NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE"}
        sovereignty = {
            "external_calls_recorded": external_calls,
            "network_guard_scope": "application-level agent run",
            "whole_machine_airgap_certified": False,
        }
        artifact_info = {
            "logical_path": self._logical_path(record.artifact_path),
            "sha256": record.artifact_sha256,
            "verification_ok": bool(record.artifact_verification_ok),
        }
        chain_linked = False
        chain_info = None

        if record.status in (ApprovalStatus.APPROVED, ApprovalStatus.REJECTED):
            receipt_svc = ReceiptService(db_path=approval_svc.db_path)
            try:
                receipt = receipt_svc.get_receipt(run_id)
                receipt_available = True
                receipt_verification = receipt_svc.verify_receipt(run_id)
                receipt_payload = receipt.payload
                model_execution = receipt_payload.get("model_execution", model_execution)
                sovereignty = receipt_payload.get("sovereignty", sovereignty)
                artifact_info = receipt_payload.get("artifact", artifact_info)
            except ReceiptNotFoundError:
                receipt_available = False
                receipt_verification = {
                    "valid": False,
                    "checks": {"receipt_exists": False},
                    "receipt_sha256": None,
                }
                model_execution = {"recorded_models": [], "status": "NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE"}
                sovereignty = {
                    "external_calls_recorded": external_calls,
                    "network_guard_scope": "application-level agent run",
                    "whole_machine_airgap_certified": False,
                }

            chain_svc = ReceiptChainService(db_path=approval_svc.db_path)
            try:
                chain_entry = chain_svc.get_entry(run_id)
                chain_linked = True
                chain_info = {
                    "sequence_no": chain_entry.sequence_no,
                    "previous_chain_sha256": chain_entry.previous_chain_sha256,
                    "chain_sha256": chain_entry.chain_sha256,
                }
            except Exception:
                chain_linked = False
                chain_info = None
        else:
            receipt_available = False
            receipt_verification = {
                "valid": False,
                "checks": {"receipt_exists": False},
                "receipt_sha256": None,
            }
            recorded_models = []
            for ev in vision_evidence:
                if isinstance(ev, dict):
                    m = ev.get("model")
                    if m:
                        recorded_models.append(str(m))
            if recorded_models:
                model_execution = {
                    "recorded_models": recorded_models,
                    "status": "EXPLICIT_VISION_EVIDENCE",
                }
            else:
                model_execution = {
                    "recorded_models": [],
                    "status": "NO_EXPLICIT_MODEL_EXECUTION_EVIDENCE",
                }
            sovereignty = {
                "external_calls_recorded": external_calls,
                "network_guard_scope": "application-level agent run",
                "whole_machine_airgap_certified": False,
            }
            artifact_info = {
                "logical_path": self._logical_path(record.artifact_path),
                "sha256": record.artifact_sha256,
                "verification_ok": bool(record.artifact_verification_ok),
            }
            chain_linked = False
            chain_info = None

        chain_svc = ReceiptChainService(db_path=approval_svc.db_path)
        global_chain = chain_svc.verify_chain()

        result = {
            "run_id": run_id,
            "approval_status": record.status,
            "asset": {
                "requested_tag": record.asset_tag,
                "canonical_tag": asset_identity.get("canonical_tag"),
                "identity_status": asset_identity.get("status"),
                "identity_source": asset_identity.get("source"),
            },
            "retrieval": {
                "chunk_count": retrieval.get("chunk_count"),
                "unique_asset_tags": retrieval.get("unique_asset_tags") or [],
                "source_files": retrieval.get("source_files") or [],
                "document_types": retrieval.get("document_types") or [],
                "retrieval_modes": retrieval.get("retrieval_modes") or [],
            },
            "calculations": {
                "any_threshold_breach": calculations.get("any_threshold_breach"),
                "breached_signals": calculations.get("breached_signals") or [],
                "inspection_findings": calculations.get("inspection_findings") or [],
                "vendor_parts": calculations.get("vendor_parts") or [],
                "sop_requirements": calculations.get("sop_requirements") or [],
                "sandbox_used": calculations.get("sandbox_used"),
            },
            "execution_trace": {
                "executed_nodes": executed_nodes,
            },
            "routing": {
                "task_type": routing.get("task_type"),
                "selected_model": routing.get("selected_model"),
                "models_required": routing.get("models_required") or [],
                "requires_rag": routing.get("requires_rag"),
                "requires_tools": routing.get("requires_tools"),
                "local_only": routing.get("local_only"),
                "all_local": routing.get("all_local"),
                "confidence": routing.get("confidence"),
                "reason": routing.get("reason"),
            },
            "actual_model_execution": model_execution,
            "human_review": {
                "approval_required": bool(record.approval_required),
                "status": record.status,
                "reviewer_id": record.reviewer_id,
                "reviewer_comment": record.reviewer_comment,
                "reviewer_identity_verified": bool(record.reviewer_identity_verified),
                "created_at": record.created_at,
                "reviewed_at": record.reviewed_at,
            },
            "artifact": artifact_info,
            "receipt": {
                "available": receipt_available,
                "receipt_id": receipt.receipt_id if receipt else None,
                "schema_version": receipt.schema_version if receipt else None,
                "receipt_sha256": receipt_verification.get("receipt_sha256"),
                "valid": receipt_verification.get("valid", False),
                "checks": receipt_verification.get("checks", {}),
            } if receipt_available else {
                "available": False,
            },
            "chain": {
                "linked": chain_linked,
                "global_chain_valid": global_chain.get("valid", True),
                "global_chain_status": global_chain.get("status", "VALID"),
            },
            "sovereignty": sovereignty,
        }

        if chain_info:
            result["chain"].update(chain_info)

        return result

    def _logical_path(self, artifact_path: str) -> str:
        try:
            return str(Path(artifact_path).resolve().relative_to(self.repo_root.resolve()))
        except Exception:
            return artifact_path

    @staticmethod
    def _first_or_none(lst: Optional[List[Any]]) -> Optional[Any]:
        if lst:
            return lst[0]
        return None
