#!/usr/bin/env python3
"""
Test to verify that load_csv_data and other methods use cached files properly.
"""

import logging
import time
from unii_client import UniiDataClient

# Enable info logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def test_cache_usage():
    """Test that CSV loading uses cached files without triggering downloads."""
    
    print("=== Testing Cached File Usage ===\n")
    
    client = UniiDataClient()
    
    # Step 1: Check if we have a cached file
    cached_path = client.get_cached_zip_path()
    if cached_path:
        print(f"✓ Found cached file: {cached_path}")
        print(f"  Size: {cached_path.stat().st_size / (1024*1024):.2f} MB")
    else:
        print("No cached file found - will download on first use")
    
    # Step 2: Get data info (should use cache or download if needed)
    print("\\n1. Getting data info...")
    start_time = time.time()
    info = client.get_data_info()
    info_time = time.time() - start_time
    print(f"   Time taken: {info_time:.2f} seconds")
    print(f"   Files in archive: {info['file_count']}")
    print(f"   CSV files: {len(info['csv_files'])}")
    print(f"   TXT files: {len(info['txt_files'])}")
    
    # Step 3: List zip contents (should use cache)
    print("\\n2. Listing zip contents...")
    start_time = time.time()
    contents = client.list_zip_contents()
    list_time = time.time() - start_time
    print(f"   Time taken: {list_time:.2f} seconds")
    print(f"   Found {len(contents)} files")
    
    # Step 4: Try to load data if there are files to load
    if contents:
        print("\\n3. Testing file extraction...")
        first_file = contents[0]
        print(f"   Extracting: {first_file}")
        
        start_time = time.time()
        try:
            file_content = client.extract_file(first_file)
            extract_time = time.time() - start_time
            print(f"   Time taken: {extract_time:.2f} seconds")
            print(f"   File size: {len(file_content)} bytes")
            
            # If it's a text file, show a preview
            if first_file.endswith('.txt'):
                preview = file_content.decode('utf-8')[:200]
                print(f"   Preview: {preview}...")
                
        except Exception as e:
            print(f"   Error extracting file: {e}")
    
    # Step 5: Test CSV loading if available
    if info.get('csv_files'):
        csv_file = info['csv_files'][0]
        print("\\n4. Testing CSV loading...")
        print(f"   Loading: {csv_file}")
        
        start_time = time.time()
        try:
            df = client.load_csv_data(csv_file, nrows=10)  # Load only first 10 rows
            csv_time = time.time() - start_time
            print(f"   Time taken: {csv_time:.2f} seconds")
            print(f"   Loaded {len(df)} rows, {len(df.columns)} columns")
            print(f"   Columns: {list(df.columns)[:5]}")  # Show first 5 columns
            
        except Exception as e:
            print(f"   Error loading CSV: {e}")
    else:
        print("\\n4. No CSV files available for testing")
    
    # Summary
    print("\\n=== Summary ===")
    print("All operations should be fast if using cached file:")
    print(f"  - Data info: {info_time:.2f}s")
    print(f"  - List contents: {list_time:.2f}s")
    
    # Check if we're hitting cache properly (operations should be sub-second)
    if info_time < 1.0 and list_time < 0.1:
        print("  ✓ Operations are fast - likely using cached file")
    else:
        print("  ⚠ Operations took longer - may have downloaded from remote")

if __name__ == "__main__":
    test_cache_usage()