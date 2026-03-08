# Claude AI Assistant - Project Context

## Quick Start Commands

**Important**: Always use `uv` for this project instead of pip/python directly.

```bash
# Run tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_substance.py -v

# Install dependencies
uv sync

# Run the main generation script
uv run python generate_docs.py

# Start Jupyter lab for data exploration
uv run jupyter lab
```

## Project Overview

This is a **DoD Prohibited Substances Database** project that makes DoD OPSS (Operation Supplement Safety) data accessible and searchable. It:

- Scrapes and parses substance data from the OPSS Drupal site
- Generates individual substance pages, sortable/filterable tables, and summary statistics
- Integrates with FDA UNII (Unique Ingredient Identifier) database for enhanced substance information
- Deploys as a MkDocs static site with JavaScript-based search and filtering

**Python version**: 3.14 (pinned in `.python-version`)

## Architecture & Key Components

### Core Modules

All source code lives in the `dod_prohibited/` package. Root-level files are scripts and config only.

| File | Description |
| ---- | ----------- |
| `dod_prohibited/models.py` | `Substance` and `UniiInfo` dataclasses — core data models |
| `dod_prohibited/site_builder.py` | `SubstancePageGenerator`, `generate_substance_pages`, `generate_substances_table`, `generate_substances_index`, `generate_changelog` — all page generation |
| `dod_prohibited/parser.py` | Normalizes raw Drupal data into structured pandas DataFrames |
| `dod_prohibited/loaders.py` | `RemoteDataLoader`, `JsonFileDataLoader`, and other data loaders |
| `dod_prohibited/http.py` | `HttpClient` hierarchy — base client, streaming client |
| `dod_prohibited/unii.py` | `UniiDataClient`, `UniiDataConfig` — downloads/caches FDA UNII ZIP, provides substance lookup |
| `dod_prohibited/overrides.py` | `load_overrides`, `get_unii_override` — loads `overrides.yaml` for manual substance data overrides |
| `dod_prohibited/changelog.py` | `ChangeType`, `SubstanceChange`, `DateChanges` dataclasses for change tracking |
| `dod_prohibited/user_agent.py` | `RandomUserAgent` — rotates user agent strings from device JSON |
| `generate_docs.py` | Main orchestration script with `Settings` dataclass (env var config) |
| `workflow_helper.py` | GitHub Actions / git utilities for automated changelog generation |
| `overrides.yaml` | Manual substance data overrides (e.g. UNII codes for name-mismatch substances) |

### File Structure

```
dod-prohibited/
├── generate_docs.py          # Main orchestration script + Settings dataclass
├── workflow_helper.py        # Git/GitHub Actions utilities
├── overrides.yaml            # Manual substance overrides (UNII codes, etc.)
├── prohibited.db             # SQLite database (~2MB)
│
├── dod_prohibited/           # Main package
│   ├── models.py             # Substance + UniiInfo dataclasses
│   ├── site_builder.py       # All page/table/index generation
│   ├── parser.py             # Data normalization (Drupal → DataFrames)
│   ├── loaders.py            # Multi-source data loaders
│   ├── http.py               # HTTP client hierarchy
│   ├── unii.py               # FDA UNII database client
│   ├── overrides.py          # Substance overrides loader
│   ├── changelog.py          # Change tracking models
│   └── user_agent.py         # User agent rotation
│
├── tests/                    # 11 test files
│   ├── test_substance.py
│   ├── test_overrides.py
│   ├── test_parsing.py
│   ├── test_generate_docs.py
│   └── ...
│
├── templates/                # Jinja2 templates
│   ├── substances-table.md
│   └── table-features-note.md
│
├── docs/                     # Generated documentation (880+ files)
│   ├── substances/           # Individual substance pages
│   ├── js/                   # Table filtering JavaScript
│   ├── css/                  # Custom styles
│   ├── index.md
│   ├── table.md
│   ├── changelog.md
│   └── data.json             # Machine-readable export
│
├── pyproject.toml            # Project config (uv)
├── mkdocs.yml                # MkDocs config (zensical theme)
├── pytest.ini                # Pytest config (markers, logging)
└── .python-version           # Python 3.14
```

### Data Flow

1. **Retrieval** → `loaders.py` / `http.py` fetches Drupal JSON from OPSS
2. **Parsing** → `parser.py` normalizes into pandas DataFrames
3. **Substance Objects** → `models.py` creates `Substance` dataclass instances
4. **Overrides** → `overrides.py` applies manual overrides from `overrides.yaml`
5. **UNII Enhancement** → `unii.py` adds FDA database links (matched by name or overridden UNII code)
6. **Generation** → `site_builder.py` renders Jinja2 templates to markdown
7. **Static Site** → MkDocs builds and deploys

## Development Workflow

### Making Changes

1. **Data model**: Modify `Substance`/`UniiInfo` in `dod_prohibited/models.py`
2. **Page generation**: Update `SubstancePageGenerator` in `dod_prohibited/site_builder.py`
3. **Templates**: Edit Jinja2 templates in `templates/`
4. **Tests**: Update relevant test files in `tests/`

### Testing
```bash
# Run all tests
uv run pytest tests/ -v

# Test markers: slow, integration, unit
uv run pytest tests/ -v -m unit
uv run pytest tests/test_parsing.py -v
uv run pytest tests/test_overrides.py -v
```

### Adding New Fields
1. Add property to `Substance` dataclass in `dod_prohibited/models.py`
2. Update `SubstancePageGenerator` in `dod_prohibited/site_builder.py`
3. Add tests
4. Update templates if needed

## Common Tasks

### Debugging Substance Data
```python
from dod_prohibited.models import Substance

data = {"Name": "Test Substance", "Classifications": "[\"stimulant\"]"}
substance = Substance(data=data)

print(substance.name)              # "Test Substance"
print(substance.classifications)   # ["stimulant"]
print(substance.slug)              # "test-substance"
```

### Adding a Substance UNII Override

Some substances (e.g. Kratom) have records in the FDA UNII database but don't match by name. Add them to `overrides.yaml`:

```yaml
substances:
  substance-slug:   # URL-safe slug of the substance name
    unii: XXXXXXXXXX
```

The slug is the lowercase, hyphenated version of the substance name (same as the URL path).

### Running Generation
```bash
# Full document generation
uv run python generate_docs.py

# With UNII data enhancement (DOD_ prefix for env vars)
DOD_USE_UNII_DATA=true uv run python generate_docs.py
```

## Important Notes

- **Use `uv`**: Do not use pip or python directly
- **Python 3.14**: Pinned in `.python-version`
- **Package structure**: All source code is in `dod_prohibited/` package
- **Dataclass-based**: `Substance` wraps raw dict data with typed properties (in `models.py`)
- **UNII optional**: Gracefully degrades if UNII data unavailable; controlled by `DOD_USE_UNII_DATA=true`
- **Overrides**: `overrides.yaml` at project root allows manual UNII code assignment for name-mismatch substances
- **Config via env vars**: `Settings` dataclass (in `generate_docs.py`) uses `DOD_` prefix
- **Changelog automation**: `workflow_helper.py` + `dod_prohibited/changelog.py` support GitHub Actions CI

## Troubleshooting

1. **Import errors**: Use `uv run` for all Python commands; import from `dod_prohibited.*` package
2. **Missing UNII data**: Set `DOD_USE_UNII_DATA=true` and check `.cache/` directory
3. **UNII name mismatch**: Add substance slug + UNII code to `overrides.yaml`
4. **Template errors**: Verify templates exist in `templates/`
5. **Parsing errors**: `Substance` handles malformed data gracefully

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```
