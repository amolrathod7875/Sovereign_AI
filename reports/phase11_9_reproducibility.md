# Phase 11.9 — Production Configuration & Reproducibility

> **Purpose:** Lock the known-good CUDA + AVX2 llama-cpp-python configuration
> into the repository and document the exact steps to reproduce the validated
> setup on this host.
>
> **Validated:** Phases 11.4–11.8 (2026-09-01 — 2026-09-02)
> **Hardware:** RTX 4050 Laptop GPU / AMD Ryzen 5 5600G / Windows 11

---

## 1. Hardware requirements

| Component | Minimum | Validated |
|-----------|---------|-----------|
| CPU | x86-64 with AVX2 | AMD Ryzen 5 5600G (AVX2 yes, AVX-512 no) |
| GPU | NVIDIA with compute capability ≥ 8.0, ≥ 4 GB VRAM | NVIDIA GeForce RTX 4050 Laptop GPU (6 141 MiB, sm_89) |
| RAM | ≥ 8 GB | 16 GB+ recommended for concurrent models |
| Storage | ≥ 10 GB free | SSD recommended for model loading speed |

**Important:** The AMD Ryzen 5 5600G does NOT support AVX-512. The prebuilt
llama-cpp-python CUDA wheel crashes on this CPU with
`OSError: [WinError -1073741795]`. A custom source build with
`GGML_AVX512=OFF` is required (see §8).

---

## 2. NVIDIA driver requirement

| Item | Version |
|------|---------|
| Driver | 591.66 or newer |
| CUDA Driver API | 13.1 (reported by driver) |

Verify with:
```bash
nvidia-smi
```

---

## 3. CUDA Toolkit requirement

| Item | Version |
|------|---------|
| CUDA Toolkit | 12.4.99 |
| nvcc | 12.4.99 |

**Note:** The CUDA Toolkit must be installed and on `PATH`. The build uses
`nvcc` directly (via Ninja generator), so the MSBuild integration
(`Nvcc.targets`) is not required.

Verify with:
```bash
nvcc --version
```

---

## 4. Python version

| Item | Version |
|------|---------|
| Python | 3.11.9 |
| Environment | `sovereign-ai` (conda) |

The conda environment must be activated before running any model server
or the backend:
```bash
conda activate sovereign-ai
```

---

## 5. llama-cpp-python version

| Item | Version |
|------|---------|
| Package | llama-cpp-python |
| Version | 0.3.35 |
| Install type | Custom source build (CUDA + AVX2) |

Verify with:
```bash
python -c "import llama_cpp; print(llama_cpp.__version__); print('GPU offload:', llama_cpp.llama_supports_gpu_offload())"
```

Expected output:
```
0.3.35
GPU offload: True
```

---

## 6. Required compiler/toolchain

| Tool | Version | Purpose |
|------|---------|---------|
| MSVC (cl) | 19.44 (Visual Studio 2022) | C/C++ host compiler |
| nvcc | 12.4.99 | CUDA device code compiler |
| cmake | 4.4.3+ (pip) | Build system generator |
| ninja | 1.13.2+ (pip) | Build system (required — see §8) |

**Why Ninja, not Visual Studio generator:** The CUDA 12.4 install has no
`Nvcc.targets` MSBuild integration, so the VS generator fails with
"No CUDA toolset found". Ninja invokes `nvcc` directly and bypasses the
problem.

Activate the MSVC environment before building:
```bash
"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" amd64
```

---

## 7. CMake/Ninja requirement

CMake 4.4.3+ and Ninja 1.13.2+ are required. Install via pip if not present:
```bash
pip install cmake ninja
```

---

## 8. Exact CMAKE_ARGS used for the successful build

```bash
CMAKE_ARGS="-DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=89 -DGGML_AVX=ON -DGGML_AVX2=ON -DGGML_AVX512=OFF -DGGML_NATIVE=OFF" \
CMAKE_GENERATOR=Ninja \
pip install . --no-build-isolation --force-reinstall
```

**Flag explanation:**

| Flag | Value | Reason |
|------|-------|--------|
| `GGML_CUDA` | `ON` | Enable CUDA backend |
| `CMAKE_CUDA_ARCHITECTURES` | `89` | Target RTX 4050 (sm_89) |
| `GGML_AVX` | `ON` | Enable AVX instructions |
| `GGML_AVX2` | `ON` | Enable AVX2 instructions |
| `GGML_AVX512` | `OFF` | Ryzen 5 5600G has no AVX-512; ON crashes |
| `GGML_NATIVE` | `OFF` | Disable `-march=narrow` for portability |

**Source:** `llama_cpp_python-0.3.35-source.tar.gz` (74.9 MB, cached at
`_rollback/llama_cpp_python-0.3.35-source.tar.gz`).

**Resulting DLLs** in `Lib\site-packages\llama_cpp\lib\`:
- `ggml-cuda.dll` (180 MB)
- `ggml-base.dll`
- `ggml-cpu.dll`
- `ggml.dll`
- `llama.dll`
- `mtmd.dll` (1.17 MB — multimodal)

---

## 9. Exact model files expected

All models live under `models/` (gitignored). Timestamps from 27-08-2026.

| Role | File | Size | SHA256 |
|------|------|------|--------|
| Coder | `models/qwen-coder/qwen2.5-coder-3b-instruct-q4_k_m.gguf` | 1.96 GB | (verify before use) |
| Vision | `models/qwen-vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf` | 1.80 GB | (verify before use) |
| mmproj | `models/qwen-vision/mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf` | 0.79 GB | (verify before use) |

**Important:** These files must NEVER be downloaded automatically by the
application. They are local-only assets.

---

## 10. Model ports

| Service | Port | Binding |
|---------|------|---------|
| Backend (FastAPI) | 8000 | `0.0.0.0` |
| General LLM | 8001 | loopback (reserved, weights absent) |
| Coder LLM | 8002 | loopback |
| Vision LLM | 8003 | loopback |
| Frontend (Vite) | 3000 | loopback |

---

## 11. Production n_gpu_layers

| Model | n_gpu_layers | n_ctx | Validated |
|-------|-------------|-------|-----------|
| Coder (Qwen2.5-Coder-3B) | 40 | 2048 | Phase 11.7–11.8 |
| Vision (Qwen2.5-VL-3B) | 99 | 2048 | Phase 11.6–11.8 |

**Why ngl=40 for coder (not 99):** The coder has 36 layers. ngl=99 offloads
all layers but uses more VRAM (~3 132 MiB) for marginal gain. ngl=40
achieves 42.18 t/s with lower VRAM (~3 177 MiB init), leaving more
headroom for concurrent workloads.

**Why ngl=99 for vision:** The vision model benefits from full offload.
Peak VRAM ~5 832 MiB leaves ~309 MiB headroom on the 6 141 MiB card.

**VRAM warning:** Vision is VRAM-constrained. The ngl=99 configuration is
validated for the tested workload (Qwen2.5-VL-3B-Instruct Q4_K_M). Monitor
VRAM under production workloads; arbitrary high-resolution workloads have
not been tested.

---

## 12. Production n_ctx

Both models use `n_ctx=2048` for production. This is sufficient for:
- Code generation tasks (coder)
- Single-image analysis with structured prompts (vision)

Larger contexts increase VRAM usage and reduce throughput.

---

## 13. Server startup commands

```bash
# Terminal 1: coder (CUDA, ngl=40)
python scripts/serve_model.py --model-id qwen-coder \
    --model-path models/qwen-coder/qwen2.5-coder-3b-instruct-q4_k_m.gguf \
    --port 8002 --n-gpu-layers 40 --n-ctx 2048

# Terminal 2: vision (CUDA, ngl=99)
python scripts/serve_model.py --model-id qwen-vision \
    --model-path models/qwen-vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf \
    --mmproj models/qwen-vision/mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf \
    --chat-format qwen2-vl --port 8003 --n-gpu-layers 99 --n-ctx 2048
```

---

## 14. Backend startup command

```bash
cd backend
PYTHONPATH=. uvicorn app.main:app --reload --port 8000
```

---

## 15. Health/status verification

| Check | Endpoint | Expected |
|-------|----------|----------|
| Backend health | `GET /api/system/health` | `{"status": "healthy", "sovereign_mode": true}` |
| Backend status | `GET /api/system/status` | Full component list with real status |
| Coder server | `GET http://localhost:8002/v1/models` | `{"data": [{"id": "qwen-coder"}]}` |
| Vision server | `GET http://localhost:8003/v1/models` | `{"data": [{"id": "qwen-vision"}]}` |

**Sovereignty verification:**
- `external_api_calls` must be 0
- `data_origin` must be `local`
- All model endpoints must be loopback/private

---

## 16. CPU rollback procedure

If the CUDA build needs to be reverted (e.g., after a system change):

```bash
# Activate environment
conda activate sovereign-ai

# Uninstall CUDA build
pip uninstall llama-cpp-python -y

# Install known-good CPU wheel
pip install _rollback/llama_cpp_python-0.3.35-cpu-py3-none-win_amd64.whl
```

**Rollback wheel:** `_rollback/llama_cpp_python-0.3.35-cpu-py3-none-win_amd64.whl`
(6.76 MB, SHA256 verified).

**After rollback:** Set `--n-gpu-layers 0` for all model servers to force
CPU-only inference.

---

## 17. VRAM limitations

| Scenario | Peak VRAM | Headroom |
|----------|-----------|----------|
| Coder only (ngl=40) | ~3 383 MiB | ~2 758 MiB |
| Vision only (ngl=99) | ~5 832 MiB | ~309 MiB |
| Concurrent (tested) | 5 699–5 771 MiB | ~370–442 MiB |

**Total GPU VRAM:** 6 141 MiB

**Warning:** Vision is VRAM-constrained. The ngl=99 configuration is
validated for the tested workload only. Arbitrary high-resolution
workloads, multiple concurrent vision requests, or larger models may
exceed available VRAM.

---

## 18. Concurrency limitations

Concurrent multi-model GPU inference was tested in Phase 11.7 with peak
VRAM 5 699–5 771 MiB (under the 5 800 MiB safety limit).

**Status:** CONDITIONAL. Production concurrency should be monitored and
is not guaranteed under arbitrary workloads. The validated configuration
is for single-request-per-model at a time.

---

## 19. Sovereignty verification

The Sovereign AI runtime enforces local-only inference:

- **NetworkGuard** (`backend/agent/security/netguard.py`) blocks all
  non-loopback/private network connections during agent runs.
- **Registry** (`backend/app/models/registry.py`) validates that all
  model endpoints resolve to loopback or RFC1918 addresses.
- **Vision tool** (`backend/agent/tools/vision.py`) refuses to send
  image bytes to any non-trusted-local endpoint.

**Trusted local destinations:**
- `127.0.0.0/8` (IPv4 loopback)
- `::1/128` (IPv6 loopback)
- `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16` (RFC1918)

**Explicitly blocked:** link-local, documentation ranges, benchmark
ranges, IPv6 link-local, IPv6 ULA, CGNAT, multicast, reserved, and any
hostname requiring DNS resolution.

---

## 20. What must NEVER be downloaded automatically

The following must NEVER be downloaded by the application at runtime:

- GGUF model weights (coder, vision, mmproj, general)
- Embedding model weights (`sentence-transformers/all-MiniLM-L6-v2`)
- Reranker model weights
- CUDA runtime libraries
- llama-cpp-python wheels or source
- Any external API payloads

All model weights are local-only assets. The application must fail
gracefully (503 Service Unavailable) if weights are absent, never fall
back to a remote provider.

---

## Validated capabilities

| Capability | Status | Phase |
|------------|--------|-------|
| Coder CUDA inference | VALIDATED | 11.4, 11.7, 11.8 |
| Vision CUDA inference | VALIDATED | 11.6, 11.7, 11.8 |
| Local RAG (Qdrant + BM25) | VALIDATED | 11.8 |
| NetworkGuard | VALIDATED | 10.3 |
| Backend integration | VALIDATED | 9.x–11.x |

---

## Not validated / blocked

| Capability | Status | Reason |
|------------|--------|--------|
| General model inference | BLOCKED | Weights absent |
| Arbitrary high-resolution vision | NOT VALIDATED | VRAM-constrained |
| Unlimited concurrent inference | NOT VALIDATED | Single-request tested |
| Long-running production load | NOT VALIDATED | Benchmark-only |

---

## Performance baseline

### Coder (Qwen2.5-Coder-3B-Instruct Q4_K_M)

| Metric | CPU (ngl=0) | GPU (ngl=40) | Speedup |
|--------|-------------|--------------|---------|
| Mean latency | 0.8911 s | 0.2894 s | 3.08x |
| Mean TPS | 17.96 | 55.91 | 3.11x |
| VRAM | N/A | ~3 383 MiB | — |

### Vision (Qwen2.5-VL-3B-Instruct Q4_K_M)

| Metric | CPU (ngl=0) | GPU (ngl=99) | Speedup |
|--------|-------------|--------------|---------|
| Mean latency | 1.8477 s | 0.5587 s | 3.31x |
| Mean TPS | 6.72 | 23.32 | 3.47x |
| VRAM | N/A | ~5 832 MiB | — |

### RAG (hybrid Qdrant + BM25)

| Metric | Value |
|--------|-------|
| Warm-up | ~25.1 s |
| Subsequent queries | ~25–47 ms |
| Chunks indexed | 393 |
| Data origin | local |
| External calls | 0 |

---

## References

- `reports/phase11_4_cuda_source_build.md` — CUDA build documentation
- `_rollback/llama_cpp_python-0.3.35-cpu-py3-none-win_amd64.whl` — CPU fallback wheel
- `_rollback/llama_cpp_python-0.3.35-source.tar.gz` — Source tarball for rebuilds
- `backend/app/config.py` — Production configuration (Settings class)
- `scripts/serve_model.py` — Model server launcher
