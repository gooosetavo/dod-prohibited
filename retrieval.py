import requests
from bs4 import BeautifulSoup
import json
from typing import Any, Dict
import logging

# Configure logging for GitHub Actions (stdout, INFO level by default)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)


def fetch_drupal_settings(url: str) -> Dict[str, Any]:
    """
    Fetches the Drupal settings JSON from a given URL.

    Args:
        url: The URL to fetch the settings from.

    Returns:
        The parsed settings as a dictionary.
    """
    logging.info(f"Fetching Drupal settings from {url}")
    try:
        response = requests.get(url)
        response.raise_for_status()
        logging.info("Fetched page successfully.")
    except Exception as e:
        logging.error(f"Failed to fetch URL {url}: {e}")
        raise
    soup = BeautifulSoup(response.text, "html.parser")
    script_tag = soup.find(
        "script",
        {"type": "application/json", "data-drupal-selector": "drupal-settings-json"},
    )
    if not script_tag:
        logging.error("Drupal settings script tag not found")
        raise ValueError("Drupal settings script tag not found")
    settings = json.loads(script_tag.string)
    logging.info("Parsed Drupal settings JSON.")
    return settings
