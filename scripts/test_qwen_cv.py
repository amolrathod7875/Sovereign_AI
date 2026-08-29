import base64
import io

from PIL import Image, ImageDraw
from llama_cpp import Llama
from llama_cpp.llama_chat_format import Qwen25VLChatHandler

MODEL_PATH = r"D:\Sovereign_AI\models\qwen-vision\Qwen2.5-VL-3B-Instruct-Q4_K_M.gguf"
MMPROJ_PATH = r"D:\Sovereign_AI\models\qwen-vision\mmproj-Qwen2.5-VL-3B-Instruct-Q8_0.gguf"


def make_test_image() -> str:
    """Render a simple image with readable text; return base64 JPEG."""
    img = Image.new("RGB", (512, 256), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, 492, 236], outline="red", width=6)
    draw.text((120, 110), "SOVEREIGN AI", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode("utf-8")


print("Loading vision model + projector...")
chat_handler = Qwen25VLChatHandler(clip_model_path=MMPROJ_PATH, verbose=False)
llm = Llama(
    model_path=MODEL_PATH,
    chat_handler=chat_handler,
    chat_format="qwen2-vl",
    n_ctx=4096,
    n_gpu_layers=0,
    verbose=False,
)

b64 = make_test_image()
messages = [
    {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": "What text is written in this image?"},
        ],
    }
]

print("Generating...")
out = llm.create_chat_completion(messages=messages, max_tokens=128, temperature=0.1)
text = out["choices"][0]["message"]["content"]
print("---- MODEL OUTPUT ----")
print(text)
print("---------------------")
