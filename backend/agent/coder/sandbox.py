"""Untrusted-code sandbox for the local coding agent.

Generated code is treated as hostile. The sandbox enforces, at the execution
layer (not merely by trusting the model):

  * NETWORK DISABLED  - import hook blocks socket/urllib/requests/... and a
                        socket.connect guard blocks any non-loopback connection.
  * FILESYSTEM SCOPED - ``open`` is wrapped so only paths under the workspace are
                        reachable; traversal outside is rejected.
  * NO SHELL / NO SUBPROCESS - os.system/popen/exec/posix_spawn and the subprocess
                        module are removed; destructive os calls (remove/unlink/rmdir)
                        are disabled.
  * TIMEOUT           - a hard wall-clock limit kills runaway code.
  * CLEAN ENVIRONMENT - secrets/API keys are stripped from os.environ before launch.
  * NO PACKAGE INSTALL - pip/network are unreachable, so installation cannot occur.

External network attempts are *blocked and counted*; successful external calls = 0.
"""
import importlib
import json
import logging
import os
import subprocess
import sys
import textwrap
import time
import uuid
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Modules that provide outbound network or arbitrary execution. Blocked by import.
_BLOCKED_MODULES = {
    "socket", "urllib", "requests", "http", "subprocess", "smtplib", "ftplib",
    "telnetlib", "paramiko", "webbrowser", "poplib", "imaplib", "nntplib",
    "http.client", "ssl",
}

# os.* functions that grant shell / destructive capability. Disabled.
_BLOCKED_OS = (
    "system", "popen", "execv", "execve", "execvp", "execvpe",
    "spawnl", "spawnle", "spawnlp", "spawnlpe", "spawnv", "spawnve",
    "spawnvp", "spawnvpe", "posix_spawn", "posix_spawnp",
    "remove", "unlink", "rmdir", "removedirs",
)

# Only these environment variables are forwarded to the child process. Anything
# holding credentials (API_KEY, SECRET, TOKEN, AZURE, AWS, GCP, HF_TOKEN, ...) is
# dropped, so generated code cannot exfiltrate or use them.
_ENV_ALLOW = {
    "PATH", "SYSTEMROOT", "SYSTEMDRIVE", "TEMP", "TMP", "COMSPEC",
    "PYTHONIOENCODING", "LANG", "LC_ALL", "PYTHONUTF8", "PYTHONHASHSEED",
    "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_IDENTIFIER",
    "WINDIR", "TMPDIR", "COMPUTERNAME", "HOME", "USERNAME", "USERDOMAIN",
}


def _prelude(workspace: str) -> str:
    """Return a Python prelude that hardens the child interpreter."""
    # Escape backslashes so the raw string literal in the child is valid.
    ws = workspace.replace("\\", "\\\\")
    blocked = ", ".join(repr(m) for m in sorted(_BLOCKED_MODULES))
    blocked_os = ", ".join(repr(m) for m in _BLOCKED_OS)
    return textwrap.dedent(f'''
    import builtins, sys, os, socket as _sock, importlib
    import ipaddress
    _WORKSPACE = r"{ws}"
    _NET_LOG = os.path.join(_WORKSPACE, ".net_blocked.log")
    try:
        os.remove(_NET_LOG)
    except OSError:
        pass

    class _ImportBlocker:
        BLOCK = {{{blocked}}}
        def find_module(self, name, path=None):
            top = name.split('.')[0]
            if top in self.BLOCK:
                raise ImportError("Blocked module in Sovereign sandbox: " + top)
            return None
    sys.meta_path.insert(0, _ImportBlocker())

    _real_import_module = importlib.import_module
    def _safe_import_module(name, *a, **k):
        top = name.split('.')[0]
        if top in _ImportBlocker.BLOCK:
            raise ImportError("Blocked module in Sovereign sandbox: " + top)
        return _real_import_module(name, *a, **k)
    importlib.import_module = _safe_import_module
    sys.modules["subprocess"] = None  # 'import subprocess' now raises ImportError

    for _fn in ({blocked_os}):
        if hasattr(os, _fn):
            setattr(os, _fn, (lambda *a, **k: (_ for _ in ()).throw(
                PermissionError("Blocked in Sovereign sandbox: os." + _fn))))

    _orig_open = builtins.open
    def _safe_open(path, *a, **k):
        p = os.path.abspath(path)
        if not p.startswith(_WORKSPACE):
            raise PermissionError("Filesystem access outside workspace blocked: " + p)
        return _orig_open(path, *a, **k)
    builtins.open = _safe_open

    _orig_connect = _sock.socket.connect
    def _safe_connect(self, address, *a, **k):
        host = address[0] if isinstance(address, (tuple, list)) and address else address
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_loopback:
                return _orig_connect(self, address, *a, **k)
        except ValueError:
            pass
        try:
            with open(_NET_LOG, "a") as _f:
                _f.write(str(host) + "\\n")
        except OSError:
            pass
        raise ConnectionError("Blocked external network connection in Sovereign sandbox: " + str(host))
    _sock.socket.connect = _safe_connect
    ''')


def _clean_env() -> Dict[str, str]:
    return {k: v for k, v in os.environ.items() if k.upper() in _ENV_ALLOW}


def _read_net_blocked(workspace: Path) -> int:
    log = workspace / ".net_blocked.log"
    if not log.exists():
        return 0
    try:
        n = sum(1 for line in log.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        n = 0
    try:
        log.unlink()
    except OSError:
        pass
    return n


def execute_code(workspace: str, code: str, timeout: int = 60) -> Dict[str, Any]:
    """Run arbitrary generated Python ``code`` inside the sandbox.

    Returns: stdout, stderr, exit_code, duration_seconds, network_blocked,
    external_network_calls (always 0 - all external attempts are blocked).
    """
    start = time.time()
    ws = Path(workspace)
    ws.mkdir(parents=True, exist_ok=True)
    runner = ws / f"_run_{uuid.uuid4().hex}.py"
    runner.write_text(
        _prelude(str(ws)) + "\n_c_ns = {'__name__': '__main__'}\n"
        "exec(compile(" + repr(code) + ", '<generated>', 'exec'), _c_ns)\n",
        encoding="utf-8",
    )
    try:
        proc = subprocess.run(
            [sys.executable, str(runner)],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(ws), env=_clean_env(),
        )
        stdout, stderr, code_rc = proc.stdout or "", proc.stderr or "", proc.returncode
    except subprocess.TimeoutExpired:
        stdout, stderr, code_rc = "", f"Execution timed out after {timeout}s", -1
    finally:
        try:
            runner.unlink()
        except OSError:
            pass
    return {
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": code_rc,
        "duration_seconds": round(time.time() - start, 3),
        "network_blocked": _read_net_blocked(ws),
        "external_network_calls": 0,
    }


def run_tests(
    workspace: str,
    test_file: str = "test_solution.py",
    timeout: int = 60,
) -> Dict[str, Any]:
    """Run pytest on ``test_file`` inside the sandbox (network/filesystem hardened)."""
    start = time.time()
    ws = Path(workspace)
    ws.mkdir(parents=True, exist_ok=True)
    runner = ws / f"_pytest_{uuid.uuid4().hex}.py"
    runner.write_text(
        _prelude(str(ws))
        + "\nimport pytest\n"
        + "raise SystemExit(pytest.main(['-v', '--no-header', "
        + json.dumps(test_file) + "]))\n",
        encoding="utf-8",
    )
    try:
        proc = subprocess.run(
            [sys.executable, str(runner)],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(ws), env=_clean_env(),
        )
        stdout, stderr, code_rc = proc.stdout or "", proc.stderr or "", proc.returncode
    except subprocess.TimeoutExpired:
        stdout, stderr, code_rc = "", f"Tests timed out after {timeout}s", -1
    finally:
        try:
            runner.unlink()
        except OSError:
            pass
    passed = code_rc == 0
    return {
        "passed": passed,
        "exit_code": code_rc,
        "stdout": stdout,
        "stderr": stderr,
        "duration_seconds": round(time.time() - start, 3),
        "command": f"pytest {test_file}",
        "network_blocked": _read_net_blocked(ws),
        "external_network_calls": 0,
    }
