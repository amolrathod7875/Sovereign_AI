"""Coding-agent LangGraph nodes.

Flow:
  understand_task -> plan -> generate_code -> write_workspace -> run_tests
  run_tests --pass--> verify            (-> final)
  run_tests --fail--> analyze_failure -> fix_code -> run_tests (loop)
  run_tests --maxed--> verify           (-> final, status FAILED)
"""
import logging
import re
import time
from typing import Dict, Any, List

from agent.coder import prompts
from agent.coder import tools
from agent.coder.config import CODER_MAX_ITERATIONS
from agent.coder.model import chat
from agent.coder.state import CoderState
from agent.coder.artifact import write_artifact
from agent.utils import trace_entry, elapsed_ms
from agent.coder.tools import parse_files

logger = logging.getLogger(__name__)


def _format_sources(state: Dict[str, Any]) -> str:
    parts = []
    for name, content in (state.get("file_contents") or {}).items():
        parts.append(f"### {name}\n{content}")
    return "\n\n".join(parts) if parts else "(no source yet)"


def _format_test_output(to: Dict[str, Any]) -> str:
    if not to:
        return "(no test output)"
    return (
        f"command: {to.get('command')}\n"
        f"passed: {to.get('passed')}\n"
        f"exit_code: {to.get('exit_code')}\n"
        f"--- stdout ---\n{to.get('stdout','')}\n"
        f"--- stderr ---\n{to.get('stderr','')}"
    )


def understand_task(state: CoderState) -> Dict[str, Any]:
    start = time.time()
    out = chat(
        prompts.SYSTEM_CODER,
        "Restate this task in one sentence and list the deliverable files.\n\n"
        f"Task: {state['task']}",
        max_tokens=256,
    )
    return {
        "task_understanding": out,
        "execution_trace": [trace_entry(
            "understand_task", "analyze", "model", elapsed_ms(start), "SUCCESS")],
    }


def plan(state: CoderState) -> Dict[str, Any]:
    start = time.time()
    out = chat(prompts.SYSTEM_CODER, prompts.PLAN_USER.format(task=state["task"]), max_tokens=512)
    return {
        "plan": out,
        "execution_trace": [trace_entry("plan", "plan", "model", elapsed_ms(start), "SUCCESS")],
    }


def generate_code(state: CoderState) -> Dict[str, Any]:
    start = time.time()
    raw = chat(
        prompts.GEN_SYSTEM,
        prompts.GEN_USER.format(task=state["task"], plan=state.get("plan", "")),
        max_tokens=2048,
    )
    try:
        files = parse_files(raw)
        status = "SUCCESS" if files else "FAILED"
    except Exception as e:  # pragma: no cover
        files, status = {}, "FAILED"
        logger.error("parse_files failed: %s", e)
    return {
        "generated_code": raw,
        "file_contents": files,
        "execution_trace": [trace_entry(
            "generate_code", "generate", "model", elapsed_ms(start), status,
            files=list(files.keys()))],
        "errors": [] if files else ["generate_code: no files parsed"],
    }


def write_workspace(state: CoderState) -> Dict[str, Any]:
    start = time.time()
    ws = state["workspace"]
    written: List[str] = []
    for name, content in (state.get("file_contents") or {}).items():
        try:
            path = tools.create_code_file(ws, name, content)
            written.append(path)
        except Exception as e:
            logger.error("write failed for %s: %s", name, e)
    return {
        "files": written,
        "test_command": f"pytest test_solution.py",
        "execution_trace": [trace_entry(
            "write_workspace", "create_code_file", "filesystem", elapsed_ms(start),
            "SUCCESS" if written else "FAILED", files=written)],
        "errors": [] if written else ["write_workspace: no files written"],
    }


def run_tests(state: CoderState) -> Dict[str, Any]:
    start = time.time()
    result = tools.run_tests(state["workspace"], test_file="test_solution.py")
    passed = bool(result.get("passed"))
    status = "TEST_PASSED" if passed else "TEST_FAILED"
    updates: Dict[str, Any] = {
        "test_output": result,
        "execution_trace": [trace_entry(
            "run_tests", "pytest", "sandbox", elapsed_ms(start), status,
            exit_code=result.get("exit_code"))],
    }
    # Capture the very first failing run to prove the loop detected a real failure.
    if not passed and not state.get("first_failure"):
        updates["first_failure"] = result
    return updates


def test_route(state: CoderState) -> str:
    if state.get("test_output", {}).get("passed"):
        return "pass"
    if state.get("iteration", 0) >= CODER_MAX_ITERATIONS:
        return "maxed"
    return "fail"


def analyze_failure(state: CoderState) -> Dict[str, Any]:
    start = time.time()
    test_out = _format_test_output(state.get("test_output"))
    analysis = chat(
        prompts.ANALYZE_SYSTEM,
        prompts.ANALYZE_USER.format(
            task=state["task"], test_output=test_out,
            sources=_format_sources(state)),
        max_tokens=512,
    )
    return {
        "failure_analysis": analysis,
        "execution_trace": [trace_entry(
            "analyze_failure", "diagnose", "model", elapsed_ms(start), "SUCCESS")],
    }


def fix_code(state: CoderState) -> Dict[str, Any]:
    start = time.time()
    test_out = _format_test_output(state.get("test_output"))
    raw = chat(
        prompts.FIX_SYSTEM,
        prompts.FIX_USER.format(
            task=state["task"], analysis=state.get("failure_analysis", ""),
            test_output=test_out, sources=_format_sources(state)),
        max_tokens=2048,
    )
    files = parse_files(raw)
    # Overwrite the workspace files with the corrected versions.
    written: List[str] = []
    for name, content in files.items():
        try:
            written.append(tools.create_code_file(state["workspace"], name, content))
        except Exception as e:
            logger.error("fix write failed for %s: %s", name, e)
    return {
        "generated_code": raw,
        "file_contents": files,
        "files": written,
        "iteration": state.get("iteration", 0) + 1,
        "execution_trace": [trace_entry(
            "fix_code", "generate", "model", elapsed_ms(start), "SUCCESS",
            files=list(files.keys()))],
    }


def verify(state: CoderState) -> Dict[str, Any]:
    start = time.time()
    passed = bool(state.get("test_output", {}).get("passed"))
    status = "PASS" if passed else "FAIL"
    artifact_dir = None
    try:
        artifact_dir = write_artifact(state)
    except Exception as e:
        logger.error("artifact write failed: %s", e)
    return {
        "status": "COMPLETED" if passed else "FAILED",
        "final_result": {
            "passed": passed,
            "iterations": state.get("iteration", 0),
            "test_output": state.get("test_output"),
            "files": state.get("files", []),
            "artifact_dir": artifact_dir,
        },
        "execution_trace": [trace_entry(
            "verify", "verify", "pytest", elapsed_ms(start), status)],
    }


def final_node(state: CoderState) -> Dict[str, Any]:
    return {
        "execution_trace": [trace_entry(
            "final", "complete", "graph", 0, state.get("status", "DONE"))],
    }
