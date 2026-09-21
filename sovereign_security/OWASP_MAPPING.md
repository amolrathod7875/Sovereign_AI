# OWASP LLM Top 10 Mapping

This document maps the localized threats in Sovereign AI to the OWASP LLM Top 10 framework.

| OWASP LLM Top 10 Risk | Sovereign AI Mapping | Mitigating Subsystem Module |
|---|---|---|
| **LLM01: Prompt Injection** | Instructions hidden in P&ID diagrams, OCR, or uploaded PDFs. | `security/prompt/injection_detector.py`, `security/prompt/prompt_guard.py` |
| **LLM02: Insecure Output Handling** | Malformed JSON or outputs executed blindly by sandbox. | `security/output/schema_guard.py`, `security/output/output_guard.py` |
| **LLM03: Training Data Poisoning** | Poisoning of local embeddings or RAG ingestion documents. | `security/rag/poisoning_detector.py`, `security/rag/rag_guard.py` |
| **LLM04: Model Denial of Service** | Extremely large images, unlimited PDF pages, heavy archive uploads. | `security/input/resource_limits.py`, `security/input/file_guard.py` |
| **LLM05: Supply Chain Vulnerabilities** | Compromised models, Python packages, plugins. | `security/scanners/dependency_scanner.py` |
| **LLM06: Sensitive Information Disclosure** | Leaking database connection strings, passwords in generated reports. | `security/secrets/secret_detector.py`, `security/secrets/redactor.py` |
| **LLM07: Insecure Plugin Design** | Sandbox tool executing shell commands directly without bounds. | `security/agent/tool_policy.py`, `security/agent/capability_policy.py` |
| **LLM08: Excessive Agency** | Agent autonomously attempting filesystem modifications or network requests. | `security/agent/agency_guard.py`, `security/network/airgap_guard.py` |
| **LLM09: Overreliance** | Generating unsupported engineering claims based on hallucinations. | `security/output/claim_guard.py`, `security/provenance/evidence.py` |
| **LLM10: Model Theft** | (Low Risk) Local environment, models are air-gapped and not exposed over public APIs. | `security/network/airgap_guard.py` (prevent exfiltration) |
