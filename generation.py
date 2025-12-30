import sqlite3
from pathlib import Path
import json
from datetime import datetime, timezone
import hashlib
import re
import unicodedata
from collections import defaultdict

def slugify(value):
    value = str(value).strip().lower()
    value = unicodedata.normalize('NFKD', value).encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^a-z0-9]+', '-', value)
    value = value.strip('-')
    return value or None

def get_short_slug(entry):
    for key in ['Name', 'ingredient', 'name', 'substance', 'title']:
        if key in entry and isinstance(entry[key], str) and entry[key].strip():
            slug = slugify(entry[key])
            if slug:
                return slug
    hashval = hashlib.sha1(json.dumps(entry, sort_keys=True).encode('utf-8')).hexdigest()[:10]
    return f"substance-{hashval}"

# The rest of the generation logic (writing markdown, changelog, etc.) would be implemented here as functions.
from typing import List, Dict, Any

def generate_substance_pages(data: List[Dict[str, Any]], columns: List[str], substances_dir: Path) -> None:
    """
    Generates a Markdown file for each substance in the data list.
    Args:
        data: List of substance dictionaries.
        columns: List of column names to include.
        substances_dir: Path to the directory where files will be written.
    """
    links = []
    for entry in data:
        # Prefer 'Name' field for display, then fallback
        name = entry.get('Name') or entry.get('ingredient') or entry.get('name') or entry.get('substance') or entry.get('title') or "(no name)"
        slug = get_short_slug(entry)
        page_path = substances_dir / f"{slug}.md"
        links.append((name, f"{slug}.md"))
        with open(page_path, "w", encoding="utf-8") as f:
            f.write(f"# {name}\n\n")
            # Other names
            other_names = entry.get('Other_names') or entry.get('other_names')
            if other_names:
                if isinstance(other_names, str):
                    try:
                        import ast
                        other_names = ast.literal_eval(other_names)
                    except Exception:
                        other_names = [other_names]
                f.write(f"**Other names:** {', '.join(other_names)}\n\n")
            # Classifications
            classifications = entry.get('Classifications') or entry.get('classifications')
            if classifications:
                if isinstance(classifications, str):
                    try:
                        import ast
                        classifications = ast.literal_eval(classifications)
                    except Exception:
                        classifications = [classifications]
                f.write(f"**Classifications:** {', '.join(classifications)}\n\n")
            # Reasons
            reasons = entry.get('Reasons') or entry.get('reasons')
            if reasons:
                if isinstance(reasons, str):
                    try:
                        import ast
                        reasons = ast.literal_eval(reasons)
                    except Exception:
                        reasons = [reasons]
                f.write("**Reasons for prohibition:**\n")
                for reason in reasons:
                    if isinstance(reason, dict):
                        line = f"- {reason.get('reason', '')}"
                        if reason.get('link'):
                            line += f" ([source]({reason['link']}))"
                        f.write(line + "\n")
                    else:
                        f.write(f"- {reason}\n")
                f.write("\n")
            # Warnings
            warnings = entry.get('Warnings') or entry.get('warnings')
            if warnings:
                if isinstance(warnings, str):
                    try:
                        import ast
                        warnings = ast.literal_eval(warnings)
                    except Exception:
                        warnings = [warnings]
                f.write(f"**Warnings:** {', '.join(warnings)}\n\n")
            # References
            refs = entry.get('References') or entry.get('references')
            if refs:
                if isinstance(refs, str):
                    try:
                        import ast
                        refs = ast.literal_eval(refs)
                    except Exception:
                        refs = [refs]
                f.write("**References:**\n")
                for ref in refs:
                    f.write(f"- {ref}\n")
                f.write("\n")
            # More info URL
            more_info_url = entry.get('More_info_url') or entry.get('more_info_url')
            if more_info_url:
                f.write(f"**More info:** [{more_info_url}]({more_info_url})\n\n")
            # Sourceof
            sourceof = entry.get('Sourceof') or entry.get('sourceof')
            if sourceof:
                f.write(f"**Source of:** {sourceof}\n\n")
            # Reason
            reason = entry.get('Reason') or entry.get('reason')
            if reason:
                f.write(f"**Reason:** {reason}\n\n")
            # Label terms
            label_terms = entry.get('Label_terms') or entry.get('label_terms')
            if label_terms:
                f.write(f"**Label terms:** {label_terms}\n\n")
            # Linked ingredients
            linked_ingredients = entry.get('Linked_ingredients') or entry.get('linked_ingredients')
            if linked_ingredients:
                f.write(f"**Linked ingredients:** {linked_ingredients}\n\n")
            # Searchable name
            searchable_name = entry.get('Searchable_name') or entry.get('searchable_name')
            if searchable_name:
                f.write(f"**Searchable name:** {searchable_name}\n\n")
            # Guid
            guid = entry.get('Guid') or entry.get('guid')
            if guid:
                f.write(f"**GUID:** {guid}\n\n")
            # Added/Updated
            added = entry.get('added')
            if added:
                f.write(f"**Added:** {added}\n\n")
            updated = entry.get('updated')
            if updated:
                f.write(f"**Updated:** {updated}\n\n")

def generate_main_index(docs_dir: Path) -> None:
    """
    Generates the main index.md file that includes README content plus site-specific info.
    Args:
        docs_dir: Path to the docs directory.
    """
    index_path = docs_dir / "index.md"
    with open(index_path, "w", encoding="utf-8") as f:
        f.write("--8<-- \"README.md\"\n\n")
        f.write("---\n\n")
        f.write("## How to use this site\n\n")
        f.write("- Use the search bar or navigation to find a substance.\n")
        f.write("- Click on a substance to view detailed information, including:\n")
        f.write("\t- Name and other known names\n")
        f.write("\t- Classifications and legal status\n")
        f.write("\t- Reasons for prohibition (with links)\n")
        f.write("\t- Warnings and references\n")
        f.write("\t- Source and more info links\n")
        f.write("\t- When the entry was added/updated\n")
        f.write("- Use the dark/light mode toggle in the top right for your preferred viewing mode.\n\n")
        f.write("---\n\n")
        f.write("- [Browse all substances](substances/index.md)\n")
        f.write("- [Download as JSON](data.json)\n\n")


def generate_substances_index(data: List[Dict[str, Any]], columns: List[str], docs_dir: Path) -> None:
    """
    Generates the substances index Markdown file.
    Args:
        data: List of substance dictionaries.
        columns: List of column names to include.
        docs_dir: Path to the docs directory.
    """
    substances_index = docs_dir / "substances" / "index.md"
    links = []
    for entry in data:
        name = entry.get('Name') or entry.get('ingredient') or entry.get('name') or entry.get('substance') or entry.get('title') or "(no name)"
        slug = get_short_slug(entry)
        links.append((name, f"{slug}.md"))
    
    with open(substances_index, "w", encoding="utf-8") as f:
        f.write("# Prohibited Substances\n\n")
        f.write("| Name | Details |\n|---|---|\n")
        for name, slug in links:
            f.write(f"| {name} | [View details]({slug}) |\n")

def generate_changelog(data: List[Dict[str, Any]], columns: List[str], docs_dir: Path) -> None:
    """
    Generates a changelog Markdown file that includes the main CHANGELOG.md content.
    Args:
        data: List of substance dictionaries (not used).
        columns: List of column names (not used).
        docs_dir: Path to the docs directory.
    """
    changelog_path = docs_dir / "changelog.md"
    
    with open(changelog_path, "w", encoding="utf-8") as f:
        f.write("--8<-- \"CHANGELOG.md\"\n")
