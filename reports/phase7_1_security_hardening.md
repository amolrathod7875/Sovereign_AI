# Phase 7.1 — Security Hardening

Scope: fix the two remaining hardening issues from the Phase 7 sovereignty audit.
No architecture changes, no model/agent/RAG/NetworkGuard modifications.

---

## Issue 1 — `.env` protection

**Before:** Root `.gitignore` (11 lines) ignored models/data/caches only. It did
**not** ignore `.env` / `.env.local`, so a locally created `.env` (which can carry
`POSTGRES_URL` and other secrets) was at risk of being committed. `git ls-files`
showed no tracked secret `.env`, but the gap was real.

**After:** Added a secrets section to `D:\Sovereign_AI\.gitignore`:

```
# Secrets — never commit local env files
.env
.env.local
.env.*
!.env.example
```

`.env.example` files remain tracked (useful, non-secret); real secret files are ignored.

**Verification:**
- `git ls-files | findstr /E .env` → no secret-bearing `.env` tracked (only the
  checked-in `*.env.example` files: `backend/rag/.env.example`,
  `frontend/.env.example`, `infra/.env.example`).
- `git check-ignore .env` → `.gitignore:16:.env  .env` (confirmed ignored).
- `git check-ignore .env.local` and `git check-ignore backend/.env` → both ignored.
- No existing tracked `.env` exists, so nothing needed un-tracking.
- No secret values were printed.

---

## Issue 2 — Piston endpoint validation

`/api/sandbox` → Piston (`PISTON_URL`, default `http://piston:2000`) previously sent
execution requests with **no** endpoint validation and **no** NetworkGuard, so a
tampered `PISTON_URL` could offload code execution to an external host.

**Before:** `backend/app/tools/python_tool.py` called
`httpx.AsyncClient().post(f"{settings.PISTON_URL}/execute")` and `.../status`
directly, with no local/internal check.

**After:** Reused the existing endpoint-validation utility
(`app.models.registry.is_local_endpoint`) and added a Piston-specific internal check
that additionally permits internal docker/service hostnames (single-label names such
as `piston`, `postgres`, which resolve only inside the private deployment network):

- New helpers in `python_tool.py`:
  - `is_internal_piston_url(url)` — True for loopback / RFC1918 private IPs (via
    `is_local_endpoint`) **and** for internal hostnames (no dot, or `.local` /
    `.internal` / `.svc` / `.docker.internal` suffixes). Public FQDNs rejected.
  - `validate_piston_url(url)` — raises `ConnectionError` when not internal/local.
- `execute_in_sandbox()` and `get_sandbox_status()` now:
  1. call `validate_piston_url(settings.PISTON_URL)` before any request
     (tampered external URL is rejected up-front); and
  2. execute the Piston HTTP call inside `no_network()` (defense in depth via the
     existing `agent.security.netguard.NetworkGuard`).

**Validation matrix (verified by `tests/test_piston_security.py`):**

| PISTON_URL                     | Result   |
|-------------------------------|----------|
| `http://piston:2000`          | ALLOWED  |
| `http://localhost:2000`       | ALLOWED  |
| `http://127.0.0.1:2000`       | ALLOWED  |
| `https://example.com`         | BLOCKED  |
| `https://api.openai.com/v1`   | BLOCKED  |
| `http://1.2.3.4:2000`         | BLOCKED  |

**NetworkGuard:** the Piston request runs under the existing `no_network()` guard
(no new NetworkGuard created, NetworkGuard itself untouched). External sockets are
still blocked; loopback/private connections still allowed and delegated to the real
socket.

---

## Security Tests (`tests/test_piston_security.py`)

New file, 10 tests:

1. `test_piston_internal_docker_hostname_allowed` — `piston:2000` accepted
2. `test_piston_localhost_allowed` — `localhost` / `127.0.0.1` accepted
3. `test_piston_external_fqdn_rejected` — `example.com` / `api.openai.com` / public IP rejected
4. `test_validate_piston_url_rejects_external` — raises on external, passes on internal
5. `test_existing_piston_execution_still_works` — mocked Piston returns `258`/exit 0 under guard
6. `test_existing_piston_status_still_works` — mocked `/status` returns online
7. `test_external_piston_url_blocks_execution` — external URL raises `ConnectionError`
8. `test_existing_agent_sandbox_still_works` — real local sandbox runs `print('sov_ok')`
9. `test_networkguard_blocks_external_socket` — external IP + FQDN blocked
10. `test_networkguard_allows_loopback` — loopback delegated to real socket, `external_calls==0`

**Passed:** 10 / 10
**Failed:** 0
**Skipped:** 0

---

## Regression Tests

Required files:

- `pytest tests/test_netguard.py` → `test_localhost_allowed_without_guard_leak` FAILED
  (environmental: connects to `127.0.0.1:8003` where no vision server is running in
  this environment → `TimeoutError`). All other netguard tests pass. This failure is
  pre-existing and independent of the Phase 7.1 change (NetworkGuard itself was not
  modified).
- `pytest tests/test_coder_sandbox.py` → **all passed / skipped** (66 passed, 7 skipped
  in the combined run).
- `pytest tests/test_router.py` → **all passed** (sovereignty routing intact).

Full suite:

- `pytest tests` → **96 passed, 14 skipped, 2 failed.**
  - Failed: `test_netguard.py::test_localhost_allowed_without_guard_leak` and
    `test_vision.py::test_vision_server_connectivity` — both require the local
    `:8003` vision/model server, which is not running here. Identical to the 2
    environmental failures recorded in the Phase 7 baseline, so **no new regressions
    introduced**.

No assertions were weakened; no failures were converted to skips.

---

## Files Changed

- `D:\Sovereign_AI\.gitignore` — added `.env` / `.env.local` / `.env.*` (keep `.env.example`).
- `D:\Sovereign_AI\backend\app\tools\python_tool.py` — added
  `is_internal_piston_url` / `validate_piston_url`; `execute_in_sandbox` and
  `get_sandbox_status` now validate the Piston URL and run under `no_network()`.
- `D:\Sovereign_AI\backend\tests\test_piston_security.py` — new focused security tests.

(Untracked build artifact `reports/phase7_sovereignty_security.md` from Phase 7 also
present; not modified by this phase.)

---

## Remaining Risks

1. **Endpoint validation trusts internal hostnames by name only.** A single-label
   hostname (e.g. `piston`) is accepted even though DNS resolution is not performed;
   this is intentional for docker-compose/k8s service names but means a host that
   *resolves* a single-label name to a public IP could bypass the check. In the
   intended deployment such names only resolve inside the private network. If stronger
   guarantees are needed, add a resolved-IP allow-list or require `https://` with
   mTLS for the sandbox service.
2. **Default `PISTON_URL` (`http://piston:2000`) is plaintext HTTP.** Acceptable on an
   internal docker network; if the sandbox is ever exposed beyond the host, terminate
   with TLS or bind to a private interface only.
3. **Sovereignty still depends on configuration.** All enforcement assumes
   `PISTON_URL` / model endpoints remain loopback/private; the guards prevent
   tampering at runtime, but a misconfigured deployment (e.g. pointing the compose
   `piston` service at an external host) would be honored. This is inherent to the
   "application-level sovereign" posture established in Phase 7 (not air-gap).

---

## Final Verdict

**PHASE 7.1 COMPLETE**

Both hardening issues are fixed with minimal, targeted changes: secret env files are
now git-ignored, and the Piston sandbox endpoint is validated as internal/local and
runs under the existing NetworkGuard. Existing security/router/sandbox behavior is
preserved; the only test failures are the same environmental (no local model server)
failures present before this phase.
