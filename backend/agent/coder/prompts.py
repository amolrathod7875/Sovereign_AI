"""Prompt templates for the coding agent nodes.

The generation contract is intentionally strict so the small local model has a
real chance of a first-attempt failure (comparison direction, "first breach"
timestamp, CSV parsing) - which exercises the repair loop honestly.
"""
SYSTEM_CODER = (
    "You are SovereignCoder, a careful local Python coding assistant running fully "
    "offline. You write correct, minimal, well-tested code. You follow the exact "
    "output format requested. You never explain at length; you produce the files."
)

PLAN_USER = (
    "Task:\n---\n{task}\n---\n\nProduce a SHORT implementation plan (markdown bullet "
    "list, <= 8 items). Identify the files to create and the core algorithm. "
    "Keep it under 200 words."
)

GEN_SYSTEM = (
    "You are SovereignCoder, a careful local Python coding assistant running fully "
    "offline. You must return EXACTLY the files requested using this format, with no "
    "extra commentary outside the file blocks:\n\n"
    "### FILE: <filename>\n<full file content>\n\n"
    "Use that marker at the start of every file. Do not wrap the whole answer in a "
    "code fence. Each file must be complete and runnable."
)

GEN_USER = (
    "Task:\n---\n{task}\n---\n\nPlan:\n---\n{plan}\n---\n\n"
    "Create these files in the workspace:\n\n"
    "1) solution.py\n"
    "   - Reads a CSV of sensor readings with columns: timestamp, temperature, pressure, vibration.\n"
    "   - Define `def analyze(csv_path: str, thresholds: dict) -> dict` where `thresholds` maps "
    "each signal name ('temperature','pressure','vibration') to a numeric threshold. "
    "A reading is a BREACH when its value is STRICTLY GREATER THAN the threshold.\n"
    "   - Return a dict: {{signal: {{'breaches': int, 'first_breach_timestamp': str|None}}}}.\n"
    "     'first_breach_timestamp' is the timestamp of the FIRST (chronologically earliest) row "
    "whose value exceeds the threshold, or None if there are no breaches.\n"
    "   - Also include an `if __name__ == '__main__':` block that reads 'sensor_fixture.csv', "
    "uses thresholds temperature=320.0, pressure=21.0, vibration=4.0, and prints a summary "
    "with the number of breaches and first breach timestamp per signal.\n\n"
    "2) test_solution.py\n"
    "   - Import `solution` and test `analyze()` against 'sensor_fixture.csv' (or a temp CSV you "
    "create) with thresholds temperature=320.0, pressure=21.0, vibration=4.0. Assert the exact "
    "breach counts and that 'first_breach_timestamp' equals the EARLIEST timestamp whose value "
    "exceeds the threshold. Include at least 3 assertions, including one breach and one non-breach.\n\n"
    "3) sensor_fixture.csv\n"
    "   - A small CSV (header + several rows) with columns timestamp,temperature,pressure,vibration. "
    "Include at least one breach per signal so tests are meaningful.\n\n"
    "Return the three files using the ### FILE: format described above."
)

ANALYZE_SYSTEM = (
    "You are SovereignCoder's debugging analyst. You receive a failing test run and the current "
    "source. You identify the root cause precisely and concisely (<= 150 words). You do NOT rewrite "
    "the code; you only explain what is wrong and how to fix it."
)

ANALYZE_USER = (
    "Task:\n---\n{task}\n---\n\nFailing test output:\n---\n{test_output}\n---\n\n"
    "Current source files:\n---\n{sources}\n---\n\n"
    "Identify the bug(s) and state the minimal correction needed."
)

FIX_SYSTEM = GEN_SYSTEM

FIX_USER = (
    "The previous implementation failed its tests. Use the diagnosis below to produce CORRECTED "
    "versions of the files.\n\n"
    "Task:\n---\n{task}\n---\n\nDiagnosis:\n---\n{analysis}\n---\n\n"
    "Failing test output:\n---\n{test_output}\n---\n\n"
    "Current source files:\n---\n{sources}\n---\n\n"
    "Return the corrected files using the ### FILE: <filename> format (solution.py, "
    "test_solution.py, sensor_fixture.csv). Keep the same public API and test contract."
)
