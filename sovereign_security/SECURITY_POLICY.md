# Sovereign AI - Security Policy

## Core Principles

1. **Air-Gapped & Local First**: The system must assume zero external internet connectivity. No telemetry, no external LLMs, no remote security services.
2. **Default Deny**: All capabilities, network endpoints, file accesses, and tool usages are implicitly denied unless explicitly permitted.
3. **Fail-Closed**: If a security check encounters an error, throws an exception, or is uncertain, it must fail closed and block the action.
4. **Untrusted Input**: All inputs (images, PDFs, RAG text, OCR results, tool outputs) are strictly untrusted and must never be evaluated as system instructions.
5. **No Autonomous Engineering Approval**: Model findings for engineering facts (pressures, ratings, specifications) must be explicitly backed by traceable provenance evidence. `uncertain`, `conflict`, or `not_visible` claims are rejected.

## Enforcement Architecture

The `security/` directory acts as an independent, modular subsystem.
Existing Sovereign AI application code (`backend/`, `frontend/`) is not modified by this subsystem's installation. Instead, security enforcement relies on future integration of these modular guards.

### Modules:
- **Input Guard**: Validates file types, sizes, paths.
- **Prompt Guard**: Detects injection and bounds instructions.
- **Output Guard**: Strict JSON and claim validation.
- **RAG Guard**: Provenance and trust enforcement.
- **Agent Guard**: Capability and tool restrictions.
- **Network Guard**: Blocks external IP access.
- **Audit Logger**: Local logs of security decisions.
