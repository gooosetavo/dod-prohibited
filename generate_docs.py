
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
    generate_docs_force: str = "0"
    
    @property
    def github_url(self) -> str:
        return f"https://github.com/{self.github_owner}/{self.github_repo}"
    
    @property
    def should_generate_docs(self) -> bool:
        """Determine if docs should be generated based on branch and environment."""
        branch = os.environ.get("GITHUB_REF", "") or os.environ.get("BRANCH", "")
        force = os.environ.get("DOD_PROHIBITED_GENERATE_DOCS", "0") == "1"
        is_gh_pages = branch.endswith("/gh-pages") or branch == "gh-pages"
        return is_gh_pages or force



# Configure logging for GitHub Actions (stdout, INFO level by default)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler()]
)

settings = Settings()


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
    
    # Group changes by their source date
    changes_by_date = {}
    computed_changes = []
    
    for change in changes_detected:
        if change['type'] == 'added' and 'source_date' in change:
            # Use self-reported date from the substance data
            date_key = change['source_date']
            if date_key not in changes_by_date:
                changes_by_date[date_key] = {'added': [], 'updated': [], 'removed': []}
            changes_by_date[date_key]['added'].append(change)
        elif change['type'] in ['removed', 'updated']:
            # Use computed detection date for our analysis
            computed_changes.append(change)
        else:
            # Fallback to today's date
            if today not in changes_by_date:
                changes_by_date[today] = {'added': [], 'updated': [], 'removed': []}
            changes_by_date[today][change['type']].append(change)
    
    # Add computed changes to detection date
    detection_date = detection_date or today
    if computed_changes:
        if detection_date not in changes_by_date:
            changes_by_date[detection_date] = {'added': [], 'updated': [], 'removed': []}
        for change in computed_changes:
            changes_by_date[detection_date][change['type']].append(change)
    
    # Generate changelog entries for each date
    new_entries = []
    for date_key in sorted(changes_by_date.keys(), reverse=True):
        date_changes = changes_by_date[date_key]
        
        new_entry = f"## {date_key}\n\n"
        has_content = False
        
        # New substances (from self-reported dates)
        if date_changes['added']:
            new_entry += "### New Substances Added\n\n"
            for change in date_changes['added']:
                new_entry += f"- **{change['name']}**"
                if 'source_date' in change and change['source_date'] != date_key:
                    new_entry += f" (source date: {change['source_date']})"
                new_entry += "\n"
            new_entry += "\n"
            has_content = True
        
        # Modified substances (from our detection)
        if date_changes['updated']:
            new_entry += "### Substances Modified\n\n"
            new_entry += "*Changes detected through data comparison*\n\n"
            for change in date_changes['updated']:
                if change['fields']:
                    field_list = ", ".join(f"`{field}`" for field in change['fields'])
                    new_entry += f"- **{change['name']}:** Updated {field_list}\n"
                else:
                    new_entry += f"- **{change['name']}:** Updated\n"
            new_entry += "\n"
            has_content = True
        
        # Removed substances (from our detection)
        if date_changes['removed']:
            new_entry += "### Substances Removed\n\n"
            new_entry += "*Removals detected through data comparison*\n\n"
            for change in date_changes['removed']:
                new_entry += f"- **{change['name']}**\n"
            new_entry += "\n"
            has_content = True
        
        if has_content:
            new_entries.append(new_entry.rstrip())
            
    if new_entries:
        # Prepare combined new entry
        combined_entry = "\n\n".join(new_entries) + "\n\n"
        
        # Insert new entries after the header
        lines = existing_content.split('\n')
        header_end = 0
        for i, line in enumerate(lines):
            if line.startswith('# ') and i == 0:
                continue
            elif line.strip() == "":
                continue
            elif not line.startswith('#') and line.strip():
                header_end = i
                break
            elif line.startswith('## '):
                header_end = i
                break
        
        # Insert new entries
        new_lines = lines[:header_end] + combined_entry.rstrip().split('\n') + [''] + lines[header_end:]
        
        # Write back
        with open(changelog_file, "w", encoding="utf-8") as f:
            f.write('\n'.join(new_lines))
        
        total_changes = sum(len(changes_by_date[d]['added']) + len(changes_by_date[d]['updated']) + len(changes_by_date[d]['removed']) for d in changes_by_date)
        logging.info(f"Updated changelog with {total_changes} changes across {len(changes_by_date)} date(s).")


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
                # Use the same key logic as current data - first two columns of current data
                if len(current_columns) >= 2:
                    key = '|'.join(str(item.get(col, '')) for col in current_columns[:2])
                    previous_dict[key] = item
                else:
                    # Fallback to all available fields
                    key = '|'.join(str(item.get(col, '')) for col in sorted(item.keys()) if col not in ['added', 'updated'])
                    previous_dict[key] = item
                    
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
        
        # Create a unique key and readable name
        substance_key = '|'.join(str(row.get(col, '')) for col in columns[:2])
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

    # Only generate docs if on gh-pages branch or DOD_PROHIBITED_GENERATE_DOCS=1
    if settings.should_generate_docs:
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
    else:
        logging.info("Skipping docs/ generation: not on gh-pages branch and not forced.")

    conn.close()
    logging.info("Closed SQLite connection. Script complete.")

if __name__ == "__main__":
    main()
