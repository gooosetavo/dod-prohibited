"""
Data loader abstraction for unified loading of substance data from multiple sources.

This module provides a common interface for loading substance data from:
- Remote Drupal source (web scraping)
- SQLite database (prohibited.db)
- JSON files (data.json) - from filesystem or git history
"""

import json
import logging
import sqlite3
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, List, Any, Optional, Union

import pandas as pd

from dod_prohibited.http import DrupalClient
from dod_prohibited.parser import parse_prohibited_list


class DataLoader(ABC):
    """
    Abstract base class for data loaders.

    All data loaders must implement the load() method which returns
    a list of substance dictionaries.
    """

    def __init__(self, settings=None):
        """
        Initialize the data loader.

        Args:
            settings: Optional Settings object for configuration
        """
        self.settings = settings
        self.logger = logging.getLogger(self.__class__.__name__)

    @abstractmethod
    def load(self) -> List[Dict[str, Any]]:
        """
        Load substance data from the source.

        Returns:
            List of dictionaries, each representing a substance
        """
        pass

    def validate_data(self, data: List[Dict[str, Any]]) -> bool:
        """
        Validate that loaded data has the expected structure.

        Args:
            data: List of substance dictionaries to validate

        Returns:
            True if data is valid, False otherwise
        """
        if not isinstance(data, list):
            self.logger.error("Data is not a list")
            return False

        if len(data) == 0:
            self.logger.warning("Data is empty")
            return True  # Empty is valid but unusual

        # Check that first item has expected keys
        first_item = data[0]
        if not isinstance(first_item, dict):
            self.logger.error("Data items are not dictionaries")
            return False

        # Check for at least a Name field
        if "Name" not in first_item:
            self.logger.error("Data items missing 'Name' field")
            return False

        return True


class RemoteDataLoader(DataLoader):
    """
    Load substance data from the remote Drupal source.

    Fetches data from the OPSS website and parses the Drupal settings JSON.
    """

    def __init__(self, url: Optional[str] = None, user_agent: Optional[str] = None, settings=None):
        """
        Initialize the remote data loader.

        Args:
            url: URL to fetch from (defaults to settings.source_url)
            user_agent: User agent string for HTTP requests
            settings: Optional Settings object
        """
        super().__init__(settings)
        self.url = url or (settings.source_url if settings else None)
        self.user_agent = user_agent

        if not self.url:
            raise ValueError("URL must be provided either directly or via settings")

    def load(self) -> List[Dict[str, Any]]:
        """
        Load substance data from remote Drupal source.

        Returns:
            List of substance dictionaries
        """
        self.logger.info(f"Fetching data from remote source: {self.url}")

        try:
            # Fetch Drupal settings
            with DrupalClient(user_agent=self.user_agent) as client:
                settings_data = client.fetch_drupal_settings(self.url)

            # Parse prohibited list from settings
            df = parse_prohibited_list(settings_data)

            if df.empty:
                self.logger.error("No data parsed from remote source")
                return []

            # Convert DataFrame to list of dictionaries
            data = df.to_dict(orient="records")

            self.logger.info(f"Successfully loaded {len(data)} substances from remote source")

            if not self.validate_data(data):
                self.logger.error("Remote data validation failed")
                return []

            return data

        except Exception as e:
            self.logger.error(f"Failed to load data from remote source: {e}")
            raise


class SqliteDataLoader(DataLoader):
    """
    Load substance data from a SQLite database.

    Reads all substances from a SQLite database file (typically prohibited.db).
    """

    def __init__(self, db_path: Union[str, Path] = "prohibited.db", settings=None):
        """
        Initialize the SQLite data loader.

        Args:
            db_path: Path to the SQLite database file
            settings: Optional Settings object
        """
        super().__init__(settings)
        self.db_path = Path(db_path)

        if not self.db_path.exists():
            raise FileNotFoundError(f"Database file not found: {self.db_path}")

    def load(self) -> List[Dict[str, Any]]:
        """
        Load substance data from SQLite database.

        Returns:
            List of substance dictionaries (including 'added' and 'updated' fields)
        """
        self.logger.info(f"Loading data from database: {self.db_path}")

        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()

            # Get column names
            cursor.execute("PRAGMA table_info(substances)")
            columns_info = cursor.fetchall()
            columns = [col[1] for col in columns_info]

            # Load all substances
            column_names = ", ".join([f'"{col}"' for col in columns])
            cursor.execute(f"SELECT {column_names} FROM substances")
            rows = cursor.fetchall()

            conn.close()

            # Convert to list of dictionaries
            data = [dict(zip(columns, row)) for row in rows]

            self.logger.info(f"Successfully loaded {len(data)} substances from database")

            if not self.validate_data(data):
                self.logger.error("Database data validation failed")
                return []

            return data

        except Exception as e:
            self.logger.error(f"Failed to load data from database: {e}")
            raise


class JsonFileDataLoader(DataLoader):
    """
    Load substance data from a JSON file.

    Can load from either the current filesystem or from git history.
    Supports loading previous versions for change detection.
    """

    def __init__(
        self,
        file_path: Union[str, Path] = "docs/data.json",
        git_revision: Optional[str] = None,
        settings=None
    ):
        """
        Initialize the JSON file data loader.

        Args:
            file_path: Path to the JSON file
            git_revision: Optional git revision (e.g., 'HEAD~1', 'abc123')
                         If provided, loads from git history instead of filesystem
            settings: Optional Settings object
        """
        super().__init__(settings)
        self.file_path = Path(file_path) if not git_revision else str(file_path)
        self.git_revision = git_revision

        # Only check file existence for filesystem loads
        if not git_revision and not Path(file_path).exists():
            raise FileNotFoundError(f"JSON file not found: {file_path}")

    def load(self) -> List[Dict[str, Any]]:
        """
        Load substance data from JSON file.

        Loads from git history if git_revision is set, otherwise from filesystem.

        Returns:
            List of substance dictionaries
        """
        if self.git_revision:
            return self._load_from_git()
        else:
            return self._load_from_filesystem()

    def _load_from_filesystem(self) -> List[Dict[str, Any]]:
        """Load JSON data from the filesystem."""
        self.logger.info(f"Loading data from JSON file: {self.file_path}")

        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, list):
                self.logger.error(f"JSON file does not contain a list: {type(data)}")
                return []

            self.logger.info(f"Successfully loaded {len(data)} substances from JSON file")

            if not self.validate_data(data):
                self.logger.error("JSON file data validation failed")
                return []

            return data

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON file: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Failed to load data from JSON file: {e}")
            raise

    def _load_from_git(self) -> List[Dict[str, Any]]:
        """Load JSON data from git history."""
        # Check if git history should be used
        if self.settings and hasattr(self.settings, 'use_git_history'):
            if not self.settings.use_git_history:
                self.logger.info("Skipping git history load (disabled in settings)")
                return []

        self.logger.info(f"Loading data from git: {self.git_revision}:{self.file_path}")

        try:
            result = subprocess.run(
                ["git", "show", f"{self.git_revision}:{self.file_path}"],
                capture_output=True,
                text=True,
                cwd=Path.cwd(),
            )

            if result.returncode != 0:
                self.logger.warning(
                    f"Could not load from git history (possibly first commit): {result.stderr.strip()}"
                )
                return []

            data = json.loads(result.stdout)

            if not isinstance(data, list):
                self.logger.error(f"Git history data is not a list: {type(data)}")
                return []

            self.logger.info(f"Successfully loaded {len(data)} substances from git history")

            if not self.validate_data(data):
                self.logger.warning("Git history data validation failed")
                return []

            return data

        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse JSON from git history: {e}")
            return []
        except FileNotFoundError:
            self.logger.warning("Git command not found")
            return []
        except Exception as e:
            self.logger.error(f"Failed to load data from git history: {e}")
            return []


class DataFrameDataLoader(DataLoader):
    """
    Load substance data from a pandas DataFrame.

    Useful for loading data that has already been parsed or processed
    into a DataFrame format.
    """

    def __init__(self, dataframe: pd.DataFrame, settings=None):
        """
        Initialize the DataFrame data loader.

        Args:
            dataframe: pandas DataFrame containing substance data
            settings: Optional Settings object
        """
        super().__init__(settings)
        self.dataframe = dataframe

    def load(self) -> List[Dict[str, Any]]:
        """
        Load substance data from DataFrame.

        Returns:
            List of substance dictionaries
        """
        self.logger.info(f"Loading data from DataFrame with {len(self.dataframe)} rows")

        if self.dataframe.empty:
            self.logger.warning("DataFrame is empty")
            return []

        # Convert DataFrame to list of dictionaries
        data = self.dataframe.to_dict(orient="records")

        if not self.validate_data(data):
            self.logger.error("DataFrame data validation failed")
            return []

        return data


# Convenience factory function
def create_loader(
    source: str,
    settings=None,
    **kwargs
) -> DataLoader:
    """
    Factory function to create the appropriate data loader.

    Args:
        source: Data source type ('remote', 'sqlite', 'json', 'dataframe')
        settings: Optional Settings object
        **kwargs: Additional arguments passed to the loader constructor

    Returns:
        Appropriate DataLoader instance

    Examples:
        >>> # Load from remote Drupal source
        >>> loader = create_loader('remote', settings=settings)
        >>> data = loader.load()

        >>> # Load from SQLite database
        >>> loader = create_loader('sqlite', db_path='prohibited.db')
        >>> data = loader.load()

        >>> # Load from JSON file on filesystem
        >>> loader = create_loader('json', file_path='docs/data.json')
        >>> data = loader.load()

        >>> # Load from JSON file in git history
        >>> loader = create_loader('json', file_path='docs/data.json', git_revision='HEAD~1')
        >>> data = loader.load()

        >>> # Load from DataFrame
        >>> loader = create_loader('dataframe', dataframe=df)
        >>> data = loader.load()
    """
    loaders = {
        'remote': RemoteDataLoader,
        'sqlite': SqliteDataLoader,
        'json': JsonFileDataLoader,
        'dataframe': DataFrameDataLoader,
    }

    if source not in loaders:
        raise ValueError(
            f"Unknown data source: {source}. "
            f"Valid sources: {', '.join(loaders.keys())}"
        )

    loader_class = loaders[source]
    return loader_class(settings=settings, **kwargs)
