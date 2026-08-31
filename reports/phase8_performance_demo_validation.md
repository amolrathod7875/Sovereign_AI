# Phase 8 — Final Performance & Demo Validation

## Executive Summary

Phase 8 measured the **live, local, sovereign** Sovereign AI stack end-to-end using the
authoritative FastAPI surface (`backend/app/api/*`), exactly the endpoints the React
frontend (`frontend/src/lib/api/client.ts`) calls. No mock responses were used; every
number below is a real wall-clock measurement against running local models and the
embedded Qdrant + BM25 RAG index.

Headline result: **three of the five golden workflows are demonstrably reliable and
sovereign** (Coder, RAG, Artifact). **Two are blocked by an environment security policy
outside the repository** — the Qwen-VL vision server cannot start because **Windows Smart
App Control** is enforced on this machine and blocks `llama_cpp/lib/mtmd.dll` with
`WinError 4551`. This kills Vision and the primary Multimodal demo. It is **not** a code
defect, and I did not modify it, the sandbox, or NetworkGuard.

Network sovereignty is fully verified: **successful external calls = 0, blocked external
connections = 0** across every run. GPU acceleration is **NOT VERIFIED** — the installed
llama.cpp wheel is CPU-only (`llama_supports_gpu_offload() == False`), so all inference
runs on CPU; VRAM stays at desktop-idle levels (~0.8–1.1 GiB) the whole time.

Verdict: **PHASE 8 PARTIALLY COMPLETE** — blocked on Vision/Multimodal by Smart App Control.

## Environment

| Item | Value |
|------|-------|
| Python | 3.11.9 (conda env `sovereign-ai`) |
| CUDA toolkit (`nvcc`) | 12.4.99 |
| NVIDIA driver | 591.66 (reports CUDA 13.1) |
| GPU | NVIDIA GeForce RTX 4050 Laptop GPU, 6141 MiB (~6 GB) VRAM |
| llama.cpp | 0.3.35 — `llama_supports_gpu_offload() = False` (CPU-only build, no `ggml-cuda.dll`) |
| torch | 2.13.0+cpu (`cuda.is_available() = False`) |
| System RAM | 23.69 GB total / 13.6 GB free at start |
| Disk C: | 47.4 GB free (start) / 47.7 GB (end) |
| Disk D: | 218.6 GB free (start) / 218.6 GB (end) |
| OS security | Windows Smart App Control = **Enforced** (policy `VerifiedAndReputableDesktop`, refreshed 2026-08-30 16:30) |

Branch `main` @ `1644174` ("Phase 7.1 Done"); working tree was clean before this phase.

## Startup

Intended startup sequence (from `README.md`, `scripts/serve_model.py`, `backend/app/main.py`,
`frontend/vite.config.ts`) — no startup commands were invented:

1. **Coder model server** — `python scripts/serve_model.py --model-id qwen-coder \
   --model-path models/qwen-coder/qwen2.5-coder-3b-instruct-q4_k_m.gguf --port 8002`
   (OpenAI-compatible llama.cpp server).
2. **Vision model server** — `python scripts/serve_model.py --model-id qwen-vision \
   --model-path models/qwen-vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf \
   --mmproj models/qwen-vision/mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf \
   --chat-format qwen2-vl --port 8003`. **BLOCKED by Smart App Control this run.**
3. **FastAPI backend** — `cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`
   (boots Qdrant+BM25 on first use; PostgreSQL optional/degrades).
4. **Frontend** — `cd frontend && npm run dev` (Vite, port 3000, proxies `/api` → `:8000`).

| Service | Port | Dependency | Health |
|---------|------|-----------|--------|
| Qwen Coder | 8002 | none | ONLINE (ready in ~2–4 s model load) |
| Qwen-VL | 8003 | none | **OFFLINE — Smart App Control blocks `mtmd.dll`** |
| FastAPI | 8000 | none (loads RAG lazily) | ONLINE (`/api/system/health` 200) |
| Frontend | 3000 | backend | ONLINE (HTTP 200) |
| Qdrant (embedded) | on-disk | backend | ONLINE (index present) |
| BM25 | on-disk | backend | ONLINE (393 chunks) |
| PostgreSQL | 5432 | — | OFFLINE (not running; backend degrades gracefully) |
| General model (:8001) | — | — | UNAVAILABLE (no GGUF on host) |

Clean-start to usable system: backend + frontend + coder ready in seconds; RAG first call
loads the local sentence-transformers embedding model (cold ~10 s, then <0.1 s).

## Resource Baseline

Captured before any inference (Part 4):

- VRAM: **1039 MiB** (desktop baseline; GPU idle).
- RAM: **13.77 GB used / 9.92 GB free**.
- CPU load: 26 %.
- C: 47.42 GB free · D: 218.58 GB free.

Post-startup (all services up): VRAM 1039 MiB, RAM 13.77 GB. Loading the Coder GGUF adds
~2.8 GB RAM (model resident). No VRAM was consumed by model inference at any point.

## Coder Performance

Task (identical to Phase 6.5/6.6): *"Write a Python function that calculates Reynolds
number. Include input validation."* — `POST /api/coder/run` (the frontend endpoint),
`qwen2.5-coder-3b` on `:8002`, sandbox verification + pytest inside the hardened sandbox.

| Run | Total (s) | Status | Iter | Test | ext_calls |
|-----|-----------|--------|------|------|-----------|
| 1 | 385.93 | **COMPLETED** | 4 | PASS (exit 0) | 0 |
| 2 | 630.88 | FAILED | 5 | FAIL | 0 |
| 3 | 468.95 | FAILED | 5 | FAIL | 0 |

- Min **385.9 s** · Avg **495.3 s** · Max **630.9 s**.
- Per-stage (Run 1): `generate_code` 65.4 s, 4× `fix_code` (24–83 s each),
  `run_tests` ~0.33–0.43 s, `verify` 0.028 s. So **~99.9 % of latency is CPU-only 3B
  generation/repair**; sandbox+pytest verification is sub-second.
- The FAILED runs are **model non-convergence under CPU-only load** (the repair loop
  exhausted its iterations producing code that did not pass the generated test). The
  sandbox/verification harness itself is correct — Run 1 reached `COMPLETED` and
  Phase 6.6 demonstrated it passing repeatedly. **Not a code defect; a latency/reliability
  property of 3B CPU inference.**
- VRAM during coder: 879–1092 MiB (no model allocation; GPU idle). GPU util peaked 72 %
  only as transient Windows DWM flicker, not model compute.
- **external calls = 0** every run.

> Honest classification: **RELIABLE on a good run, but RISKY for a live demo** — 1/3 runs
> converged within the repair budget. A judge-facing coder demo should be rehearsed and a
> passing run pre-warmed/`cached`, or the task scoped to raise convergence odds.

## Vision Performance

*Blocked.* `POST /api/vision/analyze` on `158.jpg` returns **HTTP 503** with a clear
message because `:8003` never starts:

```
RuntimeError: HTTP 503: {"detail":"Local vision model (Qwen2.5-VL) is not reachable on
http://localhost:8003/v1. Start it with 'python scripts/serve_model.py --model-id
qwen-vision ... --port 8003'."}
```

Root cause (reproduced twice, confirmed via CodeIntegrity event log id 3077/3033):

- `python.exe` attempts to load
  `C:\Users\shiva\anaconda3\envs\sovereign-ai\Lib\site-packages\llama_cpp\lib\mtmd.dll`
  (the multimodal projector library) → **`WinError 4551` An Application Control policy has
  blocked this file**.
- Windows **Smart App Control** (`VerifiedAndReputableDesktop`, enforced) blocks the
  unsigned `mtmd.dll`. Sibling `llama.dll`/`ggml-*.dll` are allowed, so only the vision
  projector is affected. Postgres/NetworkGuard/RAG unaffected.
- This is an **OS security policy**, not repository code. Per the Phase-8 rules I did not
  disable it or change the sandbox/NetworkGuard. The user confirmed: measure everything
  else, record Vision/Multimodal as BLOCKED.

**No Vision latency, VRAM, or accuracy could be measured.** The Qwen-VL model itself is
present on disk (`Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf` + `mmproj` Q8) and was validated in
earlier phases on this same code path; only the local OS now prevents it from loading.

## RAG Performance

*Prompt:* "Explain the maintenance requirements for R-1001 using the local knowledge
base." — `POST /api/rag/search` (authoritative `agent.tools.search_kb` → embedded Qdrant
`sovereign_knowledge` + local BM25, offline sentence-transformers).

| Run | Latency (s) | Hits | Sources |
|-----|-------------|------|---------|
| 1 (cold) | 8.59 | 8 | approval_note, manual, pm_sop, inspection_report, vendor_correspondence, … |
| 2 (cold after restart) | 10.46 | 8 | same |
| 3 (warm) | 0.023 | 8 | same |

- Min **0.023 s** · Avg **6.36 s** (cold-call dominated) · Max **10.46 s**.
- Warm calls are **< 0.1 s**. Each chunk carries `source_file`, `document_type`,
  `asset_tag`, `data_origin` (fully grounded, no fabricated retrieval).
- **external calls = 0**.

## Multimodal Performance

*Intended:* `158.jpg` + "Inspect this P&ID, identify R-1001, and explain its maintenance
requirements using the local knowledge base." — `POST /api/agent/run` with `image_path`.

**Degraded, not blocked-by-architecture but blocked-by-environment.** With `:8003` down the
vision node fails fast (connection error) and the agent **gracefully degrades to the RAG
path**, still producing a VERIFIED answer + DOCX:

| Run | Total (s) | Status | Vision | Evidence | ext_calls |
|-----|-----------|--------|--------|----------|-----------|
| 1 | 14.68 | VERIFIED | FAILED (conn err), tags=[] | 14 RAG items | 0 |
| 2 | 13.99 | VERIFIED | same | same | 0 |
| 3 | 14.11 | VERIFIED | same | same | 0 |

- Min **13.99 s** · Avg **14.26 s** · Max **14.68 s**. (~13.7 s is the vision connection
  timeout; RAG+synthesis+DOCX is <1 s.)
- The failure is **not silently claimed as success at the data layer**: `errors` carries
  `["vision:Connection error."]`, `vision_evidence[].confidence = 0.0`, and
  `uncertain_items = ["vision_error: Connection error."]`. However, the **frontend
  `VisionResult` component does not render `uncertain_items` or the `errors` array**, so a
  viewer sees an empty "VISUAL ANALYSIS" block and a top-level `VERIFIED` badge — a
  **disclosure gap** (no UI crash, but vision failure is not surfaced prominently).
- With Vision unavailable this cannot be demoed as a true *multimodal* (vision+RAG) workflow.

## Artifact Performance

*Prompt:* "Generate the R-1001 maintenance approval note using the local knowledge base."
— `POST /api/agent/run` (no image) → `generate_approval_note` → VERIFY → DOCX in
`data/outputs/`.

| Run | Total (s) | Status | DOCX bytes | opens | asset present | ext_calls |
|-----|-----------|--------|-----------|-------|---------------|-----------|
| 1 | 0.905 | VERIFIED | 39,485 | yes | yes | 0 |
| 2 | 0.542 | VERIFIED | 39,485 | yes | yes | 0 |
| 3 | 0.551 | VERIFIED | 39,485 | yes | yes | 0 |

- Min **0.542 s** · Avg **0.666 s** · Max **0.905 s**.
- Verification: `ok=True`, `missing_sections=[]`, `asset_present=True`,
  `disclaimer_present=True`, `sources_present=True` (75–78 paragraphs).
- `python-docx` opens each file; non-empty; `R-1001` present; generated locally.
- File is listed by `GET /api/artifacts?kind=DOCX` and downloadable.
- **external calls = 0**. **RELIABLE.**

## Repeated Demo Stability

Three complete golden cycles (Coder → Vision → RAG → Multimodal → Artifact) were run
against the same live stack without restarting services between operations.

| Cycle | Coder | Vision | RAG | Multimodal | Artifact |
|-------|-------|--------|-----|-----------|----------|
| 1 | PASS (COMPLETED) | FAIL 503 (SAC) | PASS | DEGRADED (RAG-only, VERIFIED) | PASS |
| 2 | FAIL (non-converge) | FAIL 503 (SAC) | PASS | DEGRADED (RAG-only, VERIFIED) | PASS |
| 3 | FAIL (non-converge) | FAIL 503 (SAC) | PASS | DEGRADED (RAG-only, VERIFIED) | PASS |

Observed issues:
- **No crashes, no frontend failures, no server failures, no VRAM exhaustion.**
- Coder non-convergence in 2/3 cycles (CPU-only 3B; see Coder section).
- Vision blocked every cycle (Smart App Control).
- Multimodal degrades without erroring (good resilience, weak UI disclosure).
- Artifact and RAG 3/3 stable.

## Resource Stability

Before vs after the three cycles (no services were bounced mid-cycle):

| Resource | Before | Peak | After |
|----------|--------|------|-------|
| VRAM | 1039 MiB | 1092 MiB (coder, idle GPU) | 812 MiB |
| RAM | 13.77 GB | 19.26 GB (coder run, cycle 2) | 13.15 GB |
| CPU | 26 % | ~100 % during coder generation | low |
| C: disk | 47.42 GB free | — | 47.71 GB free |
| D: disk | 218.58 GB free | — | 218.57 GB free |

- **No VRAM growth** (GPU unused by models; stays at desktop idle ~0.8–1.1 GiB).
- **No RAM leak**: coder RAM returns to baseline after the model is unloaded/reloaded;
  peak 19.3 GB is well under the 23.7 GB physical limit.
- Generated artifacts are small and confined to gitignored `data/` + `uploads/`:
  `data/outputs` 98 files / 2.27 MB, `data/code_runs` 68 files / 0.06 MB,
  `uploads` 10 files / 2.08 MB. RAG indices unchanged (`qdrant_db` 2.31 MB, `bm25` 1 MB).
- No unexpected temp-file accumulation outside `data/`/`uploads/`; no leaked python
  processes (verified by `tasklist`).

## VRAM Strategy

The machine has ~6 GB VRAM but the model build is **CPU-only**, so VRAM is not the
constraint — CPU compute is. Measured VRAM for the coder server is ~0.8–1.1 GiB and does
not grow with inference. Because both models run on CPU and the vision projector DLL is
currently blocked by Smart App Control, **only the Coder server was loadable this run**.

Recommended strategy based on observation: **Sequential model serving.**
- Today (CPU-only, vision blocked): only Coder needs to run; RAG/agent are embedded in the
  backend. There is no VRAM pressure to force unloading.
- If Vision is later unblocked on this 6 GB GPU: do **not** load Coder (2 GB weights) and
  VL (2.6 GB weights + mmproj) simultaneously unless VRAM allows; serve them sequentially
  to avoid OOM. CPU contention alone would also favour sequencing.

## Cold Start

| Component | Cold start |
|-----------|-----------|
| FastAPI backend | < 1 s to health 200 (RAG index lazy-loaded on first call, ~10 s) |
| Frontend (Vite dev) | ~3.1 s |
| Qwen Coder (:8002) | ~2–4 s (GGUF model load; fast because file is OS-cached) |
| Qwen-VL (:8003) | **cannot start** — Smart App Control blocks `mtmd.dll` before model load |
| RAG embedding model | ~10 s first call, then warm (<0.1 s) |

(Note: a naïve "0.05 s" probe reading was an artifact of the prior instance still holding
the port; true fresh-process model load is the 2–4 s above.)

## Failure Recovery

| Case | Endpoint behaviour | Useful to user? |
|------|-------------------|-----------------|
| Vision server down | 503 + explicit "start … :8003" message | **Yes** |
| Invalid image path | 404 "Vision input not found: …" | **Yes** |
| Unsupported upload (`.exe`) | 415 + supported-type list | **Yes** |
| Empty coder task | 422 "task must not be empty" | **Yes** |
| Empty agent task | 422 "task must not be empty" | **Yes** |
| Multimodal w/ image, vision down | 200 + `errors=["vision:Connection error."]`, confidence 0.0, `uncertain_items` set | **Partial** — data is honest, but the UI `VisionResult` block does not surface it |
| Backend unavailable | client (frontend) shows "Cannot reach the local backend" | **Yes** |
| Coder server down | backend raises 500 surfaced by frontend | **Yes** |

No case silently claims success. The only weakness is the **multimodal degraded path not
being visibly flagged in the UI** (top-level badge stays VERIFIED).

## Network Validation

Across all runs (Coder ×3, RAG ×3, Multimodal ×3, Artifact ×3, Vision ×3):

- `GET /api/system/status` → `external_api_calls = 0`, `blocked_connections = 0`.
- All traffic was loopback (`127.0.0.1:8000`, `:8002`; `:8003` attempted locally and
  refused by SAC). No external destination was contacted.
- NetworkGuard (`no_network()`) wraps coder, vision, and the agent run; the coder sandbox
  blocks/subprocess-stubs network and process APIs. Embedded Qdrant/BM25 and BM25 are
  fully local.

**Result: successful external calls = 0 — VERIFIED.**

## Recommended Demo

Shortest reliable judge-facing demo (steps that are actually proven to work here):

1. **System** — open frontend `:3000` → System page shows LOCAL AI, NetworkGuard ONLINE,
   Coder ONLINE, RAG ONLINE, external calls = 0.
2. **Coder** *(ACCEPTABLE / rehearse)* — "Write a Python function that calculates Reynolds
   number. Include input validation." → Qwen-Coder, sandbox, pytest verification.
3. **Knowledge (RAG)** *(RELIABLE)* — "Explain the maintenance requirements for R-1001
   using the local knowledge base." → sources + grounded answer.
4. **Artifact** *(RELIABLE)* — "Generate the R-1001 maintenance approval note…" → DOCX,
   verify (asset + disclaimer + sources present), download.
5. **Network** — show external calls = 0, NetworkGuard enforced.

**Do NOT demo Vision or Multimodal** until `mtmd.dll` is permitted by Smart App Control;
they will surface as 503 / degraded-only and undercut the "local multimodal" claim.

If Vision is restored: replace steps 3–4 interleaving with the P&ID upload + "identify R-1001
and explain maintenance requirements" multimodal flow (the intended primary demo).

## Demo Timing

Measured live-demo durations for the reliable path:

- Startup: seconds (services already warm).
- Coder: **6–10 min** (CPU-only 3B; rehearse to land a pass). *(Vision would add ~35 s if
  unblocked; not measured.)*
- RAG: < 0.1 s warm.
- Artifact: ~0.6 s.
- Multimodal (degraded, RAG-only): ~14 s — not recommended to show.

**Approximate total live-demo duration (reliable path): 5–10 min** (dominated by the single
Coder run). Classification: **5–10 min**.

## Demo Reliability

| Step | Verdict | Basis |
|------|---------|-------|
| Frontend | RELIABLE | builds + serves; live `/api` proxy 200 |
| FastAPI | RELIABLE | health 200; all routes respond |
| Coder | ACCEPTABLE→RISKY | 1/3 converged; correct when it passes; ~6–10 min |
| Coder sandbox | RELIABLE | verification sub-second, pytest exit 0 on pass (Phase 6.6) |
| Coder verification | RELIABLE (when run passes) | 1/3 runs failed to converge |
| Vision | **BLOCKED** | Smart App Control blocks `mtmd.dll` |
| RAG | RELIABLE | 3/3, grounded, <0.1 s warm |
| Multimodal | **BLOCKED** (degrades) | vision unavailable; RAG-only VERIFIED but not truly multimodal |
| Artifact | RELIABLE | 3/3 valid DOCX, 0 ext calls |
| NetworkGuard | RELIABLE | 0 external calls, 0 blocked (no external attempt made) |
| Zero external calls | RELIABLE | verified every run |
| Resource stability | RELIABLE | no leak/VRAM growth; RAM peak 19.3 GB < 23.7 GB |
| Demo repeatability | ACCEPTABLE | cycles repeatable; coder variance is the only risk |

## What Not To Demo

- **Vision / Qwen-VL** — server cannot start (Smart App Control). Will show 503.
- **Multimodal (vision+RAG)** — cannot run as designed; only degrades to RAG-only, which
  misrepresents the capability and is not surfaced clearly in the UI.
- **Long un-rehearsed Coder run** — risk of non-convergence (FAILED) and a 6–10 min wait.
- **PostgreSQL-dependent features** (document registry `/documents` list, ingestion) — PG
  is OFFLINE; backend reports 503 honestly but these paths are not demoable here.
- **General model (:8001)** — not configured on this host.
- Anything requiring **simultaneous GPU model loading** — moot today (CPU-only), but on 6 GB
  keep models sequential.

## Performance Table

| Workflow | Runs | Min (s) | Avg (s) | Max (s) | Result |
|----------|------|---------|---------|---------|--------|
| Coder | 3 | 385.93 | 495.25 | 630.88 | ACCEPTABLE/RISKY (1/3 COMPLETED) |
| Vision | 3 | — | — | — | **BLOCKED** (SAC, 503) |
| RAG | 3 | 0.02 | 6.36 | 10.46 | RELIABLE (warm <0.1 s) |
| Multimodal | 3 | 13.99 | 14.26 | 14.68 | **BLOCKED/degraded** (vision down) |
| Artifact | 3 | 0.54 | 0.67 | 0.91 | RELIABLE |

## Resource Table

| Resource | Before | Peak | After |
|----------|--------|------|-------|
| VRAM | 1039 MiB | 1092 MiB | 812 MiB |
| RAM | 13.77 GB | 19.26 GB | 13.15 GB |
| CPU | 26 % | ~100 % (coder) | low |
| C: disk | 47.42 GB free | — | 47.71 GB free |
| D: disk | 218.58 GB free | — | 218.57 GB free |

## Acceptance Matrix

| Requirement | Result | Evidence |
|-------------|--------|----------|
| Frontend | PASS | `npm run dev` 200; live `/api` proxy |
| FastAPI | PASS | `/api/system/health` 200; all routes respond |
| Coder | PARTIAL | 1/3 COMPLETED (385.9 s, pytest exit 0); 2/3 FAILED non-converge; sandbox/verify correct |
| Coder sandbox | PASS | pytest runs in hardened sandbox, exit 0 on pass (Phase 6.6) |
| Coder verification | PASS (when run passes) | `test_passed=True`, `exit_code=0` run 1 |
| Vision | **BLOCKED** | SAC `WinError 4551` on `mtmd.dll`; 503 at endpoint |
| RAG | PASS | 3/3, 8 grounded hits, <0.1 s warm, ext=0 |
| Multimodal | **BLOCKED/degraded** | vision down → RAG-only VERIFIED; not true multimodal |
| Artifact | PASS | 3/3 valid DOCX (39 KB), opens, asset+disclaimer+sources, ext=0 |
| NetworkGuard | PASS | `external_api_calls=0`, `blocked_connections=0` every run |
| Zero successful external calls | PASS | verified all runs |
| Resource stability | PASS | no VRAM/RAM leak; peak 19.3 GB < 23.7 GB |
| Demo repeatability | ACCEPTABLE | 3 cycles repeatable; coder variance only risk |

## Remaining Issues

1. **Vision blocked by Windows Smart App Control (BLOCKER for Vision + Multimodal).**
   `mtmd.dll` unsigned → blocked (`WinError 4551`, CodeIntegrity 3077/3033). Fix options
   (user decision, outside Phase 8 scope): disable/turn-off Smart App Control, add a WDAC
   exclusion for the file, or run inside the Docker path that carries a bundled signed
   `llama-server.exe` (`C:\Users\shiva\.docker\bin\inference\llama-server.exe`). This is an
   OS policy, not a code change.
2. **Coder reliability on CPU-only 3B** — 2/3 runs did not converge within the repair
   budget (~6–10 min). Not a defect; a property of 3B CPU inference. Mitigate by rehearsal
   or a smaller/scoped task.
3. **Multimodal degraded-path UI disclosure** — when vision fails, top-level status stays
   `VERIFIED` and `VisionResult` does not render `uncertain_items`/`errors`. The data layer
   is honest; the UI is not. Recommend surfacing `errors`/`vision_evidence.confidence` in
   `Workbench.tsx` (one component change, not done here per "measure first" + no broad
   changes without confirmation).
4. **GPU acceleration NOT VERIFIED** — CPU-only llama.cpp wheel; rebuilding forbidden by
   Phase-8 rules. RTX 4050 present but unused by models.
5. PostgreSQL OFFLINE — document registry/ingestion paths return 503 (honest); not needed
   for the validated workflows.
6. General model not configured on this host.

## Final Verdict

# PHASE 8 PARTIALLY COMPLETE

The sovereign local pipeline is validated end-to-end with **zero external calls** for the
workflows that can run: **RAG (RELIABLE), Artifact/DOCX (RELIABLE), Coder (works but
RISKY on CPU-only 3B), FastAPI + Frontend (RELIABLE), NetworkGuard (VERIFIED 0 external
calls), Resource stability (no leaks)**. The **Vision and Multimodal demos are BLOCKED by
Windows Smart App Control** blocking the `mtmd.dll` multimodal projector — an environment
security policy outside the repository, confirmed with OS event-log evidence and reproduced
twice. No code was changed to work around it, and no sandbox/NetworkGuard was weakened.

Measured evidence (raw harness JSON): `C:\Users\shiva\AppData\Local\Temp\kilo\phase8\cycle{1,2,3}.json`.
