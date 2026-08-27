from llama_cpp import Llama

model_path = r"D:\Sovereign_AI\models\qwen-coder\qwen2.5-coder-3b-instruct-q4_k_m.gguf"

print("Loading model...")
llm = Llama(model_path=model_path, n_ctx=2048, n_gpu_layers=0, verbose=False)

prompt = (
    "You are a helpful coding assistant. "
    "Write a Python program that prints 1 to 10 ."
)

print("Generating...")
output = llm(prompt, max_tokens=128, temperature=0.1)
text = output["choices"][0]["text"]
print("---- MODEL OUTPUT ----")
print(text)
print("---------------------")
