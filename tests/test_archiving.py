#!/usr/bin/env python3
"""
Test script to demonstrate the archiving functionality of the UNII client.

This script will simulate file changes and show how archiving works.
"""

import tempfile
from pathlib import Path
from unii_client import UniiDataClient, UniiDataConfig
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)

def test_archiving():
    """Test the archiving functionality with a temporary cache directory."""
    
    print("=== Testing UNII Client Archiving ===\\n")
    
    # Create a temporary directory for testing
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_cache = Path(temp_dir) / "test_cache"
        
        # Create client with temporary cache
        config = UniiDataConfig(cache_dir=str(temp_cache))
        client = UniiDataClient(config)
        
        print(f"Test cache directory: {client.cache_dir}")
        print(f"Test archive directory: {client.archive_dir}")
        
        # Step 1: First download
        print("\\n1. First download...")
        zip_path = client.download_zip()
        original_size = zip_path.stat().st_size
        print(f"   Downloaded file size: {original_size} bytes")
        
        # Step 2: Check remote size
        print("\\n2. Checking remote file size...")
        remote_size = client.get_remote_file_size()
        if remote_size:
            print(f"   Remote file size: {remote_size} bytes")
            if remote_size == original_size:
                print("   ✓ File sizes match - no archiving needed")
            else:
                print("   ⚠ File sizes differ - would trigger archiving")
        else:
            print("   ⚠ Could not determine remote file size")
        
        # Step 3: Simulate file change by modifying local file
        print("\\n3. Simulating file change for archiving test...")
        
        # Create a fake "old" file with different size
        fake_content = b"This is a fake old UNII file for testing"
        with open(zip_path, 'wb') as f:
            f.write(fake_content)
        
        old_size = zip_path.stat().st_size
        print(f"   Modified local file size: {old_size} bytes")
        
        # Step 4: Download again (should trigger archiving)
        print("\\n4. Downloading again (should archive old file)...")
        try:
            new_zip_path = client.download_zip()
            new_size = new_zip_path.stat().st_size
            print(f"   New file size: {new_size} bytes")
            
            # Check for archived files
            archived_files = client.list_archived_files()
            if archived_files:
                print(f"   ✓ Successfully archived {len(archived_files)} old file(s):")
                for archived_file in archived_files:
                    print(f"     - {archived_file['filename']} ({archived_file['size_mb']} MB)")
            else:
                print("   ℹ No files were archived (size difference may be handled differently)")
                
        except Exception as e:
            print(f"   Error during second download: {e}")
        
        # Step 5: Show final state
        print("\\n5. Final cache state...")
        try:
            info = client.get_data_info()
            print(f"   Current file: {info['zip_size_mb']} MB")
            print(f"   Archive count: {info['archive_count']}")
            
            if info['archive_count'] > 0:
                print("   Archived files:")
                for archived_file in info['archived_files']:
                    print(f"     - {archived_file['filename']} ({archived_file['size_mb']} MB)")
            
        except Exception as e:
            print(f"   Error getting final info: {e}")


def test_force_refresh():
    """Test force refresh functionality."""
    
    print("\\n=== Testing Force Refresh ===\\n")
    
    # Create client with default cache
    client = UniiDataClient()
    
    print("1. Normal download (uses cache if available)...")
    zip_path1 = client.download_zip()
    print(f"   File: {zip_path1}")
    
    print("\\n2. Force refresh download...")
    zip_path2 = client.download_zip(force_refresh=True)
    print(f"   File: {zip_path2}")
    
    print(f"\\n   Same file path: {zip_path1 == zip_path2}")

