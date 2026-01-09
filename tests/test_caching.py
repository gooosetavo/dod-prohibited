#!/usr/bin/env python3
"""
Quick test to verify that the UNII client properly uses cached files.
"""

import logging
from unii_client import UniiDataClient
import time
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_caching():
    """Test that the client uses cached files correctly."""
    
    print("=== Testing UNII Client Caching ===\n")
    
    client = UniiDataClient()
    
    print("1. First download (will download from remote)...")
    start_time = time.time()
    zip_path1 = client.download_zip()
    first_download_time = time.time() - start_time
    print(f"   File: {zip_path1}")
    print(f"   Download time: {first_download_time:.2f} seconds")
    
    print("\n2. Second call (should use cache)...")
    start_time = time.time()
    zip_path2 = client.download_zip()
    second_call_time = time.time() - start_time
    print(f"   File: {zip_path2}")
    print(f"   Call time: {second_call_time:.2f} seconds")
    
    print("\n3. Force refresh (will download again)...")
    start_time = time.time()
    zip_path3 = client.download_zip(force_refresh=True)
    force_refresh_time = time.time() - start_time
    print(f"   File: {zip_path3}")
    print(f"   Download time: {force_refresh_time:.2f} seconds")
    
    print("\n=== Results ===")
    print(f"Same file path: {zip_path1 == zip_path2 == zip_path3}")
    print(f"Second call much faster: {second_call_time < (first_download_time / 10)}")
    print(f"Force refresh took longer: {force_refresh_time > second_call_time}")
    
    # Get file info
    try:
        info = client.get_data_info()
        print("\nFile info:")
        print(f"  Size: {info['zip_size_mb']} MB")
        print(f"  Files in archive: {info['file_count']}")
        print(f"  CSV files: {len(info['csv_files'])}")
        
    except Exception as e:
        print(f"Error getting file info: {e}")
