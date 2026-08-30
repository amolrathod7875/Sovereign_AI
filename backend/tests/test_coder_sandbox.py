"""Phase 6.6 — coder sandbox import-blocker / cleanup / security regression tests.

These tests exercise the REAL sandbox (``agent.coder.sandbox``), i.e. a hardened
child interpreter is actually spawned for every case. Nothing is mocked and no
result is asserted "by intent" — every verdict comes from the sandbox itself.

Covered:
  * allowed imports still work                       (test_allowed_*)
  * blocked imports still blocked                    (test_blocked_*)
  * ``import pytest`` works inside the sandbox       (test_pytest_*)
  * standard-library imports work                    (test_stdlib_*)
  * modern Python 3.11 import-hook protocol is used  (test_import_hook_*)
  * sandbox cleanup / no import-hook leakage         (test_cleanup_*)
  * security policy not weakened                     (test_policy_*, test_security_*)
  * network restrictions preserved                   (test_network_*)
"""
import builtins
import socket
import sys
import textwrap

import pytest

from agent.coder import sandbox
from agent.coder.sandbox import (
    _ALLOWED_EXACT_MODULES,
    _BLOCKED_MODULES,
    _BLOCKED_OS,
    _BLOCKED_SUBPROCESS_API,
)

TIMEOUT = 60


def run(ws, code: str):
    """Execute ``code`` inside the real sandbox and return the result dict."""
    return sandbox.execute_code(str(ws), textwrap.dedent(code), timeout=TIMEOUT)


def ok(res) -> bool:
    return res["exit_code"] == 0


def why(res) -> str:
    return f"exit={res['exit_code']}\nstdout={res['stdout']}\nstderr={res['stderr']}"


# --------------------------------------------------------------------------
# Part 2 / Part 5 — the security POLICY itself must not have been weakened.
# --------------------------------------------------------------------------

# The exact policy that existed before Phase 6.6. Hard-coded on purpose: if
# anyone silently shrinks the blocklist, this test fails.
_POLICY_BEFORE_6_6 = {
    "socket", "urllib", "requests", "http", "subprocess", "smtplib", "ftplib",
    "telnetlib", "paramiko", "webbrowser", "poplib", "imaplib", "nntplib",
    "http.client", "ssl",
}


def test_policy_blocklist_not_shrunk():
    """Every module blocked before Phase 6.6 is still blocked."""
    assert _POLICY_BEFORE_6_6 <= _BLOCKED_MODULES


def test_policy_allowlist_is_narrow_and_capability_free():
    """The harness exception list is exact-match only and grants no capability."""
    assert _ALLOWED_EXACT_MODULES == {"urllib", "urllib.parse"}
    # The network-capable members of urllib must NOT be exempted.
    for dangerous in ("urllib.request", "urllib.error", "urllib.response",
                      "urllib.robotparser"):
        assert dangerous not in _ALLOWED_EXACT_MODULES
    # No exemption may be a bare top-level blocked module other than the empty
    # ``urllib`` namespace package.
    assert _ALLOWED_EXACT_MODULES & _BLOCKED_MODULES == {"urllib"}


def test_policy_destructive_os_and_subprocess_api_still_listed():
    for fn in ("system", "popen", "execv", "posix_spawn", "remove", "unlink",
               "rmdir", "removedirs"):
        assert fn in _BLOCKED_OS
    for fn in ("Popen", "run", "call", "check_call", "check_output"):
        assert fn in _BLOCKED_SUBPROCESS_API


def test_policy_blocker_is_not_allow_all(tmp_path):
    """The blocker must deny by default, not merely deny a hand-picked few."""
    res = run(tmp_path, """
        import sys
        blk = [f for f in sys.meta_path if type(f).__name__ == '_ImportBlocker'][0]
        denied = 0
        for name in sorted(blk.BLOCK):
            if name in blk.ALLOW:
                continue
            try:
                blk._check(name)
            except ImportError:
                denied += 1
        print('DENIED', denied, 'OF', len(blk.BLOCK) - len(blk.BLOCK & blk.ALLOW))
        assert denied == len(blk.BLOCK) - len(blk.BLOCK & blk.ALLOW)
    """)
    assert ok(res), why(res)
    expected = len(_BLOCKED_MODULES) - len(_BLOCKED_MODULES & _ALLOWED_EXACT_MODULES)
    assert f"DENIED {expected} OF {expected}" in res["stdout"], res["stdout"]


# --------------------------------------------------------------------------
# Part 4.1 — allowed imports
# --------------------------------------------------------------------------

def test_allowed_import_third_party_math_stack(tmp_path):
    res = run(tmp_path, """
        import math, json, csv, dataclasses, decimal, fractions, statistics
        print('ALLOWED_OK', math.sqrt(16), json.dumps({'a': 1}))
    """)
    assert ok(res), why(res)
    assert "ALLOWED_OK 4.0" in res["stdout"]


def test_allowed_import_urllib_parse_is_pure_string_parsing(tmp_path):
    """urllib.parse is exempted, but it is a parser - it must not reach the net."""
    res = run(tmp_path, """
        import urllib.parse
        print('PARSE', urllib.parse.urlparse('https://example.com/a?b=1').netloc)
        assert not hasattr(urllib.parse, 'urlopen')
        import urllib
        assert not hasattr(urllib, 'request')
    """)
    assert ok(res), why(res)
    assert "PARSE example.com" in res["stdout"]


# --------------------------------------------------------------------------
# Part 4.4 — standard-library imports
# --------------------------------------------------------------------------

def test_stdlib_import_pathlib_and_friends(tmp_path):
    """pathlib pulls urllib.parse at module scope - the classic breakage."""
    res = run(tmp_path, """
        import pathlib, tempfile, logging, warnings, unittest, typing, re, io
        import email.message, importlib.metadata
        print('STDLIB_OK', pathlib.PurePosixPath('/a/b').name)
    """)
    assert ok(res), why(res)
    assert "STDLIB_OK b" in res["stdout"]


# --------------------------------------------------------------------------
# Part 4.2 / Part 5 — blocked imports remain blocked
# --------------------------------------------------------------------------

@pytest.mark.parametrize("module", [
    "requests", "ssl", "smtplib", "ftplib", "telnetlib", "poplib", "imaplib",
    "nntplib", "paramiko", "webbrowser", "http", "http.client",
    "urllib.request", "urllib.error", "urllib.robotparser",
])
def test_blocked_import_raises_importerror(tmp_path, module):
    res = run(tmp_path, f"""
        try:
            import {module}
        except ImportError as e:
            print('BLOCKED_OK', {module!r}, str(e)[:80])
        else:
            raise AssertionError({module!r} + ' was NOT blocked')
    """)
    assert ok(res), why(res)
    assert f"BLOCKED_OK {module}" in res["stdout"], res["stdout"]
    # Must be OUR refusal, not an incidental "package not installed".
    assert "Blocked module in Sovereign sandbox" in res["stdout"], res["stdout"]


def test_blocked_import_via_importlib_import_module(tmp_path):
    """The importlib.import_module back door honours the same policy."""
    res = run(tmp_path, """
        import importlib
        for name in ('requests', 'ssl', 'urllib.request', 'smtplib'):
            try:
                importlib.import_module(name)
            except ImportError:
                print('IMPORTLIB_BLOCKED', name)
            else:
                raise AssertionError(name + ' reachable via importlib')
    """)
    assert ok(res), why(res)
    for name in ("requests", "ssl", "urllib.request", "smtplib"):
        assert f"IMPORTLIB_BLOCKED {name}" in res["stdout"]


def test_blocked_import_via_dunder_import(tmp_path):
    res = run(tmp_path, """
        for name in ('requests', 'ssl', 'urllib.request'):
            try:
                __import__(name)
            except ImportError:
                print('DUNDER_BLOCKED', name)
            else:
                raise AssertionError(name + ' reachable via __import__')
    """)
    assert ok(res), why(res)
    for name in ("requests", "ssl", "urllib.request"):
        assert f"DUNDER_BLOCKED {name}" in res["stdout"]


# --------------------------------------------------------------------------
# Part 4.5 — Python 3.11 import-hook protocol
# --------------------------------------------------------------------------

def test_import_hook_implements_find_spec(tmp_path):
    res = run(tmp_path, """
        import sys, inspect
        blockers = [f for f in sys.meta_path if type(f).__name__ == '_ImportBlocker']
        assert len(blockers) == 1, blockers
        blk = blockers[0]
        assert callable(getattr(blk, 'find_spec', None)), 'find_spec missing'
        params = list(inspect.signature(blk.find_spec).parameters)
        print('FIND_SPEC_PARAMS', params)
        assert params[:3] == ['fullname', 'path', 'target']
        # It must be installed FIRST so nothing can be resolved behind its back.
        assert sys.meta_path[0] is blk
    """)
    assert ok(res), why(res)
    assert "FIND_SPEC_PARAMS ['fullname', 'path', 'target']" in res["stdout"]


def test_import_hook_uses_modern_protocol_not_legacy_fallback(tmp_path):
    """Regression guard for the original defect.

    On Python 3.11 a meta-path finder without ``find_spec`` is reached through
    ``importlib._bootstrap._find_spec_legacy``, which emits an ``ImportWarning``
    (and on Python >= 3.12 such a finder is skipped entirely, silently turning
    the blocker into allow-all). Turning ImportWarning into an error proves the
    modern ``find_spec`` hook is the one actually being used.
    """
    res = run(tmp_path, """
        import warnings
        warnings.simplefilter('error', ImportWarning)
        import json.decoder, email.header, gzip, base64
        print('MODERN_PROTOCOL_OK')
    """)
    assert ok(res), why(res)
    assert "MODERN_PROTOCOL_OK" in res["stdout"]


def test_import_hook_blocks_through_importlib_util_find_spec(tmp_path):
    """importlib.util.find_spec goes straight through the machinery's find_spec."""
    res = run(tmp_path, """
        import importlib.util
        try:
            importlib.util.find_spec('requests')
        except ImportError as e:
            print('FIND_SPEC_BLOCKED', str(e)[:60])
        else:
            raise AssertionError('find_spec did not block requests')
    """)
    assert ok(res), why(res)
    assert "FIND_SPEC_BLOCKED" in res["stdout"]


def test_import_hook_legacy_alias_enforces_same_policy(tmp_path):
    """find_module is retained only as an alias - it must not be an escape hatch."""
    res = run(tmp_path, """
        import sys
        blk = sys.meta_path[0]
        try:
            blk.find_module('requests')
        except ImportError:
            print('LEGACY_ALIAS_BLOCKS')
        else:
            raise AssertionError('legacy find_module allowed requests')
        assert blk.find_module('math') is None
    """)
    assert ok(res), why(res)
    assert "LEGACY_ALIAS_BLOCKS" in res["stdout"]


# --------------------------------------------------------------------------
# Part 4.3 — pytest works inside the sandbox
# --------------------------------------------------------------------------

def test_pytest_imports_inside_sandbox(tmp_path):
    res = run(tmp_path, """
        import pytest
        print('PYTEST_IMPORT_OK', pytest.__version__)
    """)
    assert ok(res), why(res)
    assert "PYTEST_IMPORT_OK" in res["stdout"]


def test_pytest_verification_reports_real_pass(tmp_path):
    (tmp_path / "solution.py").write_text(
        "def double(x):\n"
        "    if not isinstance(x, (int, float)):\n"
        "        raise TypeError('numeric required')\n"
        "    return 2 * x\n",
        encoding="utf-8",
    )
    (tmp_path / "test_solution.py").write_text(
        "import pytest\n"
        "from solution import double\n"
        "def test_valid():\n"
        "    assert double(3) == 6\n"
        "def test_invalid():\n"
        "    with pytest.raises(TypeError):\n"
        "        double('x')\n",
        encoding="utf-8",
    )
    res = sandbox.run_tests(str(tmp_path), "test_solution.py", timeout=TIMEOUT)
    assert res["passed"] is True, why(res)
    assert res["exit_code"] == 0
    assert "2 passed" in res["stdout"], res["stdout"]
    assert res["external_network_calls"] == 0


def test_pytest_verification_reports_real_failure(tmp_path):
    """The harness must not paper over failures - the repair loop depends on it."""
    (tmp_path / "solution.py").write_text("def double(x):\n    return 3 * x\n",
                                          encoding="utf-8")
    (tmp_path / "test_solution.py").write_text(
        "from solution import double\n"
        "def test_valid():\n    assert double(3) == 6\n",
        encoding="utf-8",
    )
    res = sandbox.run_tests(str(tmp_path), "test_solution.py", timeout=TIMEOUT)
    assert res["passed"] is False
    assert res["exit_code"] != 0
    assert "1 failed" in res["stdout"], res["stdout"]
    # A usable diagnostic must reach the model.
    assert "test_valid" in res["stdout"]


def test_pytest_import_policy_still_applies_to_generated_tests(tmp_path):
    """pytest being importable must not make the test file itself privileged."""
    (tmp_path / "test_solution.py").write_text(
        "import pytest\n"
        "def test_requests_blocked():\n"
        "    with pytest.raises(ImportError):\n"
        "        import requests\n"
        "def test_ssl_blocked():\n"
        "    with pytest.raises(ImportError):\n"
        "        import ssl\n"
        "def test_urllib_request_blocked():\n"
        "    with pytest.raises(ImportError):\n"
        "        import urllib.request\n"
        "def test_subprocess_spawn_blocked():\n"
        "    import subprocess\n"
        "    with pytest.raises(PermissionError):\n"
        "        subprocess.Popen(['cmd', '/c', 'echo', 'pwned'])\n"
        "def test_os_system_blocked():\n"
        "    import os\n"
        "    with pytest.raises(PermissionError):\n"
        "        os.system('echo pwned')\n",
        encoding="utf-8",
    )
    res = sandbox.run_tests(str(tmp_path), "test_solution.py", timeout=TIMEOUT)
    assert res["passed"] is True, why(res)
    assert "5 passed" in res["stdout"], res["stdout"]


# --------------------------------------------------------------------------
# Part 5 — security regression (execution capability)
# --------------------------------------------------------------------------

def test_security_subprocess_real_module_never_loaded(tmp_path):
    res = run(tmp_path, """
        import subprocess
        print('SP_FILE', getattr(subprocess, '__file__', None))
        assert getattr(subprocess, '__file__', None) is None, 'real subprocess loaded!'
        for name in ('Popen', 'run', 'call', 'check_call', 'check_output',
                     'getoutput', 'getstatusoutput'):
            try:
                getattr(subprocess, name)(['cmd', '/c', 'echo', 'pwned'])
            except PermissionError:
                print('SP_DENIED', name)
            else:
                raise AssertionError('subprocess.' + name + ' executed!')
    """)
    assert ok(res), why(res)
    assert "SP_FILE None" in res["stdout"]
    for name in ("Popen", "run", "call", "check_call", "check_output",
                 "getoutput", "getstatusoutput"):
        assert f"SP_DENIED {name}" in res["stdout"]


def test_security_os_shell_and_destructive_calls_blocked(tmp_path):
    res = run(tmp_path, """
        import os
        for fn in ('system', 'popen', 'remove', 'unlink', 'rmdir', 'removedirs'):
            try:
                getattr(os, fn)('anything')
            except PermissionError:
                print('OS_DENIED', fn)
            else:
                raise AssertionError('os.' + fn + ' executed!')
    """)
    assert ok(res), why(res)
    for fn in ("system", "popen", "remove", "unlink", "rmdir", "removedirs"):
        assert f"OS_DENIED {fn}" in res["stdout"]


def test_security_filesystem_scoped_to_workspace(tmp_path):
    """Inside the workspace: allowed. Outside: refused."""
    res = run(tmp_path, """
        import os
        with open('inside.txt', 'w') as f:
            f.write('hello')
        print('INSIDE_WRITE_OK', open('inside.txt').read())
        for target in (os.path.join(os.path.dirname(os.getcwd()), 'escape.txt'),
                       os.path.join('..', 'escape2.txt')):
            try:
                open(target, 'w')
            except PermissionError as e:
                print('OUTSIDE_DENIED', str(e)[:60])
            else:
                raise AssertionError('escaped the workspace: ' + target)
    """)
    assert ok(res), why(res)
    assert "INSIDE_WRITE_OK hello" in res["stdout"]
    assert res["stdout"].count("OUTSIDE_DENIED") == 2, res["stdout"]
    assert (tmp_path / "inside.txt").exists()
    assert not (tmp_path.parent / "escape.txt").exists()


def test_security_secrets_stripped_from_child_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("SOVEREIGN_TEST_API_KEY", "super-secret-value")
    monkeypatch.setenv("HF_TOKEN", "hf-secret")
    res = run(tmp_path, """
        import os
        leaked = [k for k in os.environ if 'KEY' in k.upper() or 'TOKEN' in k.upper()]
        print('LEAKED', leaked)
        assert 'super-secret-value' not in ''.join(os.environ.values())
    """)
    assert ok(res), why(res)
    assert "LEAKED []" in res["stdout"], res["stdout"]


# --------------------------------------------------------------------------
# Part 8 — network restrictions preserved
# --------------------------------------------------------------------------

def test_network_external_connect_blocked_and_counted(tmp_path):
    res = run(tmp_path, """
        import socket
        s = socket.socket()
        try:
            s.connect(('8.8.8.8', 53))
        except ConnectionError as e:
            print('NET_BLOCKED', str(e)[:70])
        else:
            raise AssertionError('external connection succeeded!')
    """)
    assert ok(res), why(res)
    assert "NET_BLOCKED" in res["stdout"]
    # The attempt is recorded by the sandbox, not merely refused.
    assert res["network_blocked"] >= 1, res
    assert res["external_network_calls"] == 0


def test_network_probe_used_by_evaluation_still_reports_blocked():
    """Criterion 9 of the coder evaluation must still see a blocked network."""
    from agent.coder.evaluation import _probe_sandbox_blocks_network
    probe = _probe_sandbox_blocks_network()
    assert probe["blocked"] is True, probe


def test_network_no_network_module_reachable_for_new_imports(tmp_path):
    res = run(tmp_path, """
        import sys
        # Nothing that can open a new outbound channel may be freshly importable.
        for name in ('requests', 'ssl', 'http.client', 'urllib.request',
                     'smtplib', 'ftplib'):
            assert name not in sys.modules, name + ' preloaded!'
            try:
                __import__(name)
            except ImportError:
                pass
            else:
                raise AssertionError(name + ' importable')
        print('NO_NET_MODULES_OK')
    """)
    assert ok(res), why(res)
    assert "NO_NET_MODULES_OK" in res["stdout"]


# --------------------------------------------------------------------------
# Part 4.6 — sandbox cleanup / no import-hook leakage
# --------------------------------------------------------------------------

def test_cleanup_parent_meta_path_untouched_by_execute_code(tmp_path):
    before = list(sys.meta_path)
    before_open = builtins.open
    before_connect = socket.socket.connect
    res = run(tmp_path, "import sys; print('HOOKS', len(sys.meta_path))")
    assert ok(res), why(res)
    assert list(sys.meta_path) == before, "sys.meta_path leaked after execute_code"
    assert builtins.open is before_open, "builtins.open leaked"
    assert socket.socket.connect is before_connect, "socket.connect leaked"
    assert not any(type(f).__name__ == "_ImportBlocker" for f in sys.meta_path)


def test_cleanup_parent_meta_path_untouched_by_run_tests(tmp_path):
    (tmp_path / "test_solution.py").write_text(
        "def test_trivial():\n    assert True\n", encoding="utf-8")
    before = list(sys.meta_path)
    before_open = builtins.open
    before_connect = socket.socket.connect
    res = sandbox.run_tests(str(tmp_path), "test_solution.py", timeout=TIMEOUT)
    assert res["passed"] is True, why(res)
    assert list(sys.meta_path) == before, "sys.meta_path leaked after run_tests"
    assert builtins.open is before_open, "builtins.open leaked"
    assert socket.socket.connect is before_connect, "socket.connect leaked"


def test_cleanup_parent_state_restored_even_when_sandbox_code_crashes(tmp_path):
    before = list(sys.meta_path)
    res = run(tmp_path, "raise RuntimeError('boom')")
    assert res["exit_code"] != 0
    assert "boom" in res["stderr"]
    assert list(sys.meta_path) == before


def test_cleanup_hook_installed_exactly_once_and_not_accumulated(tmp_path):
    """Repeated runs must not stack hooks (each run is a fresh interpreter)."""
    code = """
        import sys
        n = sum(1 for f in sys.meta_path if type(f).__name__ == '_ImportBlocker')
        print('BLOCKER_COUNT', n)
    """
    for _ in range(3):
        res = run(tmp_path, code)
        assert ok(res), why(res)
        assert "BLOCKER_COUNT 1" in res["stdout"], res["stdout"]


def test_cleanup_runner_scripts_removed_from_workspace(tmp_path):
    (tmp_path / "test_solution.py").write_text(
        "def test_trivial():\n    assert True\n", encoding="utf-8")
    run(tmp_path, "print('hi')")
    sandbox.run_tests(str(tmp_path), "test_solution.py", timeout=TIMEOUT)
    leftovers = sorted(p.name for p in tmp_path.iterdir()
                       if p.name.startswith(("_run_", "_pytest_")) and p.is_file())
    assert leftovers == [], f"sandbox left runner scripts behind: {leftovers}"


def test_cleanup_net_log_consumed_and_not_left_behind(tmp_path):
    res = run(tmp_path, """
        import socket
        try:
            socket.socket().connect(('8.8.8.8', 53))
        except ConnectionError:
            pass
    """)
    assert res["network_blocked"] >= 1, res
    assert not (tmp_path / ".net_blocked.log").exists()


# --------------------------------------------------------------------------
# Workspace path handling (the guard must compare real paths)
# --------------------------------------------------------------------------

def test_prelude_embeds_a_usable_workspace_path():
    """Regression: a raw literal with pre-doubled backslashes never matched."""
    import os as _os
    src = sandbox._prelude(r"C:\tmp\ws 1")
    ns = {"os": _os}
    exec(compile("\n".join(l for l in src.splitlines() if "_WORKSPACE =" in l),
                 "<prelude>", "exec"), ns)
    assert ns["_WORKSPACE"] == _os.path.abspath(r"C:\tmp\ws 1")
