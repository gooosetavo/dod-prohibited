"""
This module defines the Substance dataclass, which encapsulates all data 
and logic related to a single prohibited substance.
"""

import ast
import hashlib
import json
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import pandas as pd


def slugify(value: str) -> Optional[str]:
    """
    Normalizes string, converts to lowercase, removes non-alpha characters,
    and converts spaces to hyphens.
    """
    value = str(value).strip().lower()
    value = (
        unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    )
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or None


def _parse_list_field(value: Any) -> List[Any]:
    """
    Parses a field that can be a string representation of a list or a list.
    """
    if not value:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        if value.strip().startswith("[") and value.strip().endswith("]"):
            try:
                # More reliable for JSON-like strings
                return json.loads(value)
            except json.JSONDecodeError:
                try:
                    # Fallback for Python literal structures
                    return ast.literal_eval(value)
                except (ValueError, SyntaxError):
                    # If parsing fails, return the raw string in a list
                    return [value]
        # It's just a plain string, wrap it in a list
        return [value]
    return []


@dataclass
class UniiInfo:
    """
    Dataclass to hold UNII (Unique Ingredient Identifier) information.
    """
    data: Dict[str, Any]

    @property
    def unii(self) -> Optional[str]:
        return self.data.get("UNII")

    @property
    def preferred_term(self) -> Optional[str]:
        return self.data.get("PT")

    @property
    def cas_rn(self) -> Optional[str]:
        return self.data.get("RN")

    @property
    def substance_type(self) -> Optional[str]:
        return self.data.get("TYPE")

    @property
    def pubchem_cid(self) -> Optional[int]:
        pubchem = self.data.get("PUBCHEM")
        return int(pubchem) if pd.notna(pubchem) else None

    @property
    def comptox_id(self) -> Optional[str]:
        return self.data.get("EPA_CompTox")

    @property
    def fda_unii_url(self) -> Optional[str]:
        return self.data.get("UNII_URL")

    @property
    def gsrs_record_url(self) -> Optional[str]:
        return self.data.get("GSRS_FULL_RECORD_URL")

    @property
    def ncats_url(self) -> Optional[str]:
        return self.data.get("NCATS_URL")

    @property
    def cas_common_chemistry_url(self) -> Optional[str]:
        return self.data.get("COMMONCHEMISTRY_URL")

    @property
    def pubchem_url(self) -> Optional[str]:
        return self.data.get("PUBCHEM_URL")

    @property
    def epa_comptox_url(self) -> Optional[str]:
        return self.data.get("EPA_COMPTOX_URL")


@dataclass
class Substance:
    """
    Represents a single substance, encapsulating its data and related logic.
    """
    data: Dict[str, Any]
    unii_info: Optional[UniiInfo] = None

    @property
    def name(self) -> str:
        """Returns the primary name of the substance."""
        return (
            self.data.get("Name")
            or self.data.get("ingredient")
            or self.data.get("name")
            or self.data.get("substance")
            or self.data.get("title")
            or "(no name)"
        )

    @property
    def slug(self) -> str:
        """Generates a URL-friendly slug for the substance."""
        name_slug = slugify(self.name)
        if name_slug:
            return name_slug
        # Fallback to a hash if no name is available
        hashval = hashlib.sha1(
            json.dumps(self.data, sort_keys=True).encode("utf-8")
        ).hexdigest()[:10]
        return f"substance-{hashval}"

    @property
    def other_names(self) -> List[str]:
        """Returns a list of other names for the substance."""
        return _parse_list_field(
            self.data.get("Other_names") or self.data.get("other_names")
        )

    @property
    def classifications(self) -> List[str]:
        """Returns a list of classifications."""
        return _parse_list_field(
            self.data.get("Classifications") or self.data.get("classifications")
        )

    @property
    def reasons_for_prohibition(self) -> List[Union[str, Dict[str, str]]]:
        """Returns a list of reasons for prohibition."""
        return _parse_list_field(self.data.get("Reasons") or self.data.get("reasons"))

    @property
    def warnings(self) -> List[str]:
        """Returns a list of warnings."""
        return _parse_list_field(self.data.get("Warnings") or self.data.get("warnings"))

    @property
    def references(self) -> List[Union[str, Dict[str, str]]]:
        """Returns a list of references."""
        return _parse_list_field(
            self.data.get("References") or self.data.get("references")
        )

    @property
    def more_info_url(self) -> Optional[str]:
        """Returns the URL for more information."""
        return self.data.get("More_info_url") or self.data.get("more_info_url")

    @property
    def source_of(self) -> Optional[str]:
        """Returns the source of the substance."""
        return self.data.get("Sourceof") or self.data.get("sourceof")

    @property
    def reason(self) -> Optional[str]:
        """Returns the primary reason for prohibition."""
        return self.data.get("Reason") or self.data.get("reason")

    @property
    def label_terms(self) -> Optional[str]:
        """Returns label terms."""
        return self.data.get("Label_terms") or self.data.get("label_terms")

    @property
    def linked_ingredients(self) -> Optional[str]:
        """Returns linked ingredients."""
        return self.data.get("Linked_ingredients") or self.data.get("linked_ingredients")

    @property
    def searchable_name(self) -> Optional[str]:
        """Returns the searchable name."""
        return self.data.get("Searchable_name") or self.data.get("searchable_name")

    @property
    def guid(self) -> Optional[str]:
        """Returns the GUID."""
        return self.data.get("Guid") or self.data.get("guid")

    @property
    def added_date(self) -> Optional[str]:
        """Returns the date the substance was added to the database."""
        return self.data.get("added")

    @property
    def source_updated_date(self) -> Optional[str]:
        """Returns the date the substance was last updated in the source database."""
        updated = self.data.get("updated")
        if isinstance(updated, str) and updated.strip():
            try:
                updated_json = json.loads(updated)
                if isinstance(updated_json, dict) and "_seconds" in updated_json:
                    timestamp = updated_json["_seconds"]
                    return datetime.fromtimestamp(timestamp).isoformat()
            except (json.JSONDecodeError, ValueError, TypeError, OSError):
                logging.warning(f"Could not parse source update timestamp for {self.name}")
        return updated

    @property
    def dea_schedule(self) -> Optional[str]:
        """Extracts the DEA schedule from the reasons for prohibition."""
        reasons = self.reasons_for_prohibition
        for reason in reasons:
            reason_text = (
                reason.get("reason", "").lower()
                if isinstance(reason, dict)
                else str(reason).lower()
            )
            if "schedule" in reason_text and ("dea" in reason_text or "csa" in reason_text):
                # Check for specific schedules in order from most specific to least
                if "schedule v" in reason_text:
                    return "Schedule V"
                if "schedule iv" in reason_text:
                    return "Schedule IV"
                if "schedule iii" in reason_text:
                    return "Schedule III"
                if "schedule ii" in reason_text:
                    return "Schedule II"
                if "schedule i" in reason_text:
                    return "Schedule I"
        return None

    def set_unii_info(self, unii_data: Dict[str, Any]):
        """
        Attaches UNII information to the substance.
        """
        self.unii_info = UniiInfo(data=unii_data)
