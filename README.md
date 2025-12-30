
# DoD Prohibited Dietary Supplement Ingredients Project

This project provides an easy-to-browse, searchable, and regularly updated list of substances prohibited by the Department of Defense (DoD) for use in dietary supplements. The data is automatically retrieved, parsed, and published as a website using MkDocs.

## What does this project do?

- **Retrieves** the official DoD prohibited ingredients list from the [OPSS website](https://www.opss.org/dod-prohibited-dietary-supplement-ingredients).
- **Parses** the data into a structured format.
- **Generates** a user-friendly website with a page for each substance, a changelog, and search functionality.
- **Updates** automatically every day and on every code change.

## How does it work?
1. **Retrieval**: The script downloads the latest data from the official DoD page.
2. **Parsing**: The data is extracted and cleaned up for use.
3. **Generation**: The cleaned data is used to create web pages and a changelog.

## For non-technical users
- You do **not** need to run any code to use the website. Just visit the published site for the latest information.
- The site is updated automatically.
- If you want to contribute or run the code yourself, see below.

## For contributors and technical users
- The code is split into three main modules:
  - `retrieval.py`: Handles downloading the data from the source.
  - `parsing.py`: Extracts and cleans the data.
  - `generation.py`: Generates the website content and changelog.
- The main script (`generate_docs.py`) ties these together.
- To run locally:
  1. Install dependencies with `uv pip install -r requirements.txt --system && uv pip install -r requirements-docs.txt --system`
  2. Run `python generate_docs.py`
  3. Serve the site with `mkdocs serve`

## License
This project is open source. See [LICENSE](LICENSE).

## Contact
For questions or suggestions, open an issue or pull request on [GitHub](https://github.com/gooosetavo/dod-prohibited).
