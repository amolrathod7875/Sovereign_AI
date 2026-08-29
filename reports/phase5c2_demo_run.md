# Phase 5C-2 — Unified Local Model Router Demo Run

_Generated: 2026-08-29T12:06:20.989530Z_

## Environment

- Router: `backend/app/models/router.py` (capability-based)
- Registry: `backend/app/models/registry.py` (all local=True)
- Coder: Qwen2.5-Coder-3B-Instruct @ http://localhost:8002/v1
- Vision: Qwen2.5-VL-3B-Instruct @ http://127.0.0.1:8003/v1 (live)
- General: Qwen2.5-3B-Instruct @ http://localhost:8001/v1 (weights not present on this host; RAG-grounded path used)
- Network: every demo wrapped in `no_network()`; external_calls must be 0

## Routing latency (classification + selection)

- DEMO1_CODING: route overhead 0.0ms, execute 14.4s
- DEMO2_VISION: route overhead 0.0ms, execute 9.5s
- DEMO3_KNOWLEDGE: route overhead 0.0ms, execute 10.6s
- DEMO4_MULTIMODAL: route overhead 0.0ms, execute 13.0s

## Sovereignty
- Total external calls across all demos: **0**

## DEMO1_CODING

- selected_model: qwen-coder
- models_used: ['coder']
- external_calls: 0
- sandbox_verified: True (exit 0)

## DEMO2_VISION

- selected_model: vision
- models_used: ['vision']
- external_calls: 0
- vision_tags: []

## DEMO3_KNOWLEDGE

- selected_model: general
- models_used: ['general']
- external_calls: 0
- rag_hits: 6
- general_synthesis_used: False

## DEMO4_MULTIMODAL

- selected_model: vision
- models_used: ['vision', 'general']
- external_calls: 0
- vision_tags: ['R-1001']
- rag_hits: 6
