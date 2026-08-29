"""Tests for the LangGraph agent graph and the run entrypoint."""
import pytest

from agent.graph import GRAPH
from agent.state import create_initial_state
from agent.run import run_agent_task

TASK = (
    "Analyze the recent R-1001 operating data and inspection findings, compare them with "
    "the equipment manual and maintenance SOP, check the vendor recommendation, determine the "
    "required corrective action, and prepare a maintenance approval note."
)


def test_graph_runs_end_to_end():
    state = create_initial_state("test_run_1", TASK, asset_tag="R-1001")
    final = GRAPH.invoke(state)
    assert final["status"] in ("VERIFIED", "VERIFY_FAILED")
    assert final["evidence"], "expected evidence collected"
    assert final["findings"], "expected findings synthesized"
    assert final["decision"], "expected a decision"
    assert final["decision"]["approval_required"] is True
    assert final["artifacts"], "expected a generated artifact"
    assert final["external_calls"] == 0


def test_graph_nodes_present():
    # sanity: the compiled graph exposes the expected nodes
    expected = {
        "planner", "retrieve_evidence", "analyze_evidence", "calc_gate",
        "python_analysis", "synthesize_findings", "make_decision",
        "generate_approval_note", "verify_output",
    }
    nodes = set(GRAPH.nodes.keys())
    assert expected.issubset(nodes)


def test_run_agent_task_output_shape():
    res = run_agent_task(TASK, asset_tag="R-1001", run_id="test_run_2", artifact_filename="R-1001_agent_test.docx")
    assert res["status"] == "VERIFIED"
    assert res["approval_required"] is True
    assert isinstance(res["artifacts"], list) and res["artifacts"]
    assert res["external_calls"] == 0
    # every finding has supporting provenance
    for f in res["findings"]:
        assert f.get("source_document_type") or f.get("source_file")
    # trace records every step
    node_names = {e["node"] for e in res["trace"]}
    assert {"plan", "retrieve_evidence", "analyze_evidence", "python_analysis",
            "synthesize_findings", "make_decision", "generate_approval_note",
            "verify_output"}.issubset(node_names)
