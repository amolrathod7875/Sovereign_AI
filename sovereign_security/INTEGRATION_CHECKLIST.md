# Integration Checklist

Follow these steps to integrate the security subsystem into the production application.

- [ ] Read `SECURITY_ARCHITECTURE.md`
- [ ] Read `INTEGRATION_CONTRACTS.md`
- [ ] Read `INTEGRATION_MAP.md`
- [ ] Connect input validation (e.g., via FastAPI middleware in `backend/app/main.py`)
- [ ] Connect prompt inspection (in `backend/agent/run.py`)
- [ ] Connect agent authorization (in `backend/agent/graph.py`)
- [ ] Connect RAG validation (in `backend/app/api/rag.py`)
- [ ] Connect output validation (in `backend/app/api/models.py` and `vision.py`)
- [ ] Connect network policy (alongside existing netguard)
- [ ] Connect audit logging (verify `security/reports/audit.log` populates during tests)
- [ ] Add production-path tests (e.g., end-to-end tests ensuring API requests are blocked)
- [ ] Verify fail-closed behavior (e.g., simulate a crash in `security_gateway` and ensure request drops)
- [ ] Verify bypass paths (ensure direct internal calls still hit security boundaries if exposed)
- [ ] Run security tests (`pytest security/tests/`)
- [ ] Run application tests (`pytest backend/tests/`)
- [ ] Perform final integration audit
