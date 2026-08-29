"""Runner for the local coding agent.

Enforces network sovereignty at the parent level (any non-loopback socket from
this process is blocked) and returns a self-contained, serialisable result.
"""
import logging
import uuid
from typing import Dict, Any, Optional

from agent.coder.config import CODER_DIR
from agent.coder.graph import GRAPH
from agent.coder.state import CoderState
from agent.security.netguard import no_network

logger = logging.getLogger(__name__)


def create_initial_state(run_id: str, task: str, workspace: str) -> CoderState:
    return {
        "run_id": run_id,
        "task": task,
        "workspace": workspace,
        "file_contents": {},
        "files": [],
        "generated_code": "",
        "failure_analysis": "",
        "first_failure": {},
        "test_command": "",
        "test_output": {},
        "errors": [],
        "iteration": 0,
        "status": "STARTED",
        "final_result": {},
        "execution_trace": [],
    }


def run_coder_task(
    task: str,
    run_id: Optional[str] = None,
    workspace: Optional[str] = None,
) -> Dict[str, Any]:
    run_id = run_id or f"coder_{uuid.uuid4().hex[:12]}"
    workspace = workspace or str(CODER_DIR / run_id)
    initial = create_initial_state(run_id, task, workspace)

    with no_network() as guard:
        final = GRAPH.invoke(initial)

    final["external_calls"] = guard.external_calls

    fr = final.get("final_result") or {}
    to = fr.get("test_output") or final.get("test_output") or {}

    return {
        "run_id": run_id,
        "status": final.get("status", "UNKNOWN"),
        "task": task,
        "workspace": workspace,
        "files": final.get("files", []),
        "file_contents": final.get("file_contents", {}),
        "test_output": to,
        "test_command": final.get("test_command", ""),
        "iteration": final.get("iteration", 0),
        "first_failure": final.get("first_failure"),
        "failure_analysis": final.get("failure_analysis", ""),
        "external_calls": final.get("external_calls", 0),
        "trace": final.get("execution_trace", []),
        "errors": final.get("errors", []),
        "final_result": fr,
    }
