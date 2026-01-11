"""
Changelog management module for the DoD prohibited substances project.
"""

import logging
import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field
from typing import List, Set, Dict, Optional
from enum import Enum


class ChangeType(Enum):
    """Type of change to a substance."""
    ADDED = "added"
    UPDATED = "updated"
    REMOVED = "removed"


@dataclass
class SubstanceChange:
    """Represents a change to a substance."""
    name: str
    change_type: ChangeType
    key: Optional[str] = None
    fields: List[str] = field(default_factory=list)
    source_date: Optional[str] = None
    detection_date: Optional[str] = None

    @property
    def type(self) -> str:
        """Return the change type as a string for backward compatibility."""
        return self.change_type.value


@dataclass
class DateChanges:
    """Container for changes organized by type for a specific date."""
    added: List[SubstanceChange] = field(default_factory=list)
    updated: List[SubstanceChange] = field(default_factory=list)
    removed: List[SubstanceChange] = field(default_factory=list)

    def get_changes(self, change_type: ChangeType) -> List[SubstanceChange]:
        """Get changes by type."""
        if change_type == ChangeType.ADDED:
            return self.added
        elif change_type == ChangeType.UPDATED:
            return self.updated
        elif change_type == ChangeType.REMOVED:
            return self.removed
        return []

    def add_change(self, change: SubstanceChange) -> None:
        """Add a change to the appropriate list."""
        if change.change_type == ChangeType.ADDED:
            self.added.append(change)
        elif change.change_type == ChangeType.UPDATED:
            self.updated.append(change)
        elif change.change_type == ChangeType.REMOVED:
            self.removed.append(change)

    def has_changes(self) -> bool:
        """Check if there are any changes."""
        return bool(self.added or self.updated or self.removed)


@dataclass
class ParsedChanges:
    """Container for parsed existing changes by date."""
    changes_by_date: Dict[str, Dict[str, Set[str]]] = field(default_factory=dict)

    def add_substance(self, date: str, change_type: ChangeType, substance_name: str) -> None:
        """Add a substance to the parsed changes."""
        if date not in self.changes_by_date:
            self.changes_by_date[date] = {
                "added": set(),
                "updated": set(),
                "removed": set(),
            }
        self.changes_by_date[date][change_type.value].add(substance_name)

    def has_substance(self, date: str, change_type: ChangeType, substance_name: str) -> bool:
        """Check if a substance already exists for a given date and type."""
        return (
            date in self.changes_by_date and
            substance_name in self.changes_by_date[date][change_type.value]
        )


def parse_existing_changelog_entries(changelog_content) -> ParsedChanges:
    """Parse existing changelog to extract already recorded changes by date."""
    existing_changes = ParsedChanges()
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

        # Match section headers
        elif line.startswith("### "):
            if "New Substances Added" in line:
                current_section = ChangeType.ADDED
            elif "Substances Modified" in line:
                current_section = ChangeType.UPDATED
            elif "Substances Removed" in line:
                current_section = ChangeType.REMOVED
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
                        existing_changes.add_substance(current_date, current_section, substance_name)

    # Debug: log what we parsed
    total_existing = sum(
        len(changes["added"]) + len(changes["updated"]) + len(changes["removed"])
        for changes in existing_changes.changes_by_date.values()
    )
    logging.debug(
        f"Parsed {total_existing} existing changelog entries across {len(existing_changes.changes_by_date)} dates"
    )

    return existing_changes


def create_substance_change_from_dict(change_dict: dict) -> SubstanceChange:
    """Convert a legacy change dictionary to a SubstanceChange object."""
    change_type = ChangeType(change_dict["type"])
    return SubstanceChange(
        name=change_dict["name"],
        change_type=change_type,
        key=change_dict.get("key"),
        fields=change_dict.get("fields", []),
        source_date=change_dict.get("source_date"),
        detection_date=change_dict.get("detection_date"),
    )


def update_persistent_changelog(changes_detected, today, detection_date=None):
    """Update the persistent changelog file that gets committed to git.

    Args:
        changes_detected: List of detected changes (legacy dict format)
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
    changes_by_date: Dict[str, DateChanges] = {}
    computed_changes: List[SubstanceChange] = []

    # Convert legacy dictionaries to SubstanceChange objects
    for change_dict in changes_detected:
        change = create_substance_change_from_dict(change_dict)
        
        if change.change_type == ChangeType.ADDED and change.source_date:
            # Use self-reported date from the substance data
            date_key = change.source_date
            if date_key not in changes_by_date:
                changes_by_date[date_key] = DateChanges()

            # Check if this substance is already recorded for this date
            if existing_changes.has_substance(date_key, ChangeType.ADDED, change.name):
                logging.debug(
                    f"Skipping duplicate added entry for {change.name} on {date_key}"
                )
                continue

            changes_by_date[date_key].add_change(change)
        elif change.change_type in [ChangeType.REMOVED, ChangeType.UPDATED]:
            # Use computed detection date for our analysis
            computed_changes.append(change)
        else:
            # Fallback to today's date
            if today not in changes_by_date:
                changes_by_date[today] = DateChanges()

            # Check for duplicates
            if existing_changes.has_substance(today, change.change_type, change.name):
                logging.debug(
                    f"Skipping duplicate {change.change_type.value} entry for {change.name} on {today}"
                )
                continue

            changes_by_date[today].add_change(change)

    # Add computed changes to detection date with duplicate checking
    detection_date = detection_date or today
    if computed_changes:
        if detection_date not in changes_by_date:
            changes_by_date[detection_date] = DateChanges()
        
        for change in computed_changes:
            # Check for duplicates
            if existing_changes.has_substance(detection_date, change.change_type, change.name):
                logging.debug(
                    f"Skipping duplicate {change.change_type.value} entry for {change.name} on {detection_date}"
                )
                continue

            changes_by_date[detection_date].add_change(change)

    # Remove dates that have no new changes
    changes_by_date = {
        date: changes
        for date, changes in changes_by_date.items()
        if changes.has_changes()
    }

    if not changes_by_date:
        logging.info("No new changelog entries needed - all changes already recorded.")
        return

    # For dates that already exist in the changelog, we need to update existing entries
    # For new dates, we add completely new entries
    lines = existing_content.split("\n")
    
    # Build a completely new changelog by processing dates systematically
    new_content_lines = []
    
    # Copy header until we hit the first date
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip().startswith("## ") and len(line.strip()) > 3:
            # This is a date header, stop copying header
            break
        new_content_lines.append(line)
        i += 1
    
    # Get all dates (both existing and new) and sort them chronologically (newest first)
    all_dates = set()
    
    # Add dates that have new changes
    all_dates.update(changes_by_date.keys())
    
    # Add existing dates that don't have new changes
    for existing_date in existing_changes.changes_by_date.keys():
        all_dates.add(existing_date)
    
    # Sort dates newest first
    sorted_dates = sorted(all_dates, reverse=True)
    
    # Process each date in order
    for date_key in sorted_dates:
        new_content_lines.append(f"## {date_key}")
        new_content_lines.append("")
        
        if date_key in changes_by_date:
            # This date has new changes, merge with existing
            logging.info(f"Adding/updating changelog entry for {date_key}")
            merged_changes = merge_changes_for_date(
                date_key, existing_changes, changes_by_date
            )
            date_content = generate_changelog_content_for_date(
                date_key, merged_changes
            )
        else:
            # This date exists but has no new changes, copy existing content
            date_content = extract_existing_date_content(lines, date_key)
        
        # Add the content (without any date headers)
        if date_content.strip():
            content_lines = [line for line in date_content.split("\n") if line.strip()]
            new_content_lines.extend(content_lines)
            new_content_lines.append("")  # Add spacing after content

    # Write back the updated changelog
    with open(changelog_file, "w", encoding="utf-8") as f:
        f.write("\n".join(new_content_lines))

    total_new_changes = sum(
        len(changes.added) + len(changes.updated) + len(changes.removed)
        for changes in changes_by_date.values()
    )
    logging.info(
        f"Updated changelog with {total_new_changes} new changes across {len(changes_by_date)} date(s)."
    )


def extract_existing_date_content(lines, date_key):
    """Extract existing content for a specific date from the changelog lines."""
    content_parts = []
    i = 0
    
    # Find the date header
    while i < len(lines):
        line = lines[i].strip()
        if line == f"## {date_key}":
            i += 1  # Skip the date header
            break
        i += 1
    
    # Extract content until we hit the next date header or end of file
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("## "):
            # Hit another date header, stop
            break
        if lines[i].rstrip():  # Only include non-empty lines (preserve content)
            content_parts.append(lines[i].rstrip())
        i += 1
    
    return "\n".join(content_parts)


def merge_changes_for_date(date_key: str, existing_changes: ParsedChanges, new_changes: Dict[str, DateChanges]) -> DateChanges:
    """Merge existing and new changes for a specific date."""
    merged = DateChanges()

    # Start with existing changes
    if date_key in existing_changes.changes_by_date:
        for change_type_str, substance_names in existing_changes.changes_by_date[date_key].items():
            change_type = ChangeType(change_type_str)
            for substance_name in substance_names:
                # Create a basic change object for existing entries
                change = SubstanceChange(
                    name=substance_name,
                    change_type=change_type,
                    fields=[]
                )
                merged.add_change(change)

    # Add new changes (duplicates already filtered out)
    if date_key in new_changes:
        date_changes = new_changes[date_key]
        merged.added.extend(date_changes.added)
        merged.updated.extend(date_changes.updated)
        merged.removed.extend(date_changes.removed)

    return merged


def generate_changelog_content_for_date(date_key: str, date_changes: DateChanges) -> str:
    """Generate changelog content for a specific date."""
    content_parts = []

    # New substances (from self-reported dates)
    if date_changes.added:
        count = len(date_changes.added)
        substance_word = "substance" if count == 1 else "substances"
        content_parts.append("### New Substances Added")
        content_parts.append("")
        content_parts.append(f"    {count} new {substance_word}")
        content_parts.append("")
        content_parts.append("???+ info \"Show details\"")
        content_parts.append("")
        for change in date_changes.added:
            line = f"    - **{change.name}**"
            if (
                change.source_date
                and change.source_date != date_key
            ):
                line += f" (source date: {change.source_date})"
            content_parts.append(line)
        content_parts.append("")  # Add spacing

    # Modified substances (from our detection)
    if date_changes.updated:
        count = len(date_changes.updated)
        substance_word = "substance" if count == 1 else "substances"
        content_parts.append("### Substances Modified")
        content_parts.append("")
        content_parts.append(f"*{count} {substance_word} modified, detected through data comparison*")
        content_parts.append("")
        content_parts.append("???+ info \"Show details\"")
        content_parts.append("")
        for change in date_changes.updated:
            if change.fields:
                field_list = ", ".join(f"`{field}`" for field in change.fields)
                content_parts.append(f"    - **{change.name}:** Updated {field_list}")
            else:
                content_parts.append(f"    - **{change.name}:** Updated")
        content_parts.append("")  # Add spacing

    # Removed substances (from our detection)
    if date_changes.removed:
        count = len(date_changes.removed)
        substance_word = "substance" if count == 1 else "substances"
        content_parts.append("### Substances Removed")
        content_parts.append("")
        content_parts.append(f"*{count} {substance_word} removals, detected through data comparison*")
        content_parts.append("")
        content_parts.append("???+ info \"Show details\"")
        content_parts.append("")
        for change in date_changes.removed:
            content_parts.append(f"    - **{change.name}**")
        content_parts.append("")  # Add spacing

    return "\n\n".join(content_parts).rstrip()


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