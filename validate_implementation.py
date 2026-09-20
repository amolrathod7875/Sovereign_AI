#!/usr/bin/env python3
# Quick validation of Phase 12.1 fixes

import sys
import traceback

def check_file_imports(filepath, expected_imports):
    """Check if expected imports exist in a Python file."""
    try:
        with open(filepath, 'r') as f:
            content = f.read()
            
        for expected in expected_imports:
            if expected in content:
                print(f"✅ Found import: {expected} in {filepath}")
                return True
            else:
                print(f"❌ Missing import: {expected} in {filepath}")
                return False
    except Exception as e:
        print(f"❌ Error reading {filepath}: {e}")
        return False

def main():
    print("Phase 12.1 Runtime Resilience - Implementation Verification")
    print("=" * 70)
    
    # Files to check
    checks = [
        ("backend/app/api/coder.py", [
            "from httpx import ConnectError",
            "from agent.coder.config import CODER_MODEL_TIMEOUT, CODER_ENDPOINT"
        ]),
        ("backend/app/api/vision.py", [
            "class VisionUpstreamResponseError(Exception)",
            "except VisionUpstreamResponseError as e:"
        ]),
        ("backend/app/models/client.py", [
            "raise ValueError(f\"Model {self.model_id} response missing or invalid 'choices' field\")",
            "if not isinstance(result, dict):"
        ]),
        ("backend/agent/tools/vision.py", [
            "class VisionUpstreamResponseError(Exception)",
            "raise VisionUpstreamResponseError"
        ])
    ]
    
    results = []
    for filepath, expected_imports in checks:
        print(f"\nChecking {filepath}:")
        success = check_file_imports(filepath, expected_imports)
        results.append(success)
    
    print("\n" + "=" * 70)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✅ ALL CHECKS PASSED ({passed}/{total})")
        return 0
    else:
        print(f"❌ SOME CHECKS FAILED ({passed}/{total} passed)")
        return 1

if __name__ == "__main__":
    exit(main())
