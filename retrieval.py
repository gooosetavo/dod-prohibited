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
    except requests.RequestException as e:
        # Provide detailed error information for HTTP issues
        error_details = {
            "error_type": type(e).__name__,
            "error_message": str(e),
            "url": url,
        }
        
        # Add response details if available
        if hasattr(e, 'response') and e.response is not None:
            error_details.update({
                "status_code": e.response.status_code,
                "reason": e.response.reason,
                "headers": dict(e.response.headers),
                "response_text": e.response.text[:500] if hasattr(e.response, 'text') else "N/A"
            })
            
        # Log detailed error information
        logging.error(f"Failed to fetch URL {url}: {error_details['error_message']}")
        logging.debug(f"HTTP Error Details: {error_details}")
        
        # Provide specific guidance for common HTTP errors
        if hasattr(e, 'response') and e.response is not None:
            if e.response.status_code == 403:
                logging.error("403 Forbidden: Access denied. Check if the URL requires authentication or has access restrictions.")
            elif e.response.status_code == 404:
                logging.error("404 Not Found: The requested page does not exist. Verify the URL is correct.")
            elif e.response.status_code == 429:
                logging.error("429 Too Many Requests: Rate limiting detected. Wait before retrying.")
            elif e.response.status_code >= 500:
                logging.error("Server Error: The remote server is experiencing issues. Try again later.")
                
        raise
    except Exception as e:
        logging.error(f"Unexpected error fetching URL {url}: {e}")
        logging.debug(f"Exception type: {type(e).__name__}")
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
