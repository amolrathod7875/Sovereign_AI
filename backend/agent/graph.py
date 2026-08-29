"""LangGraph definition for the Phase 4 Sovereign AI maintenance agent.

Flow:
  START -> PLANNER -> RETRIEVE_EVIDENCE -> ANALYZE_EVIDENCE -> CALC_GATE
       CALC_GATE --yes--> PYTHON_ANALYSIS --+
       CALC_GATE --no------------------------+--> SYNTHESIZE_FINDINGS
       -> MAKE_DECISION -> GENERATE_APPROVAL_NOTE -> VERIFY_OUTPUT
       VERIFY_OUTPUT --retry--> GENERATE_APPROVAL_NOTE   (error recovery)
       VERIFY_OUTPUT --end--> END

Node names are kept distinct from AgentState keys (LangGraph forbids collisions).
"""
from langgraph.graph import StateGraph, START, END

from agent.state import AgentState
from agent.nodes import (
    plan, retrieve, analyze, needs_calculation, python_analysis,
    synthesize, decide, generate, verify, verify_route,
)


def build_graph():
    g = StateGraph(AgentState)

    g.add_node("planner", plan)
    g.add_node("retrieve_evidence", retrieve)
    g.add_node("analyze_evidence", analyze)
    g.add_node("calc_gate", needs_calculation)
    g.add_node("python_analysis", python_analysis)
    g.add_node("synthesize_findings", synthesize)
    g.add_node("make_decision", decide)
    g.add_node("generate_approval_note", generate)
    g.add_node("verify_output", verify)

    g.add_edge(START, "planner")
    g.add_edge("planner", "retrieve_evidence")
    g.add_edge("retrieve_evidence", "analyze_evidence")
    g.add_edge("analyze_evidence", "calc_gate")

    g.add_conditional_edges(
        "calc_gate",
        lambda s: "calculate" if s.get("needs_calculation") else "synthesize",
        {"calculate": "python_analysis", "synthesize": "synthesize_findings"},
    )
    g.add_edge("python_analysis", "synthesize_findings")

    g.add_edge("synthesize_findings", "make_decision")
    g.add_edge("make_decision", "generate_approval_note")
    g.add_edge("generate_approval_note", "verify_output")

    g.add_conditional_edges(
        "verify_output",
        verify_route,
        {"retry": "generate_approval_note", "end": END},
    )
    return g


GRAPH = build_graph().compile()
