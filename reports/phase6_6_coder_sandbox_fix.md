# Phase 6.6 — Coder Sandbox Repair

> All results below were produced on the developer machine in the conda env
> `sovereign-ai` (Python 3.11.9) against the **live** local stack: Qwen2.5-Coder-3B
> on `:8002`, Qwen2.5-VL-3B on `:8003`, FastAPI on `:8000`, embedded Qdrant + BM25.
> No mocks. Every PASS/FAIL below is a verdict emitted by pytest running *inside*
> the sandbox, not an assertion made by hand.

## Original Defect

Phase 6.5 reported that generated-code verification failed with:

```
AttributeError: '_ImportBlocker' object has no attribute 'find_spec'
```

`backend/agent/coder/sandbox.py` built the child interpreter's import blocker with
only the deprecated `MetaPathFinder.find_module()` hook:

```python
class _ImportBlocker:
    BLOCK = {...}
    def find_module(self, name, path=None):        # deprecated (Py 3.4), removed in 3.12
        ...
```

Reproduced verbatim before any change:

```
Traceback (most recent call last):
  File "<frozen importlib._bootstrap>", line 1072, in _find_spec
AttributeError: '_ImportBlocker' object has no attribute 'find_spec'
During handling of the above exception, another exception occurred:
  ...
  File ".../Lib/pathlib.py", line 14, in <module>
    from urllib.parse import quote_from_bytes as urlquote_from_bytes
  File ".../_pytest_<hex>.py", line 16, in find_module
    raise ImportError("Blocked module in Sovereign sandbox: " + top)
ImportError: Blocked module in Sovereign sandbox: urllib
```

## Root Cause

The reported `AttributeError` is a **symptom, not the cause**. Investigation found
**three** distinct defects behind the verification failure.

### 1. Deprecated import-hook API (the reported defect)

Python 3.11's `importlib._bootstrap._find_spec` does `find_spec = finder.find_spec`
first; the resulting `AttributeError` is caught and it falls back to
`_find_spec_legacy` → `find_module`. So on 3.11 the blocker *did* still fire — via
the deprecated path — which is why the `AttributeError` appears only as the
`During handling of the above exception` frame.

The genuinely dangerous part: `_find_spec_legacy` was **removed in Python 3.12**. A
`find_module`-only meta-path finder is then *silently skipped*, which would turn the
import blocker into a complete **allow-all**. So this was also a latent security
hole, not merely a compatibility wart.

### 2. Import policy blocked stdlib the interpreter needs unconditionally

The policy blocks whole top-level packages. Core stdlib depends on some of them, so
`import pytest` could never complete. Verified by bisecting each block:

| Blocked top-level | Reached via | Consequence |
|---|---|---|
| `urllib` | `pathlib` line 14 → `from urllib.parse import quote_from_bytes` | `import pathlib` fails ⇒ pytest cannot import |
| `socket` | `importlib.metadata` → `email.message` → `email.utils` line 29 → `import socket` | (masked: prelude pre-imports `socket`) |
| `subprocess` | `_pytest/legacypath.py` line 9 → `import subprocess` | `sys.modules["subprocess"] = None` ⇒ pytest cannot import |

Additionally, `pytest.main()` auto-loads third-party `pytest11` entry-point plugins
from the host env; in this env `anyio` does `import ssl` → blocked → `INTERNALERROR`.

### 3. Filesystem guard could never match a real path (second genuine defect)

The prelude emitted the workspace as a **raw** literal with **pre-doubled**
backslashes:

```python
ws = workspace.replace("\\", "\\\\")
...
_WORKSPACE = r"{ws}"          # -> _WORKSPACE = r"C:\\tmp\\ws1"
```

In a raw literal the backslashes are *not* unescaped, so the child's `_WORKSPACE`
was `C:\\tmp\\ws1` (two backslashes) and `os.path.abspath(path).startswith(_WORKSPACE)`
was **always False**. Measured before the fix:

```
GENERATED LINE: _WORKSPACE = r"C:\\tmp\\ws1"
CHILD _WORKSPACE value : 'C:\\\\tmp\\\\ws1'
EXPECTED               : 'C:\\tmp\\ws1'
MATCHES                : False
```

Consequences: `open()` refused **every** path including legitimate workspace files
(so generated code could never read its own `sensor_fixture.csv`), and `_NET_LOG`
pointed at a bogus path — which is exactly why Phase 6.5 observed
`network_blocked=0` even though connections were being refused.

This guard failed *closed*, so it was never a security hole — but it made the
documented "scoped to workspace" policy unimplementable.

## Fix

One production file changed: `backend/agent/coder/sandbox.py` (+95 / −18).

1. **Modern import hook.** `_ImportBlocker` now implements `find_spec(fullname, path,
   target)` and routes both hooks through one `_check()` policy method.
   `find_module` is retained as a legacy alias enforcing the *identical* policy, so
   the block also holds on any interpreter that still consults the old hook.
   `importlib.import_module` uses the same `_check()`.
2. **Narrow, capability-free allowlist.** `_ALLOWED_EXACT_MODULES = {"urllib",
   "urllib.parse"}` — exact-name matches only. `urllib/__init__.py` is empty and
   `urllib.parse` is a pure URL *string* parser. `urllib.request`, `urllib.error`,
   `urllib.response`, `urllib.robotparser` remain blocked.
3. **`subprocess` stub.** The real module is **never loaded**. A `types.ModuleType`
   stub is installed whose `Popen/run/call/check_call/check_output/getoutput/
   getstatusoutput/list2cmdline` all raise `PermissionError`. Strictly stronger than
   the previous `sys.modules["subprocess"] = None`: the real implementation and its
   `_winapi` import are never brought into the sandbox at all.
4. **Correct workspace literal.** `_WORKSPACE = os.path.abspath({repr(workspace)})`
   instead of a raw literal with pre-doubled backslashes.
5. **Hermetic pytest invocation** (backend choices only — no policy relaxation):
   `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` (no third-party plugins in the sandbox),
   `--capture=sys` (in-memory capture; the default fd-capture opens `os.devnull` and
   a `TemporaryFile` outside the workspace), `--log-file=_pytest.log` (redirects the
   logging plugin's default `os.devnull` sink into the workspace),
   `-p no:cacheprovider` (avoids `.pytest_cache` management via blocked destructive
   `os.*` calls).

Deliberately **not** changed: the blocklist, the destructive-`os.*` list, the
`socket.connect` guard, the env allowlist, the workspace scoping rule, timeouts,
NetworkGuard, the coder graph/prompts/model, and every unrelated file.

## Security Preservation

| Property | Before | After | Evidence |
|---|---|---|---|
| Import blocking | 15 top-level modules, via deprecated hook (allow-all on ≥3.12) | same 15, via `find_spec` + legacy alias | `test_policy_blocklist_not_shrunk`, `test_policy_blocker_is_not_allow_all` (14/14 non-exempt denied) |
| Deny-by-default | yes | yes — allowlist is 2 exact names, both capability-free | `test_policy_allowlist_is_narrow_and_capability_free` |
| `urllib.request` etc. | blocked | **still blocked** | `test_blocked_import_raises_importerror[urllib.request/error/robotparser]` |
| Back doors (`importlib.import_module`, `__import__`, `importlib.util.find_spec`) | blocked | still blocked | 3 dedicated tests |
| Process creation | `import subprocess` → ImportError | stub; real module never loaded; all spawn APIs raise | `test_security_subprocess_real_module_never_loaded` (`__file__ is None`) |
| Shell / destructive `os.*` | blocked | unchanged | `test_security_os_shell_and_destructive_calls_blocked` |
| Filesystem scope | guard broken (denied everything) | correctly workspace-scoped; `..` traversal refused | `test_security_filesystem_scoped_to_workspace` |
| Secrets stripped | yes | unchanged | `test_security_secrets_stripped_from_child_environment` |
| Network blocking | connect guard active; counter broken | connect guard active; **counter now works** | `test_network_external_connect_blocked_and_counted` (`network_blocked >= 1`) |
| Sandbox cleanup | child process, parent untouched | unchanged + explicitly asserted | 6 `test_cleanup_*` tests |

**No allow-all was introduced.** The allowlist is exact-match (`urllib.parse` is
permitted; `urllib.request` is not), and `test_policy_blocker_is_not_allow_all`
asserts that every non-exempt blocked name is still denied *from inside the
sandbox*.

**Net security change: two hardenings.** The `find_spec` migration closes the
Python-3.12 allow-all hole, and the `subprocess` stub keeps the real module out of
the sandbox entirely.

### `sys.meta_path` restoration / no hook leakage

The sandbox executes in a **separate child interpreter**, so the parent's import
state is never mutated. Asserted explicitly rather than assumed:

- `sys.meta_path` list-equal before/after `execute_code` and `run_tests`
- `builtins.open` and `socket.socket.connect` identity-unchanged
- no `_ImportBlocker` present in the parent afterwards
- state restored even when the sandboxed code raises
- exactly **one** blocker inside the child, at index 0, and no accumulation across
  3 consecutive runs
- runner scripts (`_run_*.py`, `_pytest_*.py`) deleted; `.net_blocked.log` consumed

## Unit Tests

New file: `backend/tests/test_coder_sandbox.py` — 46 tests, every one spawning the
real sandbox.

```
tests/test_coder_sandbox.py .............................................. [100%]
46 passed in 7.73s
```

- **Passed: 46**
- **Failed: 0**
- **Skipped: 0**

Coverage map: allowed imports (2) · stdlib imports (1) · blocked imports (15
parametrised + 2 back doors) · pytest inside sandbox (4) · import-hook protocol (4)
· security regression (4) · network (3) · cleanup / no leakage (6) · policy
invariants (4) · workspace-path regression (1).

Two of these are explicit regression guards for the original defect:
- `test_import_hook_uses_modern_protocol_not_legacy_fallback` — turns
  `ImportWarning` into an error inside the sandbox, so if the finder ever loses
  `find_spec` and falls back to `_find_spec_legacy`, the test fails.
- `test_prelude_embeds_a_usable_workspace_path` — pins the escaping fix.

Coder-related subset run separately, as required:

```
pytest tests/test_coder_sandbox.py tests/test_coder.py tests/test_netguard.py
58 passed, 1 skipped in 209.30s
```

## Coder E2E

Task (identical to Phase 6.5): *"Write a Python function that calculates Reynolds
number. Include input validation."*

Run via `POST /api/coder/run` — the same endpoint the frontend uses and the same one
Phase 6.5 measured:

| Stage | Phase 6.5 | Phase 6.6 |
|---|---|---|
| server (`:8002`) | PASS | **PASS** |
| routing | PASS (`qwen-coder`, local) | **PASS** (`qwen-coder`, `confidence=0.88`) |
| **Generation** | PASS | **PASS** |
| **Sandbox** | EXECUTED | **EXECUTED** (`duration=0.319s`) |
| **Verification** | **FAILED (harness defect)** | **PASS** (`exit_code=0`, `1 passed`) |
| repair loop | n/a (harness never ran) | **3 iterations**, 3 real TEST_FAILED → TEST_PASSED |
| final result | `FAILED` | **`COMPLETED`** |
| external calls | 0 | **0** |
| latency | 573.82 s | **281.66 s** |

Live trace from the API run (`coder_aa11b497275f`):

```
understand_task SUCCESS 2884ms      run_tests TEST_FAILED 365ms
plan            SUCCESS 6203ms      analyze_failure SUCCESS 19389ms
generate_code   SUCCESS 70167ms     fix_code SUCCESS 23297ms
write_workspace SUCCESS 8ms         run_tests TEST_FAILED 386ms
run_tests       TEST_FAILED 384ms   analyze_failure SUCCESS 28650ms
analyze_failure SUCCESS 35722ms     fix_code SUCCESS 27679ms
fix_code        SUCCESS 66122ms     run_tests TEST_PASSED 318ms
                                    verify PASS 2ms / final COMPLETED
```

A second direct run of `run_coder_task` (`coder_d75cd762ca35`, 360.44 s, 4 repair
iterations) also reached `COMPLETED` and scored **10/10** on the existing
`agent.coder.evaluation` checklist, including criterion 9 (live external-socket
probe blocked) and criterion 10 (external calls = 0).

**Generation:** PASS · **Sandbox:** EXECUTED · **Verification:** PASS ·
**Final result:** COMPLETED

## Generated-Code Verification (Part 7)

The model's own test was weak, so the generated implementation was re-verified
against an **independent** suite written for this phase and executed *inside the
sandbox* (`solution.py` copied unmodified from `coder_d75cd762ca35`):

```python
def calculate_reynolds_number(diameter, velocity, fluid_density, kinematic_viscosity):
    if diameter <= 0 or velocity <= 0 or fluid_density <= 0 or kinematic_viscosity <= 0:
        raise ValueError("All parameters must be positive.")
    return (velocity * diameter) / kinematic_viscosity
```

```
13 passed in 0.05s      (sandbox passed=True, exit_code=0)
  test_valid_typical_water_flow                 Re = 100000.0
  test_valid_laminar_regime                     Re = 50.0    (<2300)
  test_valid_turbulent_regime                   Re = 600000.0 (>4000)
  test_valid_scales_linearly_with_velocity
  test_invalid_inputs_rejected[8 cases]          zero/negative D, v, rho, nu
  test_invalid_zero_viscosity_does_not_raise_zerodivision
```

**Negative control** — a deliberately wrong expectation, to prove the harness can
still fail and that the PASS above is not vacuous:

```
test_deliberately_wrong_expectation FAILED
E   assert 100000.00000000001 == 42.0
1 failed in 0.07s       (sandbox passed=False, exit_code=1)
```

Re = v·D/ν is correct for the kinematic-viscosity form. Validation is correct and
ordered *before* the division. Honest caveats: `fluid_density` is validated but
unused, and the model's **own** generated test (`test_analyze`) is near-vacuous —
it creates a CSV and contains `# Add test cases here`. The sandbox reported that
test's real result (1 passed); it simply asserts very little. That is model
quality, not harness behaviour.

## Regression Tests

Full suite run with both model servers live (same conditions as Phase 6.5) and the
FastAPI backend stopped so the embedded Qdrant index was not double-locked.

| Area | Tests | Result |
|---|---|---|
| **Vision** | `test_vision.py` (10) incl. `test_vision_inference_stays_local`, `test_pid_analysis_returns_structured_evidence` | **PASS** |
| **RAG** | `test_tools.py::test_search_knowledge_base_*` (2), `test_vision.py::test_vision_tags_drive_rag_retrieval` | **PASS** |
| **Multimodal** | `test_vision.py::test_end_to_end_multimodal_task`, `test_agent_e2e.py::test_full_task_end_to_end` | **PASS** |
| **Artifact** | `test_tools.py::test_create_and_verify_docx`, `test_agent_e2e.py::test_evaluation_against_ground_truth` | **PASS** |
| **Frontend** | `test_agent_e2e.py::test_fastapi_endpoint`; `git status -- frontend` clean (zero frontend files touched); live `/api/system/status` → 200 `sovereign=True` | **PASS** |
| **Network sovereignty** | `test_netguard.py` (12), `test_agent_e2e.py::test_zero_external_network_calls`, `test_netguard_blocks_external_connections` | **PASS** |

No regression occurred, so no investigation was needed and no unrelated component
was touched.

## Full Test Suite

```
pytest tests rag/tests        (from backend/, both model servers up)
101 passed, 1 skipped in 578.97s (0:09:38)          exit code 0
SKIPPED [1] tests/test_coder.py:42: local Qwen Coder server not running
```

- **Passed: 101**
- **Failed: 0**
- **Skipped: 1**

Baseline reconciliation: Phase 6.5 recorded 55 passed + 1 skipped = 56. This phase
adds 46 new tests → 55 + 46 = **101 passed**, same 1 skip. **No new regression, no
lost coverage, no weakened assertion, no failure converted into a skip.**

### Classification of every non-pass

| Item | Classification | Detail |
|---|---|---|
| `test_coder.py::test_coder_pipeline_end_to_end` skipped | **pre-existing** (Phase 6.5 already flagged it) | Its probe builds `…/v1/v1/models` (double `/v1`) so it skips even with the server up. See Remaining Issues #2. |
| `ingestion/tests/test_hardening.py`, `test_ingestion.py` collection errors when running bare `pytest` from `backend/` | **pre-existing / environment** | `backend/ingestion` is a *separate* project (own `pyproject.toml`, own `app/` package, `requires-python >=3.14`). `backend/app` shadows `backend/ingestion/app`. Unrelated to Phase 6.6; excluded from the suite path exactly as in Phase 6.5. |
| `rag/tests/test_retrieval.py` collects 0 tests | **pre-existing** | It is a manual demo script (`main()` + `if __name__ == "__main__"`), not a pytest module. |
| Nothing | fixed-by-6.6 regressions | none |
| Nothing | unrelated regressions | none |

## Performance

| Metric | Phase 6.5 | Phase 6.6 |
|---|---|---|
| Coder E2E via `POST /api/coder/run` | 573.82 s (ended in FAILED) | **281.66 s** (ended in COMPLETED) |
| Coder E2E direct `run_coder_task` | — | 360.44 s (COMPLETED, 10/10) |
| Sandbox pytest verification step | never completed | **0.318 – 0.491 s** |
| Repair iterations | n/a (harness never ran) | 3 (API) / 4 (direct) |
| 46-test sandbox suite (46 child interpreters) | — | 7.73 s |
| Full suite | ~? (55 tests) | 578.97 s (102 tests) |

The verification step costs ~0.3–0.5 s per iteration, so the fix adds negligible
overhead; end-to-end latency is dominated by CPU-only 3B inference. The latency
*improvement* is not an optimisation — the workflow now terminates as soon as tests
pass instead of exhausting the repair loop. Model inference was not touched. GPU
offload remains unavailable (CPU-only llama.cpp wheel, unchanged from Phase 6.5).

Security cost of the fix: none measurable. The blocker does one set membership test
plus one `str.split` per import — identical to before.

## Files Changed

| File | Change |
|---|---|
| `backend/agent/coder/sandbox.py` | **modified** (+95 / −18) — `find_spec` hook, exact-name allowlist, `subprocess` stub, workspace-literal fix, hermetic pytest flags, docstring corrected |
| `backend/tests/test_coder_sandbox.py` | **new** — 46 tests |

Nothing else was modified. Verified:

```
$ git diff --name-only
backend/agent/coder/sandbox.py
$ git status --short
 M backend/agent/coder/sandbox.py
?? backend/tests/test_coder_sandbox.py
```

(`.pyc` files under `__pycache__` are tracked by this repo and show as modified
after any test run; no `.py` source other than the two files above was touched. No
`git add`, `commit`, `reset`, `clean`, or `push` was performed.)

## Remaining Issues

1. **Same deprecated-hook defect still present in `backend/agent/tools/python_execute.py`
   (line 44).** The agent's *other* sandbox uses an identical `find_module`-only
   `_ImportBlocker`. On Python 3.11 it still works via the legacy fallback (its
   tests pass), but on Python ≥ 3.12 it would become **allow-all**. Not fixed here
   because Phase 6.6 is scoped to `agent/coder/sandbox.py` and the rules forbid
   modifying unrelated files. *Recommended as the next one-line phase.* Its path
   escaping is correct — it does **not** have defect #3.
2. **`test_coder.py` connectivity probe is still broken** (`…/v1/v1/models`), so the
   coder integration test skips even with the server running. I fixed it, measured
   the outcome, then **reverted** it: with the probe corrected the test genuinely
   runs (475 s) and **fails** because Qwen2.5-Coder-3B generates `pandas`-dependent
   code for the sensor-CSV demo task and `pandas` is **not installed** in this env
   (confirmed: absent from `backend/requirements.txt` and from the env), while the
   sandbox correctly forbids installing it. Shipping that would add a slow,
   model-nondeterministic red test for a reason unrelated to this phase. The
   one-line fix is `CODER_ENDPOINT.rstrip("/") + "/models"` in
   `backend/tests/test_coder.py:23` and `backend/scripts/run_coder_e2e.py:40`.
3. **Coder generation prompt is hard-coded to the sensor-CSV scenario.**
   `agent/coder/prompts.py:GEN_USER` instructs the model to produce
   `analyze(csv_path, thresholds)` + `sensor_fixture.csv` *regardless of the user's
   task*. For the Reynolds task the prompt fights the request, which is why the API
   run produced a CSV-loop `analyze()` rather than a clean validated function. This
   is a coder-agent design issue; the rules forbid redesigning the coder agent.
4. **`tempfile` is unusable inside the sandbox** (pre-existing policy interaction):
   `tempfile._get_default_tempdir()` probes candidate dirs and calls `os.unlink`,
   which the destructive-`os.*` policy blocks, so every candidate is rejected. Any
   generated test using the `tmp_path`/`tmpdir` fixtures will therefore fail.
   Fixing it would require relaxing the destructive-`os.*` policy, which this phase
   must not do.
5. **`open()` by file descriptor bypasses the workspace guard** (pre-existing):
   `_safe_open` calls `os.path.abspath(path)`, which raises `TypeError` on an `int`
   fd; and `io.open` / `pathlib.Path.open` are not wrapped at all. Defence in depth
   still applies (child process, clean env, blocked spawn, connect guard), but the
   filesystem guard is not airtight. Out of scope.
6. **`_winapi` / `_posixsubprocess` are importable** (pre-existing, unchanged):
   low-level process creation is reachable without `subprocess`. The `subprocess`
   stub does not make this worse — it makes it *less* reachable, since the real
   `subprocess` module (which imports `_winapi`) is no longer loaded.
7. **GPU acceleration still unavailable** (unchanged from Phase 6.5): the installed
   llama.cpp wheel is CPU-only; rebuilding it is forbidden.

## Final Verdict

# PHASE 6.6 COMPLETE

Stop-condition checklist:

| Requirement | Status | Evidence |
|---|---|---|
| Python 3.11 import blocker works | **YES** | `find_spec` implemented; `test_import_hook_*` (4 tests) |
| blocked imports remain blocked | **YES** | 15 parametrised + 2 back-door tests; blocklist invariant test |
| allowed imports remain allowed | **YES** | `test_allowed_*`, `test_stdlib_*` |
| pytest import works inside sandbox | **YES** | `test_pytest_imports_inside_sandbox`; live E2E |
| `sys.meta_path` is restored | **YES** | 6 `test_cleanup_*` tests (incl. crash path and 3× no-accumulation) |
| network restrictions remain | **YES** | connect guard blocks + **now counts** (`network_blocked>=1`); eval criterion 9 live probe; 12 NetworkGuard tests |
| coder generation works | **YES** | API + direct runs, `generate_code SUCCESS` |
| sandbox execution works | **YES** | `run_tests` executed 4× per run, real TEST_FAILED → TEST_PASSED |
| coder verification works | **YES** | `verification passed=True`, `exit_code=0`, `status=COMPLETED`, 10/10 evaluation |
| full test suite has no new regression | **YES** | 101 passed / 0 failed / 1 pre-existing skip (was 55 + 1) |
| report generated | **YES** | this file |

Phase 6.5's Coder verdict of **PARTIAL** is now resolved: the transition
`verification = FAIL → verification = PASS` was achieved by fixing the harness, with
the import policy, network policy, filesystem policy and cleanup guarantees all
preserved or strengthened — and with two additional latent defects (the Python-3.12
allow-all hole and the broken workspace-path comparison) closed along the way.
