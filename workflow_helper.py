#!/usr/bin/env python3
"""
Workflow helper script for GitHub Actions.
Handles change detection, file operations, and summary generation.
"""

import subprocess
import os
import sys
import logging
import json
from pathlib import Path
from generate_docs import main as generate_docs_main


def run_command(cmd, check=True):
    """Run a shell command and return the result."""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, check=check
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.CalledProcessError as e:
        return e.stdout.strip(), e.stderr.strip(), e.returncode


def get_git_status():
    """Get current git status."""
    stdout, stderr, code = run_command("git status --porcelain", check=False)
    return stdout.splitlines() if code == 0 else []


def set_github_output(key, value):
    """Set GitHub Actions output variable."""
    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a') as f:
            f.write(f"{key}={value}\n")
    else:
        # For local testing
        print(f"OUTPUT: {key}={value}")


def parse_changelog_counts():
    """Parse the latest CHANGELOG entry to get change counts."""
    changelog_path = Path("CHANGELOG.md")
    if not changelog_path.exists():
        return 0, 0, 0
    
    try:
        with open(changelog_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        new_count = 0
        updated_count = 0
        removed_count = 0
        current_section = None
        
        # Look at first 100 lines for the latest entry
        for line in lines[:100]:
            line = line.strip()
            if line.startswith('### New Substances Added'):
                current_section = 'new'
            elif line.startswith('### Substances Modified'):
                current_section = 'updated'
            elif line.startswith('### Substances Removed'):
                current_section = 'removed'
            elif line.startswith('### ') or line.startswith('## '):
                current_section = None
            elif line.startswith('- **') and current_section:
                if current_section == 'new':
                    new_count += 1
                elif current_section == 'updated':
                    updated_count += 1
                elif current_section == 'removed':
                    removed_count += 1
        
        return new_count, updated_count, removed_count
    except Exception as e:
        logging.warning(f"Could not parse changelog counts: {e}")
        return 0, 0, 0


def check_for_changes():
    """
    Main function to check for changes in prohibited substances.
    Returns True if changes detected, False otherwise.
    """
    print("🔍 Checking for changes in prohibited substances list...")
    
    # Store initial git status
    initial_status = get_git_status()
    print(f"📋 Git status before generation: {len(initial_status)} files")
    if initial_status:
        for status_line in initial_status[:5]:  # Show first 5 files
            print(f"   {status_line}")
        if len(initial_status) > 5:
            print(f"   ... and {len(initial_status) - 5} more files")
    
    # Set environment variable for docs generation
    os.environ["DOD_PROHIBITED_GENERATE_DOCS"] = "1"
    
    # Run the generation script
    print("🔄 Running prohibited substances data generation...")
    try:
        generate_docs_main()
        print("✅ Data generation completed successfully")
    except Exception as e:
        print(f"❌ Error during data generation: {e}")
        return False
    
    # Check git status after generation
    post_generation_status = get_git_status()
    print(f"📋 Git status after generation: {len(post_generation_status)} files")
    
    # Stage all changes
    print("📝 Staging changes...")
    run_command("git add -A")
    
    # Check if any files were staged
    staged_status = get_git_status()
    print(f"📋 Git status after staging: {len(staged_status)} files")
    
    # Check if there are any staged changes
    stdout, stderr, code = run_command("git diff --staged --quiet", check=False)
    has_changes = code != 0
    
    if has_changes:
        print("🔥 Changes detected!")
        
        # Show changed files
        changed_files, _, _ = run_command("git diff --staged --name-only")
        if changed_files:
            print("📁 Changed files:")
            for file in changed_files.splitlines()[:10]:  # Show first 10 files
                print(f"   {file}")
            if len(changed_files.splitlines()) > 10:
                print(f"   ... and {len(changed_files.splitlines()) - 10} more files")
        
        # Parse changelog to get detailed counts
        new_count, updated_count, removed_count = parse_changelog_counts()
        
        # Only report meaningful changes
        total_changes = new_count + updated_count + removed_count
        if total_changes == 0:
            print("⚠️  Warning: Files changed but no meaningful substance changes detected")
            print("   This might indicate only metadata/timestamp changes occurred")
            set_github_output("has-changes", "false")
            set_github_output("changes-summary", "metadata only")
            return False
        
        # Create summary
        summary_parts = []
        if new_count > 0:
            summary_parts.append(f"{new_count} new")
        if updated_count > 0:
            summary_parts.append(f"{updated_count} updated")
        if removed_count > 0:
            summary_parts.append(f"{removed_count} removed")
        
        changes_summary = ", ".join(summary_parts) if summary_parts else "changes detected"
        
        print(f"📊 Change summary: {changes_summary}")
        
        # Set GitHub Actions outputs
        set_github_output("has-changes", "true")
        set_github_output("changes-summary", changes_summary)
        
        # Also create a JSON summary file for more detailed information
        summary_data = {
            "has_changes": True,
            "new_count": new_count,
            "updated_count": updated_count,
            "removed_count": removed_count,
            "summary": changes_summary,
            "changed_files": changed_files.splitlines() if changed_files else []
        }
        
        with open("changes_summary.json", "w") as f:
            json.dump(summary_data, f, indent=2)
        
    else:
        print("✅ No changes detected in prohibited substances list")
        set_github_output("has-changes", "false")
        set_github_output("changes-summary", "no changes")
        
        # Create summary for no changes
        summary_data = {
            "has_changes": False,
            "new_count": 0,
            "updated_count": 0,
            "removed_count": 0,
            "summary": "no changes",
            "changed_files": []
        }
        
        with open("changes_summary.json", "w") as f:
            json.dump(summary_data, f, indent=2)
    
    return has_changes


def main():
    """Main entry point for the script."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
        handlers=[logging.StreamHandler()]
    )
    
    action = sys.argv[1] if len(sys.argv) > 1 else "check-changes"
    
    if action == "check-changes":
        has_changes = check_for_changes()
        sys.exit(0 if has_changes else 1)  # Exit code indicates if changes found
    elif action == "debug":
        print("🔍 Running change detection debug analysis...")
        print("For detailed analysis, run: python tests/debug_changes.py")
        has_changes = check_for_changes()
        sys.exit(0 if has_changes else 1)
    else:
        print(f"❌ Unknown action: {action}")
        print("Available actions: check-changes, debug")
        sys.exit(1)


if __name__ == "__main__":
    main()