
import subprocess
import logging
from retrieval import fetch_drupal_settings
from parsing import parse_prohibited_list
import generation
import sqlite3
from pathlib import Path
import os
import json
from datetime import datetime, timezone
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Optional


class Settings(BaseSettings):
    """Configuration settings for the DoD prohibited substances project."""
    
    model_config = ConfigDict(env_prefix="DOD_", case_sensitive=False)
    
    # Data source
    source_url: str = "https://www.opss.org/dod-prohibited-dietary-supplement-ingredients"
    
    # GitHub configuration
    github_owner: str = "gooosetavo"
    github_repo: str = "dod-prohibited"
    
    # Site configuration
    site_title: str = "DoD Prohibited Dietary Supplement Ingredients"
    site_description: str = "A searchable, browsable, and regularly updated list of substances prohibited by the Department of Defense (DoD) for use in dietary supplements."
    
    # Environment overrides
    github_ref: Optional[str] = None
    branch: Optional[str] = None
    
    @property
    def github_url(self) -> str:
        return f"https://github.com/{self.github_owner}/{self.github_repo}"



# Configure logging for GitHub Actions (stdout, INFO level by default)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler()]
)

settings = Settings()


def parse_existing_changelog_entries(changelog_content):
    """Parse existing changelog to extract already recorded changes by date."""
    existing_changes = {}
    lines = changelog_content.split('\n')
    current_date = None
    current_section = None
    
    for line in lines:
        line = line.strip()
        
        # Match date headers like "## 2026-01-02"
        if line.startswith('## ') and len(line) > 3:
            date_part = line[3:].strip()
            # Skip empty or invalid date headers
            if date_part and not date_part.startswith('#') and not date_part == "":
                current_date = date_part
                if current_date not in existing_changes:
                    existing_changes[current_date] = {'added': set(), 'updated': set(), 'removed': set()}
        
        # Match section headers
        elif line.startswith('### '):
            if 'New Substances Added' in line:
                current_section = 'added'
            elif 'Substances Modified' in line:
                current_section = 'updated'
            elif 'Substances Removed' in line:
                current_section = 'removed'
            else:
                current_section = None
        
        # Extract substance names from bullet points
        elif line.startswith('- **') and current_date and current_section:
            # Extract substance name between ** markers
            if line.count('**') >= 2:
                start = line.find('**') + 2
                end = line.find('**', start)
                if end > start:
                    substance_name = line[start:end].strip()
                    # Clean up malformed names (remove extra colons)
                    substance_name = substance_name.rstrip(':').strip()
                    if substance_name:  # Only add non-empty names
                        existing_changes[current_date][current_section].add(substance_name)
    
    # Debug: log what we parsed
    total_existing = sum(len(changes['added']) + len(changes['updated']) + len(changes['removed']) 
                        for changes in existing_changes.values())
    logging.debug(f"Parsed {total_existing} existing changelog entries across {len(existing_changes)} dates")
    
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
            f.write("All notable changes to the DoD prohibited substances list will be documented in this file.\n\n")
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
        if change['type'] == 'added' and 'source_date' in change:
            # Use self-reported date from the substance data
            date_key = change['source_date']
            if date_key not in changes_by_date:
                changes_by_date[date_key] = {'added': [], 'updated': [], 'removed': []}
            
            # Check if this substance is already recorded for this date
            if date_key in existing_changes and change['name'] in existing_changes[date_key]['added']:
                logging.debug(f"Skipping duplicate added entry for {change['name']} on {date_key}")
                continue
            
            changes_by_date[date_key]['added'].append(change)
        elif change['type'] in ['removed', 'updated']:
            # Use computed detection date for our analysis
            computed_changes.append(change)
        else:
            # Fallback to today's date
            if today not in changes_by_date:
                changes_by_date[today] = {'added': [], 'updated': [], 'removed': []}
            
            # Check for duplicates
            if today in existing_changes and change['name'] in existing_changes[today][change['type']]:
                logging.debug(f"Skipping duplicate {change['type']} entry for {change['name']} on {today}")
                continue
            
            changes_by_date[today][change['type']].append(change)
    
    # Add computed changes to detection date with duplicate checking
    detection_date = detection_date or today
    if computed_changes:
        if detection_date not in changes_by_date:
            changes_by_date[detection_date] = {'added': [], 'updated': [], 'removed': []}
        for change in computed_changes:
            # Check for duplicates
            if detection_date in existing_changes and change['name'] in existing_changes[detection_date][change['type']]:
                logging.debug(f"Skipping duplicate {change['type']} entry for {change['name']} on {detection_date}")
                continue
            
            changes_by_date[detection_date][change['type']].append(change)
    
    # Remove dates that have no new changes
    changes_by_date = {date: changes for date, changes in changes_by_date.items() 
                      if changes['added'] or changes['updated'] or changes['removed']}
    
    if not changes_by_date:
        logging.info("No new changelog entries needed - all changes already recorded.")
        return
    
    # For dates that already exist in the changelog, we need to update existing entries
    # For new dates, we add completely new entries
    lines = existing_content.split('\n')
    new_lines = []
    i = 0
    
    # Copy header
    while i < len(lines):
        line = lines[i]
        new_lines.append(line)
        if line.startswith('## ') or (line.strip() and not line.startswith('#')):
            break
        i += 1
    
    # Process each date in chronological order (newest first)
    all_dates = set(changes_by_date.keys()) | set(existing_changes.keys())
    sorted_dates = sorted(all_dates, reverse=True)
    
    dates_processed = set()
    
    # Continue processing existing content, updating or inserting as needed
    while i < len(lines):
        line = lines[i]
        
        # Check if this is a date header
        if line.strip().startswith('## '):
            date_part = line.strip()[3:].strip()
            
            if date_part in changes_by_date and date_part not in dates_processed:
                # This date has new changes - merge with existing entry
                logging.info(f"Updating existing changelog entry for {date_part}")
                
                # Add the existing date header
                new_lines.append(line)
                i += 1
                
                # Skip the existing content for this date, we'll regenerate it
                while i < len(lines) and not lines[i].strip().startswith('## '):
                    i += 1
                
                # Generate merged content for this date
                merged_changes = merge_changes_for_date(date_part, existing_changes, changes_by_date)
                date_content = generate_changelog_content_for_date(date_part, merged_changes)
                new_lines.extend(date_content.split('\n'))
                new_lines.append('')  # Add spacing
                
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
            
            date_content = generate_changelog_content_for_date(date_key, changes_by_date[date_key])
            content_lines = [f"## {date_key}", ""] + date_content.split('\n') + [""]
            
            new_lines = new_lines[:insert_position] + content_lines + new_lines[insert_position:]
    
    # Write back the updated changelog
    with open(changelog_file, "w", encoding="utf-8") as f:
        f.write('\n'.join(new_lines))
    
    total_new_changes = sum(len(changes_by_date[d]['added']) + len(changes_by_date[d]['updated']) + len(changes_by_date[d]['removed']) for d in changes_by_date)
    logging.info(f"Updated changelog with {total_new_changes} new changes across {len(changes_by_date)} date(s).")


def merge_changes_for_date(date_key, existing_changes, new_changes):
    """Merge existing and new changes for a specific date."""
    merged = {'added': [], 'updated': [], 'removed': []}
    
    # Start with existing changes
    if date_key in existing_changes:
        for change_type in ['added', 'updated', 'removed']:
            for substance_name in existing_changes[date_key][change_type]:
                # Create a basic change object for existing entries
                merged[change_type].append({'name': substance_name, 'fields': []})
    
    # Add new changes (duplicates already filtered out)
    if date_key in new_changes:
        for change_type in ['added', 'updated', 'removed']:
            merged[change_type].extend(new_changes[date_key][change_type])
    
    return merged


def generate_changelog_content_for_date(date_key, date_changes):
    """Generate changelog content for a specific date."""
    content_parts = []
    
    # New substances (from self-reported dates)
    if date_changes['added']:
        content_parts.append("### New Substances Added\n")
        for change in date_changes['added']:
            line = f"- **{change['name']}**"
            if isinstance(change, dict) and 'source_date' in change and change['source_date'] != date_key:
                line += f" (source date: {change['source_date']})"
            content_parts.append(line)
        content_parts.append("")  # Add spacing
    
    # Modified substances (from our detection)
    if date_changes['updated']:
        content_parts.append("### Substances Modified\n")
        content_parts.append("*Changes detected through data comparison*\n")
        for change in date_changes['updated']:
            if isinstance(change, dict) and change.get('fields'):
                field_list = ", ".join(f"`{field}`" for field in change['fields'])
                content_parts.append(f"- **{change['name']}:** Updated {field_list}")
            else:
                content_parts.append(f"- **{change['name']}:** Updated")
        content_parts.append("")  # Add spacing
    
    # Removed substances (from our detection)
    if date_changes['removed']:
        content_parts.append("### Substances Removed\n")
        content_parts.append("*Removals detected through data comparison*\n")
        for change in date_changes['removed']:
            content_parts.append(f"- **{change['name']}**")
        content_parts.append("")  # Add spacing
    
    return '\n'.join(content_parts).rstrip()


def find_insert_position(lines, new_date):
    """Find the correct position to insert a new date entry."""
    # Skip header
    pos = 0
    while pos < len(lines) and not lines[pos].strip().startswith('## '):
        pos += 1
    
    # Find the right position based on date order (newest first)
    while pos < len(lines):
        line = lines[pos].strip()
        if line.startswith('## '):
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
            from datetime import datetime
            return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
        
        # Fallback: look for other date fields
        for field in ['date_added', 'created', 'modified_date', 'last_updated']:
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
        updated_field = substance_data.get('updated', '')
        if isinstance(updated_field, str) and updated_field.strip():
            import json
            updated_json = json.loads(updated_field)
            if isinstance(updated_json, dict) and '_seconds' in updated_json:
                return updated_json['_seconds']
        return 0
    except (json.JSONDecodeError, ValueError, TypeError):
        return 0


def has_substance_been_modified_since(substance_data, timestamp_threshold):
    """Check if substance was modified after a given timestamp."""
    last_modified = get_substance_last_modified(substance_data)
    return last_modified > timestamp_threshold


def load_previous_data_from_git(current_columns):
    """Load the previous version of data.json from git history for comparison."""
    try:
        # Try to get the previous version of docs/data.json
        result = subprocess.run(
            ['git', 'show', 'HEAD~1:docs/data.json'],
            capture_output=True,
            text=True,
            cwd=Path.cwd()
        )
        
        if result.returncode == 0:
            data = json.loads(result.stdout)
            previous_dict = {}
            previous_count = len(data)
            
            for item in data:
                # Use the same key logic as current data processing
                substance_key = None
                
                # Try guid first (most unique)
                guid = item.get('guid') or item.get('Guid')
                if guid and str(guid).strip():
                    substance_key = f"guid:{guid}"
                # Try Name second
                elif item.get('Name') and str(item['Name']).strip():
                    substance_key = f"name:{item['Name']}"
                # Try searchable_name third
                elif item.get('searchable_name') and str(item['searchable_name']).strip():
                    substance_key = f"search:{item['searchable_name']}"
                else:
                    # Fallback: use meaningful columns that are more likely to have unique values
                    meaningful_cols = ['Name', 'searchable_name', 'Reason', 'guid']
                    available_cols = [col for col in meaningful_cols if col in item and str(item[col]).strip()]
                    if available_cols:
                        substance_key = '|'.join(str(item.get(col, '')) for col in available_cols[:2])
                    else:
                        # Last resort: use all non-empty values from the item
                        non_empty_vals = [str(val) for val in item.values() if val and str(val).strip() and str(val) not in ['[]', '{}', 'nan']]
                        substance_key = '|'.join(non_empty_vals[:3]) if non_empty_vals else str(hash(str(item)))
                
                previous_dict[substance_key] = item
                    
            logging.info(f"Loaded previous data.json from git history: {previous_count} substances")
            return previous_dict, previous_count
    except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError) as e:
        logging.warning(f"Could not load previous data.json from git: {e}")
    
    return None


def main():
    logging.info("Starting generate_docs.py script.")
    drupal_settings = fetch_drupal_settings(settings.source_url)
    logging.info("Fetched Drupal settings.")
    df = parse_prohibited_list(drupal_settings)
    logging.info(f"Parsed prohibited list. {len(df)} substances found.")

    # Setup SQLite DB
    db_path = Path("prohibited.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    logging.info("Connected to SQLite database.")

    columns = list(df.columns)
    col_defs = ", ".join([f'"{col}" TEXT' for col in columns])
    c.execute(f'''CREATE TABLE IF NOT EXISTS substances (
        id INTEGER PRIMARY KEY AUTOINCREMENT
    )''')
    logging.debug("Ensured substances table exists.")
    c.execute('PRAGMA table_info(substances)')
    existing_cols = set([row[1] for row in c.fetchall()])
    for col in columns + ["added", "updated"]:
        if col not in existing_cols:
            try:
                c.execute(f'ALTER TABLE substances ADD COLUMN "{col}" TEXT')
                logging.debug(f"Added column '{col}' to substances table.")
            except sqlite3.OperationalError:
                # Column might already exist, ignore
                logging.debug(f"Column '{col}' already exists in substances table.")
    unique_cols = ", ".join([f'"{col}"' for col in columns])
    # Create unique index only on the actual data columns, not added/updated timestamps
    try:
        c.execute(f'DROP INDEX IF EXISTS idx_unique_substance')
        c.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_substance ON substances ({unique_cols})')
        logging.debug("Ensured unique index on substances table.")
    except Exception as e:
        logging.warning(f"Could not create unique index: {e}")

    # Create changes table to track daily summaries (but use git for persistence)
    c.execute('''
        CREATE TABLE IF NOT EXISTS substance_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            substance_key TEXT,
            substance_name TEXT,
            change_date TEXT,
            change_type TEXT, -- 'added' or 'updated'
            fields_changed TEXT, -- JSON list of field names that changed
            UNIQUE(substance_key, change_date, change_type)
        )
    ''')
    logging.debug("Ensured substance_changes table exists.")

    # Clear the table to avoid duplicates on each run
    c.execute('DELETE FROM substances')
    c.execute('DELETE FROM substance_changes')
    logging.debug("Cleared substances and substance_changes tables.")

    now = datetime.now(timezone.utc).isoformat()
    today = now[:10]  # YYYY-MM-DD
    logging.info(f"Current date: {today}")
    
    # Load previous data from git history for comparison
    previous_result = load_previous_data_from_git(columns)
    previous_data = None
    previous_count = 0
    latest_previous_timestamp = 0
    if previous_result:
        if len(previous_result) == 3:
            previous_data, previous_count, latest_previous_timestamp = previous_result
        else:
            previous_data, previous_count = previous_result
    
    current_count = len(df)
    logging.info(f"Current substances: {current_count}, Previous substances: {previous_count}")
    
    # Log first few substance keys for debugging
    sample_keys = []
    for i, row in df.head(3).iterrows():
        sample_key = '|'.join(str(row.get(col, '')) for col in columns[:2])
        sample_keys.append(sample_key[:100])  # Truncate for readability
    logging.info(f"Sample current keys: {sample_keys}")
    
    if previous_data:
        sample_prev_keys = list(previous_data.keys())[:3]
        logging.info(f"Sample previous keys: {[k[:100] for k in sample_prev_keys]}")
    
    changes_detected = []
    current_keys = set()
    
    for _, row in df.iterrows():
        values = []
        for col in columns:
            val = row.get(col, None)
            if isinstance(val, (list, dict)):
                val = json.dumps(val, ensure_ascii=False)
            values.append(val)
        
        # Create a unique key based on meaningful identifiers
        # Priority: guid > Name > searchable_name > fallback to first meaningful fields
        substance_key = None
        current_row_dict = dict(zip(columns, values))
        
        # Try guid first (most unique)
        guid = current_row_dict.get('guid') or current_row_dict.get('Guid')
        if guid and str(guid).strip():
            substance_key = f"guid:{guid}"
        # Try Name second
        elif current_row_dict.get('Name') and str(current_row_dict['Name']).strip():
            substance_key = f"name:{current_row_dict['Name']}"
        # Try searchable_name third
        elif current_row_dict.get('searchable_name') and str(current_row_dict['searchable_name']).strip():
            substance_key = f"search:{current_row_dict['searchable_name']}"
        else:
            # Fallback: use meaningful columns that are more likely to have unique values
            meaningful_cols = ['Name', 'searchable_name', 'Reason', 'guid']
            available_cols = [col for col in meaningful_cols if col in current_row_dict and str(current_row_dict[col]).strip()]
            if available_cols:
                substance_key = '|'.join(str(current_row_dict.get(col, '')) for col in available_cols[:2])
            else:
                # Last resort: use all non-empty values
                non_empty_vals = [str(val) for val in values if val and str(val).strip() and str(val) not in ['[]', '{}', 'nan']]
                substance_key = '|'.join(non_empty_vals[:3]) if non_empty_vals else f"row_{_}"
        
        substance_name = row.get('Name') or row.get('ingredient') or row.get('name') or substance_key
        current_keys.add(substance_key)
        
        # Check if this substance is new or changed compared to git history
        added_date = now  # Default for new substances
        if previous_data is not None:
            prev_substance = previous_data.get(substance_key)
            if prev_substance is not None:
                # Existing substance - preserve original added date
                existing_added = prev_substance.get('added')
                if existing_added:
                    added_date = existing_added
        
        placeholders = ", ".join(["?"] * len(columns))
        sql = f'''
            INSERT INTO substances ({unique_cols}, added, updated)
            VALUES ({placeholders}, ?, ?)
        '''
        c.execute(sql, (*values, added_date, now))
        
        # Check if this substance is new or changed compared to git history
        if previous_data is not None:
            prev_substance = previous_data.get(substance_key)
            if prev_substance is None:
                # New substance - use self-reported date if available
                current_row_dict = dict(zip(columns, values))
                source_date = get_substance_source_date(current_row_dict)
                
                change_data = {
                    'type': 'added',
                    'key': substance_key,
                    'name': substance_name,
                    'fields': []
                }
                
                if source_date:
                    change_data['source_date'] = source_date
                    logging.debug(f"NEW SUBSTANCE: {substance_name} (source date: {source_date})")
                else:
                    logging.debug(f"NEW SUBSTANCE: {substance_name} (detection date: {today})")
                
                changes_detected.append(change_data)
            else:
                # Check if substance was modified using timestamp
                current_row_dict = dict(zip(columns, values))
                current_timestamp = get_substance_last_modified(current_row_dict)
                prev_timestamp = get_substance_last_modified(prev_substance)
                
                if current_timestamp > prev_timestamp:
                    # Substance was modified - check what fields actually changed
                    changed_fields = []
                    ignore_fields = {'added', 'updated', 'guid', 'More_info_URL', 'SourceOf'}
                    
                    for col in columns:
                        if col in ignore_fields:
                            continue
                            
                        current_val = current_row_dict.get(col)
                        prev_val = prev_substance.get(col)
                        
                        if current_val != prev_val:
                            # Special handling for JSON fields
                            if isinstance(current_val, str) and isinstance(prev_val, str):
                                try:
                                    import ast
                                    curr_parsed = ast.literal_eval(current_val) if current_val else None
                                    prev_parsed = ast.literal_eval(prev_val) if prev_val else None
                                    if curr_parsed != prev_parsed:
                                        changed_fields.append(col)
                                except:
                                    if current_val != prev_val:
                                        changed_fields.append(col)
                            else:
                                changed_fields.append(col)
                    
                    if changed_fields:
                        changes_detected.append({
                            'type': 'updated',
                            'key': substance_key,
                            'name': substance_name,
                            'fields': changed_fields,
                            'detection_date': today
                        })
                        logging.debug(f"UPDATED SUBSTANCE: {substance_name} (timestamp: {current_timestamp} > {prev_timestamp}, fields: {changed_fields}, detected: {today})")
    
    # Check for removed substances
    if previous_data is not None:
        previous_keys = set(previous_data.keys())
        removed_keys = previous_keys - current_keys
        for removed_key in removed_keys:
            removed_substance = previous_data[removed_key]
            removed_name = removed_substance.get('Name') or removed_substance.get('ingredient') or removed_substance.get('name') or removed_key
            changes_detected.append({
                'type': 'removed',
                'key': removed_key,
                'name': removed_name,
                'fields': [],
                'detection_date': today
            })
            logging.debug(f"REMOVED SUBSTANCE: {removed_name} (key: {removed_key[:50]}...)")
        
        # Log summary of changes
        new_count = len([c for c in changes_detected if c['type'] == 'added'])
        updated_count = len([c for c in changes_detected if c['type'] == 'updated'])
        removed_count = len([c for c in changes_detected if c['type'] == 'removed'])
        logging.info(f"Change summary: {new_count} added, {updated_count} updated, {removed_count} removed")
        logging.info(f"Net change: {current_count - previous_count} (from {previous_count} to {current_count})")
    
    # Store changes in database for changelog generation
    for change in changes_detected:
        c.execute('''
            INSERT OR REPLACE INTO substance_changes 
            (substance_key, substance_name, change_date, change_type, fields_changed)
            VALUES (?, ?, ?, ?, ?)
        ''', (change['key'], change['name'], today, change['type'], json.dumps(change['fields'])))
    logging.info(f"Detected {len(changes_detected)} changes.")
    
    # Also update persistent changelog file that gets committed to git
    if changes_detected:
        # Filter out changes that are only metadata/timestamp changes
        meaningful_changes = []
        for change in changes_detected:
            if change['type'] in ['added', 'removed']:
                meaningful_changes.append(change)
            elif change['type'] == 'updated':
                # Only include updates that aren't just metadata changes
                meaningful_fields = [f for f in change['fields'] 
                                   if f not in {'added', 'updated', 'guid', 'More_info_URL', 'SourceOf'}]
                if meaningful_fields:
                    change['fields'] = meaningful_fields  # Update to show only meaningful fields
                    meaningful_changes.append(change)
        
        if meaningful_changes:
            update_persistent_changelog(meaningful_changes, today, detection_date=today)
            logging.info(f"Updated persistent changelog with {len(meaningful_changes)} meaningful changes.")
        else:
            logging.info("No meaningful changes detected (only metadata/timestamp changes).")
    else:
        logging.info("No changes detected.")
    
    conn.commit()

    # Always generate docs since they're gitignored and needed for deployment
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    substances_dir = docs_dir / "substances"
    substances_dir.mkdir(exist_ok=True)
    json_path = docs_dir / "data.json"
    c.execute(f'SELECT {unique_cols}, added, updated FROM substances')
    rows = c.fetchall()
    all_cols = columns + ["added", "updated"]
    data = [dict(zip(all_cols, row)) for row in rows]
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logging.info(f"Wrote {len(data)} substances to docs/data.json.")

    # Use generation module for page and changelog creation
    generation.generate_substance_pages(data, columns, substances_dir)
    logging.info("Generated substance pages.")
    generation.generate_substances_index(data, columns, docs_dir)
    logging.info("Generated substances index.")
    generation.generate_changelog(data, columns, docs_dir)
    logging.info("Generated changelog page.")

    conn.close()
    logging.info("Closed SQLite connection. Script complete.")

if __name__ == "__main__":
    main()
