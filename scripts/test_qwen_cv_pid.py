import base64
import sys

from llama_cpp import Llama
from llama_cpp.llama_chat_format import Qwen25VLChatHandler

MODEL_PATH = r"D:\Sovereign_AI\models\qwen-vision\Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf"
MMPROJ_PATH = r"D:\Sovereign_AI\models\qwen-vision\mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf"

IMAGE_PATH = sys.argv[1] if len(sys.argv) > 1 else r"D:\Sovereign_AI\PID_Dataset\0__raw_data\sheets\train\1.jpg"


def encode_image(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


print(f"Loading Qwen2.5-VL and analyzing: {IMAGE_PATH}")
chat_handler = Qwen25VLChatHandler(clip_model_path=MMPROJ_PATH, verbose=False)
llm = Llama(
    model_path=MODEL_PATH,
    chat_handler=chat_handler,
    chat_format="qwen2-vl",
    n_ctx=4096,
    n_gpu_layers=0,
    verbose=False,
)

b64 = encode_image(IMAGE_PATH)
messages = [
    {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {
                "type": "text",
                "text": (
                    "This is a Piping and Instrumentation Diagram (P&ID). "
                    "Describe what you see at a high level, then list any instrument "
                    "symbols, valves, pumps, tanks, or tagged equipment you can identify "
                    "(with their tag numbers if visible). If the image is unclear, say so."
                ),
            },
        ],
    }
]

print("Generating...")
out = llm.create_chat_completion(messages=messages, max_tokens=400, temperature=0.1)
print("---- MODEL OUTPUT ----")
print(out["choices"][0]["message"]["content"])
print("---------------------")
