import subprocess
import logging
from retrieval import fetch_drupal_settings
from parsing import parse_prohibited_list
import generation
import sqlite3
from pathlib import Path
import json
from datetime import datetime, timezone
from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import Optional
from changelog import (
    parse_existing_changelog_entries,
    update_persistent_changelog,
    merge_changes_for_date,
    generate_changelog_content_for_date,
    find_insert_position,
    get_substance_source_date,
    get_substance_last_modified,
    has_substance_been_modified_since,
)


class Settings(BaseSettings):
    """Configuration settings for the DoD prohibited substances project."""

    model_config = ConfigDict(env_prefix="DOD_", case_sensitive=False)

    # Data source
    source_url: str = (
        "https://www.opss.org/dod-prohibited-dietary-supplement-ingredients"
    )

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
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)

settings = Settings()




















def load_previous_data_from_git(current_columns):
    """Load the previous version of data.json from git history for comparison."""
    try:
        # Try to get the previous version of docs/data.json
        result = subprocess.run(
            ["git", "show", "HEAD~1:docs/data.json"],
            capture_output=True,
            text=True,
            cwd=Path.cwd(),
        )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            previous_dict = {}
            previous_count = len(data)

            for item in data:
                # Use the same key logic as current data processing
                substance_key = None

                # Try guid first (most unique)
                guid = item.get("guid") or item.get("Guid")
                if guid and str(guid).strip():
                    substance_key = f"guid:{guid}"
                # Try Name second
                elif item.get("Name") and str(item["Name"]).strip():
                    substance_key = f"name:{item['Name']}"
                # Try searchable_name third
                elif (
                    item.get("searchable_name") and str(item["searchable_name"]).strip()
                ):
                    substance_key = f"search:{item['searchable_name']}"
                else:
                    # Fallback: use meaningful columns that are more likely to have unique values
                    meaningful_cols = ["Name", "searchable_name", "Reason", "guid"]
                    available_cols = [
                        col
                        for col in meaningful_cols
                        if col in item and str(item[col]).strip()
                    ]
                    if available_cols:
                        substance_key = "|".join(
                            str(item.get(col, "")) for col in available_cols[:2]
                        )
                    else:
                        # Last resort: use all non-empty values from the item
                        non_empty_vals = [
                            str(val)
                            for val in item.values()
                            if val
                            and str(val).strip()
                            and str(val) not in ["[]", "{}", "nan"]
                        ]
                        substance_key = (
                            "|".join(non_empty_vals[:3])
                            if non_empty_vals
                            else str(hash(str(item)))
                        )

                previous_dict[substance_key] = item

            logging.info(
                f"Loaded previous data.json from git history: {previous_count} substances"
            )
            return previous_dict, previous_count
    except (
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        FileNotFoundError,
    ) as e:
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
    c.execute("""CREATE TABLE IF NOT EXISTS substances (
        id INTEGER PRIMARY KEY AUTOINCREMENT
    )""")
    logging.debug("Ensured substances table exists.")
    c.execute("PRAGMA table_info(substances)")
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
        c.execute("DROP INDEX IF EXISTS idx_unique_substance")
        c.execute(
            f"CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_substance ON substances ({unique_cols})"
        )
        logging.debug("Ensured unique index on substances table.")
    except Exception as e:
        logging.warning(f"Could not create unique index: {e}")

    # Create changes table to track daily summaries (but use git for persistence)
    c.execute("""
        CREATE TABLE IF NOT EXISTS substance_changes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            substance_key TEXT,
            substance_name TEXT,
            change_date TEXT,
            change_type TEXT, -- 'added' or 'updated'
            fields_changed TEXT, -- JSON list of field names that changed
            UNIQUE(substance_key, change_date, change_type)
        )
    """)
    logging.debug("Ensured substance_changes table exists.")

    # Clear the table to avoid duplicates on each run
    c.execute("DELETE FROM substances")
    c.execute("DELETE FROM substance_changes")
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
    logging.info(
        f"Current substances: {current_count}, Previous substances: {previous_count}"
    )

    # Log first few substance keys for debugging
    sample_keys = []
    for i, row in df.head(3).iterrows():
        # Use the same key generation logic as the main loop
        values = []
        for col in columns:
            val = row.get(col, None)
            if isinstance(val, (list, dict)):
                val = json.dumps(val, ensure_ascii=False)
            values.append(val)

        current_row_dict = dict(zip(columns, values))
        substance_key = None

        # Try guid first (most unique)
        guid = current_row_dict.get("guid") or current_row_dict.get("Guid")
        if guid and str(guid).strip():
            substance_key = f"guid:{guid}"
        # Try Name second
        elif current_row_dict.get("Name") and str(current_row_dict["Name"]).strip():
            substance_key = f"name:{current_row_dict['Name']}"
        # Try searchable_name third
        elif (
            current_row_dict.get("searchable_name")
            and str(current_row_dict["searchable_name"]).strip()
        ):
            substance_key = f"search:{current_row_dict['searchable_name']}"
        else:
            substance_key = f"fallback_{i}"

        sample_keys.append(substance_key[:100])  # Truncate for readability
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
        guid = current_row_dict.get("guid") or current_row_dict.get("Guid")
        if guid and str(guid).strip():
            substance_key = f"guid:{guid}"
        # Try Name second
        elif current_row_dict.get("Name") and str(current_row_dict["Name"]).strip():
            substance_key = f"name:{current_row_dict['Name']}"
        # Try searchable_name third
        elif (
            current_row_dict.get("searchable_name")
            and str(current_row_dict["searchable_name"]).strip()
        ):
            substance_key = f"search:{current_row_dict['searchable_name']}"
        else:
            # Fallback: use meaningful columns that are more likely to have unique values
            meaningful_cols = ["Name", "searchable_name", "Reason", "guid"]
            available_cols = [
                col
                for col in meaningful_cols
                if col in current_row_dict and str(current_row_dict[col]).strip()
            ]
            if available_cols:
                substance_key = "|".join(
                    str(current_row_dict.get(col, "")) for col in available_cols[:2]
                )
            else:
                # Last resort: use all non-empty values
                non_empty_vals = [
                    str(val)
                    for val in values
                    if val and str(val).strip() and str(val) not in ["[]", "{}", "nan"]
                ]
                substance_key = (
                    "|".join(non_empty_vals[:3]) if non_empty_vals else f"row_{_}"
                )

        substance_name = (
            row.get("Name") or row.get("ingredient") or row.get("name") or substance_key
        )
        current_keys.add(substance_key)

        # Check if this substance is new or changed compared to git history
        added_date = now  # Default for new substances
        if previous_data is not None:
            prev_substance = previous_data.get(substance_key)
            if prev_substance is not None:
                # Existing substance - preserve original added date
                existing_added = prev_substance.get("added")
                if existing_added:
                    added_date = existing_added

        placeholders = ", ".join(["?"] * len(columns))
        sql = f"""
            INSERT INTO substances ({unique_cols}, added, updated)
            VALUES ({placeholders}, ?, ?)
        """
        c.execute(sql, (*values, added_date, now))

        # Check if this substance is new or changed compared to git history
        if previous_data is not None:
            prev_substance = previous_data.get(substance_key)
            if prev_substance is None:
                # New substance - use self-reported date if available
                current_row_dict = dict(zip(columns, values))
                source_date = get_substance_source_date(current_row_dict)

                change_data = {
                    "type": "added",
                    "key": substance_key,
                    "name": substance_name,
                    "fields": [],
                }

                if source_date:
                    change_data["source_date"] = source_date
                    logging.debug(
                        f"NEW SUBSTANCE: {substance_name} (source date: {source_date})"
                    )
                else:
                    logging.debug(
                        f"NEW SUBSTANCE: {substance_name} (detection date: {today})"
                    )

                changes_detected.append(change_data)
            else:
                # Check if substance was modified using timestamp
                current_row_dict = dict(zip(columns, values))
                current_timestamp = get_substance_last_modified(current_row_dict)
                prev_timestamp = get_substance_last_modified(prev_substance)

                if current_timestamp > prev_timestamp:
                    # Substance was modified - check what fields actually changed
                    changed_fields = []
                    ignore_fields = {
                        "added",
                        "updated",
                        "guid",
                        "More_info_URL",
                        "SourceOf",
                    }

                    for col in columns:
                        if col in ignore_fields:
                            continue

                        current_val = current_row_dict.get(col)
                        prev_val = prev_substance.get(col)

                        if current_val != prev_val:
                            # Special handling for JSON fields
                            if isinstance(current_val, str) and isinstance(
                                prev_val, str
                            ):
                                try:
                                    import ast

                                    curr_parsed = (
                                        ast.literal_eval(current_val)
                                        if current_val
                                        else None
                                    )
                                    prev_parsed = (
                                        ast.literal_eval(prev_val) if prev_val else None
                                    )
                                    if curr_parsed != prev_parsed:
                                        changed_fields.append(col)
                                except:
                                    if current_val != prev_val:
                                        changed_fields.append(col)
                            else:
                                changed_fields.append(col)

                    if changed_fields:
                        changes_detected.append(
                            {
                                "type": "updated",
                                "key": substance_key,
                                "name": substance_name,
                                "fields": changed_fields,
                                "detection_date": today,
                            }
                        )
                        logging.debug(
                            f"UPDATED SUBSTANCE: {substance_name} (timestamp: {current_timestamp} > {prev_timestamp}, fields: {changed_fields}, detected: {today})"
                        )

    # Check for removed substances
    if previous_data is not None:
        previous_keys = set(previous_data.keys())
        removed_keys = previous_keys - current_keys
        for removed_key in removed_keys:
            removed_substance = previous_data[removed_key]
            removed_name = (
                removed_substance.get("Name")
                or removed_substance.get("ingredient")
                or removed_substance.get("name")
                or removed_key
            )
            changes_detected.append(
                {
                    "type": "removed",
                    "key": removed_key,
                    "name": removed_name,
                    "fields": [],
                    "detection_date": today,
                }
            )
            logging.debug(
                f"REMOVED SUBSTANCE: {removed_name} (key: {removed_key[:50]}...)"
            )

        # Log summary of changes
        new_count = len([c for c in changes_detected if c["type"] == "added"])
        updated_count = len([c for c in changes_detected if c["type"] == "updated"])
        removed_count = len([c for c in changes_detected if c["type"] == "removed"])
        logging.info(
            f"Change summary: {new_count} added, {updated_count} updated, {removed_count} removed"
        )
        logging.info(
            f"Net change: {current_count - previous_count} (from {previous_count} to {current_count})"
        )

    # Store changes in database for changelog generation
    for change in changes_detected:
        c.execute(
            """
            INSERT OR REPLACE INTO substance_changes 
            (substance_key, substance_name, change_date, change_type, fields_changed)
            VALUES (?, ?, ?, ?, ?)
        """,
            (
                change["key"],
                change["name"],
                today,
                change["type"],
                json.dumps(change["fields"]),
            ),
        )
    logging.info(f"Detected {len(changes_detected)} changes.")

    # Also update persistent changelog file that gets committed to git
    if changes_detected:
        # Filter out changes that are only metadata/timestamp changes
        meaningful_changes = []
        for change in changes_detected:
            if change["type"] in ["added", "removed"]:
                meaningful_changes.append(change)
            elif change["type"] == "updated":
                # Only include updates that aren't just metadata changes
                meaningful_fields = [
                    f
                    for f in change["fields"]
                    if f
                    not in {"added", "updated", "guid", "More_info_URL", "SourceOf"}
                ]
                if meaningful_fields:
                    change["fields"] = (
                        meaningful_fields  # Update to show only meaningful fields
                    )
                    meaningful_changes.append(change)

        if meaningful_changes:
            update_persistent_changelog(meaningful_changes, today, detection_date=today)
            logging.info(
                f"Updated persistent changelog with {len(meaningful_changes)} meaningful changes."
            )
        else:
            logging.info(
                "No meaningful changes detected (only metadata/timestamp changes)."
            )
    else:
        logging.info("No changes detected.")

    conn.commit()

    # Always generate docs since they're gitignored and needed for deployment
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    substances_dir = docs_dir / "substances"
    substances_dir.mkdir(exist_ok=True)
    json_path = docs_dir / "data.json"
    c.execute(f"SELECT {unique_cols}, added, updated FROM substances")
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
