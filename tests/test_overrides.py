"""
Tests for the substance overrides module.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, mock_open
import pandas as pd

from dod_prohibited.overrides import load_overrides, get_unii_override
from dod_prohibited.site_builder import find_unii_data_by_code


SAMPLE_YAML = """\
substances:
  kratom:
    unii: 754HG7WK00
  another-substance:
    unii: ABCDEF1234
"""


class TestLoadOverrides:
    def test_returns_empty_dict_when_file_missing(self, tmp_path):
        result = load_overrides(tmp_path / "nonexistent.yaml")
        assert result == {}

    def test_loads_substances(self, tmp_path):
        p = tmp_path / "overrides.yaml"
        p.write_text(SAMPLE_YAML)
        result = load_overrides(p)
        assert "kratom" in result
        assert result["kratom"]["unii"] == "754HG7WK00"

    def test_returns_empty_dict_for_empty_file(self, tmp_path):
        p = tmp_path / "overrides.yaml"
        p.write_text("")
        assert load_overrides(p) == {}

    def test_returns_empty_dict_when_no_substances_key(self, tmp_path):
        p = tmp_path / "overrides.yaml"
        p.write_text("other_key: value\n")
        assert load_overrides(p) == {}


class TestGetUniiOverride:
    def test_returns_unii_for_known_slug(self):
        overrides = {"kratom": {"unii": "754HG7WK00"}}
        assert get_unii_override(overrides, "kratom") == "754HG7WK00"

    def test_returns_none_for_unknown_slug(self):
        overrides = {"kratom": {"unii": "754HG7WK00"}}
        assert get_unii_override(overrides, "caffeine") is None

    def test_returns_none_when_entry_has_no_unii(self):
        overrides = {"kratom": {"some_other_field": "value"}}
        assert get_unii_override(overrides, "kratom") is None

    def test_returns_none_for_empty_overrides(self):
        assert get_unii_override({}, "kratom") is None


class TestFindUniiDataByCode:
    def _make_df(self):
        return pd.DataFrame([
            {"UNII": "754HG7WK00", "PT": "KRATOM", "DISPLAY_NAME": "KRATOM", "RN": None, "TYPE": "Botanical"},
            {"UNII": "ABCDEF1234", "PT": "OTHER", "DISPLAY_NAME": "OTHER", "RN": "123-45-6", "TYPE": "Chemical"},
        ])

    def test_finds_by_unii_code(self):
        df = self._make_df()
        result = find_unii_data_by_code("754HG7WK00", df)
        assert result is not None
        assert result["UNII"] == "754HG7WK00"
        assert result["PT"] == "KRATOM"

    def test_returns_none_for_unknown_code(self):
        df = self._make_df()
        assert find_unii_data_by_code("XXXXXXXXXX", df) is None

    def test_returns_none_for_none_df(self):
        assert find_unii_data_by_code("754HG7WK00", None) is None

    def test_returns_none_for_empty_code(self):
        df = self._make_df()
        assert find_unii_data_by_code("", df) is None
