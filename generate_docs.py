import logging
import dod_prohibited.site_builder as generation
import sqlite3
from pathlib import Path
import json
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set, Tuple, Union, Any
from dod_prohibited.changelog import (
    update_persistent_changelog,
    get_substance_source_date,
    get_substance_last_modified,
    has_substance_been_modified_since,
)
from dod_prohibited.user_agent import RandomUserAgent
from dod_prohibited.loaders import RemoteDataLoader, JsonFileDataLoader

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

    use_git_history: bool = True
    """Whether to use git history for change detection."""

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

    use_pubchem_data: bool = False
    """Whether to fetch PubChem compound properties and embed 3D conformer widgets.
    Requires UNII data. Enable with DOD_USE_PUBCHEM_DATA=true."""

    pubchem_cache_dir: str = ".cache/pubchem"
    """Directory for caching PubChem property JSON files. Can be overridden with DOD_PUBCHEM_CACHE_DIR."""

    include_search_metadata: bool = False
    """Whether to include generated search keywords/tags in substance page frontmatter.
    Disabled by default because the tags: field renders as visible tag chips in Zensical/MkDocs Material.
    Will be removed/deprecated in the future.
    Enable with DOD_INCLUDE_SEARCH_METADATA=true."""
    
    log_level: str = "INFO"
    """Logging level (DEBUG, INFO, WARNING, ERROR). Can be overridden with DOD_LOG_LEVEL environment variable."""
    
    # HTTP configuration
    user_agent: Optional[str] = str(RandomUserAgent())
    """Custom User-Agent header for HTTP requests."""
    
    # Authentication configuration
    auth_token: Optional[str] = None
    """Bearer token for API authentication. Can be overridden with DOD_AUTH_TOKEN environment variable."""
    
    auth_username: Optional[str] = None
    """Username for basic authentication. Can be overridden with DOD_AUTH_USERNAME environment variable."""
    
    auth_password: Optional[str] = None
    """Password for basic authentication. Can be overridden with DOD_AUTH_PASSWORD environment variable."""

    @property
    def github_url(self) -> str:
        return f"https://github.com/{self.github_owner}/{self.github_repo}"
    
    @property
    def logging_level(self) -> int:
        """Convert string log level to logging module constant."""
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO, 
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        return level_map.get(self.log_level.upper(), logging.INFO)

    @classmethod
    def from_env(cls) -> "Settings":
        """Create settings from environment variables with DOD_ prefix."""
        import os
        
        kwargs = {}
        for field_name in cls.__dataclass_fields__:
            env_name = f"DOD_{field_name.upper()}"
            if env_name in os.environ:
                value = os.environ[env_name]
                field_type = cls.__dataclass_fields__[field_name].type
                # Convert to appropriate type
                if field_type == bool:
                    kwargs[field_name] = value.lower() in ('true', '1', 't')
                else:
                    kwargs[field_name] = field_type(value)
        
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

    def is_new_compared_to(self, previous_substances: Dict[str, Dict[str, Any]]) -> bool:
        """
        Check if this substance is new compared to a dictionary of previous substances.

        Args:
            previous_substances: Dictionary mapping substance keys to their data

        Returns:
            True if this is a new substance, False if it existed before
        """
        return self.key not in previous_substances

    def get_change_info(
        self,
        previous_substances: Dict[str, Dict[str, Any]],
        detection_date: str,
        ignore_fields: Set[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get change information for this substance compared to previous version.

        Args:
            previous_substances: Dictionary mapping substance keys to their data
            detection_date: Date when changes were detected (YYYY-MM-DD format)
            ignore_fields: Fields to ignore when comparing (defaults to metadata fields)

        Returns:
            Dictionary with change information, or None if no changes detected:
            - For new substances: {'type': 'added', 'key': ..., 'name': ..., 'source_date': ...}
            - For modified substances: {'type': 'updated', 'key': ..., 'name': ..., 'fields': [...], 'detection_date': ...}
            - For unchanged substances: None
        """
        if ignore_fields is None:
            ignore_fields = {"added", "updated", "guid", "More_info_URL", "SourceOf"}

        prev_substance_data = previous_substances.get(self.key)

        # Case 1: New substance
        if prev_substance_data is None:
            change_data = {
                "type": "added",
                "key": self.key,
                "name": self.name,
                "fields": [],
            }

            # Include self-reported source date if available
            source_date = self.get_source_date()
            if source_date:
                change_data["source_date"] = source_date
                logging.debug(f"NEW SUBSTANCE: {self.name} (source date: {source_date})")
            else:
                logging.debug(f"NEW SUBSTANCE: {self.name} (detection date: {detection_date})")

            return change_data

        # Case 2: Check if existing substance was modified
        prev_substance = Substance.from_dict(prev_substance_data)
        current_timestamp = self.get_last_modified_timestamp()
        prev_timestamp = prev_substance.get_last_modified_timestamp()

        logging.debug(
            f"Timestamp check for {self.name}: current={current_timestamp}, previous={prev_timestamp}"
        )

        # Only consider modified if we have valid timestamps AND current > previous
        if current_timestamp > 0 and prev_timestamp > 0 and current_timestamp > prev_timestamp:
            # Check what fields actually changed
            changed_fields = self.compare_with(prev_substance, ignore_fields)

            if changed_fields:
                logging.debug(
                    f"UPDATED SUBSTANCE: {self.name} "
                    f"(timestamp: {current_timestamp} > {prev_timestamp}, "
                    f"fields: {changed_fields}, detected: {detection_date})"
                )
                return {
                    "type": "updated",
                    "key": self.key,
                    "name": self.name,
                    "fields": changed_fields,
                    "detection_date": detection_date,
                }
        elif current_timestamp == 0 or prev_timestamp == 0:
            logging.debug(
                f"Skipping modification check for {self.name} due to unparseable timestamp "
                f"(current={current_timestamp}, previous={prev_timestamp})"
            )
        else:
            logging.debug(
                f"No modification detected for {self.name} "
                f"(timestamp {current_timestamp} <= {prev_timestamp})"
            )

        # No changes detected
        return None

    def get_preserved_added_date(
        self,
        previous_substances: Dict[str, Dict[str, Any]],
        default_date: str
    ) -> str:
        """
        Get the added date for this substance, preserving the original date if it existed before.

        Args:
            previous_substances: Dictionary mapping substance keys to their data
            default_date: Default date to use for new substances

        Returns:
            The added date (either preserved from previous version or the default)
        """
        prev_substance_data = previous_substances.get(self.key)

        if prev_substance_data is not None:
            # Preserve original added date
            existing_added = prev_substance_data.get("added")
            if existing_added:
                return existing_added

        # New substance - use default date
        return default_date

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
    
    def setup_tables(self, columns: List[str] = None) -> None:
        """Create and configure database tables with dynamic columns."""
        if columns is None:
            columns = self.cursor.execute("PRAGMA table_info(substances)").fetchall()
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
            self.setup_tables()
        
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


settings = Settings.from_env()

# Configure logging with level from settings (can be controlled via DOD_LOG_LEVEL env var)
logging.basicConfig(
    level=settings.logging_level,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
    force=True  # Override any existing configuration
)

logging.info(f"Logging level set to: {settings.log_level}")


def detect_removed_substances(
    current_substances: Dict[str, Substance],
    previous_substances: Dict[str, Dict[str, Any]],
    detection_date: str
) -> List[Dict[str, Any]]:
    """
    Detect substances that were removed (present in previous but not in current).

    Args:
        current_substances: Dictionary mapping current substance keys to Substance objects
        previous_substances: Dictionary mapping previous substance keys to their data
        detection_date: Date when removal was detected (YYYY-MM-DD format)

    Returns:
        List of change dictionaries for removed substances
    """
    removed_changes = []
    current_keys = set(current_substances.keys())
    previous_keys = set(previous_substances.keys())

    removed_keys = previous_keys - current_keys

    for removed_key in removed_keys:
        removed_substance_data = previous_substances[removed_key]
        removed_substance = Substance.from_dict(removed_substance_data)
        removed_changes.append({
            "type": "removed",
            "key": removed_substance.key,
            "name": removed_substance.name,
            "fields": [],
            "detection_date": detection_date,
        })
        logging.debug(f"REMOVED SUBSTANCE: {removed_substance.name} (detected: {detection_date})")

    return removed_changes


def load_previous_data_from_git():
    """Load the previous version of data.json from git history for comparison."""
    # Use the new JsonFileDataLoader with git_revision parameter
    loader = JsonFileDataLoader(
        file_path='docs/data.json',
        git_revision='HEAD~1',
        settings=settings
    )

    data = loader.load()

    if not data:
        return None

    # Build dictionary using substance keys for comparison
    # Use the Substance class to generate keys consistently
    previous_dict = {}
    previous_count = len(data)

    for item in data:
        # Create a temporary Substance object to generate the key
        temp_substance = Substance(data=item)
        previous_dict[temp_substance.key] = item

    logging.info(
        f"Loaded previous data.json from git history: {previous_count} substances"
    )
    return previous_dict, previous_count


def main():
    logging.info("Starting generate_docs.py script.")

    # Use the new RemoteDataLoader to fetch and parse data
    remote_loader = RemoteDataLoader(settings=settings)
    current_data = remote_loader.load()
    logging.info(f"Loaded {len(current_data)} substances from remote source.")

    # Convert to DataFrame for compatibility with existing code
    import pandas as pd  # noqa: E402
    current_prohibited_substance_df = pd.DataFrame(current_data)
    logging.info(f"Parsed prohibited list. {len(current_prohibited_substance_df)} substances found.")

    # Setup database
    substance_db = SubstanceDatabase()
    columns = list(current_prohibited_substance_df.columns)
    substance_db.setup_tables(columns)
    substance_db.clear_tables()

    now = datetime.now(timezone.utc).isoformat()
    today = now[:10]  # YYYY-MM-DD
    logging.info(f"Current date: {today}")

    # Load previous data from git history for comparison
    last_git_commit_data_json = load_previous_data_from_git()
    last_git_commit_data = {}
    last_git_commit_data_count = 0
    last_git_commit_timestamp = 0
    if last_git_commit_data_json:
        if len(last_git_commit_data_json) == 3:
            last_git_commit_data, last_git_commit_data_count, last_git_commit_timestamp = last_git_commit_data_json
        else:
            last_git_commit_data, last_git_commit_data_count = last_git_commit_data_json

    current_count = len(current_prohibited_substance_df)
    logging.info(
        f"Current substances: {current_count}, Previous substances: {last_git_commit_data_count}"
    )

    # Log first few substance keys for debugging
    sample_keys = []
    for i, row in current_prohibited_substance_df.head(3).iterrows():
        substance = Substance.from_row(dict(row), columns)
        sample_keys.append(substance.key[:100])  # Truncate for readability
    logging.info(f"Sample current keys: {sample_keys}")

    if last_git_commit_data:
        sample_prev_keys = list(last_git_commit_data.keys())[:3]
        logging.info(f"Sample previous keys: {[k[:100] for k in sample_prev_keys]}")

    changes_detected = []
    current_substances = {}  # Track current substances by key

    # Define fields to ignore when comparing substances
    ignore_fields = {"added", "updated", "guid", "More_info_URL", "SourceOf"}

    for _, row in current_prohibited_substance_df.iterrows():
        # Create substance object from row data
        substance = Substance.from_row(dict(row), columns)
        current_substances[substance.key] = substance

        # Preserve the original added date if substance existed before
        if last_git_commit_data is not None:
            added_date = substance.get_preserved_added_date(last_git_commit_data, now)
        else:
            added_date = now

        # Set the added date and updated timestamp, then insert into database
        substance.added_date = added_date
        substance.updated_date = now
        substance_db.insert_substance(substance)

        # Check if this substance is new or changed compared to git history
        if last_git_commit_data is not None:
            change_info = substance.get_change_info(
                last_git_commit_data,
                detection_date=today,
                ignore_fields=ignore_fields
            )
            if change_info:
                changes_detected.append(change_info)

    # Check for removed substances
    if last_git_commit_data is not None:
        removed_changes = detect_removed_substances(
            current_substances,
            last_git_commit_data,
            detection_date=today
        )
        changes_detected.extend(removed_changes)

        # Log summary of changes
        new_count = len([c for c in changes_detected if c["type"] == "added"])
        updated_count = len([c for c in changes_detected if c["type"] == "updated"])
        removed_count = len([c for c in changes_detected if c["type"] == "removed"])
        logging.info(
            f"Change summary: {new_count} added, {updated_count} updated, {removed_count} removed"
        )
        logging.info(
            f"Net change: {current_count - last_git_commit_data_count} (from {last_git_commit_data_count} to {current_count})"
        )

    # Store changes in database for changelog generation
    for change in changes_detected:
        substance_db.record_change(
            change["key"],
            change["name"],
            today,
            change["type"],
            change["fields"]
        )
    logging.info(f"Detected {len(changes_detected)} db <-> current changes.")

    # Also update persistent changelog file that gets committed to git
    if changes_detected:
        # Filter out changes that are only metadata/timestamp changes
        meaningful_changes = []
        logging.info("Filtering meaningful changes for persistent changelog...")
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
        logging.info("Found {} meaningful changes after filtering.".format(len(meaningful_changes)))
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
        logging.info("No meaningful changes detected.")

    substance_db.commit()

    # Always generate docs since they're gitignored and needed for deployment
    docs_dir = Path("docs")
    docs_dir.mkdir(exist_ok=True)
    substances_dir = docs_dir / "substances"
    substances_dir.mkdir(exist_ok=True)
    json_path = docs_dir / "data.json"
    
    # Export data from database
    data = substance_db.get_all_substances()
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

    substance_db.close()
    logging.info("Script complete.")


if __name__ == "__main__":
    main()
