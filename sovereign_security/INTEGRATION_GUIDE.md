# Sovereign AI - Integration Guide

> **Note:** The `security/` subsystem is built as a standalone library. No existing files outside of `security/` have been modified. This guide details how future developers should integrate these security modules into the primary application.

## 1. Network / Airgap Enforcement
To enforce network isolation, wrap the application entry point or the agent execution runner with `AirgapGuard` or `NetworkPolicy`.
**Location to update**: `backend/agent/run.py`
```python
from security.network.airgap_guard import AirgapGuard

def run_agent_task(...):
    guard = AirgapGuard(allow_localhost=True)
    with guard.enforce():
        # run agent
```

## 2. Input Guards & Path Validation
To prevent path traversal and ensure safe file processing, wrap file ingestion logic.
**Location to update**: `backend/app/api/documents.py` or file upload endpoints.
```python
from security.input.path_guard import PathGuard
from security.input.file_guard import FileGuard

def upload_document(file_path):
    PathGuard.validate(file_path)
    FileGuard.check_limits(file_path)
    # proceed with upload
```

## 3. RAG & Prompt Injection Guards
To secure the RAG pipeline from poisoned data and prompt injection.
**Location to update**: `backend/rag/retrieval/` or LLM request construction.
```python
from security.rag.rag_guard import RAGGuard
from security.prompt.injection_detector import InjectionDetector

def retrieve_and_format(query):
    chunks = rag.retrieve(query)
    RAGGuard.validate_chunks(chunks)
    for chunk in chunks:
        if InjectionDetector.detect(chunk.text).decision == "BLOCK":
            # handle injection
```

## 4. Output & Secret Guards
To prevent sensitive data leaks and ensure strict JSON compliance.
**Location to update**: LLM response parsing logic.
```python
from security.output.output_guard import OutputGuard
from security.secrets.secret_detector import SecretDetector

def parse_llm_response(text):
    safe_text = SecretDetector.redact(text)
    OutputGuard.validate_schema(safe_text, expected_schema)
```

## 5. Agent Capability Policy
To lock down tool execution and agency.
**Location to update**: `backend/agent/tools/`
```python
from security.agent.capability_policy import CapabilityPolicy

def execute_tool(tool_name, args):
    policy = CapabilityPolicy()
    if not policy.is_allowed(tool_name):
        raise PermissionError("Tool denied")
```
