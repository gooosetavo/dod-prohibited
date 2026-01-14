import subprocess
import logging
from retrieval import fetch_drupal_settings
from parsing import parse_prohibited_list
import generation
import sqlite3
from pathlib import Path
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set, Tuple, Union, Any
from changelog import (
    update_persistent_changelog,
    get_substance_source_date,
    get_substance_last_modified,
    has_substance_been_modified_since,
)


@dataclass
class Settings:
    """Configuration settings for the DoD prohibited substances project."""

    # Data source
    source_url: str = (
        "https://www.opss.org/dod-prohibited-dietary-supplement-ingredients"
    )
    """URL source for DoD prohibited dietary supplement ingredients data."""

    # GitHub configuration
    github_owner: str = "gooosetavo"
    """GitHub repository owner for the project."""
    
    github_repo: str = "dod-prohibited"
    """GitHub repository name for the project."""

    # Site configuration
    site_title: str = "DoD Prohibited Dietary Supplement Ingredients"
    """Title displayed on the generated documentation site."""
    
    site_description: str = "A searchable, browsable, and regularly updated list of substances prohibited by the Department of Defense (DoD) for use in dietary supplements."
    """Description displayed on the generated documentation site."""
    
    db_file: str = "prohibited.db"
    """SQLite database file name for storing substance data."""
    
    # Environment overrides
    github_ref: Optional[str] = None
    """GitHub reference (branch/tag) for deployment, typically set via environment."""
    
    branch: Optional[str] = None
    """Git branch name, typically set via environment variables."""
    
    use_unii_data: bool = True
    """Whether to include UNII (Unique Ingredient Identifier) data in substance pages."""

    @property
    def github_url(self) -> str:
        return f"https://github.com/{self.github_owner}/{self.github_repo}"

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables with DOD_ prefix."""
        import os
        
        kwargs = {}
        for field_name in cls.__dataclass_fields__:
            env_name = f"DOD_{field_name.upper()}"
            if env_name in os.environ:
                kwargs[field_name] = os.environ[env_name]
        
        return cls(**kwargs)


@dataclass
class Substance:
    """Represents a prohibited substance with its attributes and associated logic."""
    
    # Core data attributes (dynamically populated from DataFrame columns)
    data: Dict[str, Any] = field(default_factory=dict)
    """Dictionary containing all substance data fields from the source (e.g., Name, Reason, Classifications, etc.)."""
    
    # Metadata
    added_date: Optional[str] = None
    """Date when this substance was first added to the database (ISO format string)."""
    
    updated_date: Optional[str] = None
    """Date when this substance was last updated in the database (ISO format string)."""
    
    # Computed fields
    key: Optional[str] = field(default=None, init=False)
    """Unique identifier key generated from substance data (computed after initialization)."""
    
    name: Optional[str] = field(default=None, init=False)
    """Display name extracted from substance data (computed after initialization)."""
    
    def __post_init__(self):
        """Initialize computed fields after creation."""
        self.key = self._generate_key()
        self.name = self._extract_name()
    
    @classmethod
    def from_row(cls, row_data: Dict[str, Any], columns: List[str], 
                 added_date: Optional[str] = None, updated_date: Optional[str] = None) -> "Substance":
        """Create a Substance from a DataFrame row."""
        # Convert lists/dicts to JSON strings for storage
        processed_data = {}
        for col in columns:
            val = row_data.get(col, None)
            if isinstance(val, (list, dict)):
                val = json.dumps(val, ensure_ascii=False)
            processed_data[col] = val
        
        return cls(
            data=processed_data,
            added_date=added_date,
            updated_date=updated_date
        )
    
    @classmethod
    def from_dict(cls, data_dict: Dict[str, Any]) -> "Substance":
        """Create a Substance from a dictionary (e.g., from database)."""
        # Separate metadata from data
        added_date = data_dict.pop("added", None)
        updated_date = data_dict.pop("updated", None)
        
        return cls(
            data=data_dict.copy(),
            added_date=added_date,
            updated_date=updated_date
        )
    
    def _generate_key(self) -> str:
        """Generate a unique key for this substance based on available data."""
        # Try guid first (most unique)
        guid = self.data.get("guid") or self.data.get("Guid")
        if guid and str(guid).strip():
            return f"guid:{guid}"
        
        # Try Name second
        if self.data.get("Name") and str(self.data["Name"]).strip():
            return f"name:{self.data['Name']}"
        
        # Try searchable_name third
        if (self.data.get("searchable_name") and str(self.data["searchable_name"]).strip()):
            return f"search:{self.data['searchable_name']}"
        
        # Fallback: use meaningful columns
        meaningful_cols = ["Name", "searchable_name", "Reason", "guid"]
        available_cols = [
            col for col in meaningful_cols
            if col in self.data and str(self.data[col]).strip()
        ]
        if available_cols:
            return "|".join(str(self.data.get(col, "")) for col in available_cols[:2])
        
        # Last resort: use all non-empty values
        non_empty_vals = [
            str(val) for val in self.data.values()
            if val and str(val).strip() and str(val) not in ["[]", "{}", "nan"]
        ]
        return "|".join(non_empty_vals[:3]) if non_empty_vals else "unknown"
    
    def _extract_name(self) -> str:
        """Extract a display name for this substance."""
        return (
            self.data.get("Name") or 
            self.data.get("ingredient") or 
            self.data.get("name") or 
            self.key or
            "Unknown Substance"
        )
    
    def get_source_date(self) -> Optional[str]:
        """Get the source date when this substance was actually added/modified."""
        return get_substance_source_date(self.data)
    
    def get_last_modified_timestamp(self) -> int:
        """Get the last modified timestamp from substance data."""
        # First try the updated field in the data dict
        timestamp = get_substance_last_modified(self.data)
        if timestamp > 0:
            return timestamp
        
        # Fallback: check if updated data is stored in updated_date attribute
        if hasattr(self, 'updated_date') and self.updated_date:
            temp_data = {'updated': self.updated_date}
            return get_substance_last_modified(temp_data)
        
        return 0
    
    def was_modified_since(self, timestamp_threshold: int) -> bool:
        """Check if this substance was modified after a given timestamp."""
        return has_substance_been_modified_since(self.data, timestamp_threshold)
    
    def compare_with(self, other: "Substance", ignore_fields: Set[str] = None) -> List[str]:
        """Compare this substance with another and return list of changed fields."""
        if ignore_fields is None:
            ignore_fields = {"added", "updated", "guid", "More_info_URL", "SourceOf"}
        
        changed_fields = []
        
        # Get all unique fields from both substances
        all_fields = set(self.data.keys()) | set(other.data.keys())
        
        for field in all_fields:
            if field in ignore_fields:
                continue
            
            current_val = self._normalize_value(self.data.get(field))
            other_val = self._normalize_value(other.data.get(field))
            
            if current_val != other_val:
                changed_fields.append(field)
        
        return changed_fields
    
    def _normalize_value(self, value: Any) -> Any:
        """Normalize a value for comparison purposes."""
        # Handle null/None/empty cases
        if value is None or value == "null" or value == "":
            return None
            
        # Handle JSON string fields 
        if isinstance(value, str):
            # Try to parse as JSON if it looks like JSON
            if value.strip().startswith(('[', '{')):
                try:
                    import ast
                    parsed = ast.literal_eval(value)
                    # If it's an empty list or dict, normalize to None
                    if parsed == [] or parsed == {}:
                        return None
                    return parsed
                except:
                    # If parsing fails, keep as string
                    pass
            
            # Convert string representations of null to None
            if value.strip().lower() in ('null', 'none', ''):
                return None
                
        return value
    
    def to_db_values(self, columns: List[str]) -> Tuple[List[Any], str, str]:
        """Convert substance to database values format."""
        values = [self.data.get(col) for col in columns]
        return values, self.added_date or "", self.updated_date or ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert substance to dictionary format for JSON serialization."""
        result = self.data.copy()
        if self.added_date:
            result["added"] = self.added_date
        if self.updated_date:
            result["updated"] = self.updated_date
        return result
    
    def __str__(self) -> str:
        return f"Substance(name='{self.name}', key='{self.key}')"
    
    def __repr__(self) -> str:
        return f"Substance(name='{self.name}', key='{self.key}', data_fields={list(self.data.keys())})"


class SubstanceDatabase:
    """Manages SQLite database operations for substance tracking."""
    
    def __init__(self, db_path: Union[str, Path] = "prohibited.db"):
        """Initialize database connection and setup tables."""
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(self.db_path)
        self.cursor = self.conn.cursor()
        self.columns: List[str] = []
        logging.info(f"Connected to SQLite database: {self.db_path}")
    
    def setup_tables(self, columns: List[str]) -> None:
        """Create and configure database tables with dynamic columns."""
        self.columns = columns
        
        # Create main substances table
        self.cursor.execute("""CREATE TABLE IF NOT EXISTS substances (
            id INTEGER PRIMARY KEY AUTOINCREMENT
        )""")
        logging.debug("Ensured substances table exists.")
        
        # Add columns dynamically
        self._add_missing_columns(columns + ["added", "updated"])
        
        # Create unique index
        self._create_unique_index(columns)
        
        # Create changes tracking table
        self._create_changes_table()
        
        logging.debug("Database tables setup completed.")
    
    def _add_missing_columns(self, columns: List[str]) -> None:
        """Add any missing columns to the substances table."""
        self.cursor.execute("PRAGMA table_info(substances)")
        existing_cols = {row[1] for row in self.cursor.fetchall()}
        
        for col in columns:
            if col not in existing_cols:
                try:
                    self.cursor.execute(f'ALTER TABLE substances ADD COLUMN "{col}" TEXT')
                    logging.debug(f"Added column '{col}' to substances table.")
                except sqlite3.OperationalError:
                    logging.debug(f"Column '{col}' already exists in substances table.")
    
    def _create_unique_index(self, columns: List[str]) -> None:
        """Create unique index on data columns."""
        unique_cols = ", ".join([f'"{col}"' for col in columns])
        try:
            self.cursor.execute("DROP INDEX IF EXISTS idx_unique_substance")
            self.cursor.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_substance ON substances ({unique_cols})"
            )
            logging.debug("Created unique index on substances table.")
        except Exception as e:
            logging.warning(f"Could not create unique index: {e}")
    
    def _create_changes_table(self) -> None:
        """Create table for tracking substance changes."""
        self.cursor.execute("""
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
    
    def clear_tables(self) -> None:
        """Clear all data from tables to avoid duplicates."""
        self.cursor.execute("DELETE FROM substances")
        self.cursor.execute("DELETE FROM substance_changes")
        logging.debug("Cleared substances and substance_changes tables.")
    
    def insert_substance(self, substance: Substance) -> None:
        """Insert a substance record into the database."""
        if not self.columns:
            raise ValueError("Columns not set. Call setup_tables() first.")
        
        unique_cols = ", ".join([f'"{col}"' for col in self.columns])
        placeholders = ", ".join(["?"] * len(self.columns))
        sql = f"""
            INSERT INTO substances ({unique_cols}, added, updated)
            VALUES ({placeholders}, ?, ?)
        """
        values, added_date, updated_date = substance.to_db_values(self.columns)
        self.cursor.execute(sql, (*values, added_date, updated_date))
    
    def record_change(self, substance_key: str, substance_name: str, change_date: str, 
                     change_type: str, fields_changed: List[str]) -> None:
        """Record a substance change in the changes table."""
        self.cursor.execute("""
            INSERT INTO substance_changes 
            (substance_key, substance_name, change_date, change_type, fields_changed)
            VALUES (?, ?, ?, ?, ?)
        """, (substance_key, substance_name, change_date, change_type, 
              json.dumps(fields_changed)))
    
    def get_all_substances(self) -> List[Dict]:
        """Retrieve all substances from the database."""
        if not self.columns:
            raise ValueError("Columns not set. Call setup_tables() first.")
        
        unique_cols = ", ".join([f'"{col}"' for col in self.columns])
        self.cursor.execute(f"SELECT {unique_cols}, added, updated FROM substances")
        rows = self.cursor.fetchall()
        all_cols = self.columns + ["added", "updated"]
        return [dict(zip(all_cols, row)) for row in rows]
    
    def commit(self) -> None:
        """Commit all pending transactions."""
        self.conn.commit()
    
    def close(self) -> None:
        """Close the database connection."""
        self.conn.close()
        logging.info("Closed SQLite connection.")


# Configure logging for GitHub Actions (stdout, INFO level by default)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)

settings = Settings.from_env()




















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

    # Setup database
    db = SubstanceDatabase()
    columns = list(df.columns)
    db.setup_tables(columns)
    db.clear_tables()

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
        substance = Substance.from_row(dict(row), columns)
        sample_keys.append(substance.key[:100])  # Truncate for readability
    logging.info(f"Sample current keys: {sample_keys}")

    if previous_data:
        sample_prev_keys = list(previous_data.keys())[:3]
        logging.info(f"Sample previous keys: {[k[:100] for k in sample_prev_keys]}")

    changes_detected = []
    current_keys = set()

    for _, row in df.iterrows():
        # Create substance object from row data
        substance = Substance.from_row(dict(row), columns)  # Don't set updated_date yet
        current_keys.add(substance.key)

        # Check if this substance is new or changed compared to git history
        added_date = now  # Default for new substances
        if previous_data is not None:
            prev_substance_data = previous_data.get(substance.key)
            if prev_substance_data is not None:
                # Existing substance - preserve original added date
                existing_added = prev_substance_data.get("added")
                if existing_added:
                    added_date = existing_added

        # Set the added date and updated timestamp, then insert into database
        substance.added_date = added_date
        substance.updated_date = now
        db.insert_substance(substance)

        # Check if this substance is new or changed compared to git history
        if previous_data is not None:
            prev_substance_data = previous_data.get(substance.key)
            if prev_substance_data is None:
                # New substance - use self-reported date if available
                source_date = substance.get_source_date()

                change_data = {
                    "type": "added",
                    "key": substance.key,
                    "name": substance.name,
                    "fields": [],
                }

                if source_date:
                    change_data["source_date"] = source_date
                    logging.debug(
                        f"NEW SUBSTANCE: {substance.name} (source date: {source_date})"
                    )
                else:
                    logging.debug(
                        f"NEW SUBSTANCE: {substance.name} (detection date: {today})"
                    )

                changes_detected.append(change_data)
            else:
                # Check if substance was modified using timestamp
                prev_substance = Substance.from_dict(prev_substance_data)
                current_timestamp = substance.get_last_modified_timestamp()
                prev_timestamp = prev_substance.get_last_modified_timestamp()

                # Log timestamp parsing results for debugging
                logging.debug(f"Timestamp check for {substance.name}: current={current_timestamp}, previous={prev_timestamp}")

                # Only consider a substance modified if we have valid timestamps AND current > previous
                # If either timestamp is 0 (parsing failed), err on the side of "not modified"
                if (current_timestamp > 0 and prev_timestamp > 0 and 
                    current_timestamp > prev_timestamp):
                    
                    # Substance was modified - check what fields actually changed
                    ignore_fields = {
                        "added",
                        "updated",
                        "guid",
                        "More_info_URL",
                        "SourceOf",
                    }
                    changed_fields = substance.compare_with(prev_substance, ignore_fields)

                    if changed_fields:
                        changes_detected.append(
                            {
                                "type": "updated",
                                "key": substance.key,
                                "name": substance.name,
                                "fields": changed_fields,
                                "detection_date": today,
                            }
                        )
                        logging.debug(
                            f"UPDATED SUBSTANCE: {substance.name} (timestamp: {current_timestamp} > {prev_timestamp}, fields: {changed_fields}, detected: {today})"
                        )
                elif current_timestamp == 0 or prev_timestamp == 0:
                    logging.debug(f"Skipping modification check for {substance.name} due to unparseable timestamp (current={current_timestamp}, previous={prev_timestamp})")
                else:
                    logging.debug(f"No modification detected for {substance.name} (timestamp {current_timestamp} <= {prev_timestamp})")

    # Check for removed substances
    if previous_data is not None:
        previous_keys = set(previous_data.keys())
        removed_keys = previous_keys - current_keys
        for removed_key in removed_keys:
            removed_substance_data = previous_data[removed_key]
            removed_substance = Substance.from_dict(removed_substance_data)
            changes_detected.append(
                {
                    "type": "removed",
                    "key": removed_substance.key,
                    "name": removed_substance.name,
                    "fields": [],
                    "detection_date": today,
                }
            )
            logging.debug(
                f"REMOVED SUBSTANCE: {removed_substance.name} (key: {removed_substance.key[:50]}...)"
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
        db.record_change(
            change["key"],
            change["name"],
            today,
            change["type"],
            change["fields"]
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

    db.commit()

    # Always generate docs since they're gitignored and needed for deployment
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    substances_dir = docs_dir / "substances"
    substances_dir.mkdir(exist_ok=True)
    json_path = docs_dir / "data.json"
    
    # Export data from database
    data = db.get_all_substances()
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    logging.info(f"Wrote {len(data)} substances to docs/data.json.")

    # Use generation module for page and changelog creation
    generation.generate_substance_pages(data, columns, substances_dir, settings)
    logging.info("Generated substance pages.")
    generation.generate_substances_index(data, columns, docs_dir)
    logging.info("Generated substances index.")
    generation.generate_changelog(data, columns, docs_dir)
    logging.info("Generated changelog page.")

    db.close()
    logging.info("Script complete.")


if __name__ == "__main__":
    main()
