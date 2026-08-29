import base64
import time
import sys

from openai import OpenAI

SERVER = "http://localhost:8003/v1"
client = OpenAI(base_url=SERVER, api_key="none")

PROMPT = (
    "This is a Piping and Instrumentation Diagram (P&ID). "
    "Describe what you see at a high level, then list any instrument symbols, "
    "valves, pumps, tanks, or tagged equipment you can identify (with their tag "
    "numbers if visible). If the image is unclear, say so."
)

images = sys.argv[1:] or [
    r"D:\Sovereign_AI\PID_Dataset\0__raw_data\sheets\test\194.jpg",
    r"D:\Sovereign_AI\PID_Dataset\0__raw_data\sheets\test\194_resized.jpg",
]


def b64(path: str) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


for img in images:
    print(f"\n===== {img} =====")
    t0 = time.time()
    resp = client.chat.completions.create(
        model="qwen-vl",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64(img)}"}},
                    {"type": "text", "text": PROMPT},
                ],
            }
        ],
        max_tokens=400,
        temperature=0.1,
    )
    dt = time.time() - t0
    print(f"[elapsed {dt:.1f}s]")
    print(resp.choices[0].message.content)
