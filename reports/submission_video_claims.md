# Phase 17B — Submission Video Claims

Approved short sentences safe for narration or on-screen text.
Do not paraphrase beyond these sentences without re-auditing.

---

## APPROVED

- "Sovereign AI is designed for on-premises industrial AI workflows."
- "Application-level network controls restrict agent execution to trusted local destinations."
- "Hybrid local retrieval combines dense Qdrant search with BM25 lexical search."
- "Asset identity is verified against a canonical registry before retrieval proceeds."
- "Human authorization is persisted separately from the AI recommendation."
- "Terminal decisions produce a cryptographically hashed Sovereignty Receipt."
- "Receipts are linked into a tamper-evident local history."
- "Judge Mode separates live runtime state, persistent governance, historical flagship evidence, and frozen evaluation evidence."
- "The agent runs inside a LangGraph workflow: identity, retrieve, analyze, calculate, synthesize, decide, verify."
- "Tool use is restricted to approved local operations: knowledge-base search, Python sandbox, DOCX generation, and local vision."
- "The coder sandbox blocks network imports, subprocess, and out-of-tree writes."
- "Artifact integrity is verified with SHA256 before and after approval transitions."
- "Reviewer identity is recorded with every approval decision."
- "Embeddings are generated locally from disk with no network access."
- "A cross-process file lock serializes GPU access between model servers."
- "The flagship workflow validates one end-to-end industrial scenario with 14 of 14 checks passed."
- "The flagship artifact remains a draft pending human authorization."
- "PostgreSQL is optional; governance runs on local SQLite."
- "Docker Compose is an optional deployment path; bare-metal scripts run the same services directly."
- "CUDA-accelerated local coder and vision inference was historically validated on the RTX 4050."

---

## HISTORICAL EVIDENCE ONLY (do not present as live)

- "Frozen Phase-13 evaluation snapshot: Industrial Golden 10 of 10, RAG Hit@1 2 of 6, Routing 10 of 10, Runtime Resilience 14 of 14, Security 12 of 12, Artifact/Sandbox 11 of 11, Flagship 14 of 14."
- "Frozen Phase-13 regression snapshot: 304 passed, 2 failed, 14 skipped."
- "Flagship workflow run_07d24d69e01e passed 14 of 14 validation checks."
- "Industrial Golden tests: 10 of 10 passed."
- "Asset identity tests: 18 of 18 passed."
- "Runtime resilience tests: 14 of 14 passed."
- "Security control tests: 12 of 12 passed."
- "Artifact/sandbox tests: 11 of 11 passed."

---

## NOT APPROVED

- "The system is fully air-gapped." (Replacement: "Application-level network controls restrict agent execution to trusted local destinations.")
- "Tamper-proof blockchain audit log." (Replacement: "tamper-evident receipt chain")
- "Immutable ledger." (Replacement: "tamper-evident history")
- "All models are online and available." (Replacement: "General model weights are not yet provisioned; coder and vision weights are present but servers are not currently running.")
- "General AI executes all reasoning." (Replacement: "The router classifies tasks and selects local models by capability.")
- "Routing proves model execution." (Replacement: "Routing is a classification step; actual model execution is recorded separately when it occurs.")
- "Reviewer identity is cryptographically authenticated." (Replacement: "Reviewer identity is recorded with the approval decision.")
- "GPU concurrency is supported." (Replacement: "GPU inference is serialized across model servers.")
- "The reranker improves retrieval quality." (Replacement: "No validated active reranker is currently deployed.")
- "PostgreSQL stores governance data." (Replacement: "Governance runs on local SQLite; PostgreSQL is optional.")
- "Piston is the only sandbox." (Replacement: "The primary code sandbox runs in-process; Piston is an optional adapter.")
- "Perfect retrieval accuracy." (Replacement: "Hit@1 2 of 6, Hit@5 6 of 6.")
- "The artifact is finalized and approved." (Replacement: "The artifact remains a draft pending human authorization.")
- "Judge Mode runs live model inference." (Replacement: "Judge Mode is read-only evidence aggregation.")
- "Docker is required for deployment." (Replacement: "Docker Compose is an optional deployment path.")
- "fully air-gapped machine"
- "certified air gap"
- "tamper-proof"
- "blockchain"
- "immutable against administrator"
- "non-repudiation"
- "digitally signed"
- "authenticated reviewer"
- "active reranker"
- "general model online"
- "all models running"
- "routing proves execution"
- "perfect RAG"
- "100% retrieval accuracy"

---

## DEMO VISIBILITY KEY

- LIVE: may be demonstrated on a running system
- HISTORICAL: show as committed evidence / screenshots
- DO NOT DEMO: never show or claim

---

## Network Monitor video caveat

The current NetworkMonitor UI contains the overclaim "LOCAL / AIR-GAPPED" at frontend/src/pages/NetworkMonitor.tsx:124.
Do not record this UI prominently in the submission video in its current form.
Judge Mode is the preferred sovereignty proof UI for the video.
