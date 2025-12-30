
import requests
from bs4 import BeautifulSoup
import json
import pandas as pd
from pathlib import Path
import sqlite3
from datetime import datetime

def fetch_drupal_settings(url):
    response = requests.get(url)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    script_tag = soup.find('script', {
        'type': 'application/json',
        'data-drupal-selector': 'drupal-settings-json'
    })
    if not script_tag:
        raise ValueError("Drupal settings script tag not found")
    settings = json.loads(script_tag.string)
    return settings

def get_nested(data, path, default=None):
    keys = path.split('.')
    value = data
    try:
        for key in keys:
            value = value[key]
        return value
    except (KeyError, TypeError):
        return default

def main():

    url = "https://www.opss.org/dod-prohibited-dietary-supplement-ingredients"
    settings = fetch_drupal_settings(url)
    prohibited_list = get_nested(settings, "dodProhibited")
    df = pd.DataFrame(prohibited_list)

    # Setup SQLite DB
    db_path = Path("prohibited.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # Create table if it doesn't exist
    columns = list(df.columns)
    col_defs = ", ".join([f'"{col}" TEXT' for col in columns])
    c.execute(f'''CREATE TABLE IF NOT EXISTS substances (
        id INTEGER PRIMARY KEY AUTOINCREMENT
    )''')

    # Add missing columns (including added/updated) if not present
    c.execute('PRAGMA table_info(substances)')
    existing_cols = set([row[1] for row in c.fetchall()])
    for col in columns + ["added", "updated"]:
        if col not in existing_cols:
            c.execute(f'ALTER TABLE substances ADD COLUMN "{col}" TEXT')

    # Create unique index on all columns to ensure idempotency
    unique_cols = ", ".join([f'"{col}"' for col in columns])
    try:
        c.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_substance ON substances ({unique_cols})')
    except Exception:
        pass

    from datetime import timezone
    import hashlib
    now = datetime.now(timezone.utc).isoformat()
    for _, row in df.iterrows():
        values = []
        for col in columns:
            val = row.get(col, None)
            # Convert lists/dicts to JSON strings for SQLite
            if isinstance(val, (list, dict)):
                val = json.dumps(val, ensure_ascii=False)
            values.append(val)
        placeholders = ", ".join(["?"] * len(columns))
        sql = f'''
            INSERT INTO substances ({unique_cols}, added, updated)
            VALUES ({placeholders}, ?, ?)
            ON CONFLICT ({unique_cols}) DO UPDATE SET updated=excluded.updated
        '''
        c.execute(sql, (*values, now, now))
    conn.commit()


    import os
    # Only generate docs if on gh-pages branch or DOD_PROHIBITED_GENERATE_DOCS=1
    branch = os.environ.get("GITHUB_REF", "") or os.environ.get("BRANCH", "")
    force = os.environ.get("DOD_PROHIBITED_GENERATE_DOCS", "0") == "1"
    is_gh_pages = branch.endswith("/gh-pages") or branch == "gh-pages"
    if is_gh_pages or force:
        # Export all data as JSON for MkDocs
        docs_dir = Path("docs")
        docs_dir.mkdir(exist_ok=True)
        substances_dir = docs_dir / "substances"
        substances_dir.mkdir(exist_ok=True)
        json_path = docs_dir / "data.json"
        c.execute(f'SELECT {unique_cols}, added, updated FROM substances')
        rows = c.fetchall()
        all_cols = columns + ["added", "updated"]
        data = [dict(zip(all_cols, row)) for row in rows]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        # Generate a Markdown file for each substance
        def slugify(value):
            import re
            value = str(value).strip().lower()
            value = re.sub(r'[^a-z0-9]+', '-', value)
            return value.strip('-')

        # Use a short, unique field for the filename (prefer 'ingredient', 'name', or fallback to hash)
        def get_short_slug(entry):
            for key in ['ingredient', 'name', 'substance', 'title']:
                if key in entry and isinstance(entry[key], str) and entry[key].strip():
                    return slugify(entry[key])
            # fallback: hash of all values
            hashval = hashlib.sha1(json.dumps(entry, sort_keys=True).encode('utf-8')).hexdigest()[:10]
            return f"substance-{hashval}"

        links = []
        for entry in data:
            name = entry.get('ingredient') or entry.get('name') or entry.get('substance') or entry.get('title') or "unknown"
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

        # Create substances/index.md with a table of links
        substances_index = docs_dir / "substances" / "index.md"
        with open(substances_index, "w", encoding="utf-8") as f:
            f.write("# Prohibited Substances\n\n")
            f.write("| Name | Details |\n|---|---|\n")
            for name, slug in links:
                f.write(f"| {name} | [View details]({slug}) |\n")

        # Optionally, update index.md to point to the JSON data and substances
        md_path = docs_dir / "index.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("# DoD Prohibited Dietary Supplement Ingredients\n\n")
            f.write("This page is automatically updated daily.\n\n")
            f.write("- [Browse all substances](substances/index.md)\n")
            f.write("- [Download as JSON](data.json)\n")
    else:
        print("Skipping docs/ generation: not on gh-pages branch and not forced.")

    conn.close()

if __name__ == "__main__":
    main()
