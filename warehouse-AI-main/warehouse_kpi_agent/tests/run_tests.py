#!/usr/bin/env python3
"""Run all test suites for the Warehouse KPI Agent.

Usage:
    python run_tests.py              # Run all tests
    python run_tests.py intent       # Run intent classification tests only
    python run_tests.py kpi          # Run KPI calculation tests only
    python run_tests.py flow         # Run graph flow tests only
"""

import sys
import subprocess
from pathlib import Path

TESTS_DIR = Path(__file__).parent

TEST_FILES = {
    "intent": "test_intent_classification.py",
    "kpi": "test_kpi_calculations.py",
    "flow": "test_graph_flow.py",
}


def run_test(test_file: str) -> int:
    """Run a single test file and return exit code."""
    test_path = TESTS_DIR / test_file
    
    if not test_path.exists():
        print(f"❌ Test file not found: {test_file}")
        return 1
    
    print(f"\n{'=' * 80}")
    print(f"Running: {test_file}")
    print('=' * 80)
    
    result = subprocess.run([sys.executable, str(test_path)])
    return result.returncode


def main():
    """Run tests based on command-line arguments."""
    if len(sys.argv) > 1:
        # Run specific test
        test_key = sys.argv[1].lower()
        
        if test_key not in TEST_FILES:
            print(f"Unknown test: {test_key}")
            print(f"Available: {', '.join(TEST_FILES.keys())}")
            return 1
        
        test_file = TEST_FILES[test_key]
        return run_test(test_file)
    
    # Run all tests
    print("=" * 80)
    print("WAREHOUSE KPI AGENT - TEST SUITE")
    print("=" * 80)
    
    failed_tests = []
    
    for test_key, test_file in TEST_FILES.items():
        exit_code = run_test(test_file)
        
        if exit_code != 0:
            failed_tests.append(test_key)
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    
    if failed_tests:
        print(f"❌ {len(failed_tests)} test suite(s) FAILED:")
        for test in failed_tests:
            print(f"   - {test}")
        return 1
    else:
        print(f"✅ ALL {len(TEST_FILES)} TEST SUITES PASSED")
        return 0


if __name__ == "__main__":
    sys.exit(main())
