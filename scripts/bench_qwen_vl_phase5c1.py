"""Phase 5C-1 — Qwen-VL CPU baseline benchmark.

Measures the CURRENT (only available) configuration: llama.cpp CPU build
(llama_supports_gpu_offload == False), n_gpu_layers=0. GPU offload is NOT
available in this environment, so this is both the baseline AND the ceiling.

Outputs reports/qwen_vl_benchmark.json
"""
import json
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[1]
PID = REPO / "PID_Dataset" / "0__raw_data" / "sheets" / "test"
IMG_158 = str(PID / "158.jpg")
IMG_194 = str(PID / "194.jpg")
ENDPOINT = "http://localhost:8003/v1"
OUT = REPO / "reports" / "qwen_vl_benchmark.json"

MODEL_PATH = r"D:\Sovereign_AI\models\qwen-vision\Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf"
MPROJ_PATH = r"D:\Sovereign_AI\models\qwen-vision\mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf"

# --- model load time (server-independent, same GGUF) ---
print("Measuring model load time (n_gpu_layers=0) ...")
t0 = time.time()
from llama_cpp import Llama
Llama(model_path=MODEL_PATH, chat_handler=None, n_ctx=2048, n_gpu_layers=0,
      verbose=False)
load_time_s = round(time.time() - t0, 2)
print(f"  load_time_s = {load_time_s}")


def _request(img_path: str, at: str) -> dict:
    import base64
    from PIL import Image
    from io import BytesIO
    img = Image.open(img_path).convert("RGB")
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    prompt = (
        "You are inspecting a P&ID. Reply with ONE compact JSON object only. "
        "Schema: {plant_system, equipment, equipment_tags, pumps, vessels, "
        "reactors, valves, instruments, process_streams, relationships, uncertain}."
    )
    t = time.time()
    with httpx.Client(timeout=300) as c:
        r = c.post(f"{ENDPOINT}/chat/completions", json={
            "model": "qwen-vl",
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": prompt},
            ]}],
            "max_tokens": 500, "temperature": 0.1,
        })
        ms = round((time.time() - t) * 1000)
        body = r.json()
    txt = body["choices"][0]["message"]["content"]
    return {"total_ms": ms, "completion_chars": len(txt), "preview": txt[:200]}


print("Benchmarking 158.jpg (pid) ...")
r158 = _request(IMG_158, "pid")
print(f"  total_ms = {r158['total_ms']}")
print("Benchmarking 194.jpg (inspection) ...")
r194 = _request(IMG_194, "inspection")
print(f"  total_ms = {r194['total_ms']}")

result = {
    "configuration": "CPU-only llama.cpp build (llama_supports_gpu_offload=False), n_gpu_layers=0",
    "model": "Qwen2.5-VL-3B-Instruct (Q4_K_M)",
    "gpu_available": False,
    "gpu_offload_supported": False,
    "model_load_time_s": load_time_s,
    "gpu_vram_mb": "n/a (no CUDA backend; weights resident in system RAM)",
    "gpu_utilization": "n/a",
    "images": {
        "158.jpg": {"total_ms": r158["total_ms"], "completion_chars": r158["completion_chars"]},
        "194.jpg": {"total_ms": r194["total_ms"], "completion_chars": r194["completion_chars"]},
    },
    "note": "GPU rows omitted: n_gpu_layers=99 was attempted and ALL 36 layers were "
            "assigned to device CPU (no CUDA backend in installed llama_cpp 0.3.35).",
}
OUT.write_text(json.dumps(result, indent=2))
print(f"wrote {OUT}")
