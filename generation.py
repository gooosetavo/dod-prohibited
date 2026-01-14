from pathlib import Path
import ast
import json
import hashlib
import logging
import re
import unicodedata
import pandas as pd
from typing import TYPE_CHECKING, List, Dict, Any, Optional
from jinja2 import Environment, FileSystemLoader
from unii_client import UniiDataClient
from substance import Substance

if TYPE_CHECKING:
    pass


# slugify and get_short_slug functions moved to substance.py


def enhance_unii_data(unii_df: pd.DataFrame) -> pd.DataFrame:
    """
    Enhance UNII DataFrame with additional URL fields for external resources.
    
    Args:
        unii_df: DataFrame containing UNII data
        
    Returns:
        Enhanced DataFrame with additional URL columns
    """
    enhanced_df = unii_df.copy()
    
    # Helper functions for URL generation
    def to_pubchem_url(pubchem_id):
        return f"https://pubchem.ncbi.nlm.nih.gov/compound/{int(pubchem_id)}" if not pd.isna(pubchem_id) else None
    
    def to_comptox_url(comptox_id):
        return f"https://comptox.epa.gov/dashboard/chemical/details/{comptox_id}" if not pd.isna(comptox_id) else None
    
    # Add DISPLAY_NAME column for matching (uppercase preferred term)
    if 'PT' in enhanced_df.columns:
        enhanced_df["DISPLAY_NAME"] = enhanced_df["PT"].str.upper()
    
    # Add URL columns
    enhanced_df["UNII_URL"] = enhanced_df["UNII"].apply(lambda x: f"https://precision.fda.gov/uniisearch/srs/unii/{x}")
    enhanced_df["COMMONCHEMISTRY_URL"] = enhanced_df["RN"].apply(lambda x: f"https://commonchemistry.cas.org/detail?cas_rn={x}" if not pd.isna(x) else None)
    enhanced_df["NCATS_URL"] = enhanced_df["UNII"].apply(lambda x: f"https://drugs.ncats.io/substance/{x}")
    enhanced_df["GSRS_FULL_RECORD_URL"] = enhanced_df["UNII"].apply(lambda x: f"https://precision.fda.gov/ginas/app/ui/substances/{x}")
    enhanced_df["PUBCHEM_URL"] = enhanced_df["PUBCHEM"].apply(to_pubchem_url)
    enhanced_df["EPA_COMPTOX_URL"] = enhanced_df["EPA_CompTox"].apply(to_comptox_url)
    
    return enhanced_df


def load_unii_data(settings=None) -> Optional[pd.DataFrame]:
    """
    Load and enhance UNII data from the FDA database.
    
    Args:
        settings: Settings object containing configuration options for authentication and user-agent
    
    Returns:
        Enhanced UNII DataFrame or None if data cannot be loaded
    """
    try:
        from unii_client import UniiDataConfig
        config = UniiDataConfig(settings=settings)
        client = UniiDataClient(config)
        # Download ZIP if needed
        client.download_zip()
        
        # Load the UNII records (assuming this is the main file)
        unii_df = client.load_csv_data('UNII_Records_18Aug2025.txt', sep='\t')
        
        # Enhance with URLs
        enhanced_df = enhance_unii_data(unii_df)
        
        return enhanced_df
    except Exception as e:
        print(f"Warning: Could not load UNII data: {e}")
        return None


def find_unii_data_for_substance(substance_name: str, unii_df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    Find UNII data for a given substance name.
    
    Args:
        substance_name: Name of the substance to look up
        unii_df: Enhanced UNII DataFrame
        
    Returns:
        Dictionary containing UNII data if found, None otherwise
    """
    if unii_df is None or substance_name is None:
        return None
    
    # Create display name for matching
    display_name = substance_name.upper()
    
    # Try exact match first
    match = unii_df[unii_df['DISPLAY_NAME'] == display_name]
    if not match.empty:
        return match.iloc[0].to_dict()
    
    # Try partial match on PT (preferred term)
    if 'PT' in unii_df.columns:
        match = unii_df[unii_df['PT'].str.upper() == display_name]
        if not match.empty:
            return match.iloc[0].to_dict()
    
    return None


def generate_substance_pages(
    data: List[Dict[str, Any]], columns: List[str], substances_dir: Path, settings=None
) -> None:
    """
    Generates a Markdown file for each substance in the data list.
    Args:
        data: List of substance dictionaries.
        columns: List of column names to include.
        substances_dir: Path to the directory where files will be written.
        settings: Settings object containing configuration options.
    """
    # Load UNII data if enabled in settings
    unii_df = None
    if settings and getattr(settings, 'use_unii_data', False):
        unii_df = load_unii_data(settings)
        if unii_df is not None:
            print(f"Loaded UNII data with {len(unii_df)} records")
        else:
            print("UNII data not available - substance pages will be generated without UNII information")
    
    # Convert dictionaries to Substance objects
    substances = []
    for entry in data:
        substance = Substance(data=entry)
        if unii_df is not None:
            unii_data = find_unii_data_for_substance(substance.name, unii_df)
            if unii_data:
                substance.set_unii_info(unii_data)
        substances.append(substance)
    
    # Sort substances alphabetically by name for consistent ordering
    sorted_substances = sorted(substances, key=lambda x: x.name.lower())

    links = []
    for i, substance in enumerate(sorted_substances):
        page_path = substances_dir / f"{substance.slug}.md"
        links.append((substance.name, f"{substance.slug}.md"))

        # Determine previous and next substance
        prev_substance = None
        next_substance = None
        if i > 0:
            prev_sub = sorted_substances[i - 1]
            prev_substance = (prev_sub.name, f"{prev_sub.slug}.md")
        if i < len(sorted_substances) - 1:
            next_sub = sorted_substances[i + 1]
            next_substance = (next_sub.name, f"{next_sub.slug}.md")

        generator = SubstancePageGenerator(substance, i + 1, len(sorted_substances), prev_substance, next_substance)
        generator.generate_page(page_path)


class SubstancePageGenerator:
    """Handles generation of individual substance pages."""
    
    def __init__(self, substance: Substance, current_index: int, total_count: int, 
                 prev_substance=None, next_substance=None):
        self.substance = substance
        self.current_index = current_index
        self.total_count = total_count
        self.prev_substance = prev_substance
        self.next_substance = next_substance
    
    def generate_page(self, page_path: Path):
        """Generate the complete markdown page for this substance."""
        with open(page_path, "w", encoding="utf-8") as f:
            self._write_header(f)
            self._write_navigation(f)
            self._write_basic_info(f)
            self._write_unii_info(f)
            self._write_footer_navigation(f)
    
    def _generate_search_keywords(self):
        """Generate search keywords including common misspellings and variations."""
        keywords = set()
        name = self.substance.name.lower()
        
        # Add the main name
        keywords.add(self.substance.name)
        keywords.add(name)
        
        # Add other names if available
        if self.substance.other_names:
            for other_name in self.substance.other_names:
                keywords.add(other_name)
                keywords.add(other_name.lower())
        
        # Generate dynamic misspellings
        keywords.update(self._generate_misspellings(name))
        keywords.update(self._generate_abbreviations(name))
        keywords.update(self._generate_chemical_variations(name))
        keywords.update(self._generate_phonetic_variations(name))
        
        # Add partial matches (useful for partial typing)
        if len(name) > 4:
            for i in range(3, min(len(name), 8)):
                keywords.add(name[:i])
        
        # Remove duplicates and very short keywords
        keywords = {k for k in keywords if len(k) >= 3}
        
        return sorted(list(keywords))
    
    def _generate_misspellings(self, name):
        """Generate common misspellings using edit distance and typing errors."""
        variations = set()
        
        # 1. Single character deletions (missing letters)
        for i in range(len(name)):
            variation = name[:i] + name[i+1:]
            if len(variation) >= 3:
                variations.add(variation)
        
        # 2. Single character substitutions (wrong letters)
        # Focus on common letter confusions
        substitutions = {
            'c': ['k', 's'], 'k': ['c'], 's': ['c', 'z'], 'z': ['s'],
            'ph': ['f'], 'f': ['ph'], 'i': ['y'], 'y': ['i'],
            'e': ['a'], 'a': ['e'], 'o': ['u'], 'u': ['o'],
            'th': ['t'], 'ine': ['ene', 'ane'], 'ene': ['ine', 'ane']
        }
        
        for original, replacements in substitutions.items():
            if original in name:
                for replacement in replacements:
                    variations.add(name.replace(original, replacement))
        
        # 3. Character transpositions (swapped letters)
        for i in range(len(name) - 1):
            swapped = name[:i] + name[i+1] + name[i] + name[i+2:]
            variations.add(swapped)
        
        # 4. Double letter variations (adding/removing doubled letters)
        # Remove doubled letters
        import re
        no_doubles = re.sub(r'(.)\1+', r'\1', name)
        if no_doubles != name:
            variations.add(no_doubles)
        
        # Add doubled letters at common positions
        for i, char in enumerate(name):
            if char.isalpha() and (i == 0 or name[i-1] != char):
                doubled = name[:i] + char + name[i:]
                variations.add(doubled)
        
        return variations
    
    def _generate_abbreviations(self, name):
        """Generate abbreviations and shortened forms."""
        abbreviations = set()
        
        # Extract abbreviations from compound names with hyphens/numbers
        parts = re.split(r'[-\s\d]+', name)
        if len(parts) > 1:
            # Take first letters of each part
            abbrev = ''.join(part[0] for part in parts if part and part[0].isalpha())
            if len(abbrev) >= 2:
                abbreviations.add(abbrev)
                # Also add with numbers/hyphens
                number_parts = re.findall(r'\d+', name)
                if number_parts:
                    for num in number_parts:
                        abbreviations.add(f"{abbrev}-{num}")
                        abbreviations.add(f"{abbrev}{num}")
        
        # Common chemical abbreviations
        if 'testosterone' in name:
            abbreviations.update(['test', 'testo'])
        if 'androstenedione' in name:
            abbreviations.update(['andro', 'dione'])
        if 'methyltestosterone' in name:
            abbreviations.update(['mtest', 'mt'])
        if 'nandrolone' in name:
            abbreviations.update(['nandro', 'nan'])
        
        # Extract from patterns like "mk-677", "lgd-4033"
        pattern_matches = re.findall(r'([a-z]+)[-\s]*(\d+)', name)
        for letter_part, number_part in pattern_matches:
            abbreviations.add(letter_part)
            abbreviations.add(f"{letter_part}{number_part}")
            abbreviations.add(f"{letter_part}-{number_part}")
        
        return abbreviations
    
    def _generate_chemical_variations(self, name):
        """Generate variations based on chemical nomenclature patterns."""
        variations = set()
        
        # Common chemical name transformations
        transformations = {
            'ine': ['in', 'ene', 'ane'],
            'ene': ['ine', 'ane', 'en'],
            'ane': ['ine', 'ene', 'an'],
            'one': ['on', 'ane'],
            'ol': ['ol', 'anol', 'enol'],
            'yl': ['il', 'al'],
            'methyl': ['meth', 'methil'],
            'ethyl': ['eth', 'ethil'],
            'hydroxy': ['hydrox', 'hydroxi', 'oh'],
            'oxy': ['ox', 'oxi'],
            'amino': ['amin', 'amina'],
            'nitro': ['nitr', 'nitru'],
            'chloro': ['chlor', 'cloro'],
            'fluoro': ['fluor', 'fluro', 'flour'],
            'bromo': ['brom', 'bromo'],
            'iodo': ['iod', 'ioda'],
            'phenyl': ['phen', 'fenil'],
            'benzyl': ['benz', 'benzil'],
            'cyclo': ['ciclo', 'cycl'],
            'steroid': ['sterod', 'esteroid'],
            'androst': ['androst', 'androste'],
            'estro': ['estro', 'estra'],
            'diol': ['diol', 'di-ol'],
            'dione': ['dion', 'di-one'],
            'triol': ['triol', 'tri-ol'],
            'trione': ['trion', 'tri-one']
        }
        
        for original, variants in transformations.items():
            if original in name:
                for variant in variants:
                    if variant != original:
                        variations.add(name.replace(original, variant))
        
        # Handle number variations (with/without hyphens)
        # e.g., "lgd-4033" -> "lgd4033", "mk-677" -> "mk677"
        no_hyphens = re.sub(r'-', '', name)
        if no_hyphens != name:
            variations.add(no_hyphens)
        
        # Add hyphens where there might be numbers
        with_hyphens = re.sub(r'([a-z])(\d)', r'\1-\2', name)
        if with_hyphens != name:
            variations.add(with_hyphens)
        
        return variations
    
    def _generate_phonetic_variations(self, name):
        """Generate phonetically similar variations."""
        variations = set()
        
        # Common phonetic substitutions
        phonetic_substitutions = {
            'ph': 'f', 'f': 'ph',
            'c': 'k', 'k': 'c',
            'z': 's', 's': 'z',
            'i': 'y', 'y': 'i',
            'tion': 'shun', 'sion': 'shun',
            'ch': 'k', 'ck': 'k',
            'qu': 'kw', 'x': 'ks',
            'j': 'g', 'g': 'j'
        }
        
        for original, replacement in phonetic_substitutions.items():
            if original in name:
                variations.add(name.replace(original, replacement))
        
        # Vowel variations (people often mix up vowels)
        vowel_groups = [
            ['a', 'e'], ['i', 'y'], ['o', 'u'], ['ei', 'ai', 'ay'], ['ou', 'ow']
        ]
        
        for group in vowel_groups:
            for vowel in group:
                if vowel in name:
                    for replacement in group:
                        if replacement != vowel:
                            variations.add(name.replace(vowel, replacement))
        
        return variations

    def _write_header(self, f):
        """Write the page header with metadata front matter."""
        # Generate search keywords including common misspellings
        search_keywords = self._generate_search_keywords()
        
        # Write YAML front matter
        f.write("---\n")
        f.write(f"title: {self.substance.name}\n")
        f.write(f"description: Information about {self.substance.name}, a substance prohibited by the Department of Defense\n")
        f.write(f"keywords: {', '.join(search_keywords)}\n")
        f.write(f"tags: {search_keywords}\n")  # Alternative format for search indexing
        f.write("---\n\n")
        
        # Also add the keywords as hidden text content for search indexing
        f.write("<!-- Search Keywords: " + " ".join(search_keywords) + " -->\n\n")
        
        f.write(f"# {self.substance.name}\n\n")
    
    def _write_navigation(self, f):
        """Write the top navigation."""
        f.write("---\n\n")
        nav_parts = []
        if self.prev_substance:
            nav_parts.append(
                f"← [Previous: {self.prev_substance[0]}]({self.prev_substance[1]})"
            )
        nav_parts.append("[🏠 All Substances](index.md)")
        nav_parts.append("[📊 Complete Table](table.md)")
        if self.next_substance:
            nav_parts.append(f"[Next: {self.next_substance[0]}]({self.next_substance[1]}) →")
        f.write(" | ".join(nav_parts) + "\n\n")
        f.write("---\n\n")
    
    def _write_basic_info(self, f):
        """Write all basic substance information sections."""
        self._write_other_names(f)
        self._write_classifications(f)
        self._write_reasons_for_prohibition(f)
        self._write_warnings(f)
        self._write_references(f)
        self._write_metadata(f)
    
    def _write_other_names(self, f):
        """Write other names section."""
        other_names = self.substance.other_names
        if other_names:
            f.write("**Other names:**\n\n")
            for name in other_names:
                f.write(f"- {name}\n")
            f.write("\n")
    
    def _write_classifications(self, f):
        """Write classifications section."""
        classifications = self.substance.classifications
        if classifications:
            f.write("**Classifications:**\n\n")
            for classification in classifications:
                f.write(f"- {classification}\n")
            f.write("\n")
    
    def _write_reasons_for_prohibition(self, f):
        """Write reasons for prohibition section."""
        reasons = self.substance.reasons_for_prohibition
        if reasons:
            f.write("**Reasons for prohibition:**\n\n")
            for reason in reasons:
                if isinstance(reason, dict):
                    reason_text = reason.get('reason', '').strip()
                    if reason_text:
                        line = f"- {reason_text}"
                        if reason.get("link"):
                            link_title = reason.get("link_title", "source")
                            line += f" (<a href=\"{reason['link']}\" target=\"_blank\">{link_title}</a>)"
                        f.write(line + "\n")
                elif isinstance(reason, str) and reason.strip():
                    f.write(f"- {reason.strip()}\n")
            f.write("\n")
    
    def _write_warnings(self, f):
        """Write warnings section."""
        warnings = self.substance.warnings
        if warnings:
            f.write("**Warnings:**\n\n")
            for warning in warnings:
                f.write(f"- {warning}\n")
            f.write("\n")
    
    def _write_references(self, f):
        """Write references section."""
        refs = self.substance.references
        if refs:
            f.write("**References:**\n\n")
            for ref in refs:
                if isinstance(ref, dict):
                    title = ref.get("title", "")
                    url = ref.get("url", "")
                    if title and url:
                        f.write(f"- <a href=\"{url}\" target=\"_blank\">{title}</a>\n")
                    elif title:
                        f.write(f"- {title}\n")
                    elif url:
                        f.write(f"- <a href=\"{url}\" target=\"_blank\">{url}</a>\n")
                    else:
                        f.write(f"- {ref}\n")
                else:
                    f.write(f"- {ref}\n")
            f.write("\n")
    
    def _write_metadata(self, f):
        """Write metadata fields."""
        # More info URL
        more_info_url = self.substance.more_info_url
        if more_info_url and more_info_url.strip():
            f.write(f"**More info:** <a href=\"{more_info_url}\" target=\"_blank\">{more_info_url}</a>\n\n")
        else:
            f.write("**More info:** Not specified\n\n")
        
        # Other metadata fields
        f.write(f"**Source of:** {self.substance.source_of or 'Not specified'}\n\n")
        f.write(f"**Reason:** {self.substance.reason or 'Not specified'}\n\n")
        f.write(f"**Label terms:** {self.substance.label_terms or 'Not specified'}\n\n")
        f.write(f"**Linked ingredients:** {self.substance.linked_ingredients or 'Not specified'}\n\n")
        f.write(f"**Searchable name:** {self.substance.searchable_name or 'Not specified'}\n\n")
        f.write(f"**GUID:** {self.substance.guid or 'Not specified'}\n\n")
        
        # Date fields
        if self.substance.added_date:
            f.write(f"**Added to this Database:** {self.substance.added_date}\n\n")
        
        source_date = self.substance.source_updated_date
        if source_date:
            f.write(f"**Last updated in source database:** {source_date}\n\n")
    
    def _write_unii_info(self, f):
        """Write UNII information section."""
        if self.substance.unii_info:
            unii = self.substance.unii_info
            f.write("## UNII (Unique Ingredient Identifier) Information\n\n")
            
            f.write(f"**UNII ID:** {unii.unii or 'Not available'}\n\n")
            
            if unii.preferred_term:
                f.write(f"**Preferred Term:** {unii.preferred_term}\n\n")
            
            if unii.cas_rn:
                f.write(f"**CAS Registry Number:** {unii.cas_rn}\n\n")
            
            if unii.substance_type:
                f.write(f"**Substance Type:** {unii.substance_type}\n\n")
            
            # External links
            f.write("**External Resources:**\n\n")
            
            links_added = False
            
            if unii.fda_unii_url:
                f.write(f"- <a href=\"{unii.fda_unii_url}\" target=\"_blank\">FDA UNII Search</a>\n")
                links_added = True
            
            if unii.gsrs_record_url:
                f.write(f"- <a href=\"{unii.gsrs_record_url}\" target=\"_blank\">GSRS Full Record</a>\n")
                links_added = True
            
            if unii.ncats_url:
                f.write(f"- <a href=\"{unii.ncats_url}\" target=\"_blank\">NCATS Inxight Drugs</a>\n")
                links_added = True
            
            if unii.cas_common_chemistry_url:
                f.write(f"- <a href=\"{unii.cas_common_chemistry_url}\" target=\"_blank\">CAS Common Chemistry</a>\n")
                links_added = True
            
            if unii.pubchem_url:
                f.write(f"- <a href=\"{unii.pubchem_url}\" target=\"_blank\">PubChem</a>\n")
                links_added = True
            
            if unii.epa_comptox_url:
                f.write(f"- <a href=\"{unii.epa_comptox_url}\" target=\"_blank\">EPA CompTox Dashboard</a>\n")
                links_added = True
            
            if not links_added:
                f.write("- No external resources available\n")
            
            f.write("\n")
    
    def _write_footer_navigation(self, f):
        """Write footer navigation."""
        f.write("---\n\n")
        f.write("📊 [Complete Table](table.md) | 🏠 [All Substances](index.md)\n\n")
        f.write(f"*Substance {self.current_index} of {self.total_count}*\n\n")


def extract_dea_schedule(reasons_data):
    """Extract DEA schedule information from reasons data."""
    if not reasons_data:
        return None

    if isinstance(reasons_data, str):
        try:
            import json
            import ast
            
            # First try JSON parsing (more reliable)
            try:
                reasons_data = json.loads(reasons_data)
            except json.JSONDecodeError:
                # Fallback to ast.literal_eval
                reasons_data = ast.literal_eval(reasons_data)
        except Exception:
            # If parsing fails, check if it looks like JSON
            if reasons_data.strip().startswith('[') and reasons_data.strip().endswith(']'):
                # This looks like JSON that failed to parse, don't process
                return None
            else:
                # Treat as simple string
                reasons_data = [reasons_data]

    if not isinstance(reasons_data, list):
        reasons_data = [reasons_data]

    for reason in reasons_data:
        if isinstance(reason, dict):
            reason_text = reason.get("reason", "").lower()
        else:
            reason_text = str(reason).lower()

        if "schedule" in reason_text and "dea" in reason_text:
            if "schedule i" in reason_text:
                return "Schedule I"
            elif "schedule ii" in reason_text:
                return "Schedule II"
            elif "schedule iii" in reason_text:
                return "Schedule III"
            elif "schedule iv" in reason_text:
                return "Schedule IV"
            elif "schedule v" in reason_text:
                return "Schedule V"

    return None


def generate_substances_table(
    data: List[Dict[str, Any]], columns: List[str], docs_dir: Path
) -> None:
    """
    Generates a comprehensive table page with all substances and their normalized data using Jinja templates.
    Args:
        data: List of substance dictionaries.
        columns: List of column names to include.
        docs_dir: Path to the docs directory.
    """
    # Setup Jinja environment
    template_dir = Path(__file__).parent / "templates"
    env = Environment(loader=FileSystemLoader(template_dir))

    # Define table structure
    table_headers = [
        "Name",
        "Other Names",
        "Classifications",
        "DEA Schedule",
        "Reason",
        "Warnings",
        "References",
        "Added to Database",
        "Source Updated",
        "Details",
    ]

    # Convert data to Substance objects for consistent processing
    substances = [Substance(data=entry) for entry in data]

    # Process table data
    table_data = []
    for substance in substances:
        # Process other names
        other_names_list = substance.other_names
        other_names = ", ".join(other_names_list) if other_names_list else "N/A"

        # Process classifications
        classifications_list = substance.classifications
        classifications = ", ".join(classifications_list) if classifications_list else "N/A"

        # Get DEA schedule
        dea_schedule = substance.dea_schedule or "N/A"

        # Process primary reason
        primary_reason = substance.reason or "N/A"

        # Process warnings
        warnings_list = substance.warnings
        warnings = ", ".join(warnings_list) if warnings_list else "N/A"

        # Process references
        references_list = substance.references
        references = (
            str(len(references_list)) + " refs"
            if references_list
            else "No refs"
        )

        # Process added date
        added_date = "Unknown"
        if substance.added_date:
            try:
                from datetime import datetime
                added_date = datetime.fromisoformat(
                    substance.added_date.replace("Z", "+00:00")
                ).strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                added_date = "Unknown"

        # Process source updated date
        source_updated = "Unknown"
        source_date = substance.source_updated_date
        if source_date:
            try:
                from datetime import datetime
                if isinstance(source_date, str):
                    # Try to parse and format the date
                    parsed_date = datetime.fromisoformat(source_date.replace("Z", "+00:00"))
                    source_updated = parsed_date.strftime("%Y-%m-%d")
            except (ValueError, TypeError):
                source_updated = "Unknown"

        # Escape pipe characters in content to prevent table breakage
        name = substance.name.replace("|", "\\|")
        other_names = other_names.replace("|", "\\|")
        classifications = classifications.replace("|", "\\|")
        primary_reason = primary_reason.replace("|", "\\|")
        warnings = warnings.replace("|", "\\|")

        # Truncate long content to keep table readable
        if len(other_names) > 50:
            other_names = other_names[:47] + "..."
        if len(classifications) > 30:
            classifications = classifications[:27] + "..."
        if len(primary_reason) > 40:
            primary_reason = primary_reason[:37] + "..."
        if len(warnings) > 30:
            warnings = warnings[:27] + "..."

        # Create the correct relative path from table.md to individual substance pages
        # Since table.md is at /substances/table.md, we need to go up one level to reach /substances/
        substance_link = f"../{substance.slug}"

        # Add row data
        table_data.append(
            [
                f'<a href="{substance_link}">{name}</a>',
                other_names,
                classifications,
                dea_schedule,
                primary_reason,
                warnings,
                references,
                added_date,
                source_updated,
                f'<a href="{substance_link}">View details</a>',
            ]
        )

    # Render table features note
    features_template = env.get_template("table-features-note.md")
    table_features_note = features_template.render(has_filters=True)

    # Render main table template
    table_template = env.get_template("substances-table.md")
    table_content = table_template.render(
        table_headers=table_headers,
        table_data=table_data,
        table_features_note=table_features_note,
    )

    # Write the rendered content
    table_path = docs_dir / "substances" / "table.md"
    with open(table_path, "w", encoding="utf-8") as f:
        f.write(table_content)


def generate_substances_index(
    data: List[Dict[str, Any]], columns: List[str], docs_dir: Path
) -> None:
    """
    Generates the substances index with metrics summary.
    Args:
        data: List of substance dictionaries.
        columns: List of column names to include.
        docs_dir: Path to the docs directory.
    """
    # Convert data to Substance objects
    substances = [Substance(data=entry) for entry in data]
    
    # Calculate metrics
    total_substances = len(substances)

    # DEA Schedule breakdown
    dea_schedules = {
        "Schedule I": 0,
        "Schedule II": 0,
        "Schedule III": 0,
        "Schedule IV": 0,
        "Schedule V": 0,
    }
    classifications_count = {}

    for substance in substances:
        # Count DEA schedules
        dea_schedule = substance.dea_schedule
        if dea_schedule:
            dea_schedules[dea_schedule] += 1

        # Count classifications
        classifications = substance.classifications
        if classifications:
            for classification in classifications:
                classifications_count[classification] = (
                    classifications_count.get(classification, 0) + 1
                )

    # Generate the table page first
    generate_substances_table(data, columns, docs_dir)

    # Generate the index with metrics
    substances_index = docs_dir / "substances" / "index.md"

    with open(substances_index, "w", encoding="utf-8") as f:
        f.write("# Prohibited Substances\n\n")

        # Metrics summary
        f.write("## Summary Statistics\n\n")
        f.write(f"**Total prohibited substances:** {total_substances}\n\n")

        # DEA Schedule breakdown
        f.write("### DEA Controlled Substances Breakdown\n\n")
        total_dea = sum(dea_schedules.values())
        f.write(f"**Total DEA controlled substances:** {total_dea}\n\n")

        if total_dea > 0:
            for schedule, count in dea_schedules.items():
                if count > 0:
                    percentage = (count / total_dea) * 100
                    f.write(
                        f"- **{schedule}:** {count} substances ({percentage:.1f}%)\n"
                    )
            f.write("\n")

        # Classifications breakdown (top 10)
        if classifications_count:
            f.write("### Top Classifications\n\n")
            sorted_classifications = sorted(
                classifications_count.items(), key=lambda x: x[1], reverse=True
            )[:10]

            for classification, count in sorted_classifications:
                percentage = (count / total_substances) * 100
                f.write(
                    f"- **{classification}:** {count} substances ({percentage:.1f}%)\n"
                )
            f.write("\n")

        # Navigation links
        f.write("## Browse Substances\n\n")
        f.write("- [📊 View Complete Table](table.md) - Sortable and filterable table of all substances\n")
        f.write("- [🔍 Search](table.md) - Use the search functionality in the table\n\n")

        # A-Z listing (first few letters as an example)
        f.write("## Browse by Name\n\n")
        
        # Group substances by first letter
        letter_groups = {}
        for substance in sorted(substances, key=lambda x: x.name.lower()):
            first_letter = substance.name[0].upper() if substance.name else '#'
            if first_letter not in letter_groups:
                letter_groups[first_letter] = []
            letter_groups[first_letter].append(substance)

        # Create alphabetical navigation
        f.write("**Quick navigation:**\n\n")
        letters = sorted(letter_groups.keys())
        letter_links = []
        for letter in letters:
            if letter.isalpha():
                letter_links.append(f"[{letter}](#{letter.lower()})")
        
        f.write(" | ".join(letter_links) + "\n\n")

        # List substances by letter (limit to first 5 per letter for brevity)
        for letter in letters:
            if letter.isalpha():
                f.write(f"### {letter} {{#{letter.lower()}}}\n\n")
                
                displayed_count = 0
                for substance in letter_groups[letter]:
                    if displayed_count < 5:  # Limit display
                        f.write(f"- [{substance.name}]({substance.slug}.md)\n")
                        displayed_count += 1
                    
                total_in_group = len(letter_groups[letter])
                if total_in_group > 5:
                    f.write(f"- ... and {total_in_group - 5} more substances starting with '{letter}'\n")
                
                f.write("\n")

        f.write("---\n\n")
        f.write("*This database contains information about substances prohibited for use in dietary supplements by the Department of Defense.*\n")


def generate_changelog(
    data: List[Dict[str, Any]], columns: List[str], docs_dir: Path
) -> None:
    """
    Generates a changelog Markdown file that includes the main CHANGELOG.md content.
    Args:
        data: List of substance dictionaries (not used).
        columns: List of column names (not used).
        docs_dir: Path to the docs directory.
    """
    changelog_path = docs_dir / "changelog.md"

    with open(changelog_path, "w", encoding="utf-8") as f:
        # Add frontmatter to exclude from search
        f.write("---\n")
        f.write("search:\n")
        f.write("  exclude: true\n")
        f.write("---\n\n")
        f.write('--8<-- "CHANGELOG.md"\n')
