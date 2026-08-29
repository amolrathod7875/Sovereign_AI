"""Phase 5B — Local Vision Model integration demonstration.

Runs the three required multimodal demonstrations end-to-end against the
SINGLE authoritative vision tool (``agent.tools.vision``) and the LangGraph
maintenance agent (``agent.run``). Inference is fully local (llama.cpp server on
127.0.0.1:8003); the RAG knowledge base is the local Qdrant+BM25 store.

Demos
-----
1. Analyze PID 158.jpg (P&ID mode) -> structured visual evidence.
2. Inspect PID 194.jpg (inspection mode) -> structured visual evidence.
3. Inspect PID 158.jpg and connect R-1001 evidence to the local knowledge base
   via the agent (IMAGE -> QWEN-VL -> STRUCTURED EVIDENCE -> RAG -> AGENT).

Outputs are written to reports/ as JSON for the evaluation report.
"""
import json
import os
import time
from pathlib import Path

from agent.tools.vision import analyze_image, analyze_pid, extract_equipment_tags
from agent.run import run_agent_task

REPO = Path(__file__).resolve().parents[1]
PID = REPO / "PID_Dataset" / "0__raw_data" / "sheets" / "test"
IMG_158 = str(PID / "158.jpg")
IMG_194 = str(PID / "194.jpg")
REPORTS = REPO / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)


def _save(name: str, payload: dict):
    path = REPORTS / name
    path.write_text(json.dumps(payload, indent=2, default=str))
    return str(path)


def demo1_pid():
    print("\n================ DEMO 1: P&ID 158.jpg (P&ID mode) ================")
    t0 = time.time()
    res = analyze_pid(
        IMG_158,
        prompt=(
            "Analyze this P&ID and identify the major process system, equipment, "
            "equipment tags, process relationships, and any uncertain elements. "
            "Do not invent unreadable information."
        ),
    )
    res["execution_time_s"] = round(time.time() - t0, 3)
    print(f"  model         : {res['model']}")
    print(f"  data_origin   : {res['data_origin']}")
    print(f"  confidence    : {res['confidence']}")
    print(f"  description   : {res['description'][:160]}")
    print(f"  findings      : {len(res['findings'])}")
    print(f"  entities      : {len(res['entities'])}")
    print(f"  uncertain     : {res['uncertain_items']}")
    print(f"  latency       : {res['execution_time_s']} s")
    path = _save("demo1_pid_158.json", res)
    print(f"  saved -> {path}")
    return res


def demo2_inspection():
    print("\n================ DEMO 2: P&ID 194.jpg (inspection mode) ================")
    t0 = time.time()
    res = analyze_image(
        IMG_194,
        analysis_type="inspection",
        prompt=(
            "Inspect this P&ID and identify the equipment and process elements that "
            "are clearly visible. Highlight anything that cannot be confidently identified."
        ),
    )
    res["execution_time_s"] = round(time.time() - t0, 3)
    print(f"  model         : {res['model']}")
    print(f"  data_origin   : {res['data_origin']}")
    print(f"  confidence    : {res['confidence']}")
    print(f"  description   : {res['description'][:160]}")
    print(f"  findings      : {len(res['findings'])}")
    print(f"  entities      : {len(res['entities'])}")
    print(f"  uncertain     : {res['uncertain_items']}")
    print(f"  latency       : {res['execution_time_s']} s")
    path = _save("demo2_inspection_194.json", res)
    print(f"  saved -> {path}")
    return res


def demo3_vision_rag():
    print("\n================ DEMO 3: Vision -> RAG -> Agent (R-1001) ================")
    t0 = time.time()
    res = run_agent_task(
        "Inspect P&ID 158.jpg and connect any identified R-1001 information to the "
        "local knowledge base. Explain the relevant R-1001 context using only "
        "retrieved local evidence.",
        asset_tag="R-1001",
        run_id="phase5b_demo3",
        artifact_filename="R-1001_vision_rag_demo.docx",
        image_path=IMG_158,
        analysis_type="pid",
    )
    elapsed = round(time.time() - t0, 3)
    print(f"  status        : {res['status']}")
    print(f"  external_calls: {res['external_calls']} (network sovereignty)")
    print(f"  vision_tags   : {res['vision_tags']}")
    print(f"  vision_evidence: {len(res['vision_evidence'])} item(s)")
    print(f"  rag_evidence  : {len(res['evidence'])} item(s)")
    print(f"  artifacts     : {res['artifacts']}")
    print(f"  trace         : {' -> '.join(t.get('node') for t in res['trace'])}")
    print(f"  latency       : {elapsed} s")
    out = dict(res)
    out["demo_execution_time_s"] = elapsed
    path = _save("demo3_vision_rag.json", out)
    print(f"  saved -> {path}")
    return res


if __name__ == "__main__":
    summary = {
        "demo1_pid_158": demo1_pid(),
        "demo2_inspection_194": demo2_inspection(),
        "demo3_vision_rag": demo3_vision_rag(),
    }
    _save("demo_phase5b_summary.json", summary)
    print("\nAll Phase 5B demos completed. Artifacts written to reports/.")
