"""Strongly-typed state for the coding-agent LangGraph workflow.

Field names are kept distinct from node names (LangGraph forbids collisions).
List-like fields use additive reducers so every node appends without clobbering.
"""
from typing import TypedDict, Dict, Any, List, Annotated


def _add(a, b):  # additive reducer for trace/log/error lists
    return a + b


class CoderState(TypedDict, total=False):
    run_id: str
    task: str
    task_understanding: str
    plan: str
    workspace: str

    # Filenames -> latest generated content (so FIX_CODE can re-emit only what changed).
    file_contents: Dict[str, str]
    # Absolute paths of files written into the workspace.
    files: Annotated[List[str], _add]
    # Latest raw model output (used as context when feeding failure back).
    generated_code: str
    # Diagnosis produced by ANALYZE_FAILURE.
    failure_analysis: str
    # Snapshot of the first failing test run (proves failure detection).
    first_failure: Dict[str, Any]
    test_command: str
    test_output: Dict[str, Any]

    errors: Annotated[List[str], _add]
    iteration: int
    status: str
    final_result: Dict[str, Any]
    execution_trace: Annotated[List[Dict[str, Any]], _add]
