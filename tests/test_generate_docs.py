"""
Tests for generate_docs.py functions
"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_docs import (
    update_persistent_changelog, 
    get_substance_last_modified,
    get_substance_source_date,
    has_substance_been_modified_since,
    load_previous_data_from_git
)


class TestGenerateDocs:
    """Tests for generate_docs.py functions"""
    
    def test_get_substance_last_modified_valid(self):
        """Test extracting timestamp from valid substance data"""
        substance = {
            'updated': '{"_seconds": 1640995200, "_nanoseconds": 0}'
        }
        timestamp = get_substance_last_modified(substance)
        assert timestamp == 1640995200
    
    def test_get_substance_last_modified_invalid(self):
        """Test extracting timestamp from invalid substance data"""
        substance = {'updated': 'invalid json'}
        timestamp = get_substance_last_modified(substance)
        assert timestamp == 0
    
    def test_get_substance_last_modified_missing(self):
        """Test extracting timestamp when field is missing"""
        substance = {}
        timestamp = get_substance_last_modified(substance)
        assert timestamp == 0
    
    def test_get_substance_source_date_with_timestamp(self):
        """Test extracting source date from timestamp"""
        substance = {
            'updated': '{"_seconds": 1640995200, "_nanoseconds": 0}'
        }
        date = get_substance_source_date(substance)
        assert date == '2021-12-31'
    
    def test_get_substance_source_date_no_timestamp(self):
        """Test extracting source date when no timestamp available"""
        substance = {'name': 'test'}
        date = get_substance_source_date(substance)
        assert date is None
    
    def test_has_substance_been_modified_since(self):
        """Test checking if substance was modified since timestamp"""
        substance = {
            'updated': '{"_seconds": 1640995200, "_nanoseconds": 0}'
        }
        assert has_substance_been_modified_since(substance, 1640995100) == True
        assert has_substance_been_modified_since(substance, 1640995300) == False
    
    def test_update_persistent_changelog_with_source_dates(self):
        """Test creating changelog with self-reported dates"""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            
            changes = [
                {
                    'type': 'added', 
                    'name': 'Test Substance', 
                    'fields': [],
                    'source_date': '2022-01-01'
                },
                {
                    'type': 'updated',
                    'name': 'Modified Substance',
                    'fields': ['Reason'],
                    'detection_date': '2026-01-02'
                }
            ]
            
            update_persistent_changelog(changes, '2026-01-02', detection_date='2026-01-02')
            
            changelog_path = Path('CHANGELOG.md')
            assert changelog_path.exists()
            
            content = changelog_path.read_text()
            assert '# Changelog' in content
            assert '## 2022-01-01' in content  # Source date entry
            assert '## 2026-01-02' in content  # Detection date entry
            assert 'Test Substance' in content
            assert 'Modified Substance' in content
            assert 'Changes detected through data comparison' in content
    
    def test_update_persistent_changelog_mixed_dates(self):
        """Test changelog with both self-reported and computed dates"""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            
            changes = [
                {
                    'type': 'added',
                    'name': 'New Substance 1',
                    'fields': [],
                    'source_date': '2022-01-01'
                },
                {
                    'type': 'added',
                    'name': 'New Substance 2', 
                    'fields': [],
                    'source_date': '2022-01-02'
                },
                {
                    'type': 'removed',
                    'name': 'Removed Substance',
                    'fields': [],
                    'detection_date': '2026-01-02'
                }
            ]
            
            update_persistent_changelog(changes, '2026-01-02')
            
            content = Path('CHANGELOG.md').read_text()
            
            # Should have entries for multiple dates
            assert '## 2022-01-02' in content
            assert '## 2022-01-01' in content
            assert '## 2026-01-02' in content
            assert 'New Substance 1' in content
            assert 'New Substance 2' in content
            assert 'Removed Substance' in content
    
    @patch('generate_docs.Path')
    @patch('subprocess.run')
    def test_load_previous_data_from_git_success(self, mock_run, mock_path):
        """Test loading previous data from git successfully"""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = '[{"Name": "Test", "updated": "{\\"_seconds\\": 1640995200}"}]'
        mock_run.return_value = mock_result
        
        # Mock Path.cwd() to return a valid path
        mock_path.cwd.return_value = Path('/fake/path')
        
        columns = ['Name', 'Reason']
        result = load_previous_data_from_git(columns)
        
        assert result is not None
        data, count = result
        assert count == 1
        assert 'Test|' in data
    
    @patch('subprocess.run')
    def test_load_previous_data_from_git_failure(self, mock_run):
        """Test loading previous data when git command fails"""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_run.return_value = mock_result
        
        columns = ['Name', 'Reason']
        result = load_previous_data_from_git(columns)
        
        assert result is None
    
    def test_update_changelog_preserves_existing_entries(self):
        """Test that new changelog entries don't overwrite existing ones"""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            
            # Create existing changelog
            changelog_path = Path('CHANGELOG.md')
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
                    'type': 'added',
                    'name': 'New Substance',
                    'fields': [],
                    'source_date': '2026-01-01'
                }
            ]
            
            update_persistent_changelog(changes, '2026-01-02')
            
            content = changelog_path.read_text()
            
            # Should preserve old content
            assert 'Old Substance' in content
            assert 'New Substance' in content
            assert '## 2025-12-31' in content
            assert '## 2026-01-01' in content