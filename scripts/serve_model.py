"""Minimal OpenAI-compatible model server for local GGUF weights.

Launched as one process per model (matches the Plan's per-model endpoints).
Example:
  python scripts/serve_model.py \
      --model-id qwen-coder \
      --model-path models/qwen-coder/qwen2.5-coder-3b-instruct-q4_k_m.gguf \
      --port 8002

  python scripts/serve_model.py \
      --model-id qwen-vision \
      --model-path models/qwen-vision/Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf \
      --mmproj models/qwen-vision/mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf \
      --chat-format qwen2-vl \
      --port 8003
"""
import argparse
import asyncio
import logging
import os
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
from llama_cpp import Llama
from llama_cpp.llama_chat_format import Qwen25VLChatHandler

from scripts.gpu_admission import GPUAdmissionLease, GPUAdmissionTimeout, acquire

logger = logging.getLogger(__name__)


def build_app(model_id: str, llm: Llama, admission_timeout: float) -> FastAPI:
    app = FastAPI(title=f"Sovereign AI - {model_id}")

    @app.get("/v1/models")
    def list_models():
        return {"object": "list", "data": [{"id": model_id, "object": "model"}]}

    def _run_inference(messages: list, temperature: float, max_tokens: int, stream: bool):
        with acquire(timeout_s=admission_timeout) as lease:
            logger.info(
                "GPU admission granted model=%s pid=%d wait_ms=%.0f",
                model_id,
                os.getpid(),
                lease.wait_ms,
            )
            try:
                return llm.create_chat_completion(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    stream=stream,
                )
            except Exception:
                logger.exception("Inference failed model=%s pid=%d", model_id, os.getpid())
                raise

    @app.post("/v1/chat/completions")
    async def chat_completions(req: Request):
        body = await req.json()
        messages = body.get("messages", [])
        temperature = float(body.get("temperature", 0.1))
        max_tokens = int(body.get("max_tokens", 512))
        stream = bool(body.get("stream", False))

        if stream:
            stream = False

        try:
            out = await asyncio.to_thread(
                _run_inference,
                messages,
                temperature,
                max_tokens,
                stream,
            )
        except GPUAdmissionTimeout:
            logger.warning(
                "GPU admission timeout model=%s pid=%d timeout_s=%.1f",
                model_id,
                os.getpid(),
                admission_timeout,
            )
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": "5"},
                content={
                    "error": {
                        "type": "gpu_busy",
                        "message": "Local GPU inference capacity is busy. Retry later.",
                    }
                },
            )

        content = out["choices"][0]["message"]["content"]
        prompt_tokens = out.get("usage", {}).get("prompt_tokens", 0)
        completion_tokens = out.get("usage", {}).get("completion_tokens", 0)

        return JSONResponse(
            {
                "id": f"chatcmpl-{uuid.uuid4().hex}",
                "object": "chat.completion",
                "created": int(time.time()),
                "model": model_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": content},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                },
            }
        )

    return app


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--model-id", required=True)
    p.add_argument("--model-path", required=True)
    p.add_argument("--mmproj", default=None)
    p.add_argument("--chat-format", default=None)
    p.add_argument("--n-ctx", type=int, default=4096)
    p.add_argument("--n-gpu-layers", type=int, default=0)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, required=True)
    p.add_argument(
        "--gpu-admission-timeout",
        type=float,
        default=float(os.environ.get("SOVEREIGN_GPU_ADMISSION_TIMEOUT", "60")),
        help="Max seconds to wait for global GPU admission before returning HTTP 429.",
    )
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    chat_handler = None
    if args.mmproj:
        chat_handler = Qwen25VLChatHandler(clip_model_path=args.mmproj, verbose=False)

    llm = Llama(
        model_path=args.model_path,
        chat_handler=chat_handler,
        chat_format=args.chat_format,
        n_ctx=args.n_ctx,
        n_gpu_layers=args.n_gpu_layers,
        verbose=False,
    )

    app = build_app(args.model_id, llm, args.gpu_admission_timeout)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
