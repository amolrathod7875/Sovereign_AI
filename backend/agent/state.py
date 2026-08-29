"""Strongly-typed agent state for the Phase 4 LangGraph maintenance agent.

The schema is fixed (no unrestricted arbitrary state). List channels use an
append reducer so successive nodes accumulate evidence without clobbering
previous work; dict channels use a merge reducer so nodes can contribute keys.
"""
from typing import TypedDict, List, Dict, Any, Optional, Annotated
from datetime import datetime


def _append(existing: list, update: list) -> list:
    return (existing or []) + (update or [])


def _merge_dict(existing: dict, update: dict) -> dict:
    out = dict(existing or {})
    out.update(update or {})
    return out


# Convenience annotations
ListAppend = Annotated[List[Any], _append]
DictMerge = Annotated[Dict[str, Any], _merge_dict]


class AgentState(TypedDict):
    # --- core request / identity ---
    run_id: str
    user_request: str
    asset_tag: str

    # --- planning ---
    plan: ListAppend  # List[Dict]: {category, document_type, query}

    # --- retrieval outputs ---
    retrieved_documents: ListAppend   # List[Dict]: full docs read for extraction
    retrieved_chunks: ListAppend      # List[Dict]: raw hybrid-retrieval hits
    evidence: ListAppend              # List[Dict]: {claim,value,source_file,document_type,asset_tag,confidence}

    # --- analysis outputs ---
    calculations: DictMerge           # Dict[str, Any]: sensor analysis, python analysis, extractions
    findings: ListAppend              # List[Dict]: synthesized findings w/ evidence refs

    # --- decision / outputs ---
    decision: Dict[str, Any]           # decision, reasoning_summary, supporting_evidence, required_actions, approval_required
    required_actions: ListAppend      # List[str]
    artifact_requests: ListAppend     # List[Dict]
    artifacts: ListAppend             # List[str] (paths)
    artifact_filename: str            # optional override for the generated DOCX filename (versioning)

    # --- control / observability ---
    needs_calculation: bool
    iterations: int
    errors: ListAppend                # List[str]
    trace: ListAppend                 # List[Dict]: observability log entries
    status: str
    verification: Dict[str, Any]
    external_calls: int               # MUST remain 0 (network sovereignty)


def create_initial_state(run_id: str, user_request: str, asset_tag: str = "R-1001") -> AgentState:
    return AgentState(
        run_id=run_id,
        user_request=user_request,
        asset_tag=asset_tag,
        plan=[],
        retrieved_documents=[],
        retrieved_chunks=[],
        evidence=[],
        calculations={},
        findings=[],
        decision={},
        required_actions=[],
        artifact_requests=[],
        artifacts=[],
        artifact_filename="",
        needs_calculation=False,
        iterations=0,
        errors=[],
        trace=[],
        status="PENDING",
        verification={},
        external_calls=0,
    )
