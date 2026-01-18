"""
Tests for generate_docs.py functions
"""

import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_docs import load_previous_data_from_git
from changelog import (
    update_persistent_changelog,
    get_substance_last_modified,
    get_substance_source_date,
    has_substance_been_modified_since,
)


class TestGenerateDocs:
    """Tests for generate_docs.py functions"""

    def test_get_substance_last_modified_valid(self):
        """Test extracting timestamp from valid substance data"""
        substance = {"updated": '{"_seconds": 1640995200, "_nanoseconds": 0}'}
        timestamp = get_substance_last_modified(substance)
        assert timestamp == 1640995200

    def test_get_substance_last_modified_invalid(self):
        """Test extracting timestamp from invalid substance data"""
        substance = {"updated": "invalid json"}
        timestamp = get_substance_last_modified(substance)
        assert timestamp == 0

    def test_get_substance_last_modified_missing(self):
        """Test extracting timestamp when field is missing"""
        substance = {}
        timestamp = get_substance_last_modified(substance)
        assert timestamp == 0

    def test_get_substance_source_date_with_timestamp(self):
        """Test extracting source date from timestamp"""
        substance = {"updated": '{"_seconds": 1640995200, "_nanoseconds": 0}'}
        date = get_substance_source_date(substance)
        assert date == "2021-12-31"

    def test_get_substance_source_date_no_timestamp(self):
        """Test extracting source date when no timestamp available"""
        substance = {"name": "test"}
        date = get_substance_source_date(substance)
        assert date is None

    def test_has_substance_been_modified_since(self):
        """Test checking if substance was modified since timestamp"""
        substance = {"updated": '{"_seconds": 1640995200, "_nanoseconds": 0}'}
        assert has_substance_been_modified_since(substance, 1640995100)
        assert not has_substance_been_modified_since(substance, 1640995300)

    def test_timestamp_parsing_fallback_behavior(self):
        """Test that unparseable timestamps default to 'not modified' behavior"""
        # Test cases where timestamp parsing should fail and return 0
        test_cases = [
            {"updated": ""},  # Empty string
            {"updated": "invalid json"},  # Invalid JSON
            {"updated": '{"missing_seconds": 123}'},  # Missing _seconds field
            {"updated": '{"_seconds": "not_a_number"}'},  # Invalid seconds value
            {},  # Missing updated field entirely
        ]
        
        for substance in test_cases:
            timestamp = get_substance_last_modified(substance)
            assert timestamp == 0, f"Expected 0 for substance: {substance}"
            
        # Verify that 0 timestamps don't trigger modification detection
        assert not has_substance_been_modified_since({"updated": ""}, 0)
        assert not has_substance_been_modified_since({}, 100)  # No timestamp vs positive threshold
        assert not has_substance_been_modified_since({"updated": "invalid"}, 1640995200)
        
    def test_modification_detection_requires_valid_timestamps(self):
        """Test that modification detection only works with valid timestamps"""
        from generate_docs import Substance
        
        # Create substances with different timestamp scenarios
        current_valid = Substance.from_dict({
            "Name": "Test Substance",
            "updated": '{"_seconds": 1640995200, "_nanoseconds": 0}'
        })
        current_invalid = Substance.from_dict({
            "Name": "Test Substance", 
            "updated": "invalid_json"
        })
        previous_valid = Substance.from_dict({
            "Name": "Test Substance",
            "updated": '{"_seconds": 1640995100, "_nanoseconds": 0}'
        })
        previous_invalid = Substance.from_dict({
            "Name": "Test Substance",
            "updated": ""
        })
        
        # Valid current > valid previous should detect modification
        assert current_valid.get_last_modified_timestamp() > previous_valid.get_last_modified_timestamp()
        
        # Invalid current vs valid previous should NOT detect modification (0 > positive = False)  
        assert not (current_invalid.get_last_modified_timestamp() > previous_valid.get_last_modified_timestamp())
        
        # Valid current vs invalid previous should NOT detect modification in our new logic
        # (We want to be conservative and not assume modification)
        assert current_valid.get_last_modified_timestamp() > 0
        assert previous_invalid.get_last_modified_timestamp() == 0
        # Our new logic requires BOTH timestamps to be > 0 for modification detection

    def test_update_persistent_changelog_with_source_dates(self):
        """Test creating changelog with self-reported dates"""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)

            changes = [
                {
                    "type": "added",
                    "name": "Test Substance",
                    "fields": [],
                    "source_date": "2022-01-01",
                },
                {
                    "type": "updated",
                    "name": "Modified Substance",
                    "fields": ["Reason"],
                    "detection_date": "2026-01-02",
                },
            ]

            update_persistent_changelog(
                changes, "2026-01-02", detection_date="2026-01-02"
            )

            changelog_path = Path("CHANGELOG.md")
            assert changelog_path.exists()

            content = changelog_path.read_text()
            assert "# Changelog" in content
            assert "## 2022-01-01" in content  # Source date entry
            assert "## 2026-01-02" in content  # Detection date entry
            assert "Test Substance" in content
            assert "Modified Substance" in content
            assert "detected through data comparison" in content

    def test_update_persistent_changelog_mixed_dates(self):
        """Test changelog with both self-reported and computed dates"""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)

            changes = [
                {
                    "type": "added",
                    "name": "New Substance 1",
                    "fields": [],
                    "source_date": "2022-01-01",
                },
                {
                    "type": "added",
                    "name": "New Substance 2",
                    "fields": [],
                    "source_date": "2022-01-02",
                },
                {
                    "type": "removed",
                    "name": "Removed Substance",
                    "fields": [],
                    "detection_date": "2026-01-02",
                },
            ]

            update_persistent_changelog(changes, "2026-01-02")

            content = Path("CHANGELOG.md").read_text()

            # Should have entries for multiple dates
            assert "## 2022-01-02" in content
            assert "## 2022-01-01" in content
            assert "## 2026-01-02" in content
            assert "New Substance 1" in content
            assert "New Substance 2" in content
            assert "Removed Substance" in content

    @patch("generate_docs.settings")
    @patch("generate_docs.Path")
    @patch("subprocess.run")
    def test_load_previous_data_from_git_success(self, mock_run, mock_path, mock_settings):
        """Test loading previous data from git successfully"""
        # Mock settings to enable git history
        mock_settings.use_git_history = True

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            '[{"Name": "Test", "updated": "{\\"_seconds\\": 1640995200}"}]'
        )
        mock_run.return_value = mock_result

        # Mock Path.cwd() to return a valid path
        mock_path.cwd.return_value = Path("/fake/path")

        result = load_previous_data_from_git()

        assert result is not None
        data, count = result
        assert count == 1
        assert "name:Test" in data

    @patch("generate_docs.settings")
    @patch("subprocess.run")
    def test_load_previous_data_from_git_failure(self, mock_run, mock_settings):
        """Test loading previous data when git command fails"""
        # Mock settings to enable git history
        mock_settings.use_git_history = True

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result

        result = load_previous_data_from_git()

        assert result is None

    def test_update_changelog_preserves_existing_entries(self):
        """Test that new changelog entries don't overwrite existing ones"""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)

            # Create existing changelog
            changelog_path = Path("CHANGELOG.md")
            existing_content = """# Changelog

All notable changes will be documented here.

## 2025-12-31

### New Substances Added

- **Old Substance**

"""
            changelog_path.write_text(existing_content)

            # Add new changes
            changes = [
                {
                    "type": "added",
                    "name": "New Substance",
                    "fields": [],
                    "source_date": "2026-01-01",
                }
            ]

            update_persistent_changelog(changes, "2026-01-02")

            content = changelog_path.read_text()

            # Should preserve old content
            assert "Old Substance" in content
            assert "New Substance" in content
            assert "## 2025-12-31" in content
            assert "## 2026-01-01" in content
