import sqlite3
from pathlib import Path
import json
from datetime import datetime, timezone
import hashlib
import re
import unicodedata
from collections import defaultdict
from typing import TYPE_CHECKING, List, Dict, Any
from jinja2 import Environment, FileSystemLoader

if TYPE_CHECKING:
    from pydantic_settings import BaseSettings

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


def extract_dea_schedule(reasons_data):
    """Extract DEA schedule information from reasons data."""
    if not reasons_data:
        return None
    
    if isinstance(reasons_data, str):
        try:
            import ast
            reasons_data = ast.literal_eval(reasons_data)
        except Exception:
            reasons_data = [reasons_data]
    
    for reason in reasons_data:
        if isinstance(reason, dict):
            reason_text = reason.get('reason', '').lower()
        else:
            reason_text = str(reason).lower()
        
        if 'schedule' in reason_text and 'dea' in reason_text:
            if 'schedule i' in reason_text:
                return 'Schedule I'
            elif 'schedule ii' in reason_text:
                return 'Schedule II'
            elif 'schedule iii' in reason_text:
                return 'Schedule III'
            elif 'schedule iv' in reason_text:
                return 'Schedule IV'
            elif 'schedule v' in reason_text:
                return 'Schedule V'
    
    return None


def generate_substances_table(data: List[Dict[str, Any]], columns: List[str], docs_dir: Path) -> None:
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
    table_headers = ["Name", "Other Names", "Classifications", "DEA Schedule", "Reason", "Warnings", "References", "Added", "Details"]
    table_header_alignment = [":-----", ":------------", ":---------------", ":-------------", ":-------", ":----------", ":-----------", ":------", ":--------"]
    
    # Column filters are now embedded in the table headers, no separate configuration needed
    
    # Process table data
    table_data = []
    for entry in data:
        # Extract basic info
        name = entry.get('Name') or entry.get('ingredient') or entry.get('name') or entry.get('substance') or entry.get('title') or "(no name)"
        slug = get_short_slug(entry)
        
        # Process other names
        other_names = entry.get('other_names') or entry.get('Other_names') or ''
        if isinstance(other_names, str) and other_names.startswith('['):
            try:
                import ast
                other_names_list = ast.literal_eval(other_names)
                other_names = ', '.join(other_names_list) if other_names_list else ''
            except:
                other_names = other_names.strip('[]"')
        elif isinstance(other_names, list):
            other_names = ', '.join(other_names)
        other_names = other_names or 'N/A'
        
        # Process classifications
        classifications = entry.get('classifications') or entry.get('Classifications') or ''
        if isinstance(classifications, str) and classifications.startswith('['):
            try:
                import ast
                classifications_list = ast.literal_eval(classifications)
                classifications = ', '.join(classifications_list) if classifications_list else ''
            except:
                classifications = classifications.strip('[]"')
        elif isinstance(classifications, list):
            classifications = ', '.join(classifications)
        classifications = classifications or 'N/A'
        
        # Extract DEA schedule
        reasons = entry.get('Reasons') or entry.get('reasons')
        dea_schedule = extract_dea_schedule(reasons) or 'N/A'
        
        # Process primary reason
        primary_reason = entry.get('Reason') or 'N/A'
        if not primary_reason or primary_reason == '':
            primary_reason = 'N/A'
        
        # Process warnings
        warnings = entry.get('Warnings') or entry.get('warnings') or ''
        if isinstance(warnings, str) and warnings.startswith('['):
            try:
                import ast
                warnings_list = ast.literal_eval(warnings)
                warnings = ', '.join(warnings_list) if warnings_list else ''
            except:
                warnings = warnings.strip('[]"')
        elif isinstance(warnings, list):
            warnings = ', '.join(warnings)
        warnings = warnings or 'N/A'
        
        # Process references
        references = entry.get('References') or entry.get('references') or ''
        if isinstance(references, str) and references.startswith('['):
            try:
                import ast
                references_list = ast.literal_eval(references)
                references = str(len(references_list)) + ' refs' if references_list else 'No refs'
            except:
                references = 'No refs'
        elif isinstance(references, list):
            references = str(len(references)) + ' refs' if references else 'No refs'
        else:
            references = 'No refs'
        
        # Process added date
        added_date = entry.get('added', '')
        if added_date:
            try:
                from datetime import datetime
                added_date = datetime.fromisoformat(added_date.replace('Z', '+00:00')).strftime('%Y-%m-%d')
            except:
                added_date = 'Unknown'
        else:
            added_date = 'Unknown'
        
        # Escape pipe characters in content to prevent table breakage
        name = name.replace('|', '\\|')
        other_names = other_names.replace('|', '\\|')
        classifications = classifications.replace('|', '\\|')
        primary_reason = primary_reason.replace('|', '\\|')
        warnings = warnings.replace('|', '\\|')
        
        # Truncate long content to keep table readable
        if len(other_names) > 50:
            other_names = other_names[:47] + '...'
        if len(classifications) > 30:
            classifications = classifications[:27] + '...'
        if len(primary_reason) > 40:
            primary_reason = primary_reason[:37] + '...'
        if len(warnings) > 30:
            warnings = warnings[:27] + '...'
        
        # Add row data
        table_data.append([
            name,
            other_names,
            classifications,
            dea_schedule,
            primary_reason,
            warnings,
            references,
            added_date,
            f'<a href="{slug}">View details</a>'
        ])
    
    # Render table features note
    features_template = env.get_template('table-features-note.md')
    table_features_note = features_template.render(has_filters=True)
    
    # Render main table template
    table_template = env.get_template('substances-table.md')
    table_content = table_template.render(
        table_headers=table_headers,
        table_data=table_data,
        table_features_note=table_features_note
    )
    
    # Write the rendered content
    table_path = docs_dir / "substances" / "table.md"
    with open(table_path, "w", encoding="utf-8") as f:
        f.write(table_content)


def generate_substances_index(data: List[Dict[str, Any]], columns: List[str], docs_dir: Path) -> None:
    """
    Generates the substances index with metrics summary.
    Args:
        data: List of substance dictionaries.
        columns: List of column names to include.
        docs_dir: Path to the docs directory.
    """
    # Calculate metrics
    total_substances = len(data)
    
    # DEA Schedule breakdown
    dea_schedules = {'Schedule I': 0, 'Schedule II': 0, 'Schedule III': 0, 'Schedule IV': 0, 'Schedule V': 0}
    classifications_count = {}
    
    for entry in data:
        # Count DEA schedules
        reasons = entry.get('Reasons') or entry.get('reasons')
        dea_schedule = extract_dea_schedule(reasons)
        if dea_schedule:
            dea_schedules[dea_schedule] += 1
        
        # Count classifications
        classifications = entry.get('Classifications') or entry.get('classifications')
        if classifications:
            if isinstance(classifications, str):
                try:
                    import ast
                    classifications = ast.literal_eval(classifications)
                except Exception:
                    classifications = [classifications]
            
            if isinstance(classifications, list):
                for classification in classifications:
                    classifications_count[classification] = classifications_count.get(classification, 0) + 1
            else:
                classifications_count[str(classifications)] = classifications_count.get(str(classifications), 0) + 1
    
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
                    f.write(f"- **{schedule}:** {count} substances ({percentage:.1f}%)\n")
            f.write("\n")
        
        # Top classifications
        f.write("### Most Common Classifications\n\n")
        sorted_classifications = sorted(classifications_count.items(), key=lambda x: x[1], reverse=True)
        for classification, count in sorted_classifications[:10]:  # Top 10
            if classification and classification.strip():
                percentage = (count / total_substances) * 100
                f.write(f"- **{classification}:** {count} substances ({percentage:.1f}%)\n")
        f.write("\n")
        
        # Navigation links
        f.write("## Browse Substances\n\n")
        f.write("- **[View Complete Table](table.md)** - All substances in a sortable table\n")
        f.write("- **[Search substances](#)** - Use the search bar above\n\n")
        
        # Recent additions (if available)
        recent_substances = []
        for entry in data:
            added = entry.get('added')
            if added:
                name = entry.get('Name') or entry.get('ingredient') or entry.get('name') or entry.get('substance') or entry.get('title') or "(no name)"
                slug = get_short_slug(entry)
                recent_substances.append((name, slug, added))
        
        # Sort by added date and show recent ones
        recent_substances.sort(key=lambda x: x[2], reverse=True)
        if recent_substances[:5]:  # Show last 5 added
            f.write("## Recently Added\n\n")
            for name, slug, added in recent_substances[:5]:
                try:
                    from datetime import datetime
                    added_date = datetime.fromisoformat(added.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                    f.write(f"- **[{name}]({slug}.md)** - Added {added_date}\n")
                except:
                    f.write(f"- **[{name}]({slug}.md)**\n")
            f.write("\n")

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
