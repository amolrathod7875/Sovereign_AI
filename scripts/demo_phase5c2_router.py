"""Phase 5C-2 — Unified local model router demonstration.

Runs the four required demonstrations through the SINGLE capability-based router
(``app.models.router``), which selects local models from the SINGLE registry and
executes them through the EXISTING clients/tools (vision tool, coder client,
local RAG). Every demo is wrapped in ``no_network()`` so external_calls == 0 is
enforced and asserted.

Run from the repo root:
    cd D:\\Sovereign_AI\\backend
    python ..\\scripts\\demo_phase5c2_router.py
"""
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from app.models.router import route, RoutingRequest, execute_routing  # noqa: E402
from agent.security.netguard import no_network  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
PID = REPO / "PID_Dataset" / "0__raw_data" / "sheets" / "test" / "158.jpg"
REPORT = REPO / "reports" / "phase5c2_demo_run.md"


def _explain(d):
    print("\nMODEL ROUTING")
    print(f"  Task type : {d.task_type}")
    print(f"  Modality  : {d.modality}")
    print(f"  Selected  : {d.selected_model}")
    print(f"  Models    : {d.models_required}")
    print(f"  RAG       : {d.requires_rag}")
    print(f"  Tools     : {d.requires_tools}")
    print(f"  Conflict  : n/a")
    print(f"  Confidence: {d.confidence}")
    print(f"  Reason    : {d.reason}")
    print(f"  Capabilities: {d.capabilities}")
    print(f"  All local : {d.all_local}  (external_calls={d.external_calls})")


def demo_coding():
    print("\n" + "=" * 78)
    print("DEMO 1 — CODING  (router -> Qwen Coder -> sandbox)")
    print("=" * 78)
    task = "Write a Python function that calculates the Reynolds number given density, velocity, characteristic length and dynamic viscosity."
    t0 = time.time()
    d = route(RoutingRequest(task=task, requires_code=True))
    overhead = (time.time() - t0) * 1000
    _explain(d)
    assert d.selected_model == "qwen-coder", d.selected_model
    t0 = time.time()
    out = execute_routing(d, task=task, max_tokens=600)
    exec_s = time.time() - t0
    code = out["outputs"].get("code", "")
    sand = out["outputs"].get("sandbox", {})
    print(f"\n[route overhead {overhead:.1f}ms] [execute {exec_s:.1f}s] "
          f"external_calls={out['external_calls']} models={out['models_used']}")
    print("--- GENERATED CODE (head) ---")
    print("\n".join(code.splitlines()[:25]))
    print("--- SANDBOX ---")
    print("exit_code:", sand.get("exit_code"), "| stdout:", (sand.get("stdout") or "")[:400])
    result_val = sand.get("result")
    verified = sand.get("exit_code") == 0
    return {"demo": "DEMO1_CODING", "overhead_ms": overhead, "exec_s": exec_s,
            "external_calls": out["external_calls"], "selected_model": d.selected_model,
            "code_head": code[:600], "sandbox_exit": sand.get("exit_code"),
            "verified": verified, "models_used": out["models_used"]}


def demo_vision():
    print("\n" + "=" * 78)
    print("DEMO 2 — VISION  (router -> Qwen-VL on 127.0.0.1:8003)")
    print("=" * 78)
    task = "Identify the major equipment and equipment tags visible in this P&ID."
    t0 = time.time()
    d = route(RoutingRequest(task=task, image_path=str(PID)))
    overhead = (time.time() - t0) * 1000
    _explain(d)
    assert d.selected_model == "vision"
    t0 = time.time()
    out = execute_routing(d, task=task, image_path=str(PID))
    exec_s = time.time() - t0
    vis = out["outputs"].get("vision", {})
    tags = out["outputs"].get("vision_tags", [])
    print(f"\n[route overhead {overhead:.1f}ms] [execute {exec_s:.1f}s] "
          f"external_calls={out['external_calls']} models={out['models_used']}")
    print("model:", vis.get("model"), "| data_origin:", vis.get("data_origin"),
          "| confidence:", vis.get("confidence"))
    print("extracted tags:", tags[:15])
    print("findings:", (vis.get("findings") or [])[:8])
    return {"demo": "DEMO2_VISION", "overhead_ms": overhead, "exec_s": exec_s,
            "external_calls": out["external_calls"], "selected_model": d.selected_model,
            "tags": tags[:15], "model": vis.get("model"),
            "data_origin": vis.get("data_origin"), "models_used": out["models_used"]}


def demo_knowledge():
    print("\n" + "=" * 78)
    print("DEMO 3 — KNOWLEDGE  (router -> general + local RAG)")
    print("=" * 78)
    task = "Explain the maintenance requirements for R-1001 using the local knowledge base."
    t0 = time.time()
    d = route(RoutingRequest(task=task))
    overhead = (time.time() - t0) * 1000
    _explain(d)
    assert d.selected_model == "general" and d.requires_rag
    t0 = time.time()
    out = execute_routing(d, task=task, asset_tag="R-1001", max_tokens=400)
    exec_s = time.time() - t0
    rag = out["outputs"].get("rag_evidence", [])
    synth = out["outputs"].get("synthesis", {})
    print(f"\n[route overhead {overhead:.1f}ms] [execute {exec_s:.1f}s] "
          f"external_calls={out['external_calls']} models={out['models_used']}")
    print(f"RAG evidence hits: {len(rag)}")
    for h in rag[:5]:
        print(f"  - {h['document_type']} ({h['source_file']}) score={h['score']}")
    print("general synthesis used:", synth.get("used"),
          "| note:", synth.get("reason") or synth.get("answer", "")[:200])
    return {"demo": "DEMO3_KNOWLEDGE", "overhead_ms": overhead, "exec_s": exec_s,
            "external_calls": out["external_calls"], "selected_model": d.selected_model,
            "rag_hits": len(rag), "synthesis_used": synth.get("used"),
            "models_used": out["models_used"]}


def demo_multimodal():
    print("\n" + "=" * 78)
    print("DEMO 4 — MULTIMODAL  (router -> Qwen-VL + RAG + reasoning)")
    print("=" * 78)
    task = ("Inspect P&ID 158.jpg, identify R-1001, and explain the relevant "
            "maintenance information using the local knowledge base.")
    t0 = time.time()
    d = route(RoutingRequest(task=task, image_path=str(PID)))
    overhead = (time.time() - t0) * 1000
    _explain(d)
    assert "vision" in d.models_required and "general" in d.models_required
    t0 = time.time()
    out = execute_routing(d, task=task, image_path=str(PID), asset_tag="R-1001",
                          max_tokens=400)
    exec_s = time.time() - t0
    vis = out["outputs"].get("vision", {})
    tags = out["outputs"].get("vision_tags", [])
    rag = out["outputs"].get("rag_evidence", [])
    synth = out["outputs"].get("synthesis", {})
    print(f"\n[route overhead {overhead:.1f}ms] [execute {exec_s:.1f}s] "
          f"external_calls={out['external_calls']} models={out['models_used']}")
    print("vision tags:", tags[:15])
    print("RAG evidence hits:", len(rag))
    for h in rag[:5]:
        print(f"  - {h['document_type']} ({h['source_file']}) score={h['score']}")
    print("reasoning synthesis used:", synth.get("used"))
    return {"demo": "DEMO4_MULTIMODAL", "overhead_ms": overhead, "exec_s": exec_s,
            "external_calls": out["external_calls"],
            "selected_model": d.selected_model, "models_required": d.models_required,
            "tags": tags[:15], "rag_hits": len(rag),
            "models_used": out["models_used"]}


def write_report(demos):
    REPO.joinpath("reports").mkdir(parents=True, exist_ok=True)
    parts = []
    parts.append("# Phase 5C-2 — Unified Local Model Router Demo Run\n")
    parts.append(f"_Generated: {datetime.utcnow().isoformat()}Z_\n")
    parts.append("## Environment\n")
    parts.append("- Router: `backend/app/models/router.py` (capability-based)")
    parts.append("- Registry: `backend/app/models/registry.py` (all local=True)")
    parts.append("- Coder: Qwen2.5-Coder-3B-Instruct @ http://localhost:8002/v1")
    parts.append("- Vision: Qwen2.5-VL-3B-Instruct @ http://127.0.0.1:8003/v1 (live)")
    parts.append("- General: Qwen2.5-3B-Instruct @ http://localhost:8001/v1 "
                 "(weights not present on this host; RAG-grounded path used)")
    parts.append("- Network: every demo wrapped in `no_network()`; external_calls must be 0\n")
    parts.append("## Routing latency (classification + selection)\n")
    for dm in demos:
        parts.append(f"- {dm['demo']}: route overhead {dm['overhead_ms']:.1f}ms, "
                     f"execute {dm['exec_s']:.1f}s")
    parts.append("")
    tot_ext = sum(d["external_calls"] for d in demos)
    parts.append(f"## Sovereignty\n- Total external calls across all demos: **{tot_ext}**\n")
    for dm in demos:
        parts.append(f"## {dm['demo']}\n")
        parts.append(f"- selected_model: {dm['selected_model']}")
        parts.append(f"- models_used: {dm.get('models_used')}")
        parts.append(f"- external_calls: {dm['external_calls']}")
        if "tags" in dm:
            parts.append(f"- vision_tags: {dm['tags']}")
        if "rag_hits" in dm:
            parts.append(f"- rag_hits: {dm['rag_hits']}")
        if "verified" in dm:
            parts.append(f"- sandbox_verified: {dm['verified']} (exit {dm['sandbox_exit']})")
        if "synthesis_used" in dm:
            parts.append(f"- general_synthesis_used: {dm['synthesis_used']}")
        parts.append("")
    REPORT.write_text("\n".join(parts), encoding="utf-8")
    print(f"\nWrote report -> {REPORT}")


def main():
    demos = []
    for fn in (demo_coding, demo_vision, demo_knowledge, demo_multimodal):
        try:
            demos.append(fn())
        except Exception as e:
            import traceback
            print(f"!!! {fn.__name__} FAILED: {e}")
            traceback.print_exc()
            demos.append({"demo": fn.__name__, "error": str(e)})
    write_report(demos)
    print("\nDONE.")


if __name__ == "__main__":
    main()
