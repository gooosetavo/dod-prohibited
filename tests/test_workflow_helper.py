"""
Tests for workflow_helper.py functions
"""

import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock, mock_open
import subprocess
import sys

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workflow_helper import (
    run_command, 
    get_git_status,
    set_github_output,
    parse_changelog_counts
)


class TestWorkflowHelper:
    """Tests for workflow_helper.py functions"""
    
    @patch('subprocess.run')
    def test_run_command_success(self, mock_run):
        """Test successful command execution"""
        mock_result = MagicMock()
        mock_result.stdout = 'output'
        mock_result.stderr = ''
        mock_result.returncode = 0
        mock_run.return_value = mock_result
        
        stdout, stderr, code = run_command('echo test')
        assert stdout == 'output'
        assert stderr == ''
        assert code == 0
    
    @patch('subprocess.run')
    def test_run_command_failure(self, mock_run):
        """Test failed command execution"""
        mock_run.side_effect = subprocess.CalledProcessError(1, 'cmd', 'out', 'err')
        
        stdout, stderr, code = run_command('false', check=False)
        assert code == 1
    
    @patch('workflow_helper.run_command')
    def test_get_git_status(self, mock_run_command):
        """Test getting git status"""
        mock_run_command.return_value = ('M file1.txt\nA file2.txt', '', 0)
        
        status = get_git_status()
        assert len(status) == 2
        assert 'M file1.txt' in status
        assert 'A file2.txt' in status
    
    def test_parse_changelog_counts_with_source_dates(self):
        """Test parsing changelog counts from file with multiple date sections"""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            
            changelog_content = """# Changelog

## 2026-01-02

### Substances Modified

*Changes detected through data comparison*

- **Modified Substance:** Updated field1

### Substances Removed

*Removals detected through data comparison*

- **Removed Substance**

## 2022-01-01

### New Substances Added

- **Substance 1**
- **Substance 2**
"""
            
            changelog_path = Path('CHANGELOG.md')
            changelog_path.write_text(changelog_content)
            
            new, updated, removed = parse_changelog_counts()
            assert new == 2
            assert updated == 1
            assert removed == 1
    
    def test_parse_changelog_counts_missing_file(self):
        """Test parsing changelog counts when file doesn't exist"""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            
            new, updated, removed = parse_changelog_counts()
            assert new == 0
            assert updated == 0
            assert removed == 0
    
    @patch.dict(os.environ, {'GITHUB_OUTPUT': '/tmp/github_output'})
    def test_set_github_output(self):
        """Test setting GitHub output variable"""
        with patch('builtins.open', mock_open()) as mock_file:
            set_github_output('test-key', 'test-value')
            mock_file.assert_called_once_with('/tmp/github_output', 'a')
            handle = mock_file()
            handle.write.assert_called_once_with('test-key=test-value\n')
    
    def test_parse_changelog_counts_ignores_metadata_markers(self):
        """Test that changelog parsing correctly handles metadata markers"""
        with tempfile.TemporaryDirectory() as temp_dir:
            os.chdir(temp_dir)
            
            changelog_content = """# Changelog

## 2026-01-02

### Substances Modified

*Changes detected through data comparison*

- **Substance A:** Updated field1
- **Substance B:** Updated field2

### Substances Removed

*Removals detected through data comparison*

- **Substance C**

## 2022-01-01

### New Substances Added

- **Substance D** (source date: 2022-01-01)
- **Substance E**
"""
            
            changelog_path = Path('CHANGELOG.md')
            changelog_path.write_text(changelog_content)
            
            new, updated, removed = parse_changelog_counts()
            assert new == 2  # Should count substances, not metadata
            assert updated == 2
            assert removed == 1