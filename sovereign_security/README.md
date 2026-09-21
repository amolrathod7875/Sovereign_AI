# Sovereign AI Security Subsystem

## WHAT THIS IS
This is the fully local, air-gapped, OWASP-informed security and guardrail subsystem for the Sovereign AI project. It provides strict enforcement capabilities for Input, Output, Prompt, RAG, Network, and Agent boundaries.

## WHAT IT PROTECTS
When fully integrated, it protects against:
- Prompt Injection & Jailbreaks
- Unauthorized File Access & Directory Traversal
- Malicious File Uploads (MIME spoofing, malformed inputs)
- Hallucinated Engineering Claims
- Vector Database Poisoning (RAG)
- Excessive Agent Agency (Tool execution)
- Secret Leakage (Passwords, API Keys, JWTs)
- Unauthorized Network Egress

## WHAT IT DOES NOT PROTECT YET
The subsystem is currently an isolated library. It does not magically protect the application just by existing.

## CURRENT STATUS

> **IMPORTANT:**
> The security subsystem is currently **NOT connected** to the production application.
> It is integration-ready and must be connected at the documented application choke points before it can enforce protection on production execution paths.

See `INTEGRATION_CHECKLIST.md` and `INTEGRATION_CONTRACTS.md` for instructions on how to connect this subsystem to the backend.
