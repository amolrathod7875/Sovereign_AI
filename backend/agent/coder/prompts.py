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
    "Implement the task described above. Create the necessary files in the workspace.\n\n"
    "Requirements:\n"
    "1) solution.py\n"
    "   - Implement the core logic required by the task.\n"
    "   - Include a `main` block or entry point that demonstrates the solution.\n"
    "   - Use only standard library and locally available packages.\n\n"
    "2) test_solution.py\n"
    "   - Import `solution` and test the core functionality.\n"
    "   - Include at least 3 assertions covering expected behavior.\n"
    "   - Tests must pass when run with pytest.\n\n"
    "3) Any additional files needed by the solution (data files, configs, etc.)\n\n"
    "Return ALL files using the ### FILE: <filename> format described above. "
    "Each file must be complete and runnable."
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
