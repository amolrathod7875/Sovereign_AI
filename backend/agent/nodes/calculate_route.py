"""NEEDS_CALCULATION decision node (pass-through used for conditional routing)."""
import time
from agent.utils import trace_entry, elapsed_ms


def run(state: dict) -> dict:
    start = time.time()
    return {
        "trace": [trace_entry("needs_calculation", "route_decision", None,
                              elapsed_ms(start), "SUCCESS",
                              needs_calculation=bool(state.get("needs_calculation")))],
    }
