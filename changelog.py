"""
Changelog management module for the DoD prohibited substances project.
"""

import logging
import json
import subprocess
from pathlib import Path
from datetime import datetime


def parse_existing_changelog_entries(changelog_content):
    """Parse existing changelog to extract already recorded changes by date."""
    existing_changes = {}
    lines = changelog_content.split("\n")
    current_date = None
    current_section = None

    for line in lines:
        line = line.strip()

        # Match date headers like "## 2026-01-02"
        if line.startswith("## ") and len(line) > 3:
            date_part = line[3:].strip()
            # Skip empty or invalid date headers
            if date_part and not date_part.startswith("#") and not date_part == "":
                current_date = date_part
                if current_date not in existing_changes:
                    existing_changes[current_date] = {
                        "added": set(),
                        "updated": set(),
                        "removed": set(),
                    }

        # Match section headers
        elif line.startswith("### "):
            if "New Substances Added" in line:
                current_section = "added"
            elif "Substances Modified" in line:
                current_section = "updated"
            elif "Substances Removed" in line:
                current_section = "removed"
            else:
                current_section = None

        # Extract substance names from bullet points
        elif line.startswith("- **") and current_date and current_section:
            # Extract substance name between ** markers
            if line.count("**") >= 2:
                start = line.find("**") + 2
                end = line.find("**", start)
                if end > start:
                    substance_name = line[start:end].strip()
                    # Clean up malformed names (remove extra colons)
                    substance_name = substance_name.rstrip(":").strip()
                    if substance_name:  # Only add non-empty names
                        existing_changes[current_date][current_section].add(
                            substance_name
                        )

    # Debug: log what we parsed
    total_existing = sum(
        len(changes["added"]) + len(changes["updated"]) + len(changes["removed"])
        for changes in existing_changes.values()
    )
    logging.debug(
        f"Parsed {total_existing} existing changelog entries across {len(existing_changes)} dates"
    )

    return existing_changes


def update_persistent_changelog(changes_detected, today, detection_date=None):
    """Update the persistent changelog file that gets committed to git.

    Args:
        changes_detected: List of detected changes
        today: Today's date string (YYYY-MM-DD)
        detection_date: Optional date when changes were detected (for computed changes)
    """
    changelog_file = Path("CHANGELOG.md")

    if not changelog_file.exists():
        with open(changelog_file, "w", encoding="utf-8") as f:
            f.write("# Changelog\n\n")
            f.write(
                "All notable changes to the DoD prohibited substances list will be documented in this file.\n\n"
            )
        logging.info("Created new CHANGELOG.md file.")

    # Read existing changelog
    with open(changelog_file, "r", encoding="utf-8") as f:
        existing_content = f.read()

    # Parse existing entries to avoid duplicates
    existing_changes = parse_existing_changelog_entries(existing_content)

    # Group changes by their source date
    changes_by_date = {}
    computed_changes = []

    for change in changes_detected:
        if change["type"] == "added" and "source_date" in change:
            # Use self-reported date from the substance data
            date_key = change["source_date"]
            if date_key not in changes_by_date:
                changes_by_date[date_key] = {"added": [], "updated": [], "removed": []}

            # Check if this substance is already recorded for this date
            if (
                date_key in existing_changes
                and change["name"] in existing_changes[date_key]["added"]
            ):
                logging.debug(
                    f"Skipping duplicate added entry for {change['name']} on {date_key}"
                )
                continue

            changes_by_date[date_key]["added"].append(change)
        elif change["type"] in ["removed", "updated"]:
            # Use computed detection date for our analysis
            computed_changes.append(change)
        else:
            # Fallback to today's date
            if today not in changes_by_date:
                changes_by_date[today] = {"added": [], "updated": [], "removed": []}

            # Check for duplicates
            if (
                today in existing_changes
                and change["name"] in existing_changes[today][change["type"]]
            ):
                logging.debug(
                    f"Skipping duplicate {change['type']} entry for {change['name']} on {today}"
                )
                continue

            changes_by_date[today][change["type"]].append(change)

    # Add computed changes to detection date with duplicate checking
    detection_date = detection_date or today
    if computed_changes:
        if detection_date not in changes_by_date:
            changes_by_date[detection_date] = {
                "added": [],
                "updated": [],
                "removed": [],
            }
        for change in computed_changes:
            # Check for duplicates
            if (
                detection_date in existing_changes
                and change["name"] in existing_changes[detection_date][change["type"]]
            ):
                logging.debug(
                    f"Skipping duplicate {change['type']} entry for {change['name']} on {detection_date}"
                )
                continue

            changes_by_date[detection_date][change["type"]].append(change)

    # Remove dates that have no new changes
    changes_by_date = {
        date: changes
        for date, changes in changes_by_date.items()
        if changes["added"] or changes["updated"] or changes["removed"]
    }

    if not changes_by_date:
        logging.info("No new changelog entries needed - all changes already recorded.")
        return

    # For dates that already exist in the changelog, we need to update existing entries
    # For new dates, we add completely new entries
    lines = existing_content.split("\n")
    new_lines = []
    i = 0

    # Copy header
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)
        if line.startswith("## ") or (line.strip() and not line.startswith("#")):
            break
        i += 1

    # Process each date in chronological order (newest first)
    all_dates = set(changes_by_date.keys()) | set(existing_changes.keys())

    dates_processed = set()

    # Continue processing existing content, updating or inserting as needed
    while i < len(lines):
        line = lines[i]

        # Check if this is a date header
        if line.strip().startswith("## "):
            date_part = line.strip()[3:].strip()

            if date_part in changes_by_date and date_part not in dates_processed:
                # This date has new changes - merge with existing entry
                logging.info(f"Updating existing changelog entry for {date_part}")

                # Add the existing date header
                new_lines.append(line)
                i += 1

                # Skip the existing content for this date, we'll regenerate it
                while i < len(lines) and not lines[i].strip().startswith("## "):
                    i += 1

                # Generate merged content for this date
                merged_changes = merge_changes_for_date(
                    date_part, existing_changes, changes_by_date
                )
                date_content = generate_changelog_content_for_date(
                    date_part, merged_changes
                )
                new_lines.extend(date_content.split("\n"))
                new_lines.append("")  # Add spacing

                dates_processed.add(date_part)
                continue

        # Copy existing content if no changes for this date
        new_lines.append(line)
        i += 1

    # Add completely new dates that weren't in the existing changelog
    for date_key in sorted(changes_by_date.keys(), reverse=True):
        if date_key not in dates_processed:
            logging.info(f"Adding new changelog entry for {date_key}")

            # Insert at the appropriate position (after header, before older dates)
            insert_position = find_insert_position(new_lines, date_key)

            date_content = generate_changelog_content_for_date(
                date_key, changes_by_date[date_key]
            )
            content_lines = [f"## {date_key}", ""] + date_content.split("\n") + [""]

            new_lines = (
                new_lines[:insert_position]
                + content_lines
                + new_lines[insert_position:]
            )

    # Write back the updated changelog
    with open(changelog_file, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))

    total_new_changes = sum(
        len(changes_by_date[d]["added"])
        + len(changes_by_date[d]["updated"])
        + len(changes_by_date[d]["removed"])
        for d in changes_by_date
    )
    logging.info(
        f"Updated changelog with {total_new_changes} new changes across {len(changes_by_date)} date(s)."
    )


def merge_changes_for_date(date_key, existing_changes, new_changes):
    """Merge existing and new changes for a specific date."""
    merged = {"added": [], "updated": [], "removed": []}

    # Start with existing changes
    if date_key in existing_changes:
        for change_type in ["added", "updated", "removed"]:
            for substance_name in existing_changes[date_key][change_type]:
                # Create a basic change object for existing entries
                merged[change_type].append({"name": substance_name, "fields": []})

    # Add new changes (duplicates already filtered out)
    if date_key in new_changes:
        for change_type in ["added", "updated", "removed"]:
            merged[change_type].extend(new_changes[date_key][change_type])

    return merged


def generate_changelog_content_for_date(date_key, date_changes):
    """Generate changelog content for a specific date."""
    content_parts = []

    # New substances (from self-reported dates)
    if date_changes["added"]:
        content_parts.append("### New Substances Added\n")
        for change in date_changes["added"]:
            line = f"- **{change['name']}**"
            if (
                isinstance(change, dict)
                and "source_date" in change
                and change["source_date"] != date_key
            ):
                line += f" (source date: {change['source_date']})"
            content_parts.append(line)
        content_parts.append("")  # Add spacing

    # Modified substances (from our detection)
    if date_changes["updated"]:
        content_parts.append("### Substances Modified\n")
        content_parts.append("*Changes detected through data comparison*\n")
        for change in date_changes["updated"]:
            if isinstance(change, dict) and change.get("fields"):
                field_list = ", ".join(f"`{field}`" for field in change["fields"])
                content_parts.append(f"- **{change['name']}:** Updated {field_list}")
            else:
                content_parts.append(f"- **{change['name']}:** Updated")
        content_parts.append("")  # Add spacing

    # Removed substances (from our detection)
    if date_changes["removed"]:
        content_parts.append("### Substances Removed\n")
        content_parts.append("*Removals detected through data comparison*\n")
        for change in date_changes["removed"]:
            content_parts.append(f"- **{change['name']}**")
        content_parts.append("")  # Add spacing

    return "\n".join(content_parts).rstrip()


def find_insert_position(lines, new_date):
    """Find the correct position to insert a new date entry."""
    # Skip header
    pos = 0
    while pos < len(lines) and not lines[pos].strip().startswith("## "):
        pos += 1

    # Find the right position based on date order (newest first)
    while pos < len(lines):
        line = lines[pos].strip()
        if line.startswith("## "):
            existing_date = line[3:].strip()
            if existing_date < new_date:  # Insert before older dates
                return pos
        pos += 1

    return len(lines)  # Insert at end if no older dates found


def get_substance_source_date(substance_data):
    """Extract the source date when a substance was actually added/modified.

    This looks for self-reported dates in the substance data that indicate
    when the substance was actually changed in the source system.
    """
    try:
        # Try to get the date from the 'updated' timestamp
        timestamp = get_substance_last_modified(substance_data)
        if timestamp > 0:
            return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d")

        # Fallback: look for other date fields
        for field in ["date_added", "created", "modified_date", "last_updated"]:
            if field in substance_data and substance_data[field]:
                # Try to parse various date formats
                date_str = str(substance_data[field])
                # Add date parsing logic here if needed
                return date_str[:10] if len(date_str) >= 10 else None

        return None
    except Exception as e:
        logging.debug(f"Could not extract source date: {e}")
        return None


def get_substance_last_modified(substance_data):
    """Extract the last modified timestamp from substance data."""
    try:
        updated_field = substance_data.get("updated", "")
        if isinstance(updated_field, str) and updated_field.strip():
            updated_json = json.loads(updated_field)
            if isinstance(updated_json, dict) and "_seconds" in updated_json:
                return updated_json["_seconds"]
        return 0
    except (json.JSONDecodeError, ValueError, TypeError):
        return 0


def has_substance_been_modified_since(substance_data, timestamp_threshold):
    """Check if substance was modified after a given timestamp."""
    last_modified = get_substance_last_modified(substance_data)
    return last_modified > timestamp_threshold