"""Local tools for the coding agent. Every operation is confined to ``workspace``.

Mirrors the tool surface required by the spec: create_code_file, read_code_file,
run_python, run_tests, list_workspace_files, and the optional apply_patch. Path
traversal is rejected before any filesystem access.
"""
import logging
import re
from pathlib import Path
from typing import Dict, Any, List

from agent.coder import sandbox
from agent.coder.config import CODER_EXEC_TIMEOUT

logger = logging.getLogger(__name__)

_FILE_RE = re.compile(r"^###\s*FILE:\s*(.+?)\s*$", re.MULTILINE)


def parse_files(text: str) -> Dict[str, str]:
    """Parse `### FILE: <name>` blocks into {filename: content}."""
    matches = list(_FILE_RE.finditer(text))
    files: Dict[str, str] = {}
    for i, m in enumerate(matches):
        name = m.group(1).strip().strip("`").strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        # strip a single surrounding code fence if present
        if body.startswith("```"):
            nl = body.find("\n")
            body = body[nl + 1:] if nl != -1 else ""
        if body.endswith("```"):
            body = body[:-3]
        files[name] = body.strip("\n")
    return files


def _safe_target(workspace: str, filename: str) -> Path:
    ws = Path(workspace).resolve()
    target = (ws / filename).resolve()
    if target != ws and ws not in target.parents:
        raise PermissionError(f"Path traversal blocked: {filename}")
    return target


def create_code_file(workspace: str, filename: str, content: str) -> str:
    ws = Path(workspace)
    ws.mkdir(parents=True, exist_ok=True)
    target = _safe_target(workspace, filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return str(target)


def read_code_file(workspace: str, filename: str) -> str:
    target = _safe_target(workspace, filename)
    return target.read_text(encoding="utf-8")


def run_python(workspace: str, filename: str, timeout: int = CODER_EXEC_TIMEOUT) -> Dict[str, Any]:
    code = read_code_file(workspace, filename)
    return sandbox.execute_code(workspace, code, timeout=timeout)


def run_tests(
    workspace: str,
    test_file: str = "test_solution.py",
    timeout: int = CODER_EXEC_TIMEOUT,
) -> Dict[str, Any]:
    return sandbox.run_tests(workspace, test_file=test_file, timeout=timeout)


def list_workspace_files(workspace: str) -> List[str]:
    ws = Path(workspace)
    if not ws.exists():
        return []
    out = []
    for p in sorted(ws.rglob("*")):
        if not p.is_file():
            continue
        name = p.name
        if name.startswith("_") or name == ".net_blocked.log":
            continue
        out.append(str(p.relative_to(ws)).replace("\\", "/"))
    return out


def apply_patch(workspace: str, filename: str, patch_text: str) -> str:
    """Apply a patch. For safety the sandbox treats ``patch_text`` as the new
    full file content (no arbitrary diff-apply against unrelated files)."""
    return create_code_file(workspace, filename, patch_text)
