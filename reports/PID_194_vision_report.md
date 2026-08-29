# Qwen2.5-VL Test — P&ID Sheet `test/194.jpg`

**Date:** 2026-08-29
**Environment:** `conda` env `sovereign-ai` (Python 3.11.9)
**Runtime:** `llama-cpp-python==0.3.35` (prebuilt CPU wheel)
**Model:** `models/qwen-vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf` + `mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf`
**Script:** `test_qwen_cv_pid.py` (image path passed as argument)
**Image:** `PID_Dataset/0__raw_data/sheets/test/194.jpg`

## Image Pre-Processing

`194.jpg` is a **high-resolution** P&ID:

- Original: **3800 × 2458 px**, ~1.1 MB
- A direct run on the full-resolution image **timed out** (>240 s) on CPU because
  Qwen2.5-VL tiles the image into many vision tokens.
- Resized to **1024 × 662 px** (LANCZOS, JPEG q85) → `test/194_resized.jpg`.
  This is the file actually analyzed.

## Result (model output, verbatim key points)

The model correctly classified the drawing and extracted meaningful structure:

> "The image is a Piping and Instrumentation Diagram (P&ID) for an industrial
> process, specifically for a **Grit Washer and Grit Classifier system**."

**Tagged equipment it read (with tag numbers):**
- **Grit Washer** — tag `GWA-51-371`
- **Grit Classifier** — tag `GCA-51-376`

**Symbol categories identified (by type):**
- Instrument symbols: flow meters, pressure gauges, temperature sensors, level indicators
- Valves: gate valve, check valve, pilot valve, control valves
- Pumps, Tanks
- Control piping

## Performance Notes

- Vision encoder (`clip_encode`) on CPU: **~39.8 s** for the 1024×662 image
  (888 image tokens). This is the dominant cost and confirms **CPU inference is
  the bottleneck** for dense P&IDs.
- Full-resolution (3800×2458) is impractical on CPU; GPU offload (CUDA build of
  `llama-cpp-python` / llama.cpp server container) is required for production speed.
- The benign `ValueError: I/O operation on closed file` at exit is the known
  `llama-cpp-python` shutdown quirk, not a failure.

## Hardware Constraint — 6 GB VRAM

- RTX 4050 (6 GB) fits one 3B Q4_K_M GGUF (~2.0 GB) + mmproj (~0.8 GB) with KV
  headroom; **only one GGUF GPU-resident at a time** → sequential loading (Plan §17).
- Current wheel is **CPU-only**; `n_gpu_layers` is ignored. With GPU offload the
  3B VL model would encode in well under a second instead of ~40 s.
- Realistic local tier on 6 GB = **3B-class GGUFs** (coder + vision + small general).

## Assessment

✅ **Demo 3 validated on a large, real P&ID.** The 3B Q4_K_M VLM:
- Correctly recognized the diagram *type* (Grit Washer / Grit Classifier P&ID).
- Read actual equipment **tag numbers** (`GWA-51-371`, `GCA-51-376`).
- Listed instrument / valve / pump / tank symbol families.

⚠️ It described symbols **by category** rather than transcribing every tag on the
sheet (expected at 3B Q4 and after downscaling). For full symbol inventories,
crop regions (`PID_Dataset/1__processed_data/crops/`) and/or use a higher-quant or
7B VL model with GPU offload.

## Recommendation

- Add automatic downscaling (cap longest side ~1024–1280 px) inside the vision
  tool to keep CPU latency bounded.
- Enable GPU offload before any live demo.
- For symbol-level extraction, feed cropped regions instead of whole-sheet images.
