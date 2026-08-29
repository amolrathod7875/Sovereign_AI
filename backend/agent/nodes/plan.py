from agent.prompts.planner import plan_for_request
from agent.utils import trace_entry, elapsed_ms

import time


def run(state: dict) -> dict:
    start = time.time()
    request = state["user_request"]
    plan = plan_for_request(request)
    return {
        "plan": plan,
        "status": "PLANNED",
        "trace": [trace_entry("plan", "create_plan", "planner", elapsed_ms(start), "SUCCESS",
                              plan_length=len(plan))],
    }
