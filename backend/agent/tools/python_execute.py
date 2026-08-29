"""Tool: python_execute

A local, sandboxed Python execution environment with NO network access and NO
filesystem access outside the project/data directories. Intended for numerical
analysis the agent needs (trend, aggregation, first/last breach) so the LLM does
not perform arithmetic by hand.

Security model:
  * Runs in a subprocess with a prelude that:
      - installs an import hook blocking network modules (socket, urllib,
        requests, http, subprocess, smtplib, ftplib, telnetlib, paramiko, ...)
      - wraps ``open`` so only paths under the repo root (read) or the agent
        output dir (write) are permitted.
  * A ``RESULT`` variable, if defined by the user code, is returned as ``result``.
"""
import logging
import os
import subprocess
import sys
import tempfile
import textwrap
import time
import uuid
from pathlib import Path
from typing import Dict, Any, Optional

from agent.config import REPO_ROOT, OUTPUT_DIR

logger = logging.getLogger(__name__)

_BLOCKED_MODULES = {
    "socket", "urllib", "requests", "http", "subprocess", "smtplib",
    "ftplib", "telnetlib", "paramiko", "webbrowser", "asyncio", "select",
    "asyncore", "poplib", "imaplib", "nntplib", "http.client",
}

_PRELUDE = textwrap.dedent(
    """
    import builtins, sys, os
    _ALLOWED_READ = {allowed_read}
    _ALLOWED_WRITE = {allowed_write}

    class _ImportBlocker:
        def find_module(self, name, path=None):
            top = name.split('.')[0]
            if top in {{{blocked}}}:
                raise ImportError("Blocked module in Sovereign sandbox: " + top)
            return None
    sys.meta_path.insert(0, _ImportBlocker())

    _orig_open = builtins.open
    def _safe_open(path, *a, **k):
        p = os.path.abspath(path)
        mode = (a[0] if a else k.get("mode", "r"))
        is_write = "w" in mode or "a" in mode or "x" in mode or "+" in mode
        if is_write:
            if not any(p.startswith(d) for d in _ALLOWED_WRITE):
                raise PermissionError("Write outside allowed dirs: " + p)
        else:
            if not any(p.startswith(d) for d in _ALLOWED_READ):
                raise PermissionError("Read outside allowed dirs: " + p)
        return _orig_open(path, *a, **k)
    builtins.open = _safe_open
    """
).format(
    allowed_read=[str(REPO_ROOT)],
    allowed_write=[str(OUTPUT_DIR), str(Path(tempfile.gettempdir()))],
    blocked=", ".join(repr(m) for m in sorted(_BLOCKED_MODULES)),
)


def python_execute(code: str, timeout: int = 30) -> Dict[str, Any]:
    """Execute ``code`` in the local sandbox.

    Returns: {stdout, stderr, result, exit_code, execution_time}
    """
    start = time.time()
    out_path = Path(tempfile.gettempdir()) / f"sov_sandbox_{uuid.uuid4().hex}.py"
    wrapped = _PRELUDE + "\n" + code + "\n"
    # Surface RESULT if defined.
    wrapped += "\nimport json as _json\ntry:\n    print('__RESULT__' + _json.dumps(RESULT))\nexcept NameError:\n    pass\n"
    out_path.write_text(wrapped, encoding="utf-8")

    try:
        proc = subprocess.run(
            [sys.executable, str(out_path)],
            capture_output=True,
            text=True,
            timeout=timeout,
            # clean environment; inherit PATH so python itself is found
            env={k: v for k, v in os.environ.items()
                 if k.upper() in ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "COMSPEC")
                 or k.startswith("PYTHON")},
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""
        result = None
        if "__RESULT__" in stdout:
            marker = stdout.rfind("__RESULT__")
            payload = stdout[marker + len("__RESULT__"):].strip()
            stdout = stdout[:marker].rstrip()
            try:
                result = payload
            except Exception:
                result = payload
        return {
            "stdout": stdout,
            "stderr": stderr,
            "result": result,
            "exit_code": proc.returncode,
            "execution_time": round(time.time() - start, 4),
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Execution timed out after {timeout}s",
            "result": None,
            "exit_code": -1,
            "execution_time": round(time.time() - start, 4),
        }
    except Exception as e:  # pragma: no cover
        return {
            "stdout": "",
            "stderr": f"Sandbox error: {e}",
            "result": None,
            "exit_code": -1,
            "execution_time": round(time.time() - start, 4),
        }
    finally:
        try:
            out_path.unlink()
        except OSError:
            pass
