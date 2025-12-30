

from retrieval import fetch_drupal_settings
from parsing import parse_prohibited_list
import generation
import sqlite3
from pathlib import Path
import os
import json
from datetime import datetime, timezone

def main():
    url = "https://www.opss.org/dod-prohibited-dietary-supplement-ingredients"
    settings = fetch_drupal_settings(url)
    df = parse_prohibited_list(settings)

    # Setup SQLite DB
    db_path = Path("prohibited.db")
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    columns = list(df.columns)
    col_defs = ", ".join([f'"{col}" TEXT' for col in columns])
    c.execute(f'''CREATE TABLE IF NOT EXISTS substances (
        id INTEGER PRIMARY KEY AUTOINCREMENT
    )''')
    c.execute('PRAGMA table_info(substances)')
    existing_cols = set([row[1] for row in c.fetchall()])
    for col in columns + ["added", "updated"]:
        if col not in existing_cols:
            c.execute(f'ALTER TABLE substances ADD COLUMN "{col}" TEXT')
    unique_cols = ", ".join([f'"{col}"' for col in columns])
    try:
        c.execute(f'CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_substance ON substances ({unique_cols})')
    except Exception:
        pass

    now = datetime.now(timezone.utc).isoformat()
    for _, row in df.iterrows():
        values = []
        for col in columns:
            val = row.get(col, None)
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

    # Only generate docs if on gh-pages branch or DOD_PROHIBITED_GENERATE_DOCS=1
    branch = os.environ.get("GITHUB_REF", "") or os.environ.get("BRANCH", "")
    force = os.environ.get("DOD_PROHIBITED_GENERATE_DOCS", "0") == "1"
    is_gh_pages = branch.endswith("/gh-pages") or branch == "gh-pages"
    if is_gh_pages or force:
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

        # Use generation module for page and changelog creation
        generation.generate_substance_pages(data, columns, substances_dir)
        generation.generate_substances_index(data, columns, docs_dir)
        generation.generate_changelog(data, columns, docs_dir)
    else:
        print("Skipping docs/ generation: not on gh-pages branch and not forced.")

    conn.close()

if __name__ == "__main__":
    main()
