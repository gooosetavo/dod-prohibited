"""
Tests for retrieval.py functions
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval import fetch_drupal_settings
from parsing import get_nested


class TestRetrieval:
    """Tests for retrieval.py functions"""

    def test_get_nested_valid_path(self):
        """Test getting nested values from dictionary"""
        data = {"a": {"b": {"c": "value"}}}
        assert get_nested(data, "a.b.c") == "value"

    def test_get_nested_invalid_path(self):
        """Test getting nested values with invalid path"""
        data = {"a": {"b": {"c": "value"}}}
        assert get_nested(data, "a.x.c") is None
        assert get_nested(data, "a.x.c", "default") == "default"

    def test_get_nested_empty_data(self):
        """Test getting nested values from empty data"""
        assert get_nested({}, "a.b.c") is None
        assert get_nested(None, "a.b.c", "default") == "default"

    @patch("http_client.HttpClient.get")
    def test_fetch_drupal_settings_success(self, mock_get):
        """Test successful Drupal settings fetch"""
        mock_response = MagicMock()
        mock_response.text = """
        <html>
            <script type="application/json" data-drupal-selector="drupal-settings-json">
                {"dodProhibited": [{"name": "test"}]}
            </script>
        </html>
        """
        mock_get.return_value = mock_response

        result = fetch_drupal_settings("http://test.com")
        assert "dodProhibited" in result
        assert result["dodProhibited"] == [{"name": "test"}]

    @patch("http_client.HttpClient.get")
    def test_fetch_drupal_settings_no_script_tag(self, mock_get):
        """Test fetch when script tag is missing"""
        mock_response = MagicMock()
        mock_response.text = "<html></html>"
        mock_get.return_value = mock_response

        with pytest.raises(ValueError, match="Drupal settings script tag not found"):
            fetch_drupal_settings("http://test.com")

    @patch("http_client.HttpClient.get")
    def test_fetch_drupal_settings_request_error(self, mock_get):
        """Test fetch when request fails"""
        mock_get.side_effect = Exception("Network error")

        with pytest.raises(Exception, match="Network error"):
            fetch_drupal_settings("http://test.com")
