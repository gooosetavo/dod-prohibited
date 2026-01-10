"""
Test cases for the new Substance dataclass functionality.
"""

import pytest
from substance import Substance, UniiInfo


class TestSubstance:
    """Test cases for the Substance dataclass."""

    def test_substance_basic_properties(self):
        """Test basic substance properties."""
        data = {
            "Name": "Test Substance",
            "Other_names": '["Alternative Name", "Another Name"]',
            "Classifications": '["stimulant", "synthetic"]',
            "Reason": "Prohibited by FDA",
            "Guid": "test-guid-123"
        }
        
        substance = Substance(data=data)
        
        assert substance.name == "Test Substance"
        assert substance.other_names == ["Alternative Name", "Another Name"]
        assert substance.classifications == ["stimulant", "synthetic"]
        assert substance.reason == "Prohibited by FDA"
        assert substance.guid == "test-guid-123"
        assert substance.slug == "test-substance"

    def test_substance_list_parsing_string(self):
        """Test parsing of string-encoded lists."""
        data = {
            "Name": "Test Substance",
            "Other_names": '["Name 1", "Name 2"]',
            "Classifications": '["class1", "class2"]',
            "Warnings": '["warning1", "warning2"]'
        }
        
        substance = Substance(data=data)
        
        assert substance.other_names == ["Name 1", "Name 2"]
        assert substance.classifications == ["class1", "class2"]
        assert substance.warnings == ["warning1", "warning2"]

    def test_substance_list_parsing_actual_list(self):
        """Test parsing when data is already a list."""
        data = {
            "Name": "Test Substance",
            "Other_names": ["Name 1", "Name 2"],
            "Classifications": ["class1", "class2"],
            "Warnings": ["warning1", "warning2"]
        }
        
        substance = Substance(data=data)
        
        assert substance.other_names == ["Name 1", "Name 2"]
        assert substance.classifications == ["class1", "class2"]
        assert substance.warnings == ["warning1", "warning2"]

    def test_substance_empty_or_none_fields(self):
        """Test behavior with empty or None fields."""
        data = {
            "Name": "Test Substance",
            "Other_names": None,
            "Classifications": "",
            "Warnings": []
        }
        
        substance = Substance(data=data)
        
        assert substance.name == "Test Substance"
        assert substance.other_names == []
        assert substance.classifications == []
        assert substance.warnings == []

    def test_substance_dea_schedule_extraction(self):
        """Test DEA schedule extraction from reasons."""
        # Test Schedule I detection
        data = {
            "Name": "Test Substance",
            "Reasons": '[{"reason": "DEA Schedule I controlled substance", "link": "http://example.com"}]'
        }
        substance = Substance(data=data)
        assert substance.dea_schedule == "Schedule I"
        
        # Test Schedule II detection
        data2 = {
            "Name": "Test Substance",
            "Reasons": '[{"reason": "Controlled under DEA Schedule II", "link": "http://example.com"}]'
        }
        substance2 = Substance(data=data2)
        assert substance2.dea_schedule == "Schedule II"
        
        # Test no schedule
        data3 = {
            "Name": "Test Substance", 
            "Reasons": '[{"reason": "Prohibited for other reasons", "link": "http://example.com"}]'
        }
        substance3 = Substance(data=data3)
        assert substance3.dea_schedule is None

    def test_substance_name_fallback(self):
        """Test name fallback logic."""
        # Test primary Name field
        data = {"Name": "Primary Name", "ingredient": "Secondary Name"}
        substance = Substance(data=data)
        assert substance.name == "Primary Name"
        
        # Test fallback to ingredient
        data = {"ingredient": "Secondary Name", "substance": "Tertiary Name"}
        substance = Substance(data=data)
        assert substance.name == "Secondary Name"
        
        # Test fallback to no name
        data = {}
        substance = Substance(data=data)
        assert substance.name == "(no name)"

    def test_substance_slug_generation(self):
        """Test URL slug generation."""
        data = {"Name": "Test Substance With Spaces!"}
        substance = Substance(data=data)
        assert substance.slug == "test-substance-with-spaces"
        
        # Test special characters
        data = {"Name": "Test-Substance (123) & More!"}
        substance = Substance(data=data)
        assert substance.slug == "test-substance-123-more"

    def test_substance_source_date_parsing(self):
        """Test source updated date parsing."""
        import json
        from datetime import datetime
        
        # Test valid timestamp
        timestamp = 1640995200  # 2022-01-01 00:00:00 UTC
        updated_data = json.dumps({"_seconds": timestamp})
        data = {
            "Name": "Test Substance",
            "updated": updated_data
        }
        
        substance = Substance(data=data)
        expected_date = datetime.fromtimestamp(timestamp).isoformat()
        assert substance.source_updated_date == expected_date
        
        # Test invalid data
        data["updated"] = "invalid json"
        substance = Substance(data=data)
        assert substance.source_updated_date == "invalid json"


class TestUniiInfo:
    """Test cases for the UniiInfo dataclass."""

    def test_unii_info_basic_properties(self):
        """Test basic UNII info properties."""
        data = {
            "UNII": "ABC123DEF456",
            "PT": "Test Chemical",
            "RN": "123-45-6",
            "TYPE": "Chemical",
            "PUBCHEM": "12345",
            "EPA_CompTox": "DTXSID123456"
        }
        
        unii_info = UniiInfo(data=data)
        
        assert unii_info.unii == "ABC123DEF456"
        assert unii_info.preferred_term == "Test Chemical"
        assert unii_info.cas_rn == "123-45-6"
        assert unii_info.substance_type == "Chemical"
        assert unii_info.pubchem_cid == 12345
        assert unii_info.comptox_id == "DTXSID123456"

    def test_unii_info_url_properties(self):
        """Test UNII URL generation."""
        data = {
            "UNII": "ABC123DEF456",
            "UNII_URL": "https://precision.fda.gov/uniisearch/srs/unii/ABC123DEF456",
            "PUBCHEM_URL": "https://pubchem.ncbi.nlm.nih.gov/compound/12345"
        }
        
        unii_info = UniiInfo(data=data)
        
        assert unii_info.fda_unii_url == "https://precision.fda.gov/uniisearch/srs/unii/ABC123DEF456"
        assert unii_info.pubchem_url == "https://pubchem.ncbi.nlm.nih.gov/compound/12345"


class TestSubstanceUniiIntegration:
    """Test integration between Substance and UNII data."""

    def test_substance_with_unii_info(self):
        """Test substance with attached UNII info."""
        substance_data = {"Name": "Test Substance"}
        unii_data = {
            "UNII": "ABC123DEF456",
            "PT": "Test Chemical",
            "RN": "123-45-6"
        }
        
        substance = Substance(data=substance_data)
        substance.set_unii_info(unii_data)
        
        assert substance.unii_info is not None
        assert substance.unii_info.unii == "ABC123DEF456"
        assert substance.unii_info.preferred_term == "Test Chemical"
        assert substance.unii_info.cas_rn == "123-45-6"

    def test_substance_without_unii_info(self):
        """Test substance without UNII info."""
        substance_data = {"Name": "Test Substance"}
        substance = Substance(data=substance_data)
        
        assert substance.unii_info is None