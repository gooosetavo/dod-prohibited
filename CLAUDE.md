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

# Run parsing
uv run python parsing.py

# Start Jupyter lab for data exploration
uv run jupyter lab
```

## Project Overview

This is a **DOD Prohibited Substances Database** project that:
- Parses and processes data about substances prohibited for use in dietary supplements by the Department of Defense
- Generates comprehensive documentation including individual substance pages, searchable tables, and summary statistics
- Integrates with UNII (Unique Ingredient Identifier) data for enhanced substance information
- Provides web-friendly markdown documentation with filtering and search capabilities

## Architecture & Key Components

### Recent Refactoring (January 2026)
The project was recently refactored to use **dataclasses** and object-oriented design:

#### Core Data Models (`substance.py`)
- **`Substance`** - Main dataclass that encapsulates substance data and logic
- **`UniiInfo`** - Handles UNII (FDA) integration data 
- **Properties & Methods**:
  - Automatic parsing of complex JSON/list fields (other_names, classifications, reasons, etc.)
  - UNII data integration and URL generation
  - DEA schedule extraction logic
  - Slug generation for URLs

#### Generation System (`generation.py`)
- **`SubstancePageGenerator`** - Handles individual substance page creation
- **Functions**:
  - `generate_substance_pages()` - Creates individual markdown files
  - `generate_substances_table()` - Creates sortable/filterable table
  - `generate_substances_index()` - Creates summary index with statistics
- **UNII Integration**: Automatic enhancement with FDA UNII database information

### File Structure

```
dod-prohibited/
├── substance.py              # NEW: Core dataclass models
├── generation.py             # Refactored to use Substance dataclass
├── parsing.py                # Data parsing and normalization
├── retrieval.py              # Data source fetching
├── unii_client.py            # FDA UNII database client
├── workflow_helper.py        # Git and workflow utilities
├── generate_docs.py          # Main documentation generator
│
├── tests/                    # Test suite
│   ├── test_generate_docs.py
│   ├── test_parsing.py
│   └── ...
│
├── docs/                     # Generated documentation
│   ├── substances/           # Individual substance pages
│   ├── index.md
│   ├── table.md
│   └── ...
│
├── templates/                # Jinja2 templates
├── data_exploration.ipynb    # Jupyter notebook for analysis
└── demo.ipynb               # Demo notebook
```

### Data Flow

1. **Data Sources** → `retrieval.py` fetches from external APIs/databases
2. **Raw Data** → `parsing.py` normalizes and structures data
3. **Substance Objects** → `substance.py` creates structured dataclass instances
4. **UNII Enhancement** → `unii_client.py` adds FDA database information
5. **Documentation** → `generation.py` creates markdown files using templates
6. **Static Site** → Ready for deployment with MkDocs

### Key Features

- **UNII Integration**: Automatically links substances to FDA UNII database with external resource URLs
- **DEA Schedule Detection**: Parses reasons to extract controlled substance schedules
- **Flexible Data Parsing**: Handles mixed JSON/string/list formats from source data
- **Template-Based Generation**: Uses Jinja2 templates for consistent formatting
- **Search & Filter**: Generated tables include JavaScript-based filtering
- **Git Integration**: Tracks changes and updates with proper version control

## Development Workflow

### Making Changes
1. **Data Model Changes**: Modify `substance.py` dataclass
2. **Page Generation**: Update methods in `SubstancePageGenerator` class
3. **Templates**: Modify Jinja2 templates in `templates/` directory
4. **Tests**: Update tests to work with new `Substance` objects

### Testing
```bash
# Run all tests
uv run pytest tests/ -v

# Test specific functionality
uv run pytest tests/test_parsing.py -v          # Data parsing
uv run pytest tests/test_generate_docs.py -v   # Document generation
uv run pytest tests/test_retrieval.py -v       # Data retrieval
```

### Adding New Fields
1. Add property to `Substance` dataclass in `substance.py`
2. Update page generation logic in `SubstancePageGenerator`
3. Add tests for the new field
4. Update templates if needed

## Common Tasks

### Debugging Substance Data
```python
from substance import Substance

# Create substance from raw data
data = {"Name": "Test Substance", "Classifications": "[\"stimulant\"]"}
substance = Substance(data=data)

# Access parsed properties
print(substance.name)              # "Test Substance"
print(substance.classifications)   # ["stimulant"]
print(substance.slug)             # "test-substance"
```

### Running Generation
```bash
# Full document generation
uv run python generate_docs.py

# With UNII data enhancement
ENABLE_UNII=true uv run python generate_docs.py
```

## Important Notes

- **Use `uv`**: This project uses `uv` for dependency management, not pip
- **Dataclass-Based**: Recent refactoring moved from dict-based to structured dataclass approach
- **UNII Integration**: The `Substance` class handles UNII data automatically when available
- **Template-Driven**: All output formatting uses Jinja2 templates for consistency
- **Git Integration**: The system tracks changes and generates changelogs automatically

## Troubleshooting

### Common Issues
1. **Import Errors**: Make sure to use `uv run` for all Python commands
2. **Missing UNII Data**: UNII integration is optional and will gracefully degrade
3. **Template Errors**: Check that templates exist in `templates/` directory
4. **Parsing Errors**: The `Substance` class handles malformed data gracefully

### Debug Mode
Add logging to see detailed processing:
```python
import logging
logging.basicConfig(level=logging.DEBUG)
```