#!/usr/bin/env python3
"""
Test script for workflow_helper.py
"""

import subprocess
import sys
import os
from pathlib import Path

def test_workflow_helper():
    """Test the workflow helper script."""
    print("🧪 Testing workflow_helper.py...")
    
    # Ensure we're in the correct directory
    if not Path("workflow_helper.py").exists():
        print("❌ workflow_helper.py not found in current directory")
        return False
    
    # Test the check-changes action
    try:
        result = subprocess.run([
            sys.executable, "workflow_helper.py", "check-changes"
        ], capture_output=True, text=True, timeout=300)
        
        print(f"📋 Exit code: {result.returncode}")
        print(f"📤 stdout:\n{result.stdout}")
        if result.stderr:
            print(f"📥 stderr:\n{result.stderr}")
        
        # Check if changes summary was created
        summary_file = Path("changes_summary.json")
        if summary_file.exists():
            print("✅ changes_summary.json created successfully")
            with open(summary_file) as f:
                import json
                summary = json.load(f)
                print(f"📊 Summary: {summary}")
        else:
            print("⚠️  changes_summary.json not created")
        
        return True
        
    except subprocess.TimeoutExpired:
        print("⏰ Test timed out after 5 minutes")
        return False
    except Exception as e:
        print(f"❌ Test failed with error: {e}")
        return False

if __name__ == "__main__":
    success = test_workflow_helper()
    sys.exit(0 if success else 1)