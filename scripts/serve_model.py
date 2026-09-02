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
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
from llama_cpp import Llama
from llama_cpp.llama_chat_format import Qwen25VLChatHandler


def build_app(model_id: str, llm: Llama) -> FastAPI:
    app = FastAPI(title=f"Sovereign AI - {model_id}")

    @app.get("/v1/models")
    def list_models():
        return {"object": "list", "data": [{"id": model_id, "object": "model"}]}

    @app.post("/v1/chat/completions")
    async def chat_completions(req: Request):
        body = await req.json()
        messages = body.get("messages", [])
        temperature = float(body.get("temperature", 0.1))
        max_tokens = int(body.get("max_tokens", 512))
        stream = bool(body.get("stream", False))

        if stream:
            # Simple non-streaming fallback (clients can call with stream=False).
            stream = False

        out = llm.create_chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=stream,
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
    # Production defaults (validated Phases 11.4-11.8 on RTX 4050):
    #   coder:  --n-gpu-layers 40 --n-ctx 2048
    #   vision: --n-gpu-layers 99 --n-ctx 2048
    # See backend/app.config Settings class for the canonical values.
    p.add_argument("--n-ctx", type=int, default=4096)
    p.add_argument("--n-gpu-layers", type=int, default=0)
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, required=True)
    args = p.parse_args()

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

    app = build_app(args.model_id, llm)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
