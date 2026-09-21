# Integration Contracts

This document specifies exactly how future contributors should connect the security subsystem into the application.

## 1. Input/Output Security Boundary

**A. WHERE**
`backend/app/main.py` (FastAPI initialization and middleware)

**B. WHEN**
Before any API route executes (Input) and after any API route returns (Output).

**C. WHAT**
`security_gateway.validate_input()` and `security_gateway.validate_output()`

**D. INPUT**
- Input: `file_path` or `mime_type` of incoming requests.
- Output: `output_data` from API routes.

**E. OUTPUT**
`SecurityDecision` object.

**F. BLOCKING BEHAVIOR**
If `decision.allowed == False`, the middleware must immediately return an HTTP 403 Forbidden or 400 Bad Request, stopping further processing.

**G. AUDIT**
Automatically handled by `SecurityGateway` (records `EVENT_INPUT_ACCEPTED`/`DENIED`).

**H. FAILURE MODE**
Fail-closed. If the security module crashes, the middleware should block the request.

**I. EXAMPLE**
See `security/examples/fastapi_middleware_example.py`

---

## 2. Agent Execution and Prompt Inspection

**A. WHERE**
`backend/agent/run.py` (Inside `run_agent_task`)

**B. WHEN**
Before `GRAPH.invoke(initial)` is executed.

**C. WHAT**
`security_gateway.inspect_prompt()`

**D. INPUT**
The combined `task` string and any context.

**E. OUTPUT**
`SecurityDecision` object.

**F. BLOCKING BEHAVIOR**
If `decision.allowed == False`, the agent execution is aborted immediately.

**G. AUDIT**
Automatically handled by `SecurityGateway` (`EVENT_PROMPT_ACCEPTED`/`EVENT_PROMPT_INJECTION_DETECTED`).

**H. FAILURE MODE**
Fail-closed.

**I. EXAMPLE**
```python
from security.security_gateway import SecurityGateway

decision = SecurityGateway.inspect_prompt(task)
if not decision.allowed:
    return {"error": "Security blocked prompt: " + decision.reason}
```

---

## 3. Tool Authorization

**A. WHERE**
`backend/agent/graph.py` (or inside individual tool execution wrappers).

**B. WHEN**
Before a LangChain/LangGraph tool executes its main logic.

**C. WHAT**
`security_gateway.authorize_tool()`

**D. INPUT**
`tool_name` (string) and any `requested_capabilities` (list).

**E. OUTPUT**
`SecurityDecision` object.

**F. BLOCKING BEHAVIOR**
If `decision.allowed == False`, the tool must not execute and should return an error observation to the agent.

**G. AUDIT**
Automatically handled by `SecurityGateway`.

**H. FAILURE MODE**
Fail-closed.

---

## 4. RAG Validation

**A. WHERE**
`backend/app/api/rag.py`

**B. WHEN**
Immediately after retrieving documents from Qdrant, before returning them to the LLM.

**C. WHAT**
`security_gateway.validate_rag()`

**D. INPUT**
List of retrieved document dictionaries.

**E. OUTPUT**
`SecurityDecision` object.

**F. BLOCKING BEHAVIOR**
If `decision.allowed == False`, the RAG pipeline should either drop the poisoned documents or abort the retrieval.

**G. AUDIT**
Automatically handled by `SecurityGateway`.

**H. FAILURE MODE**
Fail-closed.

---

## 5. Network Guard

**A. WHERE**
`backend/agent/run.py` (Currently uses `agent.security.netguard`)

**B. WHEN**
During any agent or tool execution that may attempt network calls.

**C. WHAT**
`security_gateway.validate_network()`

**D. INPUT**
Target URL or IP address.

**E. OUTPUT**
`SecurityDecision`

**F. EXISTING MECHANISM NOTE**
The existing `agent.security.netguard` provides an OS-level socket block (`no_network()` context manager). The new `security_gateway.validate_network()` is intended to provide *application-level* URL whitelisting (e.g. allowing specific local endpoints) and structured auditing. **DO NOT replace the existing `netguard`**; instead, use `validate_network()` for explicit endpoint approvals *before* attempting connections that the legacy netguard might otherwise block or allow.
