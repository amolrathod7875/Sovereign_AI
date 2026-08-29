from agent.prompts.planner import plan_for_request, EVIDENCE_CATALOGUE
from agent.utils import trace_entry, elapsed_ms

import time


def run(state: dict) -> dict:
    start = time.time()
    request = state["user_request"]
    plan = plan_for_request(request)

    # When a vision input is attached, guarantee the vision evidence category so
    # downstream nodes know to run vision-grounded retrieval.
    if state.get("image_path") and not any(p.get("category") == "vision" for p in plan):
        doc_type, query = EVIDENCE_CATALOGUE["vision"]
        plan.append({"category": "vision", "document_type": doc_type, "query": query})

    return {
        "plan": plan,
        "status": "PLANNED",
        "trace": [trace_entry("plan", "create_plan", "planner", elapsed_ms(start), "SUCCESS",
                              plan_length=len(plan))],
    }
