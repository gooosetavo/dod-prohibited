# Tests

This directory contains the test suite for the DoD prohibited substances project.

## Structure

- `test_retrieval.py` - Tests for data retrieval functions
- `test_parsing.py` - Tests for data parsing functions  
- `test_generate_docs.py` - Tests for documentation generation and changelog functions
- `test_workflow_helper.py` - Tests for workflow helper utilities
- `debug_changes.py` - Debug script to analyze change detection
- `test_workflow.py` - Integration test for workflow helper

## Running Tests

### With pytest (recommended)

```bash
# Install test dependencies
uv pip install -e .[test]

# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_generate_docs.py

# Run specific test
pytest tests/test_generate_docs.py::TestGenerateDocs::test_get_substance_last_modified_valid
```

### With basic test runner

```bash
# Run from project root
python run_tests.py
```

### Debug change detection

```bash
# Analyze why changes are being detected
python tests/debug_changes.py
```

## Test Coverage

The tests cover:

- ✅ Data retrieval from Drupal sites
- ✅ Data parsing and validation
- ✅ Timestamp extraction and comparison
- ✅ Change detection logic
- ✅ Changelog generation with self-reported vs computed dates
- ✅ Git operations and workflow helpers
- ✅ File operations and utilities
- ✅ Error handling and edge cases

## Adding Tests

When adding new functionality:

1. Add corresponding test functions to the appropriate test file
2. Follow the naming convention: `test_function_name_scenario`
3. Use descriptive docstrings explaining what is being tested
4. Include both positive and negative test cases
5. Mock external dependencies (network calls, file system operations)

## Test Data

Tests use temporary directories and mock data to avoid affecting the actual repository or external services.