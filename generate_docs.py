
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
                for col in columns:
                    f.write(f"**{col.capitalize()}**: {entry.get(col, '')}\n\n")
                f.write(f"**Added:** {entry.get('added', '')}\n\n")
                f.write(f"**Updated:** {entry.get('updated', '')}\n\n")

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
