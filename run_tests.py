#!/usr/bin/env python3
"""
Simple test runner that can work with or without pytest
"""

import sys
import os
import subprocess

def run_tests():
    """Run tests using pytest if available, otherwise run basic tests"""
    try:
        # Try to run with pytest
        result = subprocess.run([sys.executable, '-m', 'pytest', 'tests/', '-v'], 
                              capture_output=False)
        return result.returncode == 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("pytest not available, running basic tests...")
        
        # Basic test runner
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tests'))
        
        # Import test classes from tests directory
        from test_retrieval import TestRetrieval
        from test_parsing import TestParsing 
        from test_generate_docs import TestGenerateDocs
        from test_workflow_helper import TestWorkflowHelper
        
        test_classes = [
            TestRetrieval, TestParsing, TestGenerateDocs, TestWorkflowHelper
        ]
        
        passed = 0
        failed = 0
        
        for test_class in test_classes:
            print(f"\n=== Running {test_class.__name__} ===")
            test_instance = test_class()
            
            # Get all test methods
            test_methods = [method for method in dir(test_instance) 
                          if method.startswith('test_')]
            
            for method_name in test_methods:
                try:
                    print(f"  {method_name}...", end=" ")
                    method = getattr(test_instance, method_name)
                    method()
                    print("PASSED")
                    passed += 1
                except Exception as e:
                    print(f"FAILED: {e}")
                    failed += 1
        
        print(f"\n=== Test Summary ===")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        
        return failed == 0

if __name__ == '__main__':
    success = run_tests()
    sys.exit(0 if success else 1)