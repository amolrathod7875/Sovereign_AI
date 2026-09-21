# Integration Map

This table maps existing application locations to their future security modules.

| Application Location | Security Module | Integration Purpose | Trigger | Expected Decision | Current Status |
|---|---|---|---|---|---|
| `backend/app/main.py` | `security.input` | input validation | request/file input | ALLOW/DENY | NOT CONNECTED |
| `backend/agent/run.py` | `security.prompt` | prompt inspection | before model execution | ALLOW/DENY | NOT CONNECTED |
| `backend/agent/run.py` | `security.agent` | agent authorization | agent/tool action | ALLOW/DENY | NOT CONNECTED |
| `backend/app/api/rag.py` | `security.rag` | retrieval validation | retrieved chunks | ALLOW/DENY | NOT CONNECTED |
| `backend/app/api/models.py` | `security.output` | LLM output validation | model response | ALLOW/DENY | NOT CONNECTED |
| `backend/app/api/vision.py` | `security.output` | VLM output validation | vision result | ALLOW/DENY | NOT CONNECTED |
| `backend/agent/graph.py` | `security.agent` | tool authorization | tool execution | ALLOW/DENY | NOT CONNECTED |
| FUNCTION TO BE CONFIRMED DURING INTEGRATION | `security.secrets` | secret scanning | outgoing data | ALLOW/DENY | NOT CONNECTED |
| FUNCTION TO BE CONFIRMED DURING INTEGRATION | `security.network` | explicit endpoint auth | URL fetch | ALLOW/DENY | NOT CONNECTED |
