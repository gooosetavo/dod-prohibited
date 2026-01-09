#!/usr/bin/env python3
"""
Debug script to understand why the same substances are being detected as changed
"""

import json
import subprocess
from pathlib import Path


def load_current_data():
    """Load current docs/data.json"""
    data_file = Path("docs/data.json")
    if data_file.exists():
        with open(data_file) as f:
            return json.load(f)
    return []


def load_previous_data():
    """Load previous version from git"""
    try:
        result = subprocess.run(
            ['git', 'show', 'HEAD~1:docs/data.json'],
            capture_output=True,
            text=True,
            check=True
        )
        return json.loads(result.stdout)
    except:
        return []


def compare_data():
    """Compare current and previous data to understand differences"""
    current = load_current_data()
    previous = load_previous_data()
    
    print(f"📊 Current data: {len(current)} substances")
    print(f"📊 Previous data: {len(previous)} substances")
    
    if not current or not previous:
        print("❌ Cannot compare - missing data")
        return
    
    # Create lookup dictionaries using the same key logic
    current_dict = {}
    previous_dict = {}
    
    # Get column names from current data
    columns = list(current[0].keys()) if current else []
    data_columns = [col for col in columns if col not in ['added', 'updated']]
    
    print(f"📋 Columns: {columns}")
    print(f"📋 Data columns (excluding timestamps): {data_columns}")
    
    if len(data_columns) >= 2:
        key_cols = data_columns[:2]
        print(f"🔑 Using key columns: {key_cols}")
        
        # Build current dict
        for item in current:
            key = '|'.join(str(item.get(col, '')) for col in key_cols)
            current_dict[key] = item
            
        # Build previous dict  
        for item in previous:
            key = '|'.join(str(item.get(col, '')) for col in key_cols)
            previous_dict[key] = item
    
    # Find differences
    current_keys = set(current_dict.keys())
    previous_keys = set(previous_dict.keys())
    
    new_keys = current_keys - previous_keys
    removed_keys = previous_keys - current_keys
    common_keys = current_keys & previous_keys
    
    print("\n🔍 Key Analysis:")
    print(f"   📈 New substances: {len(new_keys)}")
    print(f"   📉 Removed substances: {len(removed_keys)}")
    print(f"   🔄 Common substances: {len(common_keys)}")
    
    # Show samples
    if new_keys:
        print("\n📈 Sample new keys:")
        for key in list(new_keys)[:3]:
            name = current_dict[key].get('Name', 'Unknown')
            print(f"   - {name} (key: {key[:80]}...)")
    
    if removed_keys:
        print("\n📉 Sample removed keys:")
        for key in list(removed_keys)[:3]:
            name = previous_dict[key].get('Name', 'Unknown')
            print(f"   - {name} (key: {key[:80]}...)")
    
    # Check for changes in common substances
    changed_substances = 0
    metadata_only_changes = 0
    meaningful_changes = 0
    timestamp_based_changes = 0
    
    ignore_fields = {'added', 'updated', 'guid', 'More_info_URL', 'SourceOf'}
    
    print(f"\n🔍 Analyzing substance changes (sample of {min(10, len(common_keys))}):")
    
    for key in list(common_keys)[:10]:  # Check first 10 for sample
        current_item = current_dict[key]
        previous_item = previous_dict[key]
        
        # Check timestamp-based changes
        def get_timestamp(item):
            try:
                updated_field = item.get('updated', '')
                if isinstance(updated_field, str) and updated_field.strip():
                    import json
                    updated_json = json.loads(updated_field)
                    if isinstance(updated_json, dict) and '_seconds' in updated_json:
                        return updated_json['_seconds']
                return 0
            except:
                return 0
        
        current_timestamp = get_timestamp(current_item)
        previous_timestamp = get_timestamp(previous_item)
        
        changed_fields = []
        meaningful_changed_fields = []
        
        for col in columns:
            if current_item.get(col) != previous_item.get(col):
                changed_fields.append(col)
                if col not in ignore_fields:
                    meaningful_changed_fields.append(col)
        
        if changed_fields:
            changed_substances += 1
            name = current_item.get('Name', 'Unknown')
            
            if current_timestamp > previous_timestamp:
                timestamp_based_changes += 1
                print(f"\n🕒 TIMESTAMP CHANGE: {name}")
                print(f"   Timestamp: {previous_timestamp} → {current_timestamp}")
            else:
                print(f"\n🔄 FIELD CHANGE: {name}")
                print(f"   Timestamp: {previous_timestamp} = {current_timestamp}")
            
            print(f"   All changed fields: {changed_fields}")
            print(f"   Meaningful changes: {meaningful_changed_fields}")
            
            if meaningful_changed_fields:
                meaningful_changes += 1
            else:
                metadata_only_changes += 1
    
    print(f"\n📊 Change Summary (sample of {min(10, len(common_keys))} substances):")
    print(f"   🔄 Total changed: {changed_substances}")
    print(f"   ⚡ Meaningful changes: {meaningful_changes}")
    print(f"   🏷️  Metadata-only changes: {metadata_only_changes}")
    print(f"   🕒 Timestamp-based changes: {timestamp_based_changes}")
    
    # Recommendation based on analysis
    if timestamp_based_changes > 0 and meaningful_changes == 0:
        print("\n💡 INSIGHT: All changes appear to be timestamp-only updates.")
        print("   This suggests the data source updates timestamps without changing content.")
        print("   Consider using timestamp comparison for more accurate change detection.")
    elif meaningful_changes > 0:
        print(f"\n💡 INSIGHT: {meaningful_changes} substances have actual content changes.")
        print("   These are legitimate updates that should be reflected in the changelog.")


if __name__ == "__main__":
    compare_data()