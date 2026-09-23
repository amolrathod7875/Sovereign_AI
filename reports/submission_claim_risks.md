# Phase 17B — Submission Claim Risks

Likely judge questions and concise truthful answers.

---

## Q1: "Is the system fully air-gapped?"

Risk: HIGH if answered carelessly.

Truthful answer:
"Sovereign AI enforces an application-level network boundary. During agent runs, NetworkGuard blocks external socket connections and the Network Monitor surfaces blocked events. This prevents the AI workflow from contacting external services. We do not claim whole-machine air-gap certification because that depends on the deployment environment, firewall rules, and physical network configuration."

---

## Q2: "Why is the general model unavailable?"

Risk: MEDIUM.

Truthful answer:
"The general model endpoint and router path are fully implemented, but the GGUF weights have not been downloaded to this host yet. The router will route general tasks to the general model once the weights are present. No code change is required."

---

## Q3: "Is the receipt chain a blockchain?"

Risk: HIGH.

Truthful answer:
"No. The receipt chain is a local SHA256-linked list stored in SQLite. It is tamper-evident: if any entry is modified, the chain verification fails. It is not tamper-proof: an attacker with unrestricted SQLite write access could rewrite the entire history and recompute the chain from genesis. There is no external trust anchor and no digital signature."

---

## Q4: "Can an administrator rewrite the SQLite database?"

Risk: HIGH.

Truthful answer:
"Yes. SQLite is a file on local disk. A user with file-system write access can modify or delete records. The SHA256 hashes detect accidental corruption and casual tampering, but they do not prevent a deliberate rewrite by a privileged user. For stronger non-repudiation we would need an external trust anchor or digital signatures, which are not implemented."

---

## Q5: "Is reviewer identity authenticated?"

Risk: HIGH.

Truthful answer:
"Reviewer identity is recorded as a string (reviewer_id) with the approval record. The reviewer_identity_verified flag is a boolean that defaults to 0; there is no external authentication provider, no SSO, and no cryptographic proof of identity. We record who claimed to make the decision, but we do not cryptographically prove it."

---

## Q6: "What does Hit@1 = 2/6 mean?"

Risk: MEDIUM.

Truthful answer:
"Hit@1 measures whether the expected primary source document was ranked first for a given query. For 6 frozen evaluation queries, the primary source was at rank 1 in 2 cases. Hit@3 is 4/6 and Hit@5 is 6/6, meaning all expected documents are recovered within the top 5. Some queries rank secondary or context documents above the primary source at rank 1. We do not claim perfect retrieval."

---

## Q7: "Why is there no reranker?"

Risk: MEDIUM.

Truthful answer:
"The reranker module exists but uses a deterministic word-overlap heuristic, not a trained cross-encoder model. It is not a validated BGE reranker. We have not deployed an active reranker because the current hybrid retrieval already recovers all expected documents within top 5. Reranker tuning is on the roadmap."

---

## Q8: "Does routing prove model execution?"

Risk: HIGH.

Truthful answer:
"No. Routing is a capability-based classification step. It selects which local model(s) could serve a task, but it does not invoke any model. Actual model execution is recorded separately in the receipt payload when it occurs. Routing and execution are separate concepts."

---

## Q9: "What happens if the model server is offline?"

Risk: MEDIUM.

Truthful answer:
"The backend returns 503 Service Unavailable. The frontend displays an honest 'unavailable' panel. The agent workflow degrades gracefully: if the general model is unreachable, the router still selects it and the execution layer reports it unavailable rather than falling back to an external model. The NetworkGuard ensures no external model is contacted as a fallback."

---

## Q10: "How many models can run concurrently on the GPU?"

Risk: MEDIUM.

Truthful answer:
"Currently one model at a time. A cross-process file lock serializes GPU access. Concurrent peak VRAM was tested at 5,699-5,771 MiB on a 6 GB RTX 4050, which is near the safety limit. Production concurrency is not guaranteed under arbitrary workloads."

---

## Q11: "Is PostgreSQL required?"

Risk: LOW.

Truthful answer:
"No. Governance and approval data run on local SQLite. PostgreSQL is an optional dependency for certain API features. If POSTGRES_URL is not configured, the app starts and the system status reports PostgreSQL as NOT_CONFIGURED."

---

## Q12: "Is Docker required?"

Risk: LOW.

Truthful answer:
"No. Docker Compose is an optional deployment path. The same services can be launched directly on bare metal using the provided PowerShell and Python scripts."

---

## Q13: "What happens if the artifact file is deleted after approval?"

Risk: MEDIUM.

Truthful answer:
"The approval record stores the artifact SHA256 and path. If the file is missing, the receipt verification reports artifact_current_exists = False and the receipt is marked invalid. However, the SQLite record itself remains unless explicitly deleted."

---

## Q14: "Can the vision model read any file on the system?"

Risk: MEDIUM.

Truthful answer:
"No. The vision tool is restricted to an approved directory allow-list: PID_Dataset, data, uploads, demo-data, models, reports, backend, and the repo root. Any path outside this list is rejected before the model is called."

---

## Q15: "Why does the flagship JSON say 36 chunks but README says 393?"

Risk: MEDIUM.

Truthful answer:
"The flagship workflow retrieves a focused subset of 36 chunks for the specific R-1001 scenario. The full RAG index contains 393 chunks across all document types. The 36-chunk count is scenario-specific, not the total index size."

---

## Q16: "Is the coder sandbox secure against malicious code?"

Risk: HIGH.

Truthful answer:
"The sandbox blocks network imports, subprocess creation, and out-of-tree file writes. It is designed to contain accidental misuse and casual exploitation. It is not a formally verified isolation boundary. A determined attacker with knowledge of the import hook could potentially find evasion paths. We treat it as a strong boundary, not an absolute guarantee."

---

## Q17: "What is the actual model execution evidence for the flagship?"

Risk: HIGH.

Truthful answer:
"The committed flagship report does not contain explicit model execution evidence. The report documents retrieval, calculation, artifact generation, and validation checks. Routing and actual execution are separate concepts. The frozen Phase-13 scorecard records the general model runtime as UNAVAILABLE at the source commit. Later features such as Phase 15 governance do not change that historical record."

---

## Q18: "Does the system ever contact external AI APIs?"

Risk: HIGH.

Truthful answer:
"The NetworkGuard and NetworkMonitor are designed to prevent and detect external AI API calls. The frozen scorecard records 0 external API calls for the flagship run. However, we cannot certify that no external call was ever made across all possible code paths and third-party libraries. The guard covers the agent execution path and socket-level connections."

---

## Q19: "Why are there 2 failed regression tests?"

Risk: MEDIUM.

Truthful answer:
"The frozen Phase-13 regression snapshot records 304 passed, 2 failed, 14 skipped out of 320 tests. We have not investigated or fixed the 2 failures for this submission. They may be environment-specific or known issues. We can show the exact failures if asked."

---

## Q20: "What is the evidence level for each category?"

Risk: LOW.

Truthful answer:
- Industrial Golden: INTEGRATION (live agent run against committed evidence)
- RAG Retrieval: INTEGRATION (real HybridRetriever queries, no mocks)
- Asset Identity: UNIT (deterministic resolver tests)
- Routing: UNIT (classification accuracy tests)
- Runtime Resilience: INTEGRATION (subprocess-driven failure simulations)
- Sovereignty Security: UNIT (guard and sandbox tests)
- Artifact/Sandbox: LIVE (committed JSON + live local artifact checks)
- Flagship: LIVE (read-only from committed JSON)

---

## Q21: "Is human approval actually implemented?"

Risk: HIGH if answered incorrectly.

Truthful answer:
"Yes. The current codebase implements persistent PENDING approval records, PENDING -> APPROVED and PENDING -> REJECTED transitions, artifact hash verification before terminal transition, receipt generation, and chain append. The frozen Phase-13 scorecard limitation 'Human approve/reject is not implemented yet' reflects the historical source commit before Phase 15. The generated DOCX remains DRAFT even after a terminal human decision. This is intentional."

---

## RISK SUMMARY

Highest-risk claims to avoid:

1. "Fully air-gapped" / "whole-machine certified" — application-level only.
2. "Tamper-proof" / "blockchain" — tamper-evident only, no external anchor.
3. "Reviewer authenticated" — reviewer_id is recorded, not verified.
4. "General model available" — weights absent, server not running.
5. "Routing proves execution" — routing is classification, not execution.
6. "Reranker online" — placeholder implementation, not a real model.
7. "All models running" — only embedding/reranker registry entries are "online"; servers are not running.
8. "Perfect retrieval" — Hit@1 is 2/6.
9. "Sandbox is unhackable" — strong boundary, not formally verified.
10. "PostgreSQL required" — optional; SQLite is authoritative.
11. "Human approval not implemented" — FALSE; Phase 15 implemented it. The frozen scorecard limitation is stale.
12. "Flagship executed the general model" — FALSE; committed flagship report does not contain explicit model-execution evidence.
