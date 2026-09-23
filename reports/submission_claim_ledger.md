# Phase 17B — Competition Submission Claim Ledger

## How to use this ledger

For every claim that may appear in the PPT, demo video, or judge Q&A:
- Proposed claim: the exact sentence we want to use.
- Primary classification: exactly one of the standard evidence classes.
- Evidence types: optional secondary tags (LIVE / PERSISTENT / HISTORICAL / TEST).
- Evidence source: file path + line range, or committed report.
- Safe wording: approved text.
- Forbidden wording: text that overclaims.
- Demo visibility: LIVE / HISTORICAL / DO_NOT_DEMO.

---

## CLM-SOV-01

Proposed:
"Sovereign AI is designed for on-premises industrial AI workflows."

Classification:
LIVE_VERIFIED

Evidence types:
LIVE

Evidence source:
backend/agent/security/netguard.py:91-143 (socket monkey-patch blocks external connects)
backend/app/api/system.py:191-212 (_external_call_stats reads real guard counters)
frontend/src/pages/NetworkMonitor.tsx:115-209 (live event stream + counters)

Safe wording:
"Sovereign AI is designed for on-premises industrial AI workflows."
"Application-level network controls restrict agent execution to trusted local destinations."

Forbidden wording:
"Fully air-gapped machine."
"Certified air gap."
"No network access whatsoever."

Demo visibility:
LIVE

Notes:
NetworkGuard is application-level (agent run scope). It does not certify the whole machine. The frontend NetworkMonitor page shows blocked/local events; use it carefully because the current UI contains the overclaim "LOCAL / AIR-GAPPED" at NetworkMonitor.tsx:124.

---

## CLM-SOV-02

Proposed:
"Application-level network controls restrict agent execution to trusted local destinations."

Classification:
TEST_VERIFIED

Evidence types:
TEST

Evidence source:
backend/tests/test_netguard.py (28 parametrized cases)
backend/agent/security/netguard.py:27-33 (trust list)

Safe wording:
above proposed

Forbidden wording:
"Whole-machine air-gap certified."
"Impossible to make external calls."

Demo visibility:
LIVE (show test results as HISTORICAL if desired)

Notes:
The trust list is positive: anything not matching loopback/RFC1918 is blocked. Hostnames requiring DNS are rejected. This is application-level enforcement, not whole-machine certification.

---

## CLM-SOV-03

Proposed:
"Every terminal human decision produces a Sovereignty Receipt linked into a tamper-evident history."

Classification:
PERSISTENT_VERIFIED

Evidence types:
PERSISTENT

Evidence source:
backend/governance/receipt.py:106-193 (payload build + SHA256)
backend/governance/receipt_chain.py:133-212 (append-only chain)
backend/governance/approval.py:346-462 (atomic transition + receipt + chain)

Safe wording:
above proposed
"Terminal decisions produce a cryptographically hashed Sovereignty Receipt."
"Receipts are linked into a tamper-evident local history."

Forbidden wording:
"Tamper-proof blockchain audit log."
"Immutable ledger."
"Cannot be rewritten."

Demo visibility:
LIVE (pending reviews + chain head visible in Judge Mode)

Notes:
The chain is tamper-evident, not tamper-proof. No external trust anchor, no digital signature. An attacker with SQLite write access can rewrite history.

---

## CLM-SOV-04

Proposed:
"Human approval and rejection decisions are persisted separately from the AI recommendation, with artifact-integrity verification before terminal transition."

Classification:
PERSISTENT_VERIFIED

Evidence types:
PERSISTENT

Evidence source:
backend/governance/approval.py:107-140 (SQLite schema, PENDING/APPROVED/REJECTED)
backend/governance/approval.py:321-462 (approve/reject transitions with artifact hash check)
backend/governance/receipt.py:196-369 (receipt generation + verification)
backend/governance/receipt_chain.py:133-212 (chain append on terminal transition)

Safe wording:
above proposed
"Human authorization is persisted separately from the AI recommendation."

Forbidden wording:
"Human approval is not implemented."
"Approval rewrites/finalizes the DOCX."
"Immutable approval record."
"Tamper-proof governance."

Demo visibility:
LIVE (Judge Mode shows pending reviews + terminal runs)

Notes:
Current project truth: PENDING -> APPROVED/REJECTED transitions are implemented with artifact hash verification. The generated DOCX remains DRAFT even after a terminal human decision. This is intentional. The frozen Phase-13 scorecard limitation "Human approve/reject is not implemented yet" reflects the historical source commit, NOT current project truth.

---

## CLM-MOD-01

Proposed:
"The router classifies tasks and selects local models by capability."

Classification:
TEST_VERIFIED

Evidence types:
TEST

Evidence source:
backend/app/models/router.py:189-286 (route function)
reports/competition_scorecard.json:362-453 (10/10 routing tests passed)

Safe wording:
above proposed

Forbidden wording:
"General model executes all reasoning."
"Routing proves model execution."
"The system always runs a model."

Demo visibility:
LIVE (Judge Mode shows routing.selected_model)

Notes:
Routing is classification + lookup. It never invokes a model. selected_model=general does NOT mean general model executed.

---

## CLM-MOD-02

Proposed:
"General model weights are not yet provisioned on this host."

Classification:
CONFIGURED_NOT_AVAILABLE

Evidence types:
PERSISTENT, TEST

Evidence source:
backend/app/models/registry.py:94-110 (general entry, status=standby)
backend/app/api/system.py:90-101 (_model_component probes /v1/models, checks weights dir)
reports/competition_scorecard.json:369 (general_model_runtime_status=UNAVAILABLE)

Safe wording:
above proposed

Forbidden wording:
"General AI is online."
"Reasoning model available."
"All models running."

Demo visibility:
LIVE (Judge Mode shows General Model: UNAVAILABLE or OFFLINE)

Notes:
The general model endpoint and router path are fully implemented. No code change is required to make this live; only the GGUF weights need to be downloaded to models/qwen-general/.

---

## CLM-MOD-03

Proposed:
"Qwen2.5-Coder-3B-Instruct weights are present and the server is configured to run on localhost:8002."

Classification:
CONFIGURED_NOT_AVAILABLE

Evidence types:
PERSISTENT, HISTORICAL

Evidence source:
backend/app/models/registry.py:111-126 (qwen-coder entry)
scripts/serve_model.py:1-167 (server script)
reports/competition_scorecard.json routing notes: "Does not imply model server availability."

Safe wording:
above proposed

Forbidden wording:
"Coder model is online."
"Code generation is available now."

Demo visibility:
LIVE (status shows OFFLINE if server not running)

Notes:
Weights are present on disk. Server is NOT currently running. CUDA-accelerated inference was historically validated on RTX 4050.

---

## CLM-MOD-04

Proposed:
"Qwen2.5-VL-3B-Instruct weights and mmproj are present; the server is configured for localhost:8003."

Classification:
CONFIGURED_NOT_AVAILABLE

Evidence types:
PERSISTENT, HISTORICAL

Evidence source:
backend/app/models/registry.py:127-142 (vision entry)
scripts/serve_model.py:133-151 (mmproj + chat_format qwen2-vl)

Safe wording:
above proposed

Forbidden wording:
"Vision model is online."
"P&ID analysis is available now."

Demo visibility:
LIVE (status shows OFFLINE if server not running)

Notes:
Weights present on disk. Server is NOT currently running. CUDA-accelerated inference was historically validated on RTX 4050.

---

## CLM-RAG-01

Proposed:
"Hybrid retrieval combines dense vector search with BM25 lexical search over locally indexed documents."

Classification:
PERSISTENT_VERIFIED

Evidence types:
PERSISTENT

Evidence source:
backend/rag/config.py:14-44 (QDRANT_PATH, BM25_DIR, EMBEDDING_DIM, weights)
backend/rag/retrieval/hybrid.py:31-109 (HybridRetriever, weighted fusion)
data/rag/qdrant_db/ (embedded Qdrant)
data/rag/bm25/ (BM25 index)

Safe wording:
above proposed

Forbidden wording:
"Perfect retrieval."
"All answers found at rank 1."
"No foreign assets ever retrieved." (foreign_asset_hits=0 is true but do not overclaim)

Demo visibility:
LIVE (if Qdrant+BM25 index present)

Notes:
When the embedding model is unavailable the retriever degrades honestly to BM25-only and tags results retrieval_mode="bm25_only".

---

## CLM-RAG-02

Proposed:
"Frozen evaluation metrics: Hit@1 2/6, Hit@3 4/6, Hit@5 6/6, MRR 0.56, primary source @1 2/6, foreign asset hits 0."

Classification:
HISTORICAL_VERIFIED

Evidence types:
HISTORICAL

Evidence source:
reports/competition_scorecard.json:117-205 (rag_retrieval metrics)
reports/competition_scorecard.md:51-66 (same metrics in Markdown)

Safe wording:
above proposed (exact numbers)
"The frozen Phase-13 evaluation records Hit@1 2 of 6, Hit@3 4 of 6, Hit@5 6 of 6, MRR 0.56."

Forbidden wording:
"100% accurate retrieval."
"All queries return the primary source first."

Demo visibility:
HISTORICAL (Judge Mode shows exact numbers under FROZEN COMPETITION EVIDENCE)

Notes:
These metrics come from the frozen Phase-13 scorecard. Some queries rank secondary documents above the primary source at rank 1. No reranker is currently active.

---

## CLM-RAG-03

Proposed:
"No validated active reranker is currently deployed."

Classification:
NOT_IMPLEMENTED

Evidence types:
TEST, HISTORICAL

Evidence source:
backend/app/rag/reranker.py:7-65 (Reranker class uses word-overlap placeholder, no model inference)
backend/app/rag/retrieval.py:58-63 (reranker.rerank is called but falls back to fused results on error)

Safe wording:
above proposed

Forbidden wording:
"Reranker improves retrieval quality."
"BGE reranker online."

Demo visibility:
DO NOT DEMO

Notes:
The app/rag/retrieval.py pipeline calls reranker.rerank(), but the reranker is a deterministic word-overlap heuristic, not a BGE model. The README and Better_plan list a reranker as "online" — this is inaccurate and must not be claimed.

---

## CLM-AGN-01

Proposed:
"The agent follows a LangGraph workflow: validate identity, retrieve evidence, analyze, calculate, synthesize, decide, generate artifact, verify."

Classification:
TEST_VERIFIED

Evidence types:
TEST

Evidence source:
backend/agent/graph.py:22-78 (graph definition)
backend/tests/test_agent.py + test_agent_e2e.py (9 tests PASS)

Safe wording:
above proposed

Forbidden wording:
"Agent always produces the correct answer."
"Fully autonomous decision-making."

Demo visibility:
HISTORICAL (flagship run evidence)

Notes:
The graph is implemented and tested. Execution requires model servers for full live runs.

---

## CLM-AGN-02

Proposed:
"Tool use is restricted to approved local operations: knowledge-base search, Python sandbox, DOCX artifact generation, and local vision."

Classification:
TEST_VERIFIED

Evidence types:
TEST

Evidence source:
backend/agent/tools/ (search_kb.py, python_execute.py, create_docx.py, vision.py)
backend/agent/coder/sandbox.py (import hook + socket guard)
backend/tests/test_coder_sandbox.py (29 tests PASS)

Safe wording:
above proposed

Forbidden wording:
"Unlimited code execution."
"Agent can run any tool."

Demo visibility:
LIVE (show sandbox boundary tests as historical)

Notes:
Sandbox blocks subprocess, network imports, and out-of-tree writes.

---

## CLM-GOV-01

Proposed:
"Human approval transitions are persisted in SQLite with artifact-integrity verification before terminal transition."

Classification:
PERSISTENT_VERIFIED

Evidence types:
PERSISTENT

Evidence source:
backend/governance/approval.py:107-140 (SQLite schema, artifact_sha256 column)
backend/governance/approval.py:346-462 (_transition verifies artifact hash before status change)

Safe wording:
above proposed
"Human authorization is persisted separately from the AI recommendation."

Forbidden wording:
"Human approval is not implemented."
"Immutable approval record."
"Tamper-proof governance."

Demo visibility:
LIVE (Judge Mode pending reviews)

Notes:
Current project truth: PENDING -> APPROVED/REJECTED is implemented with artifact hash verification, receipt generation, and chain append. SQLite can be rewritten by an attacker with file-system access. The hash check protects against accidental corruption, not malicious tampering by a privileged user.

---

## CLM-GOV-02

Proposed:
"The receipt chain detects modifications to historical entries."

Classification:
PERSISTENT_VERIFIED

Evidence types:
PERSISTENT

Evidence source:
backend/governance/receipt_chain.py:281-451 (verify_chain checks sequence, links, hashes, bindings)

Safe wording:
above proposed
"Receipts are linked into a tamper-evident local history."

Forbidden wording:
"Tamper-proof blockchain."
"Immutable history."

Demo visibility:
LIVE (Judge Mode shows chain valid/invalid)

Notes:
Chain is tamper-evident. No external anchor, no digital signature.

---

## CLM-FLAG-01

Proposed:
"The committed flagship report documents one end-to-end industrial scenario with 14 of 14 validation checks passed."

Classification:
HISTORICAL_VERIFIED

Evidence types:
HISTORICAL

Evidence source:
reports/flagship_workflow_latest.json:1-141 (timestamp 2026-09-22, run_07d24d69e01e, 14/14 checks passed)

Safe wording:
above proposed

Forbidden wording:
"All industrial scenarios validated."
"Flagship runs live on demand without model servers."
"General model executed the flagship."
"Vision model executed the flagship."

Demo visibility:
HISTORICAL (Judge Mode shows committed JSON under FLAGSHIP INDUSTRIAL VALIDATION)

Notes:
The committed flagship report does not contain explicit model-execution evidence. Routing and actual execution are separate concepts. Do not infer model execution from routing fields alone. The report is historical evidence; it is not re-executed on every page load.

---

## CLM-FLAG-02

Proposed:
"The flagship artifact remains a draft pending human authorization."

Classification:
HISTORICAL_VERIFIED

Evidence types:
HISTORICAL

Evidence source:
reports/flagship_workflow_latest.json:108 (approval_required=true)

Safe wording:
above proposed

Forbidden wording:
"Human-approved artifact."
"Finalized industrial decision."

Demo visibility:
HISTORICAL

Notes:
The generated DOCX remains DRAFT even after a terminal human decision. Human approve/reject is implemented in the current codebase (Phase 15). The frozen Phase-13 scorecard limitation "Human approve/reject is not implemented yet" is stale historical truth, not current project truth.

---

## CLM-EVAL-01

Proposed:
"Frozen Phase-13 evaluation snapshot: Industrial Golden 10/10, RAG Hit@1 2/6, Routing 10/10, Runtime Resilience 14/14, Security 12/12, Artifact/Sandbox 11/11, Flagship 14/14."

Classification:
HISTORICAL_VERIFIED

Evidence types:
HISTORICAL

Evidence source:
reports/competition_scorecard.json:1-888
reports/competition_scorecard.md:1-220

Safe wording:
above proposed (exact numbers)
"The frozen Phase-13 evaluation predates Phase-15 governance implementation."

Forbidden wording:
"100% overall."
"Weighted score: X%."
"All categories perfect." (RAG Hit@1 is not perfect)
"Current regression status: 304 passed." (this is a historical snapshot)

Demo visibility:
HISTORICAL (Judge Mode FROZEN COMPETITION EVIDENCE row)

Notes:
Do NOT compute an overall percentage. The scorecard explicitly records per-category results. This snapshot reflects the source commit state; later features such as Phase 15 governance supersede old implementation-state limitations.

---

## CLM-UI-01

Proposed:
"Judge Mode separates live runtime state, persistent governance, historical flagship evidence, and frozen evaluation evidence."

Classification:
LIVE_VERIFIED

Evidence types:
LIVE

Evidence source:
frontend/src/pages/JudgeMode.tsx:1-485 (rows: LIVE SOVEREIGNTY, FLAGSHIP INDUSTRIAL VALIDATION, FROZEN COMPETITION EVIDENCE)

Safe wording:
above proposed

Forbidden wording:
"All systems online."
"Every model available."
"Judge Mode runs live model inference."

Demo visibility:
LIVE

Notes:
Judge Mode is read-only. It surfaces honest status pills (OFFLINE/UNAVAILABLE) for missing models.

---

## CLM-UI-02

Proposed:
"The Network Monitor surfaces live external-call and blocked-connection counters from the backend probe."

Classification:
LIVE_VERIFIED

Evidence types:
LIVE

Evidence source:
frontend/src/pages/NetworkMonitor.tsx:131-144 (counters)
backend/app/api/network.py (SSE endpoint)

Safe wording:
above proposed

Forbidden wording:
"Zero external calls guaranteed forever."
"Air-gapped."

Demo visibility:
CONDITIONAL

Notes:
The current NetworkMonitor UI contains the overclaim "LOCAL / AIR-GAPPED" at NetworkMonitor.tsx:124. Do not record this UI prominently in the submission video in its current form. Judge Mode is the preferred sovereignty proof UI. If the wording is patched before recording, this can be upgraded to LIVE for video.

---

## CLM-DEP-01

Proposed:
"PostgreSQL is optional; the app runs without it unless explicitly configured."

Classification:
CONFIGURED_NOT_AVAILABLE

Evidence types:
PERSISTENT

Evidence source:
backend/app/config.py:19 (POSTGRES_URL default)
backend/app/api/system.py:171-188 (_postgres_component returns NOT_CONFIGURED if engine is None)

Safe wording:
above proposed

Forbidden wording:
"PostgreSQL-backed governance."
"Data stored in PostgreSQL."

Demo visibility:
LIVE (system status shows PostgreSQL state)

Notes:
Governance uses SQLite, not PostgreSQL. PostgreSQL is only for optional app features.

---

## CLM-DEP-02

Proposed:
"Docker Compose is an optional deployment path; bare-metal launcher scripts run the same services directly."

Classification:
PERSISTENT_VERIFIED

Evidence types:
PERSISTENT

Evidence source:
README.md:251-261 (docker-compose profiles)
scripts/serve_model.py:1-167 (bare-metal launcher)
scripts/sovereign.ps1 / scripts/sovereign.py (Phase 17A launcher)

Safe wording:
above proposed

Forbidden wording:
"Docker is required."
"Container-only deployment."

Demo visibility:
HISTORICAL

Notes:
The project supports both Docker Compose and bare-metal execution.

---

## CLM-DEP-03

Proposed:
"Piston is an optional sandbox boundary; the primary code sandbox runs in-process."

Classification:
PERSISTENT_VERIFIED

Evidence types:
PERSISTENT

Evidence source:
backend/agent/coder/sandbox.py (in-process PEP 451 import hook + socket guard)
backend/app/config.py:44 (PISTON_URL)

Safe wording:
above proposed

Forbidden wording:
"Piston is the only sandbox."
"All code runs in Piston."

Demo visibility:
HISTORICAL

Notes:
The in-process sandbox is the primary boundary. Piston is an optional adapter.

---

## CLM-CTX-01

Proposed:
"The context graph is implemented as LangGraph state edges: planner, identity, retrieve, analyze, calculate, synthesize, decide, generate, verify."

Classification:
TEST_VERIFIED

Evidence types:
TEST

Evidence source:
backend/agent/graph.py:22-78
backend/tests/test_agent.py (9 tests PASS)

Safe wording:
above proposed

Forbidden wording:
"Fully autonomous agent."
"Self-directing AI."

Demo visibility:
HISTORICAL

Notes:
The graph is deterministic and test-driven. It is not a free-form autonomous loop.

---

## CLM-EMB-01

Proposed:
"Embeddings are generated locally from disk with no network access."

Classification:
PERSISTENT_VERIFIED

Evidence types:
PERSISTENT

Evidence source:
backend/rag/config.py:10-12 (HF_HUB_OFFLINE=1, TRANSFORMERS_OFFLINE=1, SENTENCE_TRANSFORMERS_OFFLINE=1)
backend/rag/models/embeddings.py (LocalEmbedder enforces local_files_only=True)

Safe wording:
above proposed

Forbidden wording:
"Cloud embeddings."
"Embedding API calls."

Demo visibility:
LIVE (system status shows embedding component)

Notes:
The embedding model directory is models/embeddings/all-MiniLM-L6-v2.

---

## CLM-TOOL-01

Proposed:
"Calculations run in a sandboxed Python subprocess with network imports blocked and wall-clock timeout."

Classification:
TEST_VERIFIED

Evidence types:
TEST

Evidence source:
backend/agent/coder/sandbox.py:86-301 (import hook, socket guard, timeout)
backend/tests/test_coder_sandbox.py (29 tests PASS)

Safe wording:
above proposed

Forbidden wording:
"Arbitrary code execution."
"Unsafe calculations."

Demo visibility:
HISTORICAL

Notes:
Sandbox blocks socket, urllib, requests, subprocess, os.system, etc. Even RFC1918 is rejected inside the child.

---

## CLM-ART-01

Proposed:
"Artifacts are generated as DOCX files with embedded source references and a SHA256 integrity check."

Classification:
PERSISTENT_VERIFIED

Evidence types:
PERSISTENT

Evidence source:
backend/agent/tools/create_docx.py (DOCX generation)
backend/governance/approval.py:158-166 (artifact_sha256 verification on transition)
reports/flagship_workflow_latest.json:109-119 (artifact path + verification)

Safe wording:
above proposed

Forbidden wording:
"Tamper-proof artifact."
"Unchangeable document."

Demo visibility:
LIVE (Judge Mode shows artifact path + SHA256 + verification status)

Notes:
The artifact is a file on local disk. Its hash is recorded at creation and verified on approval transition, but the file itself can be altered outside the governance flow.

---

## CLM-IDENT-01

Proposed:
"Asset identity is verified against a canonical registry before retrieval proceeds."

Classification:
TEST_VERIFIED

Evidence types:
TEST

Evidence source:
backend/agent/nodes/identity.py (identity validation node)
backend/tests/test_asset_identity.py (18/18 cases PASS)
reports/competition_scorecard.json:207-360 (asset identity metrics)

Safe wording:
above proposed

Forbidden wording:
"Guaranteed correct asset."
"Identity cannot be spoofed."

Demo visibility:
LIVE (Judge Mode shows identity_status)

Notes:
Unknown assets are blocked (UNKNOWN_ASSET, RETRIEVAL_BLOCKED). Vision tags are used as additional evidence but do not override a missing canonical match.

---

## CLM-GPU-01

Proposed:
"CUDA-accelerated local coder and vision inference was historically validated on the RTX 4050."

Classification:
HISTORICAL_VERIFIED

Evidence types:
HISTORICAL

Evidence source:
reports/phase11_4_cuda_source_build.md (build details)
reports/phase11_7_gpu_memory_performance.md (throughput numbers)
reports/phase11_8_cpu_vs_cuda_benchmark.md (3.08x-3.47x speedups)

Safe wording:
above proposed

Forbidden wording:
"Real-time GPU inference guaranteed."
"Unlimited VRAM."
"Concurrent multi-model GPU inference supported."

Demo visibility:
HISTORICAL

Notes:
Do not make throughput a core PPT claim unless the exact benchmark artifact, model configuration, and workload are cited. GPU concurrency is conditional (one model at a time on 6 GB RTX 4050).

---

## CLM-GPU-02

Proposed:
"A cross-process file lock serializes GPU access between model servers."

Classification:
PERSISTENT_VERIFIED

Evidence types:
PERSISTENT

Evidence source:
scripts/gpu_admission.py:1-158 (GPUAdmissionLease, OS file lock via msvcrt.locking / fcntl.flock)
backend/tests/test_phase10_4.py (gpu_admission_busy_429, gpu_lock_recovers)

Safe wording:
above proposed

Forbidden wording:
"GPU concurrency supported."
"Multiple models on GPU simultaneously."

Demo visibility:
HISTORICAL

Notes:
The lock serializes access; it does not enable concurrent GPU inference.

---

## CLM-COMP-01

Proposed:
"Judge Mode aggregates live system state, persistent governance, historical flagship evidence, and frozen evaluation into a read-only dashboard."

Classification:
LIVE_VERIFIED

Evidence types:
LIVE

Evidence source:
backend/judge/service.py:68-89 (get_overview)
backend/app/api/judge.py:1-39 (read-only routes)
frontend/src/pages/JudgeMode.tsx:1-485

Safe wording:
above proposed

Forbidden wording:
"Judge Mode runs the models."
"Live model inference in Judge Mode."

Demo visibility:
LIVE

Notes:
Judge Mode is read-only. It never invokes a model.

---

## CLM-COMP-02

Proposed:
"The competition launcher manages backend, frontend, and model server lifecycles."

Classification:
TEST_VERIFIED

Evidence types:
TEST

Evidence source:
scripts/sovereign.py (launcher implementation)
backend/tests/test_phase17a_launcher_doctor.py (66+ tests)

Safe wording:
above proposed

Forbidden wording:
"Launcher guarantees cold start."
"Launcher is production-hardened."

Demo visibility:
LIVE (if launcher works in demo environment)

Notes:
Phase 17A1.2 found a port-8000 blocker on this host. Do not claim launcher reliability until the blocker is resolved.

---

## CLM-FILE-01

Proposed:
"The RAG index contains 393 chunks across Qdrant and BM25."

Classification:
PERSISTENT_VERIFIED

Evidence types:
PERSISTENT

Evidence source:
data/rag/qdrant_db/collection/sovereign_knowledge/storage.sqlite
data/rag/bm25/ (BM25 index)

Safe wording:
"393 chunks" (only if verified on the demo machine)

Forbidden wording:
"Infinite knowledge base."
"All industrial documents indexed."

Demo visibility:
HISTORICAL

Notes:
Verify the actual chunk count on the demo machine before quoting 393. If the index is missing or degraded, the retriever falls back to BM25-only.

---

## Classification audit

Unique claim IDs: 24
Duplicate classifications across buckets: 0
Primary classification per ID: exactly one
