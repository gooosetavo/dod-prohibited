from typing import Any, Dict, Optional
import logging
from http_client import DrupalClient

# Configure logging for GitHub Actions (stdout, INFO level by default)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)


def fetch_drupal_settings(url: str, user_agent: Optional[str] = None) -> Dict[str, Any]:
    """
    Fetches the Drupal settings JSON from a given URL.

    Args:
        url: The URL to fetch the settings from.
        user_agent: Optional custom User-Agent header.

    Returns:
        The parsed settings as a dictionary.

    Raises:
        ValueError: If Drupal settings script tag is not found.
        requests.RequestException: On HTTP errors.
    """
    with DrupalClient(user_agent=user_agent) as client:
        return client.fetch_drupal_settings(url)
