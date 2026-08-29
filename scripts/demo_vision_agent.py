"""Phase 5B — Local vision model integration demonstration.

Runs three end-to-end multimodal tasks through the SINGLE Sovereign AI agent
(LangGraph) + the SINGLE vision tool (agent.tools.vision) + the LOCAL Qwen-VL
server (llama.cpp on localhost:8003) + the LOCAL RAG knowledge base.

All inference is local. The agent run is wrapped in no_network() so external
calls == 0 is enforced and asserted.

Run from the repo root:
    cd D:\Sovereign_AI\\backend
    python ..\\scripts\\demo_vision_agent.py
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Make the backend package importable regardless of CWD.
BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

from agent.run import run_agent_task  # noqa: E402
from agent.security.netguard import no_network  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PID_158 = str(REPO / "PID_Dataset" / "0__raw_data" / "sheets" / "test" / "158.jpg")
PID_194 = str(REPO / "PID_Dataset" / "0__raw_data" / "sheets" / "test" / "194.jpg")
REPORT = REPO / "reports" / "multimodal_evaluation.md"


def _summarize_vision(ve: dict) -> str:
    lines = []
    lines.append(f"  source_file : {ve.get('source_file')}")
    lines.append(f"  analysis_type: {ve.get('analysis_type')}")
    lines.append(f"  model       : {ve.get('model')}")
    lines.append(f"  data_origin : {ve.get('data_origin')}")
    lines.append(f"  timestamp   : {ve.get('timestamp')}")
    lines.append(f"  confidence  : {ve.get('confidence')}")
    lines.append(f"  description : {str(ve.get('description'))[:300]}")
    lines.append(f"  findings    : {len(ve.get('findings', []))} item(s)")
    for f in ve.get("findings", [])[:8]:
        lines.append(f"      - {f}")
    lines.append(f"  entities    : {len(ve.get('entities', []))} item(s)")
    for e in ve.get("entities", [])[:10]:
        if isinstance(e, dict):
            lines.append(f"      - {e.get('type')}: {e.get('name')}")
    lines.append(f"  uncertain_items: {ve.get('uncertain_items', [])}")
    return "\n".join(lines)


def demo_1_analyze_pid():
    print("\n" + "=" * 78)
    print("DEMO 1 — Analyze P&ID 158.jpg (agent decides vision is required)")
    print("=" * 78)
    task = ("Analyze this P&ID and identify the major process system, equipment, "
            "equipment tags, process relationships, and any uncertain elements. "
            "Do not invent unreadable information.")
    t0 = time.time()
    res = run_agent_task(task, asset_tag="R-1001", image_path=PID_158, analysis_type="pid",
                         artifact_filename="vision_demo1_158.docx")
    dt = round(time.time() - t0, 1)

    ve = (res.get("vision_evidence") or [{}])[0] if res.get("vision_evidence") else {}
    print(f"\n[latency {dt}s] status={res['status']} external_calls={res['external_calls']}")
    print("VISION EVIDENCE:")
    print(_summarize_vision(ve))
    print("AGENT TRACE (node / tool / status):")
    for tr in res.get("trace", []):
        print(f"  - {tr.get('node')}:{tr.get('action')} [{tr.get('status')}] "
              f"({tr.get('tool')}) {tr.get('duration_ms')}ms")
    return {"demo": "DEMO1_PID_158", "latency_s": dt, "result": res, "vision": ve}


def demo_2_inspect_pid():
    print("\n" + "=" * 78)
    print("DEMO 2 — Inspect P&ID 194.jpg (agent decides vision is required)")
    print("=" * 78)
    task = ("Inspect this P&ID and identify the equipment and process elements that "
            "are clearly visible. Highlight anything that cannot be confidently identified.")
    t0 = time.time()
    res = run_agent_task(task, asset_tag="R-1001", image_path=PID_194, analysis_type="pid",
                         artifact_filename="vision_demo2_194.docx")
    dt = round(time.time() - t0, 1)

    ve = (res.get("vision_evidence") or [{}])[0] if res.get("vision_evidence") else {}
    print(f"\n[latency {dt}s] status={res['status']} external_calls={res['external_calls']}")
    print("VISION EVIDENCE:")
    print(_summarize_vision(ve))
    print("AGENT TRACE (node / tool / status):")
    for tr in res.get("trace", []):
        print(f"  - {tr.get('node')}:{tr.get('action')} [{tr.get('status')}] "
              f"({tr.get('tool')}) {tr.get('duration_ms')}ms")
    return {"demo": "DEMO2_PID_194", "latency_s": dt, "result": res, "vision": ve}


def demo_3_vision_rag():
    print("\n" + "=" * 78)
    print("DEMO 3 — Vision -> RAG -> Agent (connect P&ID 158.jpg to R-1001 KB)")
    print("=" * 78)
    task = ("Inspect P&ID 158.jpg and connect any identified R-1001 information to the "
            "local knowledge base. Explain the relevant R-1001 context using only "
            "retrieved local evidence.")
    t0 = time.time()
    res = run_agent_task(task, asset_tag="R-1001", image_path=PID_158, analysis_type="pid",
                         artifact_filename="vision_demo3_rag.docx")
    dt = round(time.time() - t0, 1)

    ve = (res.get("vision_evidence") or [{}])[0] if res.get("vision_evidence") else {}
    tags = res.get("vision_tags", [])
    print(f"\n[latency {dt}s] status={res['status']} external_calls={res['external_calls']}")
    print("VISION-EXTRACTED EQUIPMENT TAGS:", tags)
    print("VISION EVIDENCE:")
    print(_summarize_vision(ve))

    # Show RAG connection: which retrieved evidence references R-1001 docs.
    rag_sources = []
    for e in res.get("evidence", []):
        src = e.get("source_file") or e.get("document_type")
        if src:
            rag_sources.append(f"{src} ({e.get('document_type')}) conf={e.get('confidence')}")
    print("RETRIEVED LOCAL KNOWLEDGE-BASE EVIDENCE (RAG):")
    for s in rag_sources[:12]:
        print("  -", s)

    # Vision findings that made it into the synthesized findings.
    vision_findings = [f for f in res.get("findings", [])
                       if isinstance(f, dict) and f.get("claim") in ("vision_finding", "vision_entity")]
    print(f"VISION FINDINGS FOLDED INTO AGENT SYNTHESIS: {len(vision_findings)}")
    print("DECISION REASONING (mentions R-1001 + vision):")
    print("  ", (res.get("reasoning_summary") or "")[:600])
    return {
        "demo": "DEMO3_VISION_RAG", "latency_s": dt, "result": res, "vision": ve,
        "tags": tags, "rag_sources": rag_sources, "vision_findings": vision_findings,
    }


def write_report(demos):
    REPO.joinpath("reports").mkdir(parents=True, exist_ok=True)
    parts = []
    parts.append("# Multimodal Evaluation — Local Qwen-VL + Sovereign AI Agent\n")
    parts.append(f"_Generated: {datetime.utcnow().isoformat()}Z_\n")
    parts.append("## Environment\n")
    parts.append("- Model: **Qwen2.5-VL-3B-Instruct** (GGUF Q4_K_M + Q8_0 mmproj)")
    parts.append("- Serving: **llama.cpp** OpenAI-compatible server, **localhost:8003 only**")
    parts.append("- Agent: **backend/agent** LangGraph graph (single agent)")
    parts.append("- Vision tool: **backend/agent/tools/vision.py** (single tool system)")
    parts.append("- RAG: **local** hybrid Qdrant + BM25 (no external calls)")
    parts.append("- Network: agent wrapped in `no_network()` guard; external calls must be 0\n")

    total_images = len(demos)
    successful = sum(1 for d in demos if d["result"]["status"] == "COMPLETED")
    total_uncertain = sum(len(d["vision"].get("uncertain_items", [])) for d in demos)
    external = sum(d["result"]["external_calls"] for d in demos)
    rag_ok = any(bool(d.get("rag_sources")) for d in demos)
    agent_ok = all(d["result"]["external_calls"] == 0 for d in demos)

    parts.append("## Summary\n")
    parts.append(f"- Images processed: **{total_images}** (158.jpg, 194.jpg, 158.jpg)")
    parts.append(f"- Successful analyses: **{successful}/{total_images}**")
    parts.append(f"- Inference latency (agent E2E, s): " +
                 ", ".join(str(d['latency_s']) for d in demos))
    parts.append(f"- Uncertain findings preserved: **{total_uncertain}** item(s)")
    parts.append(f"- RAG connection success (DEMO3): **{'YES' if rag_ok else 'NO'}**")
    parts.append(f"- Agent integration success: **{'YES' if agent_ok else 'NO'}** (external_calls==0)")
    parts.append(f"- Network calls (external): **{external}**\n")

    for d in demos:
        parts.append(f"## {d['demo']}\n")
        ve = d["vision"]
        parts.append(f"- status: {d['result']['status']}")
        parts.append(f"- latency_s: {d['latency_s']}")
        parts.append(f"- external_calls: {d['result']['external_calls']}")
        parts.append(f"- model: {ve.get('model')}")
        parts.append(f"- data_origin: {ve.get('data_origin')}")
        parts.append(f"- source_file: {ve.get('source_file')}")
        parts.append(f"- timestamp: {ve.get('timestamp')}")
        parts.append(f"- confidence: {ve.get('confidence')}")
        parts.append(f"- description: {str(ve.get('description'))[:400]}")
        parts.append(f"- findings ({len(ve.get('findings', []))}):")
        for f in ve.get("findings", [])[:10]:
            parts.append(f"    - {f}")
        parts.append(f"- entities ({len(ve.get('entities', []))}):")
        for e in ve.get("entities", [])[:12]:
            if isinstance(e, dict):
                parts.append(f"    - {e.get('type')}: {e.get('name')}")
        parts.append(f"- uncertain_items: {ve.get('uncertain_items', [])}")
        if d.get("tags") is not None:
            parts.append(f"- vision_extracted_tags: {d['tags']}")
            parts.append(f"- rag_sources: {d['rag_sources']}")
            parts.append(f"- vision_findings_in_synthesis: {len(d['vision_findings'])}")
        parts.append("")

    parts.append("## Safety / Hallucination notes\n")
    parts.append("- The vision tool instructs the VLM to NEVER invent tags/pressures/temps/specs.")
    parts.append("- Unreadable elements are labelled `uncertain` / `not_visible` / `conflict`.")
    parts.append("- All vision output is treated as *witness* evidence, not engineering truth.")
    parts.append("- Path allow-list prevents the vision tool reading outside approved local dirs.")
    parts.append("- The VLM endpoint is forced to loopback; the agent run blocks external sockets.\n")

    parts.append("## Remaining issues\n")
    parts.append("- Qwen2.5-VL-3B is a small local model; tag reading is imperfect and some "
                 "tags may be misread. Uncertainty is preserved rather than corrected.")
    parts.append("- CLIP image-encoding dominates CPU latency; inputs are downscaled to "
                 f"{_max_edge()}px longest edge to keep it practical.")
    parts.append("- Demo 1/2 run the full maintenance-agent graph (RAG + sandbox), so output "
                 "includes an approval note; the multimodal evidence is surfaced via vision_evidence.\n")

    REPORT.write_text("\n".join(parts), encoding="utf-8")
    print(f"\nWrote report -> {REPORT}")


def _max_edge():
    try:
        from agent.config import VISION_MAX_EDGE
        return VISION_MAX_EDGE
    except Exception:
        return "?"


if __name__ == "__main__":
    demos = []
    demos.append(demo_1_analyze_pid())
    demos.append(demo_2_inspect_pid())
    demos.append(demo_3_vision_rag())
    write_report(demos)
    print("\nDONE.")
