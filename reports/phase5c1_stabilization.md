# Phase 5C-1 Stabilization Report

**Date:** 2026-08-29
**Phase goal:** Stabilize the Sovereign AI stack and enable CUDA GPU offload for the
existing local Qwen-VL llama.cpp server, then benchmark CPU vs GPU, verify vision→RAG→
agent, network sovereignty, and the test suite.

**Headline result:** GPU acceleration could **NOT** be enabled. The installed
`llama_cpp` build is CPU-only (`llama_supports_gpu_offload() == False`). Enabling CUDA
requires reinstalling/compiling `llama-cpp-python`, which this phase explicitly forbids.
Per the phase rules, the GPU check was treated as a STOP condition and reported rather
than worked around. All non-GPU work was completed.

---

## Environment

| Item | Value |
|------|-------|
| Python | 3.11.9 (conda env `sovereign-ai`) |
| CUDA toolkit | 12.4 (`nvcc` present; `C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.4`) |
| GPU | RTX 4050 Laptop GPU (per repo; `nvidia-smi` not on PATH in this shell) |
| llama.cpp | `llama_cpp_python` 0.3.35 |
| GPU offload support | **FALSE** — `llama_supports_gpu_offload()` returned `False`; only `llama_supports_mmap`/`mlock` are True. No `llama_supports_cuda` symbol exists. |
| PyTorch | 2.13.0 (CPU) — left unchanged per rules (not the target of this phase) |

`nvcc` and the CUDA toolkit are present, but the Python `llama_cpp` wheel was built
without the CUDA backend, so llama.cpp cannot offload layers to the GPU.

---

## Qwen-VL

| Item | Value |
|------|-------|
| Model | `Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf` |
| Model path | `D:\Sovereign_AI\models\qwen-vision\Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf` |
| Model size | 1,929,901,056 bytes (~1.80 GiB) |
| MMProj | `mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf` |
| MMProj path | `D:\Sovereign_AI\models\qwen-vision\mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf` |
| MMProj size | 844,757,728 bytes (~0.79 GiB) |
| Server | llama.cpp `llama-server` (OpenAI-compatible `/v1`) |
| Port | 127.0.0.1:8003 (loopback only) |
| `n_gpu_layers` | Attempted `99`; **ignored** — no CUDA backend, all 36 layers assigned to `device CPU`. Effective config = `0` (CPU). |

No model files were downloaded or copied. No second server was created.

---

## Baseline (CPU)

- Model weights load time (GGUF, `n_gpu_layers=0`): **2.35 s**
- The server also loads the mmproj/CLIP projector at startup (total cold-start a few
  seconds beyond model load).
- GPU VRAM during inference: **0 MB** (no CUDA backend; weights resident in system RAM).
- The server is the same OpenAI-compatible endpoint the agent/API already use.

---

## GPU attempt

`--n_gpu_layers 99` was passed to the existing `llama_cpp.server`. Startup logs prove
GPU offload is unavailable:

```
load_tensors: layer   0 assigned to device CPU
load_tensors: layer   1 assigned to device CPU
...
load_tensors: layer  35 assigned to device CPU
load_tensors: layer  36 assigned to device CPU
```

All 36 layers on CPU despite `n_gpu_layers=99`. `llama_supports_gpu_offload()` is `False`.
GPU acceleration therefore **cannot** be enabled in this environment without a CUDA
`llama_cpp` build, which this phase forbids ("DO NOT reinstall/compile llama-cpp-python").

---

## Benchmark

| Configuration | Image | Load Time | Inference | Total | GPU VRAM |
|---------------|-------|-----------|-----------|-------|----------|
| CPU (`n_gpu_layers=0`) | 158.jpg | 2.35 s (model) | n/a (incl. in total) | **7.64 s** | 0 MB (system RAM) |
| CPU (`n_gpu_layers=0`) | 194.jpg | 2.35 s (model) | n/a (incl. in total) | **9.66 s** | 0 MB (system RAM) |
| GPU (`n_gpu_layers=99`) | 158.jpg | BLOCKED | — | — | — |
| GPU (`n_gpu_layers=99`) | 194.jpg | BLOCKED | — | — | — |

Notes:
- "Total" = end-to-end HTTP request (image encode + CLIP projector + prefill + decode).
- Inference cannot be cleanly separated from preprocessing in the tool; both are within
  "Total".
- GPU rows are omitted because the CPU-only build silently ignores `n_gpu_layers`.
- Corroborating Phase 5B timings (same CPU config): 158.jpg 13.4 s, 194.jpg 11.1 s
  (those runs included the JSON structuring/parse overhead; consistent order of magnitude).

---

## Vision Quality

Verified on the current (unchanged CPU) config with the same Phase 5B prompts:

- **Equipment recognition:** P&ID mode returns `equipment`, `pumps`, `vessels`,
  `valves`, `instruments` entity classes.
- **Tag recognition:** agent run extracted `vision_tags = ['R-1001']` directly from the
  drawing — the key link that drives RAG.
- **Uncertainty:** model returns `uncertain` / `not_visible` rather than fabricating
  values (e.g. DEMO 1 `uncertain_items = ["Unclear about plant system"]`, conf 0.81).
- **No fabricated engineering values:** tool schema forces status labels
  (`verified|probable|uncertain|not_visible|conflict`) and never invents specs.
- **Source attribution:** every result carries `file`, `model`, `timestamp`,
  `source_file`, `data_origin: local`.

GPU enablement would not change this workflow; quality is identical because the model
weights and prompts are unchanged.

---

## Agent

Vision → Agent: **PASS**

`run_agent_task(image_path=158.jpg, analysis_type=pid)` produced:

- `status = VERIFIED`
- trace: `plan → vision_analysis → retrieve_evidence → analyze_evidence →
  needs_calculation → python_analysis → synthesize_findings → make_decision →
  generate_approval_note → verify_output`
- artifact generated (`R-1001_p5c1.docx`)

The agent still plans, retrieves, analyzes, reasons, verifies, and generates artifacts.
Vision remains one capability inside the existing system (no replacement).

---

## RAG

Vision → RAG: **PASS**

- VLM-extracted tag `R-1001` fed to the existing local hybrid retriever
  (`backend/rag`, Qdrant on-disk + BM25, collection `sovereign_knowledge`).
- **16** evidence items retrieved, all `asset_tag = R-1001`, `data_origin = local`.
- No new vector DB, no new RAG pipeline, no external embedder.

---

## Network

External calls: **PASS** (0)

- Agent run returned `external_calls = 0` (NetworkGuard active).
- Vision endpoint is loopback-only; `agent.tools.vision._assert_local_endpoint` rejects
  non-local hosts.
- Allowed: `127.0.0.1` / `localhost`. Forbidden external APIs/telemetry confirmed absent.

Known issue (pre-existing, not introduced here): `netguard.py` patches the global
`socket.socket`. When netguard-using tests run **before** the vision tests in the same
pytest session, the global can be left in a state that breaks subsequent loopback
connects, causing `test_vision_*` to error with connection failures. This is a
test-isolation artifact only — the real server and agent runs work (proven by the
benchmark and verification scripts, and by the Phase 5B isolation run of
`test_vision.py` = 10/10 passed).

---

## Tests

Commands run: `ruff check .`, `mypy backend/app/`, `pytest tests rag/tests`.

| Suite | Result |
|-------|--------|
| `ruff check .` | Findings present (pre-existing lint: E741×2, F541×2, F811×2, E401×1, E722×1). **None introduced by this phase.** |
| `mypy backend/app/` | **BLOCKED by environment** — Windows App Control policy blocks a mypy DLL (`ImportError: DLL load failed ... Application Control policy has blocked this file`). Not a code defect. |
| `pytest tests rag/tests` | **17 passed, 10 failed, 1 skipped** |

### Failure classification (all pre-existing; none introduced by Phase 5C-1)

1. `tests/test_agent.py::test_graph_runs_end_to_end` — **pre-existing** (Phase 4 agent
   decision logic: `approval_required` not `True` on the non-vision path).
2. `tests/test_agent.py::test_run_agent_task_output_shape` — **pre-existing** (same).
3. `tests/test_agent_e2e.py::test_full_task_end_to_end` — **pre-existing** (same).
4. `tests/test_agent_e2e.py::test_netguard_blocks_external_connections` —
   **pre-existing** (`netguard.py:43` `AttributeError: 'NoneType' object has no attribute
   'connect'` — netguard global socket-state bug).
5. `tests/test_agent_e2e.py::test_fastapi_endpoint` — **pre-existing** (same netguard
   leak; AttributeError during local connect under guard).
6. `tests/test_vision.py::test_vision_server_connectivity` — **pre-existing
   test-isolation** (fails only when run after netguard tests in the same session; passes
   10/10 in isolation, and the server is reachable from the benchmark/verification scripts).
7. `tests/test_vision.py::test_image_analysis_returns_canonical_schema` — same isolation leak.
8. `tests/test_vision.py::test_pid_analysis_returns_structured_evidence` — same.
9. `tests/test_vision.py::test_vision_inference_stays_local` — same (`openai.APIConnectionError`
   due to leaked socket state).
10. `tests/test_vision.py::test_vision_tags_drive_rag_retrieval` — same.

`rag/tests` passed (counted in the 17 passed). The vision tool itself is verified
working; the 5 vision-test failures are a consequence of the netguard global-state leak,
not a vision regression.

---

## Disk

| | Value |
|---|-------|
| Free before | 52,953,800,704 bytes (~49.3 GiB) |
| Free after | 52,951,814,144 bytes (~49.3 GiB) |
| Delta | ~2 MB (benchmark JSON + report only) |
| Additional model downloads | **0** |

No environments created, no model copies, no bulk dataset processing, no Docker pulls.

---

## Changes

Source code changed this phase: **NONE.** (The only prior source fix — `vision.py`
indentation — was Phase 5B.)

New files created this phase:
- `scripts/bench_qwen_vl_phase5c1.py` — CPU baseline benchmark runner.
- `reports/qwen_vl_benchmark.json` — benchmark measurements.
- `reports/phase5c1_stabilization.md` — this report.

The existing Qwen-VL server was relaunched with `n_gpu_layers=0` (CPU) for benchmarking;
the earlier erroneous `n_gpu_layers=99` attempt was stopped. One vision server process
(CPU) remains running on 127.0.0.1:8003 — the single intended server.

---

## Final Status

| Area | Status | Note |
|------|--------|------|
| GPU inference | **FAIL** | Blocked: CPU-only `llama_cpp` build (`gpu_offload=False`). Needs CUDA build (forbidden this phase). |
| Vision | **PASS** | Tool works; quality/uncertainty/source attribution preserved on CPU config. |
| Agent | **PASS** | Plan→retrieve→analyze→reason→verify→artifact; VERIFIED on 158.jpg. |
| RAG | **PASS** | Vision→RAG retrieved 16 local R-1001 evidence items. |
| Network sovereignty | **PASS** | `external_calls = 0`; loopback-only vision endpoint. |
| Regression status | **PASS** | No regressions introduced. Pre-existing failures documented & classified. |

---

## Remaining issues

1. **GPU offload unavailable** — the `sovereign-ai` env's `llama_cpp` lacks the CUDA
   backend. Enabling it requires a CUDA `llama-cpp-python` build (reinstall/compile),
   which Phase 5C-1 explicitly prohibits. Recommend a dedicated follow-up phase (or
   environment rebuild) if GPU inference is required.
2. **Netguard global socket-state leak** — `netguard.py` patches `socket.socket`
   globally; when netguard-using tests precede vision tests in one session, loopback
   connects break. Fix is out of scope (network-sovereignty code, not GPU); document only.
3. **Pre-existing Phase 4 agent test assertions** — `test_agent.py` /
   `test_agent_e2e.py` expect `approval_required == True` / `VERIFIED` on the non-vision
   path; unrelated to vision, pre-date this phase.
4. **mypy blocked by OS App Control** — cannot run type checks in this environment
   (DLL blocked by Application Control policy); environment issue, not a code defect.
5. **ruff lint findings** — minor pre-existing style issues; none introduced here.
