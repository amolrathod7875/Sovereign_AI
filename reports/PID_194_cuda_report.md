# Qwen2.5-VL on P&ID `194.jpg` — CUDA (GPU) Run Report

**Date:** 2026-08-29
**GPU:** NVIDIA GeForce RTX 4050 (6 GB), driver CUDA 13.1, toolkit CUDA 12.4
**Runtime:** Prebuilt CUDA `llama-server` (llama.cpp `b10679`, CUDA 12.4 build) — same binary as the plan's `ghcr.io/ggml-org/llama.cpp:server` container
**Model:** `models/qwen-vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf` + `mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf`
**Client:** `sovereign-ai` conda env, `openai` client → `http://localhost:8003/v1` (script `test_qwen_cv_server.py`)

## Why a separate CUDA binary

The `llama-cpp-python` installed in the env is the **CPU-only** wheel (`py3-none-win_amd64`),
so `n_gpu_layers` is ignored and everything ran on CPU (the full-res `194.jpg` previously
**timed out >240 s**). Building a CUDA wheel locally is blocked (no MSVC compiler, Windows
long-paths disabled). The official prebuilt CUDA `llama-server.exe` needed no compilation.

Server launch:
```
C:\llbin\llama\llama-server.exe -m <vl.gguf> --mmproj <mmproj.gguf> \
    -ngl 99 --mmproj-offload --port 8003 --host 0.0.0.0
```
(`--chat-template` was **omitted** — forcing it broke multimodal marker insertion; the
model's own template is auto-detected.)

## Results

### `test/194.jpg` — full resolution (3800 × 2458, ~1.1 MB)
- **Elapsed: 48.9 s** (GPU). On CPU this image **timed out** (>240 s). GPU made it feasible.
- Output: identified as a **wastewater treatment plant P&ID**, listed instrument/valve/pump/
  tank symbol families. The 3B Q4 model began repeating symbol categories near the 400-token
  cap (model-quality limitation, not speed).

### `test/194_resized.jpg` — downscaled (1024 × 662)
- **Elapsed: 18.2 s** (GPU).
- Output: identified **Grit Washer** tag (`GWT-51-…`), pumps/valves/instrument symbols.

## CPU vs GPU timing

| Image | CPU (llama-cpp-python) | GPU (llama-server CUDA) | Verdict |
|---|---|---|---|
| `194.jpg` full (3800×2458) | **timed out >240 s** | **48.9 s** | GPU required |
| `194_resized.jpg` (1024×662) | encode alone ~39.8 s; run completed | **18.2 s** total | ~2–4× faster |

The vision encoder (`clip_encode`/mmproj) is the dominant CPU cost; with `--mmproj-offload`
it runs on the GPU, cutting encode from tens of seconds to sub-second. End-to-end GPU time
for the full sheet (48.9 s) is **less than the CPU encode time of the small image**.

## Observations

- **GPU offload works** on the 6 GB RTX 4050: 3B Q4 main (~2.0 GB) + mmproj Q8 (~0.8 GB) + KV
  cache fit with headroom under `-ngl 99`. Only one GGUF resident at a time (Plan §17).
- The model is the same 3B Q4; **GPU changes speed, not accuracy**. Full-res still triggers
  repetition at high token counts — downscaling + higher quant (or 7B VL) improves fidelity.
- The prebuilt server is OpenAI-compatible, so the existing `openai` client and
  `scripts/serve_model.py` design apply unchanged (just point at the CUDA endpoint).
- `torch` in the env is still CPU-only; irrelevant for llama.cpp inference.

## Artifacts produced
| File | Purpose |
|---|---|
| `C:\llbin\llama\llama-server.exe` | Prebuilt CUDA 12.4 server binary |
| `test_qwen_cv_server.py` | OpenAI-client driver for the GPU server (image path args) |
| `PID_194_vision_report.md` | Prior CPU-only report |

## Recommendation
- Keep the CUDA `llama-server` as the **vision serving** component; wire it into the agent's
  `MULTIMODAL_ANALYSIS` route (port 8003) instead of the in-process CPU `llama_cpp.Llama`.
- For production accuracy on dense P&IDs, cap input at ~1024–1280 px and/or use a higher-quant
  or 7B VL GGUF with sequential loading.
- Optionally enable Windows long-paths + install MSVC later if you want a CUDA-enabled
  `llama-cpp-python` (so `scripts/serve_model.py` and `test_qwen_cv.py` also use GPU).
