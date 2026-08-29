"""Persist a successful (or final) coding run to a human-facing artifact dir."""
from pathlib import Path
from typing import Dict, Any

from agent.coder.config import CODER_ARTIFACT_DIR


_DELIVERABLES = ("solution.py", "test_solution.py", "sensor_fixture.csv")


def write_artifact(state: Dict[str, Any]) -> str:
    run_id = state["run_id"]
    out = CODER_ARTIFACT_DIR / run_id
    out.mkdir(parents=True, exist_ok=True)

    contents = state.get("file_contents") or {}
    written = []
    for name in _DELIVERABLES:
        if name in contents:
            (out / name).write_text(contents[name], encoding="utf-8")
            written.append(name)

    (out / "README.md").write_text(_readme(state), encoding="utf-8")
    written.append("README.md")
    return str(out)


def _readme(state: Dict[str, Any]) -> str:
    fr = state.get("final_result") or {}
    to = fr.get("test_output") or {}
    lines = []
    lines.append(f"# Coder Demo Artifact — {state['run_id']}\n")
    lines.append("## Task\n")
    lines.append(state.get("task", "") + "\n")
    lines.append("## Generated files\n")
    for n in _DELIVERABLES:
        if n in (state.get("file_contents") or {}):
            lines.append(f"- `{n}`")
    lines.append("")
    lines.append("## How tests were run\n")
    lines.append(f"Command: `pytest test_solution.py` inside the isolated workspace "
                 f"`{state.get('workspace')}`.\n")
    lines.append("## Final result\n")
    lines.append(f"- Status: **{fr.get('status', state.get('status'))}**")
    lines.append(f"- Iterations (repairs): {fr.get('iterations', 0)}")
    lines.append(f"- Tests passed: {to.get('passed')}")
    lines.append(f"- Exit code: {to.get('exit_code')}")
    if not to.get("passed") and state.get("first_failure"):
        lines.append("- An initial failure was detected and fed back to the model for repair.")
    lines.append("")
    lines.append("## Sandbox status\n")
    lines.append("- Network access: **disabled** (import hook + socket.connect guard).")
    lines.append("- Filesystem: **scoped to workspace only** (`open` wrapped).")
    lines.append("- Shell/subprocess/destructive `os.*`: **blocked**.")
    lines.append("- Environment: **secrets stripped**; timeout enforced.\n")
    lines.append("## Network status\n")
    lines.append(f"- External network calls: **{to.get('external_network_calls', 0)}** "
                 f"(all external attempts blocked).")
    return "\n".join(lines) + "\n"
