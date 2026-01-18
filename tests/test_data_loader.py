"""Tests for the unified data loading pattern."""

import json
import pytest
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pandas as pd

from data_loader import (
    DataLoader,
    RemoteDataLoader,
    SqliteDataLoader,
    JsonFileDataLoader,
    DataFrameDataLoader,
    create_loader
)


# Sample test data
SAMPLE_SUBSTANCE_DATA = [
    {
        "Name": "Test Substance 1",
        "Classifications": '["stimulant"]',
        "Reason": "Test reason 1",
        "guid": "123"
    },
    {
        "Name": "Test Substance 2",
        "Classifications": '["anabolic"]',
        "Reason": "Test reason 2",
        "guid": "456"
    }
]


@pytest.fixture
def sample_data():
    """Provide sample substance data for tests."""
    return SAMPLE_SUBSTANCE_DATA.copy()


@pytest.fixture
def mock_settings():
    """Mock Settings object."""
    settings = Mock()
    settings.source_url = "https://example.com/prohibited"
    settings.use_git_history = True
    return settings


@pytest.fixture
def temp_db(tmp_path):
    """Create a temporary SQLite database with test data."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create substances table
    cursor.execute("""
        CREATE TABLE substances (
            Name TEXT,
            Classifications TEXT,
            Reason TEXT,
            guid TEXT,
            added TEXT,
            updated TEXT
        )
    """)

    # Insert test data
    for item in SAMPLE_SUBSTANCE_DATA:
        cursor.execute(
            """INSERT INTO substances (Name, Classifications, Reason, guid, added, updated)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (item["Name"], item["Classifications"], item["Reason"], item["guid"],
             "2026-01-01", "2026-01-01")
        )

    conn.commit()
    conn.close()

    return db_path


@pytest.fixture
def temp_json_file(tmp_path, sample_data):
    """Create a temporary JSON file with test data."""
    json_path = tmp_path / "data.json"
    with open(json_path, "w") as f:
        json.dump(sample_data, f)
    return json_path


class TestDataLoaderBase:
    """Tests for the base DataLoader class."""

    def test_validate_data_valid_list(self, sample_data):
        """Test validation accepts valid data."""
        loader = DataFrameDataLoader(dataframe=pd.DataFrame(sample_data))
        assert loader.validate_data(sample_data) is True

    def test_validate_data_not_list(self):
        """Test validation rejects non-list data."""
        loader = DataFrameDataLoader(dataframe=pd.DataFrame())
        assert loader.validate_data("not a list") is False

    def test_validate_data_empty_list(self):
        """Test validation accepts empty list."""
        loader = DataFrameDataLoader(dataframe=pd.DataFrame())
        assert loader.validate_data([]) is True

    def test_validate_data_not_dicts(self):
        """Test validation rejects list of non-dicts."""
        loader = DataFrameDataLoader(dataframe=pd.DataFrame())
        assert loader.validate_data(["not", "dicts"]) is False

    def test_validate_data_missing_name(self):
        """Test validation rejects data without Name field."""
        loader = DataFrameDataLoader(dataframe=pd.DataFrame())
        assert loader.validate_data([{"NoName": "value"}]) is False


class TestRemoteDataLoader:
    """Tests for RemoteDataLoader."""

    def test_init_with_url(self):
        """Test initialization with explicit URL."""
        loader = RemoteDataLoader(url="https://example.com")
        assert loader.url == "https://example.com"

    def test_init_with_settings(self, mock_settings):
        """Test initialization with settings."""
        loader = RemoteDataLoader(settings=mock_settings)
        assert loader.url == mock_settings.source_url

    def test_init_without_url_or_settings(self):
        """Test initialization fails without URL."""
        with pytest.raises(ValueError, match="URL must be provided"):
            RemoteDataLoader()

    @patch('data_loader.DrupalClient')
    @patch('data_loader.parse_prohibited_list')
    def test_load_success(self, mock_parse, mock_drupal_client, sample_data, mock_settings):
        """Test successful data loading from remote source."""
        # Setup mocks
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = Mock(return_value=False)
        mock_client_instance.fetch_drupal_settings = Mock(return_value={"dodProhibited": []})
        mock_drupal_client.return_value = mock_client_instance

        mock_df = pd.DataFrame(sample_data)
        mock_parse.return_value = mock_df

        # Load data
        loader = RemoteDataLoader(settings=mock_settings)
        data = loader.load()

        # Verify
        assert len(data) == 2
        assert data[0]["Name"] == "Test Substance 1"
        mock_drupal_client.assert_called_once()
        mock_parse.assert_called_once()

    @patch('data_loader.DrupalClient')
    @patch('data_loader.parse_prohibited_list')
    def test_load_empty_dataframe(self, mock_parse, mock_drupal_client, mock_settings):
        """Test loading returns empty list when DataFrame is empty."""
        mock_client_instance = MagicMock()
        mock_client_instance.__enter__ = Mock(return_value=mock_client_instance)
        mock_client_instance.__exit__ = Mock(return_value=False)
        mock_client_instance.fetch_drupal_settings = Mock(return_value={})
        mock_drupal_client.return_value = mock_client_instance

        mock_parse.return_value = pd.DataFrame()

        loader = RemoteDataLoader(settings=mock_settings)
        data = loader.load()

        assert data == []

    @patch('data_loader.DrupalClient')
    def test_load_exception(self, mock_drupal_client, mock_settings):
        """Test loading raises exception on error."""
        mock_drupal_client.side_effect = Exception("Network error")

        loader = RemoteDataLoader(settings=mock_settings)

        with pytest.raises(Exception, match="Network error"):
            loader.load()


class TestSqliteDataLoader:
    """Tests for SqliteDataLoader."""

    def test_init_with_existing_db(self, temp_db):
        """Test initialization with existing database."""
        loader = SqliteDataLoader(db_path=temp_db)
        assert loader.db_path == temp_db

    def test_init_with_nonexistent_db(self):
        """Test initialization fails with nonexistent database."""
        with pytest.raises(FileNotFoundError):
            SqliteDataLoader(db_path="nonexistent.db")

    def test_load_success(self, temp_db):
        """Test successful data loading from database."""
        loader = SqliteDataLoader(db_path=temp_db)
        data = loader.load()

        assert len(data) == 2
        assert data[0]["Name"] == "Test Substance 1"
        assert data[1]["Name"] == "Test Substance 2"
        assert "added" in data[0]
        assert "updated" in data[0]

    def test_load_validates_data(self, temp_db):
        """Test that loaded data is validated."""
        loader = SqliteDataLoader(db_path=temp_db)
        data = loader.load()

        assert loader.validate_data(data) is True


class TestJsonFileDataLoader:
    """Tests for JsonFileDataLoader."""

    def test_init_with_existing_file(self, temp_json_file):
        """Test initialization with existing JSON file."""
        loader = JsonFileDataLoader(file_path=temp_json_file)
        assert loader.file_path == temp_json_file
        assert loader.git_revision is None

    def test_init_with_nonexistent_file(self):
        """Test initialization fails with nonexistent file."""
        with pytest.raises(FileNotFoundError):
            JsonFileDataLoader(file_path="nonexistent.json")

    def test_init_with_git_revision(self):
        """Test initialization with git revision doesn't check file existence."""
        # Should not raise even if file doesn't exist on filesystem
        loader = JsonFileDataLoader(file_path="docs/data.json", git_revision="HEAD~1")
        assert loader.git_revision == "HEAD~1"

    def test_load_from_filesystem(self, temp_json_file, sample_data):
        """Test loading from filesystem."""
        loader = JsonFileDataLoader(file_path=temp_json_file)
        data = loader.load()

        assert len(data) == 2
        assert data[0]["Name"] == "Test Substance 1"
        assert data == sample_data

    def test_load_invalid_json(self, tmp_path):
        """Test loading invalid JSON raises error."""
        json_path = tmp_path / "invalid.json"
        with open(json_path, "w") as f:
            f.write("not valid json{]")

        loader = JsonFileDataLoader(file_path=json_path)

        with pytest.raises(json.JSONDecodeError):
            loader.load()

    def test_load_non_list_json(self, tmp_path):
        """Test loading non-list JSON returns empty list."""
        json_path = tmp_path / "dict.json"
        with open(json_path, "w") as f:
            json.dump({"not": "a list"}, f)

        loader = JsonFileDataLoader(file_path=json_path)
        data = loader.load()

        assert data == []

    @patch('data_loader.subprocess.run')
    def test_load_from_git_success(self, mock_run, sample_data, mock_settings):
        """Test loading from git history."""
        # Mock successful git command
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps(sample_data)
        mock_run.return_value = mock_result

        loader = JsonFileDataLoader(
            file_path="docs/data.json",
            git_revision="HEAD~1",
            settings=mock_settings
        )
        data = loader.load()

        assert len(data) == 2
        assert data[0]["Name"] == "Test Substance 1"
        mock_run.assert_called_once()

    @patch('data_loader.subprocess.run')
    def test_load_from_git_failure(self, mock_run, mock_settings):
        """Test loading from git returns empty list on failure."""
        # Mock failed git command
        mock_result = Mock()
        mock_result.returncode = 1
        mock_result.stderr = "fatal: path not in the working tree"
        mock_run.return_value = mock_result

        loader = JsonFileDataLoader(
            file_path="docs/data.json",
            git_revision="HEAD~1",
            settings=mock_settings
        )
        data = loader.load()

        assert data == []

    @patch('data_loader.subprocess.run')
    def test_load_from_git_disabled_in_settings(self, mock_run, mock_settings):
        """Test loading from git respects settings."""
        mock_settings.use_git_history = False

        loader = JsonFileDataLoader(
            file_path="docs/data.json",
            git_revision="HEAD~1",
            settings=mock_settings
        )
        data = loader.load()

        assert data == []
        mock_run.assert_not_called()


class TestDataFrameDataLoader:
    """Tests for DataFrameDataLoader."""

    def test_load_from_dataframe(self, sample_data):
        """Test loading from DataFrame."""
        df = pd.DataFrame(sample_data)
        loader = DataFrameDataLoader(dataframe=df)
        data = loader.load()

        assert len(data) == 2
        assert data[0]["Name"] == "Test Substance 1"

    def test_load_empty_dataframe(self):
        """Test loading from empty DataFrame."""
        df = pd.DataFrame()
        loader = DataFrameDataLoader(dataframe=df)
        data = loader.load()

        assert data == []


class TestCreateLoaderFactory:
    """Tests for the create_loader factory function."""

    def test_create_remote_loader(self, mock_settings):
        """Test factory creates RemoteDataLoader."""
        loader = create_loader('remote', settings=mock_settings)
        assert isinstance(loader, RemoteDataLoader)

    def test_create_sqlite_loader(self, temp_db):
        """Test factory creates SqliteDataLoader."""
        loader = create_loader('sqlite', db_path=temp_db)
        assert isinstance(loader, SqliteDataLoader)

    def test_create_json_loader(self, temp_json_file):
        """Test factory creates JsonFileDataLoader."""
        loader = create_loader('json', file_path=temp_json_file)
        assert isinstance(loader, JsonFileDataLoader)

    def test_create_dataframe_loader(self, sample_data):
        """Test factory creates DataFrameDataLoader."""
        df = pd.DataFrame(sample_data)
        loader = create_loader('dataframe', dataframe=df)
        assert isinstance(loader, DataFrameDataLoader)

    def test_create_invalid_source(self):
        """Test factory raises error for invalid source."""
        with pytest.raises(ValueError, match="Unknown data source"):
            create_loader('invalid_source')

    def test_create_loader_with_kwargs(self, temp_json_file):
        """Test factory passes kwargs to loader."""
        loader = create_loader('json', file_path=temp_json_file, git_revision='HEAD~1')
        assert isinstance(loader, JsonFileDataLoader)
        assert loader.git_revision == 'HEAD~1'
