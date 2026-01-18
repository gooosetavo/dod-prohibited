"""Base HTTP client classes with common functionality.

This module provides a unified HTTP client architecture for all network operations
in the project, with specialized subclasses for different use cases.
"""

from abc import ABC
from typing import Optional, Dict, Any
import requests
from requests.auth import HTTPBasicAuth
from pathlib import Path
import logging


class HttpClient(ABC):
    """Base HTTP client with common functionality.

    Provides:
    - Lazy-loaded session with connection pooling
    - Configurable authentication (Bearer token or Basic auth)
    - Custom user agent support
    - Centralized error handling with helpful messages
    - Context manager support for automatic cleanup
    """

    def __init__(
        self,
        user_agent: Optional[str] = None,
        timeout: int = 30,
        auth_token: Optional[str] = None,
        auth_username: Optional[str] = None,
        auth_password: Optional[str] = None,
    ):
        """Initialize HTTP client.

        Args:
            user_agent: Custom User-Agent header value
            timeout: Default timeout in seconds for requests
            auth_token: Bearer token for Authorization header
            auth_username: Username for HTTP Basic Authentication
            auth_password: Password for HTTP Basic Authentication
        """
        self._session: Optional[requests.Session] = None
        self.user_agent = user_agent
        self.timeout = timeout
        self.auth_token = auth_token
        self.auth_username = auth_username
        self.auth_password = auth_password
        self.logger = logging.getLogger(self.__class__.__name__)

    @property
    def session(self) -> requests.Session:
        """Lazy-loaded session with connection pooling.

        Returns:
            Configured requests.Session instance
        """
        if self._session is None:
            self._session = requests.Session()
            self._configure_session(self._session)
        return self._session

    def _configure_session(self, session: requests.Session) -> None:
        """Configure session with headers and authentication.

        Args:
            session: requests.Session to configure
        """
        if self.user_agent:
            session.headers.update({"User-Agent": self.user_agent})

        if self.auth_token:
            session.headers.update({"Authorization": f"Bearer {self.auth_token}"})
        elif self.auth_username and self.auth_password:
            session.auth = HTTPBasicAuth(self.auth_username, self.auth_password)

    def get(
        self,
        url: str,
        timeout: Optional[int] = None,
        **kwargs
    ) -> requests.Response:
        """Execute GET request with error handling.

        Args:
            url: URL to fetch
            timeout: Request timeout in seconds (uses default if not specified)
            **kwargs: Additional arguments passed to requests.get()

        Returns:
            Response object

        Raises:
            requests.RequestException: On any HTTP error
        """
        timeout = timeout or self.timeout
        try:
            response = self.session.get(url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            self._handle_error(e, url)
            raise

    def head(
        self,
        url: str,
        timeout: Optional[int] = None,
        **kwargs
    ) -> requests.Response:
        """Execute HEAD request with error handling.

        Args:
            url: URL to check
            timeout: Request timeout in seconds (uses default if not specified)
            **kwargs: Additional arguments passed to requests.head()

        Returns:
            Response object

        Raises:
            requests.RequestException: On any HTTP error
        """
        timeout = timeout or self.timeout
        try:
            response = self.session.head(url, timeout=timeout, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            self._handle_error(e, url)
            raise

    def _handle_error(self, error: requests.RequestException, url: str) -> None:
        """Centralized error handling with helpful messages.

        Args:
            error: The exception that occurred
            url: The URL that was being accessed
        """
        self.logger.error(f"HTTP request failed for {url}: {error}")

        if hasattr(error, 'response') and error.response is not None:
            status = error.response.status_code

            # Provide status-specific guidance
            if status == 403:
                self.logger.error(
                    "403 Forbidden - This could be due to:\n"
                    "  - Missing or invalid authentication credentials\n"
                    "  - Rate limiting or IP blocking\n"
                    "  - Insufficient permissions"
                )
            elif status == 404:
                self.logger.error(
                    "404 Not Found - The URL may have changed or the resource no longer exists"
                )
            elif status == 429:
                self.logger.error(
                    "429 Too Many Requests - You are being rate limited. "
                    "Consider adding delays between requests."
                )
            elif 500 <= status < 600:
                self.logger.error(
                    f"{status} Server Error - The remote server is experiencing issues. "
                    "Try again later."
                )

            # Log response details for debugging
            self.logger.debug(f"Response headers: {error.response.headers}")
            try:
                self.logger.debug(f"Response body: {error.response.text[:500]}")
            except Exception:
                pass

    def close(self) -> None:
        """Close the session and free resources."""
        if self._session:
            self._session.close()
            self._session = None

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures session is closed."""
        self.close()


class StreamingHttpClient(HttpClient):
    """HTTP client with streaming download support.

    Extends HttpClient with capabilities for:
    - Streaming large file downloads with progress tracking
    - Determining remote file sizes via HEAD or Range requests
    - Chunked reading to minimize memory usage
    """

    def download_file(
        self,
        url: str,
        destination: Path,
        chunk_size: int = 8192,
        timeout: int = 300,
    ) -> None:
        """Download file with streaming and progress tracking.

        Args:
            url: URL of file to download
            destination: Path where file should be saved
            chunk_size: Size of chunks to read at a time (bytes)
            timeout: Request timeout in seconds (default: 5 minutes)

        Raises:
            requests.RequestException: On any HTTP error
        """
        self.logger.info(f"Downloading {url} to {destination}")

        try:
            response = self.session.get(
                url,
                stream=True,
                timeout=timeout,
                allow_redirects=True
            )
            response.raise_for_status()

            # Ensure destination directory exists
            destination.parent.mkdir(parents=True, exist_ok=True)

            # Stream download to file
            with open(destination, 'wb') as f:
                for chunk in response.iter_content(chunk_size=chunk_size):
                    if chunk:  # Filter out keep-alive chunks
                        f.write(chunk)

            self.logger.info(f"Download complete: {destination}")

        except requests.RequestException as e:
            self._handle_error(e, url)
            # Clean up partial download on error
            if destination.exists():
                try:
                    destination.unlink()
                except Exception as cleanup_error:
                    self.logger.warning(f"Failed to clean up partial download: {cleanup_error}")
            raise

    def get_remote_file_size(self, url: str, timeout: int = 30) -> Optional[int]:
        """Get remote file size using HEAD or Range request.

        Tries HEAD request first (most efficient), then falls back to
        Range request if HEAD doesn't provide Content-Length.

        Args:
            url: URL of file to check
            timeout: Request timeout in seconds

        Returns:
            File size in bytes, or None if size cannot be determined
        """
        try:
            # Try HEAD first - most efficient method
            response = self.session.head(url, timeout=timeout, allow_redirects=True)
            response.raise_for_status()

            if 'content-length' in response.headers:
                return int(response.headers['content-length'])

            # Fallback to Range request (HTTP 206 Partial Content)
            self.logger.debug(f"HEAD request didn't provide size, trying Range request for {url}")
            response = self.session.get(
                url,
                headers={'Range': 'bytes=0-0'},
                timeout=timeout,
                allow_redirects=True
            )

            if response.status_code == 206 and 'content-range' in response.headers:
                # Content-Range format: "bytes 0-0/12345" where 12345 is total size
                content_range = response.headers['content-range']
                total_size = content_range.split('/')[-1]
                return int(total_size)

            self.logger.warning(f"Could not determine file size for {url}")
            return None

        except requests.RequestException as e:
            self.logger.warning(f"Could not determine file size for {url}: {e}")
            return None
        except (ValueError, IndexError) as e:
            self.logger.warning(f"Failed to parse file size from response: {e}")
            return None


class DrupalClient(HttpClient):
    """HTTP client specialized for Drupal API interactions.

    Provides methods for:
    - Fetching Drupal settings from pages
    - Parsing Drupal-specific JSON structures
    - Handling Drupal CMS endpoints
    """

    def __init__(self, user_agent: Optional[str] = None):
        """Initialize Drupal client.

        Args:
            user_agent: Custom User-Agent header value (optional)
        """
        super().__init__(user_agent=user_agent, timeout=30)

    def fetch_drupal_settings(self, url: str) -> Dict[str, Any]:
        """Fetch and parse Drupal settings JSON from a page.

        Args:
            url: URL of the Drupal page to fetch

        Returns:
            Dictionary containing parsed Drupal settings

        Raises:
            ValueError: If Drupal settings script tag is not found
            requests.RequestException: On HTTP errors
        """
        from bs4 import BeautifulSoup
        import json

        self.logger.info(f"Fetching Drupal settings from {url}")

        # Fetch the page
        response = self.get(url)
        self.logger.info("Fetched page successfully")

        # Parse HTML
        soup = BeautifulSoup(response.text, "html.parser")

        # Find Drupal settings script tag
        script_tag = soup.find(
            "script",
            {"type": "application/json", "data-drupal-selector": "drupal-settings-json"},
        )

        if not script_tag:
            self.logger.error("Drupal settings script tag not found")
            raise ValueError("Drupal settings script tag not found in page")

        # Parse and return settings
        settings = json.loads(script_tag.string)
        self.logger.info("Parsed Drupal settings JSON")
        return settings
