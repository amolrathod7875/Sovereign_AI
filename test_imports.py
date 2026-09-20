#!/usr/bin/env python3
# Test script to verify Phase 12.1 implementation

import sys
import traceback

def test_coder_imports():
    """Test that coder.py imports work correctly."""
    try:
        from backend.app.api.coder import run_coder
        print("✅ coder.py imports successful")
        return True
    except Exception as e:
        print(f"❌ coder.py import failed: {e}")
        traceback.print_exc()
        return False

def test_vision_imports():
    """Test that vision.py imports work correctly."""
    try:
        from backend.app.api.vision import analyze
        print("✅ vision.py imports successful")
        return True
    except Exception as e:
        print(f"❌ vision.py import failed: {e}")
        traceback.print_exc()
        return False

def test_client_imports():
    """Test that client.py imports work correctly."""
    try:
        from backend.app.models.client import ModelClient
        print("✅ client.py imports successful")
        return True
    except Exception as e:
        print(f"❌ client.py import failed: {e}")
        traceback.print_exc()
        return False

def main():
    print("Phase 12.1 Runtime Resilience - Import Verification")
    print("=" * 60)
    
    # Test Python path
    sys.path.insert(0, "/c/Sovereign_AI/backend")
    
    results = []
    results.append(test_coder_imports())
    results.append(test_vision_imports())
    results.append(test_client_imports())
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✅ ALL IMPORTS SUCCESSFUL ({passed}/{total})")
        return 0
    else:
        print(f"❌ SOME IMPORTS FAILED ({passed}/{total} passed)")
        return 1

if __name__ == "__main__":
    exit(main())
