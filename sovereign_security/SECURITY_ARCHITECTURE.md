# Security Architecture

The security subsystem is designed as an isolated, standalone, and strictly air-gapped protection layer. 

## High-Level Request Flow

```text
User
  ↓
Application (FastAPI)
  ↓
[Future Integration Point: FastAPI Middleware]
  ↓
Security Gateway (`security_gateway.py`)
  ↓
Specific Security Guard (e.g. `security.input`, `security.prompt`)
  ↓
Decision (ALLOW/DENY/ERROR)
  ↓
Application Logic
```

## Security Domains

1. **Input**: Validates file paths, MIME types, and prevents directory traversal.
2. **Prompt**: Detects prompt injection and system prompt extraction.
3. **Output**: Validates JSON schemas, prevents hallucinated engineering values.
4. **RAG**: Evaluates document trust and prevents vector poisoning.
5. **Agent**: Enforces capability policies and tool authorization.
6. **Network**: Validates endpoints against explicit allowlists (complements OS-level socket blocking).
7. **Secrets**: Detects and redact secrets (API keys, passwords, JWTs).
8. **Provenance**: Tracks engineering evidence and claims.
9. **Audit**: Logs standardized security events.

## Current vs Future State

**CURRENT**: The security subsystem is **NOT CONNECTED**. The gateway and all modules are implemented as a standalone library ready for integration.
**FUTURE INTEGRATION**: Developers will wire `SecurityGateway` into FastAPI middlewares, LangGraph nodes, and RAG pipelines as documented in the `INTEGRATION_MAP.md`.
