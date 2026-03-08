# Claude AI Assistant - Project Context

## Quick Start Commands

**Important**: Always use `uv` for this project instead of pip/python directly.

```bash
# Run tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_generate_docs.py -v

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

| File | Description |
| ---- | ----------- |
| `substance.py` | `Substance` and `UniiInfo` dataclasses — core data models |
| `generation.py` | `SubstancePageGenerator` class — creates markdown pages, tables, index |
| `generate_docs.py` | Main orchestration script with `Settings` dataclass (env var config) |
| `retrieval.py` | `DrupalClient` — fetches raw JSON from OPSS website |
| `parsing.py` | Normalizes raw Drupal data into structured pandas DataFrames |
| `data_loader.py` | Abstract `DataLoader` base class with `RemoteDataLoader`, `SqliteDataLoader`, `JsonFileDataLoader` |
| `http_client.py` | `HttpClient` hierarchy — base client, `StreamingHttpClient`, `DrupalClient` |
| `unii_client.py` | Downloads/caches FDA UNII ZIP, provides substance lookup |
| `changelog.py` | `ChangeType`, `SubstanceChange`, `DateChanges` dataclasses for change tracking |
| `workflow_helper.py` | GitHub Actions / git utilities for automated changelog generation |
| `ua.py` | `RandomUserAgent` — rotates user agent strings from device JSON |

### File Structure

```
dod-prohibited/
├── substance.py              # Core dataclass models
├── generation.py             # Document generation
├── generate_docs.py          # Main orchestration script
├── parsing.py                # Data normalization
├── retrieval.py              # Data fetching (Drupal)
├── data_loader.py            # Multi-source data loader
├── http_client.py            # HTTP client hierarchy
├── unii_client.py            # FDA UNII database client
├── changelog.py              # Change tracking models
├── workflow_helper.py        # Git/GitHub Actions utilities
├── ua.py                     # User agent rotation
├── prohibited.db             # SQLite database (2MB)
│
├── tests/                    # 11 test files
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
├── mkdocs.yml                # MkDocs Material theme config
├── pytest.ini                # Pytest config (markers, logging)
├── .python-version           # Python 3.14
└── requirements*.txt         # Compiled dependency files
```

### Data Flow

1. **Retrieval** → `retrieval.py` fetches Drupal settings JSON from OPSS
2. **Parsing** → `parsing.py` normalizes into pandas DataFrames
3. **Substance Objects** → `substance.py` creates `Substance` dataclass instances
4. **UNII Enhancement** → `unii_client.py` adds FDA database links
5. **Generation** → `generation.py` renders Jinja2 templates to markdown
6. **Static Site** → MkDocs builds and deploys

## Development Workflow

### Making Changes

1. **Data model**: Modify `Substance`/`UniiInfo` in `substance.py`
2. **Page generation**: Update `SubstancePageGenerator` in `generation.py`
3. **Templates**: Edit Jinja2 templates in `templates/`
4. **Tests**: Update relevant test files in `tests/`

### Testing
```bash
# Run all tests
uv run pytest tests/ -v

# Test markers: slow, integration, unit
uv run pytest tests/ -v -m unit
uv run pytest tests/test_parsing.py -v
uv run pytest tests/test_generate_docs.py -v
```

### Adding New Fields
1. Add property to `Substance` dataclass in `substance.py`
2. Update `SubstancePageGenerator` in `generation.py`
3. Add tests
4. Update templates if needed

## Common Tasks

### Debugging Substance Data
```python
from substance import Substance

data = {"Name": "Test Substance", "Classifications": "[\"stimulant\"]"}
substance = Substance(data=data)

print(substance.name)              # "Test Substance"
print(substance.classifications)   # ["stimulant"]
print(substance.slug)              # "test-substance"
```

### Running Generation
```bash
# Full document generation
uv run python generate_docs.py

# With UNII data enhancement (DOD_ prefix for env vars)
DOD_ENABLE_UNII=true uv run python generate_docs.py
```

## Important Notes

- **Use `uv`**: Do not use pip or python directly
- **Python 3.14**: Pinned in `.python-version`
- **Dataclass-based**: `Substance` wraps raw dict data with typed properties
- **UNII optional**: Gracefully degrades if UNII data unavailable
- **Config via env vars**: `Settings` dataclass uses `DOD_` prefix
- **Changelog automation**: `workflow_helper.py` + `changelog.py` support GitHub Actions CI

## Troubleshooting

1. **Import errors**: Use `uv run` for all Python commands
2. **Missing UNII data**: Set `DOD_ENABLE_UNII=true` and check `.cache/` directory
3. **Template errors**: Verify templates exist in `templates/`
4. **Parsing errors**: `Substance` handles malformed data gracefully

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```
