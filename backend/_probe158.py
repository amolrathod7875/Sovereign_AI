import json, time
from agent.tools.vision import analyze_image

t0 = time.time()
r = analyze_image(
    r"..\PID_Dataset\0__raw_data\sheets\test\158.jpg",
    analysis_type="pid",
    prompt="Identify major process system, equipment, tags, relationships, uncertain elements.",
)
print("ELAPSED", round(time.time() - t0, 1))
print(json.dumps(r, indent=2, default=str))
