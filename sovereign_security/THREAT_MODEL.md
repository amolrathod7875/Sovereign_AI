# Sovereign AI - Threat Model

This document identifies potential security threats to the Sovereign AI local environment and outlines mitigation strategies, conforming to OWASP LLM guidelines.

## 1. Prompt Injection
- **Threat**: Malicious instructions embedded in uploaded files (PDFs, images), OCR text, RAG documents, or tool outputs attempting to hijack the agent.
- **Surface**: `uploads/` directory, RAG chunks, VLM extracted text.
- **Mitigation**: Implement `security/prompt/injection_detector.py` to identify imperative commands in untrusted input. Enforce clear instruction boundaries between system prompts and user data.

## 2. Sensitive Information Disclosure
- **Threat**: Leakage of engineering secrets (e.g., database credentials, system prompts) into reports or unauthorized outputs.
- **Surface**: Output generation, sandbox scripts, `config.py` parsing.
- **Mitigation**: `security/secrets/secret_detector.py` scans final outputs and logs, replacing matched secrets with `REDACTED`. `security/output/secret_guard.py` blocks outputs containing secrets.

## 3. Supply Chain Attacks
- **Threat**: Use of compromised Python dependencies, plugins, or downloaded model files.
- **Surface**: `requirements.txt`, model downloads.
- **Mitigation**: Scanner in `security/scanners/dependency_scanner.py` checks known dependency hashes/manifests. Strict path controls ensure models are loaded only from approved local paths.

## 4. Data/Model Poisoning & RAG Security
- **Threat**: Poisoned RAG data or manipulated metadata influencing the agent to make false engineering claims.
- **Surface**: `data/rag/qdrant_db`, `data/rag/bm25`, uploaded files.
- **Mitigation**: Implement document trust levels in `security/rag/document_trust.py`. Retrieval guards to detect suspicious retrieval patterns and metadata manipulation. 

## 5. Improper Output Handling & Hallucination
- **Threat**: Malformed JSON, unsafe outputs, or unsupported engineering claims (e.g., claiming a pressure is safe when evidence doesn't support it).
- **Surface**: Model text generation, agent reasoning.
- **Mitigation**: Strict schema validation (`security/output/schema_guard.py`). `claim_guard.py` cross-checks engineering claims against provenance and evidence status (must be `verified`, not `uncertain`).

## 6. Excessive Agency
- **Threat**: The agent executing unauthorized commands, deleting critical files, or escalating privileges.
- **Surface**: Sandbox environment (`Piston`), Subprocess modules.
- **Mitigation**: Default `DENY` capability policy (`security/agent/capability_policy.py`). Separate reasoning from action execution. Strict access controls over tool usage.

## 7. Path Traversal & Network Attacks
- **Threat**: Agent accessing arbitrary files (`../.env`) or communicating with external networks (SSRF, metadata servers).
- **Surface**: File reading tools, HTTP client requests.
- **Mitigation**: `path_guard.py` canonically resolves paths and blocks traversal. `network_policy.py` restricts communication strictly to `localhost`/`127.0.0.1` and explicit allowlists. 
