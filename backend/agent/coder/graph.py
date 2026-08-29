"""LangGraph definition for the Phase 5A local coding agent."""
from langgraph.graph import StateGraph, START, END

from agent.coder.state import CoderState
from agent.coder import nodes


def build_graph():
    g = StateGraph(CoderState)

    g.add_node("understand_task", nodes.understand_task)
    g.add_node("plan", nodes.plan)
    g.add_node("generate_code", nodes.generate_code)
    g.add_node("write_workspace", nodes.write_workspace)
    g.add_node("run_tests", nodes.run_tests)
    g.add_node("analyze_failure", nodes.analyze_failure)
    g.add_node("fix_code", nodes.fix_code)
    g.add_node("verify", nodes.verify)
    g.add_node("final", nodes.final_node)

    g.add_edge(START, "understand_task")
    g.add_edge("understand_task", "plan")
    g.add_edge("plan", "generate_code")
    g.add_edge("generate_code", "write_workspace")
    g.add_edge("write_workspace", "run_tests")

    g.add_conditional_edges(
        "run_tests",
        nodes.test_route,
        {"pass": "verify", "fail": "analyze_failure", "maxed": "verify"},
    )

    g.add_edge("analyze_failure", "fix_code")
    g.add_edge("fix_code", "run_tests")

    g.add_edge("verify", "final")
    g.add_edge("final", END)
    return g


GRAPH = build_graph().compile()
