# Phase 12.1 Runtime Resilience Implementation Plan

## Summary
This document outlines the implementation plan for Phase 12.1 - Model Runtime Resilience hardening. The goal is to improve error handling and recovery capabilities for both coder and vision model endpoints while maintaining strict sovereignty requirements.

## Phase 12.1 Status: PLAN

This document outlines the comprehensive implementation approach for Phase 12.1 - Model Runtime Resilience hardening. The implementation will enhance error handling and recovery for coder and vision model endpoints while preserving strict sovereignty requirements.

## 1. Initial Findings

### 1.1 Current Coder Error Handling (`backend/app/api/coder.py`)
- **Connection Errors**: Currently caught by generic Exception handler → HTTP 500
- **Transport Failures**: Same as above → HTTP 500
- **Timeouts**: Proper handling via `asyncio.TimeoutError` → HTTP 504
- **Malformed Responses**: No specific handling → Could cause 500
- **Missing Completion Fields**: No specific handling → Could cause 500
- **Recovery**: No persistent state tracking → Model availability not cached
- **Application Deadlines**: Handled via `CODER_DEADLINE` → HTTP 504

### 1.2 Current Vision Error Handling (`backend/app/api/vision.py`)
- **Connection Errors**: Specific `ConnectionError` handling → HTTP 503 (with detailed message)
- **Transport Failures**: Same as above → HTTP 503
- **Timeouts**: Caught by generic Exception → HTTP 500 (potential 504)
- **Malformed JSON**: Caught by generic Exception → HTTP 500
- **Missing Fields**: Could cause 500 traceback
- **Recovery**: No persistent state tracking
- **Application Deadlines**: No specific handling in system.py

### 1.3 Current ModelClient Error Handling (`backend/app/models/client.py`)
- **Connection/Transport Errors**: Generic exception → re-raised
- **Timeouts**: httpx timeout → exception → re-raised
- **Malformed JSON**: json.loads exception → re-raised
- **Missing Fields**: KeyError → re-raised
- **No Recovery State**: ModelClient doesn't track availability

### 1.4 Key Gaps Identified
1. Coder endpoint lacks specific ConnectionError/OSError handling → always 500
2. Vision timeout handling could be more specific (504 vs 500)
3. Malformed JSON could cause 500 instead of controlled error
4. Missing fields in completion payload not handled
5. No persistent model availability tracking between requests
6. System status health probes could block

## 2. Implementation Plan

### 2.1 Enhanced Coder Error Handling (`backend/app/api/coder.py`)
- **File**: `backend/app/api/coder.py`
- **Changes**:
  - Add specific handling for `ConnectError` and `OSError` → HTTP 503
  - Improve error messages to identify which service failed
  - Add more specific exception categories for better control

### 2.2 Enhanced Vision Error Handling (`backend/app/api/vision.py`)
- **File**: `backend/app/api/vision.py`
- **Changes**:
  - Improve ConnectionError handling with more specific error messages
  - Add timeout exception handling → HTTP 504
  - Better structured error responses with safe diagnostic info
  - Enhanced error categorization

### 2.3 Enhanced ModelClient (`backend/app/models/client.py`)
- **File**: `backend/app/models/client.py`
- **Changes**:
  - Add more specific exception handling for malformed JSON
  - Better error messages for different failure types
  - Improved timeout handling with specific status codes

### 2.4 Comprehensive Tests (`backend/tests/test_phase12_1_runtime_resilience.py`)
- **File**: `backend/tests/test_phase12_1_runtime_resilience.py`
- **Purpose**: Complete test suite for Phase 12.1 resilience requirements
- **Coverage**:
  - 14 resilience tests (6 for coder, 6 for vision, 2 for system)
  - Mock-based deterministic failure tests
  - No requirement for real model startup

## 3. Detailed Implementation Steps

### STEP 1: Modify `backend/app/api/coder.py`
```python
# Add these imports at the top
from httpx import ConnectError

# Modify the exception handling in run_coder function
except ConnectionError as e:
    # For coder, ConnectionError would come from the ModelClient
    raise HTTPException(
        status_code=503,
        detail=(
            f"Local coder model (Qwen2.5-Coder) is not reachable on "
            f"{CODER_ENDPOINT}. Start it with "
            f"'python scripts/serve_model.py --model-id qwen-coder --port 8002'. "
            f"Original error: {e}"
        ),
    )
except OSError as e:  # Covers transport failures like "Network is unreachable"
    raise HTTPException(
        status_code=503,
        detail=(
            f"Local coder model (Qwen2.5-Coder) is not reachable on "
            f"{CODER_ENDPOINT}. Start it with "
            f"'python scripts/serve_model.py --model-id qwen-coder --port 8002'. "
            f"Transport error: {e}"
        ),
    )
```

### STEP 2: Modify `backend/app/api/vision.py`
```python
# Add timeout handling for vision
try:
    payload = await asyncio.to_thread(
        _analyze_guarded, req.file_path, req.prompt, req.analysis_type
    )
except TimeoutError as e:
    raise HTTPException(
        status_code=504,
        detail=(
            f"Local vision model (Qwen2.5-VL) analysis timed out on "
            f"{VISION_ENDPOINT}. The model may be overloaded or the image large. "
            f"Try a simpler task or check the model server."
        ),
    )
except ValueError as e:  # For malformed JSON
    raise HTTPException(
        status_code=502,
        detail=(
            f"Local vision model (Qwen2.5-VL) returned an invalid response from "
            f"{VISION_ENDPOINT}. The model may be corrupted or misbehaving."
        ),
    )
```

### STEP 3: Modify `backend/app/models/client.py`
```python
# Enhance the generate method
try:
    response = await self.client.post(
        f"{self.endpoint}/chat/completions",
        json={
            "model": self.model_id,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    try:
        result = response.json()
    except ValueError as e:  # JSON decode error
        raise ValueError(f"Model {self.model_id} returned invalid JSON") from e
    
    # Check for missing required fields
    if not result.get("choices") or not result["choices"][0].get("message"):
        raise ValueError(f"Model {self.model_id} response missing completion fields")
    
    return result["choices"][0]["message"]["content"]
except httpx.ConnectError as e:
    raise ConnectError(f"Cannot connect to model {self.model_id} at {self.endpoint}") from e
except httpx.ReadTimeout as e:
    raise TimeoutError(f"Timeout connecting to model {self.model_id}") from e
```

### STEP 4: Create Comprehensive Tests
The test file should include:
- Mock-based tests for all failure scenarios
- No requirement for real model servers
- Deterministic testing of error responses
- Validation of recovery behavior

## 4. Failure Handling Matrix

| Failure Type | Coder | Vision | Expected HTTP Status | Implementation |
|--------------|-------|--------|-------------------|----------------|
| Server Unavailable | ✅ 503 | ✅ 503 | 503 | Specific exception handling |
| Transport Failure | ✅ 503 | ✅ 503 | 503 | OSError/ConnectError handling |
| Timeout | ✅ 504 | ✅ 504 | 504 | TimeoutError handling |
| Malformed JSON | ✅ 502/500 | ✅ 502/500 | 502/500 | JSON decode error handling |
| Missing Fields | ✅ Controlled error | ✅ Controlled error | Controlled | Response validation |
| Upstream HTTP Error | ✅ 502/503 | ✅ 502/503 | Appropriate | HTTP status check |
| Recovery | ✅ No persistent state | ✅ No persistent state | Success | State cleared on success |

## 5. Testing Strategy

### 5.1 Coder Tests (6/6)
1. Server unavailable → 503
2. Transport failure → 503
3. Timeout → 504
4. Malformed JSON → 502/500
5. Missing completion payload → controlled error
6. Recovery after previous failure

### 5.2 Vision Tests (6/6)
7. Server unavailable → 503
8. Transport failure → 503
9. Timeout → 504
10. Malformed response → 502/500
11. Missing completion payload → controlled error
12. Recovery after previous failure

### 5.3 System Tests (2/2)
13. Health probe doesn't block indefinitely
14. System status doesn't crash on model failures

## 6. Sovereignty Compliance

### 6.1 Requirements Met
- ✅ No external calls
- ✅ No downloads
- ✅ No cloud dependencies
- ✅ NetworkGuard behavior preserved
- ✅ Only loopback/private endpoints allowed
- ✅ Network sovereignty maintained

### 6.2 Error Response Safety
- ✅ No stack traces exposed
- ✅ No secrets in error messages
- ✅ No environment variables leaked
- ✅ Only safe diagnostic information

## 7. Known Limitations

### 7.1 Technical Limitations
1. **No Persistent Model State**: Model availability is not cached between requests
2. **Mock-Dependent Tests**: Tests rely on mocking, not real model failures
3. **Timeout Granularity**: Some timeouts still return 500 instead of 504

### 7.2 Scope Limitations
1. **No Real Server Testing**: Cannot test with actual model servers
2. **No Load Testing**: No tests for high-concurrency failure scenarios
3. **No Network Partition Testing**: Cannot simulate real network partitions

## 8. Implementation Checklist

### ✅ Files to Modify
1. [ ] `backend/app/api/coder.py` - Enhanced error handling
2. [ ] `backend/app/api/vision.py` - Improved error handling
3. [ ] `backend/app/models/client.py` - Better error handling

### ✅ Files to Create
1. [ ] `backend/tests/test_phase12_1_runtime_resilience.py` - Comprehensive tests

### ✅ Files to NOT Modify (Unrelated)
1. [ ] `.gitignore`
2. [ ] `start.txt`
3. [ ] `backend/package-lock.json`
4. [ ] `frontend/dist`

### ✅ Tests to Run
1. [ ] Targeted resilience tests (14/14)
2. [ ] Existing coder tests (30/30)
3. [ ] Existing vision tests (20/20)
4. [ ] Existing phase10.4 tests (11/11)
5. [ ] Existing netguard tests (28/28)

## 9. Success Criteria

### 9.1 Functional Requirements
- All 14 resilience tests pass
- No regressions in existing functionality
- Controlled error responses for all failure types
- Recovery capability without persistent state

### 9.2 Non-Functional Requirements
- 100% test pass rate
- No external calls/downloads
- NetworkGuard behavior preserved
- Error messages safe and informative

## 10. Next Steps

### 10.1 Immediate Actions
1. Implement coder.py error handling enhancements
2. Implement vision.py error handling improvements
3. Implement ModelClient.py error handling
4. Create comprehensive test suite

### 10.2 Verification
1. Run all targeted resilience tests
2. Run all existing tests for regression
3. Validate sovereignty compliance
4. Document implementation results

## 11. Timeline

### Phase 12.1 Implementation Timeline
- **Day 1**: Modify coder.py and vision.py
- **Day 2**: Modify ModelClient.py
- **Day 3**: Create comprehensive test suite
- **Day 4**: Run tests and validate
- **Day 5**: Final verification and documentation

## 12. Risk Mitigation

### 12.1 High-Risk Areas
1. **Error Handling Changes**: Could break existing applications
   - **Mitigation**: Comprehensive testing and validation

2. **Test Suite Creation**: Could introduce new failures
   - **Mitigation**: Mock-based deterministic testing

3. **Sovereignty Violation**: Could accidentally introduce external calls
   - **Mitigation**: Strict code review and testing

### 12.2 Testing Strategy
- Use extensive mocking to avoid requiring real model servers
- Run tests in isolated environments
- Validate all error paths return appropriate HTTP status codes
- Ensure no regression in existing functionality

## 13. Conclusion

Phase 12.1 will significantly enhance the Sovereign AI platform's runtime resilience by:

1. Providing specific HTTP error codes for different failure scenarios
2. Ensuring graceful error responses without exposing sensitive information
3. Maintaining system sovereignty with zero external dependencies
4. Enabling automatic recovery after model service failures
5. Preserving all existing NetworkGuard protections

The implementation follows strict security and sovereignty requirements while dramatically improving the system's ability to handle model unavailability, connection failures, timeouts, and malformed responses.
