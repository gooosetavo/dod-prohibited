
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


def update_persistent_changelog(changes_detected, today):
    """Update the persistent changelog file that gets committed to git."""
    changelog_file = Path("CHANGELOG.md")
    
    if not changelog_file.exists():
        with open(changelog_file, "w", encoding="utf-8") as f:
            f.write("# Changelog\n\n")
            f.write("All notable changes to the DoD prohibited substances list will be documented in this file.\n\n")
        logging.info("Created new CHANGELOG.md file.")
    
    # Read existing changelog
    with open(changelog_file, "r", encoding="utf-8") as f:
        existing_content = f.read()
    
    # Prepare new entry
    new_entry = f"## {today}\n\n"
    logging.info(f"Preparing changelog entry for {today}.")
    
    new_substances = [c for c in changes_detected if c['type'] == 'added']
    updated_substances = [c for c in changes_detected if c['type'] == 'updated']
    
    if new_substances:
        new_entry += "### New Substances Added\n\n"
        for change in new_substances:
            new_entry += f"- **{change['name']}**\n"
        logging.info(f"Added {len(new_substances)} new substances to changelog.")
        new_entry += "\n"
    
    if updated_substances:
        new_entry += "### Substances Modified\n\n"
        for change in updated_substances:
            if change['fields']:
                field_list = ", ".join(f"`{field}`" for field in change['fields'])
                new_entry += f"- **{change['name']}:** Updated {field_list}\n"
            else:
                new_entry += f"- **{change['name']}:** Updated\n"
        logging.info(f"Updated {len(updated_substances)} substances in changelog.")
        new_entry += "\n"
    
    # Insert new entry after the header
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
    
    # Insert new entry
    new_lines = lines[:header_end] + new_entry.rstrip().split('\n') + [''] + lines[header_end:]
    
    # Write back
    with open(changelog_file, "w", encoding="utf-8") as f:
        f.write('\n'.join(new_lines))


def load_previous_data_from_git():
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
            # Convert to dict keyed by substance_key for easy lookup
            previous_dict = {}
            for item in data:
                # Recreate the same key logic
                columns = list(item.keys())
                # Remove added/updated if present
                data_columns = [col for col in columns if col not in ['added', 'updated']]
                if len(data_columns) >= 2:
                    key = '|'.join(str(item.get(col, '')) for col in data_columns[:2])
                    previous_dict[key] = item
            logging.info("Loaded previous data.json from git history.")
            return previous_dict
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
    previous_data = load_previous_data_from_git()
    
    changes_detected = []
    
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
        
        placeholders = ", ".join(["?"] * len(columns))
        sql = f'''
            INSERT INTO substances ({unique_cols}, added, updated)
            VALUES ({placeholders}, ?, ?)
        '''
        c.execute(sql, (*values, now, now))
        
        # Check if this substance is new or changed compared to git history
        if previous_data is not None:
            prev_substance = previous_data.get(substance_key)
            if prev_substance is None:
                # New substance
                changes_detected.append({
                    'type': 'added',
                    'key': substance_key,
                    'name': substance_name,
                    'fields': []
                })
                logging.debug(f"Detected new substance: {substance_name}")
            else:
                # Check for changes
                changed_fields = []
                current_values = dict(zip(columns, values))
                for col in columns:
                    if current_values.get(col) != prev_substance.get(col):
                        changed_fields.append(col)
                if changed_fields:
                    changes_detected.append({
                        'type': 'updated',
                        'key': substance_key,
                        'name': substance_name,
                        'fields': changed_fields
                    })
                    logging.debug(f"Detected updated substance: {substance_name} (fields: {changed_fields})")
    
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
        update_persistent_changelog(changes_detected, today)
        logging.info("Updated persistent changelog.")
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
