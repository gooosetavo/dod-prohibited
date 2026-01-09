"""
Tests for parsing.py functions
"""

import pandas as pd
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parsing import parse_prohibited_list


class TestParsing:
    """Tests for parsing.py functions"""
    
    def test_parse_prohibited_list_valid_data(self):
        """Test parsing valid prohibited list"""
        settings = {
            'dodProhibited': [
                {'name': 'Substance 1', 'reason': 'Reason 1'},
                {'name': 'Substance 2', 'reason': 'Reason 2'}
            ]
        }
        df = parse_prohibited_list(settings)
        assert len(df) == 2
        assert 'name' in df.columns
        assert 'reason' in df.columns
    
    def test_parse_prohibited_list_empty_data(self):
        """Test parsing when no prohibited data exists"""
        settings = {}
        df = parse_prohibited_list(settings)
        assert len(df) == 0
        assert isinstance(df, pd.DataFrame)
    
    def test_parse_prohibited_list_none_data(self):
        """Test parsing when prohibited data is None"""
        settings = {'dodProhibited': None}
        df = parse_prohibited_list(settings)
        assert len(df) == 0
        assert isinstance(df, pd.DataFrame)