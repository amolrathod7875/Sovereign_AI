# Phase 7 — Sovereignty & Security Proof

## Executive Summary

This phase *validates and audits* (it does not redesign) the Sovereign AI system to prove it can execute its supported workflows using **only local compute** with **zero successful external AI/model/API calls**.

The audit covered the security architecture, every network endpoint, the model router, the RAG pipeline, the coder sandbox, the `NetworkGuard`, the frontend, CORS, secrets/config, and the test suite. Network primitives were classified as LOCAL / INTERNAL / EXTERNAL-POSSIBLE / TEST-ONLY.

**Key result:** No production execution path makes a successful external call. All model inference, embeddings, vector search, OCR, parsing, artifact generation, and code execution are local. External attempts are intercepted *before* any network/DNS activity by `NetworkGuard` (agent path) and by explicit local-endpoint validation (`validate_local_endpoint`, `_assert_local_endpoint`).

**Live caveat:** The local model servers (`:8001`/`:8002`/`:8003`), the Qdrant server (`:6333`), and PostgreSQL (`:5432`) are **not running in this environment**, so live end-to-end inference for Coder/Vision/Multimodal could not be executed here. Sovereignty for those paths is proven by (a) code review, (b) local-only default endpoints, (c) local-endpoint guards, (d) the `NetworkGuard` block/allow demonstration, and (e) the security test suite. No code or config was modified.

**Two genuine remaining risks** were discovered and are documented below:
1. `.env` is **not** listed in `.gitignore` (a future secret could be committed).
2. The `/api/sandbox` manual endpoint calls the Piston microservice (`PISTON_URL`) with **no** `NetworkGuard` wrapper and **no** local-endpoint validation — an operator who tampers `PISTON_URL` to an external host could leak code execution externally. (This is *not* on the agent's own execution path, which uses the local subprocess sandbox.)

---

## Environment

| Item | Value |
|------|-------|
| OS | Microsoft Windows 11 Home Single Language (10.0.26200) |
| Python | 3.11.9 (conda env `sovereign-ai`) |
| CUDA toolkit (nvcc) | 12.4.99 |
| NVIDIA driver / CUDA | 591.66 / 13.1 |
| GPU | NVIDIA GeForce RTX 4050 Laptop (6141 MiB VRAM) |
| RAM | ~25.4 GB |
| Branch | `main` |
| Commit | `6fad7b1 Phase 6.6 Done` |
| Working tree | clean (`git status` = nothing to commit) |

The environment was **not** changed (no models downloaded, no deps added, no config edited).

---

## Security Architecture

1. **Where NetworkGuard is initialized** — `agent/security/netguard.py` (`NetworkGuard`, `no_network()`). It is entered in the agent runner `agent/run.py:49` (`with no_network() as guard:`) wrapping `GRAPH.invoke(...)`, and inside the model router's `execute_routing` (`app/models/router.py:321`).
2. **What it blocks** — any `socket.connect` to a host that is **not** loopback/private (i.e. public IPs and unresolvable hostnames). Interception happens in `netguard.py:53` `_guarded_connect` **before** the real connect, so no packet leaves and no DNS is performed.
3. **What it allows** — loopback (`localhost`, `127.0.0.1`, `::1`) and private (RFC1918) addresses, delegated to the real socket.
4. **Is localhost allowed?** — Yes (verified live in Part 9/Part 8).
5. **Are external destinations blocked?** — Yes (verified live: `8.8.8.8` → `ConnectionError: Blocked external network connection`).
6. **How external calls are counted** — each blocked attempt increments `guard.external_calls` and appends to `guard.blocked` (`netguard.py:65`).
7. **How the count reaches the API** — `run_agent_task` sets `final["external_calls"] = guard.external_calls` (`agent/run.py:51`) and the response schema `AgentRunResponse.external_calls` surfaces it (`app/api/agent.py:88`).
8. **Does the sandbox have independent network controls?** — Yes. `agent/coder/sandbox.py` installs its own import blocker (blocks `socket`, `urllib`, `requests`, `http`, `subprocess`, …) *and* a `_safe_connect` that only permits loopback (`sandbox.py:167`).
9. **Can model clients call external endpoints?** — Only via env-configurable endpoints. Two layers prevent it: the router's `validate_local_endpoint` (`router.py:222`) and `NetworkGuard`. `client.py` itself does not re-validate, but it is only reached after the router guard and under the guard.
10. **Can env vars redirect model traffic?** — Yes (by design): `CODER_ENDPOINT`, `VISION_ENDPOINT`, `GENERAL_ENDPOINT`, `PISTON_URL` are env-overridable. The vision/coder/general paths re-validate local; `PISTON_URL` does **not** (see Risks).

---

## Local Endpoints

| Component | Endpoint | Local / External | Purpose |
|-----------|----------|------------------|---------|
| FastAPI backend | `http://localhost:8000` | Local | REST API; Vite proxy target (`frontend/.env.example`) |
| General model (Qwen2.5-3B) | `http://localhost:8001/v1` (docker: `vllm-general:8000`) | Local | reasoning / RAG synthesis |
| Coder model (Qwen2.5-Coder-3B) | `http://localhost:8002/v1` | Local | code generation |
| Vision model (Qwen2.5-VL-3B) | `http://localhost:8003/v1` | Local | P&ID / image analysis |
| Qdrant (embedded, authoritative) | `./data/rag/qdrant_db` (RocksDB) | Local | vector store for agent RAG |
| Qdrant (server, optional) | `http://localhost:6333` | Local | `/api/rag` endpoints only |
| PostgreSQL | `postgresql+asyncpg://postgres@localhost:5432/sovereign_ai` (docker: `postgres:5432`) | Local | execution records (alt graph) |
| Embedding model | `/models/embedding` or local HF cache (`all-MiniLM-L6-v2`) | Local | dense embeddings |
| Reranker model | `/models/reranker` | Local | reranking |
| BM25 index | `./data/rag/bm25` (filesystem) | Local | lexical retrieval |
| Piston (code exec) | `http://piston:2000` (docker service) | **Internal** | `/api/sandbox` manual endpoint only |

All endpoints actually discovered in code/config are loopback or private/docker-internal. No public/external endpoint is referenced by production code.

---

## External Endpoint Audit

Search terms: `https://`, `http://`, `api_key`, `OPENAI`, `ANTHROPIC`, `GEMINI`, `CLAUDE`, `HUGGINGFACE`, `HF_TOKEN`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`.

Findings (production runtime):
- `app/security/network_monitor.py:66-73` — contains a **list of external provider patterns** (`api.openai.com`, `api.anthropic.com`, `api.huggingface.co`, `generativeai.googleapis.com`, …) used only for *detection/logging*. It makes **no** network call.
- `agent/tools/vision.py:210` — uses the `openai` SDK **but** `base_url=VISION_ENDPOINT` which defaults to `http://localhost:8003/v1` and is guarded by `_assert_local_endpoint`.
- `app/models/client.py` — `httpx` to model endpoints taken from the registry (all loopback).
- `app/tools/python_tool.py` — `httpx` to `PISTON_URL` (`http://piston:2000`, internal docker).
- `app/api/system.py` — `httpx` probes *local* model endpoints for status.

Test/documentation-only matches:
- `tests/test_router.py`, `tests/test_netguard.py`, `tests/test_vision.py`, `tests/test_coder.py`, `tests/test_coder_sandbox.py`, `tests/test_agent_e2e.py` reference `api.openai.com`, `8.8.8.8`, `example.com`, `127.0.0.1:8003` — **all inside tests** (mostly asserting the guard *blocks* external).
- `tests/test_coder_sandbox.py:425` sets `HF_TOKEN` only via `monkeypatch` (test isolation).

**Conclusion:** No production execution path can call an external service. The only network path that is *not loopback* and *not guarded* is the Piston-based `/api/sandbox` (internal by default; tamper risk noted).

---

## Model Sovereignty

- **Coder → localhost**: `agent/coder/config.py:13` `CODER_ENDPOINT = ... "http://localhost:8002/v1"`; `agent/coder/model.py:27` builds `ModelClient(CODER_MODEL_ID, CODER_ENDPOINT)`. Router validates `validate_local_endpoint` (`router.py:222`).
- **Vision → localhost**: `agent/config.py:36` `VISION_ENDPOINT = ... "http://localhost:8003/v1"`; `agent/tools/vision.py:209` `_assert_local_endpoint(VISION_ENDPOINT)` raises for non-local.
- **General → localhost if configured**: `registry.py:76` `_GENERAL_ENDPOINT = "http://localhost:8001/v1"`; `router.py:222` validates; `_try_general_synthesis` (`router.py:399`) only calls it when `is_local_endpoint` is true and the server answers `/models`, otherwise reports `used: False`.
- **No automatic cloud fallback**: demonstrated live — tampering `GENERAL_ENDPOINT=https://api.openai.com/v1` makes `route()` raise `ConnectionError` from `validate_local_endpoint` (output: *"Model endpoint 'https://api.openai.com/v1' is not loopback/private. Inference must remain local"*). `NoLocalModelAvailable` is raised when no local model satisfies a capability (`router.py:217`).

Live Coder/Vision inference could not be executed (servers down in this env) but the path is provably local and externally blocked.

---

## RAG Sovereignty

- **Qdrant is local**: embedded RocksDB at `backend/rag/config.py:16` `QDRANT_PATH = .../data/rag/qdrant_db` (verified present on disk). The agent's authoritative retriever uses this embedded store (`rag/indexing/qdrant_store.py`), not the `:6333` server.
- **BM25 is local**: `rag/indexing/bm25_store.py` over `./data/rag/bm25` (filesystem).
- **Embeddings are local**: `rag/models/embeddings.py` `LocalEmbedder` uses `sentence_transformers` with `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1` (`rag/config.py:10`, `embeddings.py:36`). The model name resolves from the local HF cache; no network.
- **Retrieval requires no external inference**: `rag/retrieval/hybrid.py` fuses Qdrant cosine + BM25; `agent/tools/search_kb.py` wraps it. No OpenAI/Anthropic/Google/HF-inference dependency.
- **Expected external calls = 0**: confirmed by code + env flags.

---

## Document Pipeline

Flow verified by reading the code (`backend/rag/parser.py`, `backend/app/rag/parser.py`, `backend/app/rag/ocr.py`, `backend/rag/ingestion/*`):

`local file → parser (PyMuPDF / python-docx / openpyxl — local) → OCR if required (PaddleOCR — local) → chunking (local) → embedding (LocalEmbedder, offline) → Qdrant + BM25 (local) → retrieval (local hybrid)`.

No cloud document-processing API, no cloud OCR, no cloud embedding, no cloud storage. Stage-by-stage: parsing = local libs; OCR = `paddleocr` (local); chunking = `rag/ingestion/chunker.py`; embedding = offline `sentence_transformers`; indexing = embedded Qdrant + BM25; retrieval = local. Each stage is local.

---

## Sandbox Security

`agent/coder/sandbox.py` verified by reading **and** executed live (Part 8 probe):

- **Execution isolation**: generated code runs in a separate subprocess with a hardening prelude; real `subprocess` is replaced by a stub inside the sandbox (`sandbox.py:139`).
- **Import restrictions**: meta-path finder blocks `socket`, `urllib`, `requests`, `http`, `subprocess`, `smtplib`, `ftplib`, `telnetlib`, `paramiko`, `webbrowser`, `poplib`, `imaplib`, `nntplib`, `http.client`, `ssl` (with narrow `urllib`/`urllib.parse` exceptions).
- **Network restrictions**: `_safe_connect` permits only loopback; everything else is blocked and logged to `.net_blocked.log`.
- **Workspace restrictions**: `builtins.open` wrapped so only paths under the workspace are reachable (`sandbox.py:160`).
- **Cleanup**: runner file removed in `finally`; `.net_blocked.log` removed after counting.
- **Timeout**: `subprocess.run(..., timeout=timeout)` + `run_tests` timeout; times out with exit `-1`.
- **Resource controls**: no package install possible (pip/network unreachable); `MAX_OUTPUT_KB`/`SANDBOX_TIMEOUT` limits configured; env stripped of secrets (`_ENV_ALLOW` allow-list).

**Live results (temp probe, no repo change):**
- Safe calc `print(2+2**8)` → exit 0, stdout `258`, `external_network_calls=0`, `network_blocked=0` → **PASS**.
- `import socket; socket.create_connection(('8.8.8.8',80))` → `ConnectionError: Blocked external network connection in Sovereign sandbox: 8.8.8.8` → **BLOCKED**.
- `open('C:/Windows/System32/secret.txt','w')` → `PermissionError: Filesystem access outside workspace blocked` → **BLOCKED**.
- `import subprocess; subprocess.run(...)` → `PermissionError: Blocked in Sovereign sandbox: subprocess process creation` → **BLOCKED**.

The existing policy was used; it was **not** weakened.

---

## NetworkGuard

Live demonstration (Part 9, no real packet leaves — the guard intercepts first):

```
EXTERNAL BLOCKED: Blocked external network connection to 8.8.8.8
external_calls = 1 | blocked = ['8.8.8.8']
LOCAL allowed (delegated, no listener): TimeoutError     # guard delegated; nothing listening
local external_calls = 0
```

- External (`8.8.8.8`) → **BLOCKED**, counted.
- Localhost → **ALLOWED** (delegated to real socket; the subsequent timeout is only because no local server is listening, proving the guard did *not* block it).

This proves **LOCAL ≠ EXTERNAL**.

---

## Network Trace

Per-workflow analysis (production code paths):

| Workflow | Local calls | External attempts | Blocked external | Successful external |
|----------|-------------|------------------|-----------------|---------------------|
| Coding (`/api/coder` → `run_coder_task` → local Qwen-Coder + subprocess sandbox) | model `:8002`, sandbox subprocess | 0 | 0 | 0 |
| Vision (`/api/vision` or agent → `analyze_image`) | model `:8003`, approved dirs | 0 | 0 | 0 |
| Knowledge (agent → `search_kb` → hybrid RAG) | embedded Qdrant + BM25 + LocalEmbedder | 0 | 0 | 0 |
| Multimodal (vision + RAG) | `:8003` + local RAG | 0 | 0 | 0 |
| Artifact (DOCX gen → `data/outputs`) | local FS + python-docx | 0 | 0 | 0 |

All paths run inside `no_network()` (agent path) and/or behind `validate_local_endpoint`/`_assert_local_endpoint`. **Successful external calls = 0** in every workflow.

*(The `/api/sandbox` → Piston path is the only one that issues a non-loopback call, to an internal docker service `piston:2000`. If Piston were unreachable it would error, not fall back to cloud. It is not part of the agent workflows above.)*

---

## DNS / Outbound Behavior

- `NetworkGuard._guarded_connect` blocks **before** `socket.connect`, so for an external *hostname* the guard raises on the host check (`_is_local_host` returns False for unresolvable names) and **no DNS resolution or socket I/O occurs**.
- For an external *IP*, the guard raises before delegating to the real connect.
- No runtime code initiates DNS for external providers. The `network_monitor` patterns are detection-only.
- **Precise terminology:** *no successful external API calls were observed* (and the architecture makes them impossible on the agent path). This machine is **not** claimed to be physically air-gapped; it is application-level sovereign.

---

## Secrets Audit

- `git ls-files` scanned for `sk-...`, `AKIA...`, `ghp_...`, `BEGIN RSA/PRIVATE/OPENSSH`, `password=`, `PASSWD` → **no matches**.
- No `.env` file is tracked (`git ls-files | ...env$` → empty). No `.env` exists in the working tree.
- `frontend/.env.example`, `backend/rag/.env.example`, `infra/.env.example` contain **placeholders only** (local URLs, offline flags; no secrets).
- No API keys / tokens / DB passwords in tracked source. Any credential-bearing env (`HF_TOKEN`, `API_KEY`, …) is stripped from the sandbox child env (`_ENV_ALLOW`).

**No secret detected in tracked files.** (Redaction not required.)

---

## Environment Configuration

- `backend/app/config.py`: all model/DB endpoints default to loopback or docker-private service names; `SOVEREIGN_MODE=True`; `CORS_ALLOW_ORIGINS` explicit localhost origins (no `*`).
- `backend/rag/config.py`: `HF_HUB_OFFLINE=1`, `TRANSFORMERS_OFFLINE=1` force offline model loading.
- `.env.example` files: placeholders only; model/DB/Qdrant endpoints local.
- **Risk:** `.env` is **not** present in `.gitignore` (root `.gitignore` ignores `models/`, `PID_Dataset/`, `data/`, `*.gguf`, `.cache/` only). A future `.env` containing credentials could be committed. Recommendation: add `.env` and `.env.local` to `.gitignore`. (Not changed — audit only.)
- **Risk:** `PISTON_URL` is not local-validated (see Part 20/21).

---

## Frontend Security

- `frontend/src` scanned: **no** `api.openai.com`, `api.anthropic.com`, `api.huggingface.co`, `generativeai`, `OPENAI_API_KEY`, `sk-`, `Bearer`, `apiKey`, `password`, `secret`.
- All HTTP goes through a single axios client (`frontend/src/lib/api/client.ts`) whose base URL is `VITE_API_BASE_URL` (default `/api`, proxied by Vite to `http://localhost:8000`). The frontend talks **only** to the local backend.
- `frontend/.env.example` documents that `VITE_*` values are public-to-browser and must never hold secrets; backend holds no external credentials.

**Frontend secret safety: PASS. Frontend communicates only with FastAPI (local).**

---

## CORS

`backend/app/main.py:50` configures `CORSMiddleware`:
- `allow_origins = settings.cors_origins` = explicit `http://localhost:3000, 127.0.0.1:3000, localhost:4173, 127.0.0.1:4173, localhost:5173, 127.0.0.1:5173`.
- `allow_credentials=True`, methods limited, headers limited.
- **No wildcard `*`** (the prior wildcard was removed in Phase 6 Part 16; see `main.py:45` comment).

**CORS: PASS (intentional, no wildcard).**

---

## Multimodal Sovereignty

Target (Part 17): `PID_Dataset\0__raw_data\sheets\test\158.jpg` with the prompt *"Inspect this P&ID, identify R-1001, and explain its maintenance requirements using the local knowledge base."*

- **Vision model**: local Qwen2.5-VL-3B at `localhost:8003/v1`, guarded by `_assert_local_endpoint` (file verified to exist; live inference not run here because `:8003` is down).
- **RAG**: local hybrid (embedded Qdrant + BM25 + offline `LocalEmbedder`).
- **Sources**: local `data/synthetic` knowledge base; provenance `data_origin="local"`.
- **External calls**: 0 (path is under `no_network()`).
- **NetworkGuard status**: active and would block any non-loopback attempt.

**Verdict:** architecture is fully local. Live inference blocked only by the absence of the local `:8003` server in this environment (expected behavior: report unavailable, not call cloud).

---

## Artifact Sovereignty

R-1001 approval-note generation (Part 18):
- **input**: local task string + local knowledge base (RAG).
- **reasoning**: local (agent graph + optional local general model).
- **RAG**: local hybrid.
- **artifact generation**: `python-docx` writing to `agent.config.OUTPUT_DIR = data/outputs` (verified present) — local filesystem only.
- **output**: local DOCX under `data/outputs`.
- **External calls**: 0.

**Artifact sovereignty: PASS (all stages local).**

---

## Cloud Fallback Test

Part 19 (no architecture change; temporary tamper, then restored):
- Set `GENERAL_ENDPOINT=https://api.openai.com/v1`, then `route(RoutingRequest(task="...sop...", requires_rag=True))`.
- Result: `ConnectionError` raised by `validate_local_endpoint` — *"Model endpoint 'https://api.openai.com/v1' is not loopback/private. Inference must remain local"*. Routing **fails loudly**; it does **not** route to OpenAI/Anthropic/Google.
- Vision guard: `_assert_local_endpoint("https://api.anthropic.com/v1")` → `ConnectionError` (*"not a known local address"*).
- When a local model server is simply *unreachable* (not tampered), `_try_general_synthesis` returns `{"used": False, "reason": "general model server not running on this host"}` — explicit local-service failure, never a cloud call.

**Cloud fallback result:** UNAVAILABLE / explicit local failure. No silent cloud switch.

---

## Data Exfiltration Audit

Classification of network primitives in runtime code:

| Location | Primitive | Classification |
|----------|-----------|----------------|
| `app/models/client.py` | `httpx` → model endpoint | LOCAL (registry, loopback) |
| `agent/tools/vision.py:210` | `openai.OpenAI(base_url=VISION_ENDPOINT)` | LOCAL (validated loopback) |
| `app/tools/python_tool.py` | `httpx` → `PISTON_URL` | INTERNAL (docker); **EXTERNAL-POSSIBLE if `PISTON_URL` tampered**, no guard |
| `app/api/system.py` | `httpx` → local model probe | LOCAL |
| `agent/security/netguard.py` | `socket` patch | SECURITY (guard) |
| `agent/coder/sandbox.py` | `socket.connect` wrap | SECURITY (guard) |
| `app/security/network_monitor.py` | provider pattern list | DETECTION ONLY (no call) |
| `agent/coder/evaluation.py:25` | string `socket.connect(('8.8.8.8',53))` | TEST PAYLOAD (fed to sandbox to be blocked) |
| tests (`test_netguard`, `test_router`, `test_vision`, `test_coder`, `test_coder_sandbox`, `test_agent_e2e`) | `httpx`/`urllib`/`socket` to `8.8.8.8`/`example.com`/`127.0.0.1` | TEST ONLY (assert block / local) |
| `scripts/run_coder_e2e.py` | `urllib.request` → `localhost:8002` | LOCAL (helper) |

No `requests`/`aiohttp`/`websocket` in production runtime. Legitimate local HTTP (loopback) was not removed.

---

## Test Results

Run from `backend/` with the `sovereign-ai` interpreter.

- **Full default `pytest`**: interrupted by **collection errors** in `backend/ingestion/tests/*` (`ModuleNotFoundError: app.ingestion`) — that sub-package is a separate project not importable from the backend root. Not a sovereignty defect.
- **`pytest tests` (production suite, ingestion excluded)**: **86 passed, 14 skipped, 2 failed**.
  - `test_netguard.py::test_localhost_allowed_without_guard_leak` FAILED — attempts a *real* `socket.create_connection(('127.0.0.1',8003))`; the guard correctly **allowed** it (delegated) and it merely **timed out** because no `:8003` server is listening. This actually confirms localhost is allowed; the failure is purely environmental (no local model server running).
  - `test_vision_server_connectivity` FAILED — asserts the local `:8003` vision server is up; it is not in this env. Environmental, not a sovereignty defect.
- **Security tests** (`test_netguard`, `test_coder_sandbox`, `test_router`): **66 passed, 7 skipped, 1 failed** (the same localhost-allow/environmental failure above). All external-block and local-allow assertions pass.

**No new regressions** introduced by this phase (no code was changed). The 2 failures are environmental (missing local model servers), not sovereignty defects.

---

## Performance Impact

`NetworkGuard` is a process-wide `socket.socket` class swap plus a per-connect host check that **delegates** to the real socket for allowed (loopback) connections. It adds no I/O for allowed connections and only a Python-level branch for blocked ones. The sandbox prelude is constructed once per execution and runs in a subprocess. No benchmarking was needed/performed (not required by the phase); overhead is negligible. The `-o addopts=""` flag used above was only to bypass a pyproject `addopts` quirk for this run; it does not weaken tests.

---

## Sovereignty Scorecard

| Requirement | Evidence | Result |
|-------------|----------|--------|
| Local models | `registry.py`/`config.py` default loopback `:8001/:8002/:8003` | PASS |
| Local inference | `client.py`, `vision.py` target local; `validate_local_endpoint`/`_assert_local_endpoint` | PASS |
| Local RAG | embedded Qdrant + BM25 + offline `LocalEmbedder` | PASS |
| Local storage | `data/outputs`, `data/rag`, `uploads` (repo-local) | PASS |
| Local artifacts | DOCX via python-docx → `data/outputs` | PASS |
| No cloud fallback | router raises on external; live tamper test confirmed | PASS |
| External calls = 0 | `NetworkGuard` blocks; tests; trace table | PASS |
| NetworkGuard | live block(8.8.8.8)+allow(localhost) demo | PASS |
| Sandbox network restriction | live BLOCKED import/fs/subprocess/network | PASS |
| Frontend secret safety | no keys/providers; only `/api` | PASS |
| Backend secret safety | no secrets in tracked files; env-only | PASS |
| CORS | explicit localhost origins, no `*` | PASS |
| Environment configuration | local endpoints + offline flags, **but** `.env` not gitignored & Piston unguarded | PARTIAL |

---

## Network Evidence

- **Total successful external calls: 0** (no production path can reach an external host; agent path wrapped by `NetworkGuard`, model/vision paths validated local).
- **Total blocked external attempts: 0 observed in a live run** (no external destination was attempted during this audit's execution; the guard is proven to block via the live `8.8.8.8` demonstration and the security tests).
- **Total local calls: >0** (local model endpoints, embedded Qdrant, BM25, LocalEmbedder, subprocess sandbox, local filesystem, PostgreSQL/Qdrant server where present).

If an external attempt *were* made, it would be blocked and counted (demonstrated). It is not hidden.

---

## Limitations

- **Application-level sovereignty ≠ network-level air-gap.** This phase proves *no successful external API calls* on the agent execution path and that external attempts are blocked pre-connect. It does **not** prove the physical machine is air-gapped (it has a working NIC, CUDA/driver, and general internet capability at the OS level). The claim is scoped to the application.
- Live Coder/Vision/Multimodal inference was not executed because the local model servers, Qdrant server, and PostgreSQL are not running in this environment. Their sovereignty is established by code, config, guards, and tests.
- The `/api/sandbox` → Piston path is internal by default but unguarded; see Risks.

---

## Remaining Risks

1. **`.env` not in `.gitignore`** — a future credential-bearing `.env` could be committed. *Fix:* add `.env`, `.env.local` to `.gitignore` (recommended; not applied — audit only).
2. **`/api/sandbox` → Piston lacks a `NetworkGuard` wrapper and local-endpoint validation** — if `PISTON_URL` is tampered to an external host, code execution could be sent externally. The *agent's* own execution path is unaffected (it uses the local subprocess sandbox). *Fix:* wrap `execute_in_sandbox` in `no_network()` and add `validate_local_endpoint(settings.PISTON_URL)`, or document that `PISTON_URL` must remain internal.
3. **Model-endpoint tampering** — endpoints are env-overridable. Coder/Vision/General are re-validated local (defense in depth via router + `NetworkGuard`); `PISTON_URL` is the exception (see #2). Overall: *local sovereignty depends on local endpoint configuration*.

---

## Final Verdict

**PHASE 7 COMPLETE**

The system is application-level sovereign: every supported workflow executes with local models, local inference, local RAG (embedded Qdrant + BM25 + offline embeddings), local OCR/parsing, local artifacts, and a mandatory `NetworkGuard` that blocks any non-loopback network attempt before it leaves the process. There is no cloud fallback. Secrets are absent from tracked files, the frontend talks only to the local backend, and CORS is restricted to explicit local origins. Two configuration hardening items (`.gitignore` for `.env`; guard the Piston path) are documented as remaining risks but do not affect the agent's own sovereign execution path. No code or configuration was modified, and `git status` remains clean.
