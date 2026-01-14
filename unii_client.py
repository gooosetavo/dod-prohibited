import requests
import zipfile
import io
import pandas as pd
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler()],
)

logger = logging.getLogger(__name__)


@dataclass
class UniiDataConfig:
    """Configuration for UNII data client."""
    
    url: str = "https://precision.fda.gov/uniisearch/archive/latest/UNII_Data.zip"
    cache_dir: Optional[str] = None
    chunk_size: int = 8192
    timeout: int = 300  # 5 minutes
    settings: Optional[Any] = None  # Settings object for authentication and user-agent


class UniiDataClient:
    """
    Simple client to download and load data from FDA UNII Data ZIP archive.
    
    The UNII (Unique Ingredient Identifier) database contains substance information
    from the FDA's Global Substance Registration System (GSRS).
    """
    
    def __init__(self, config: Optional[UniiDataConfig] = None):
        self.config = config or UniiDataConfig()
        self._cache_dir = None
        self._session = None
        
    @property
    def session(self) -> requests.Session:
        """Get or create configured requests session."""
        if self._session is None:
            self._session = requests.Session()
            
            # Configure user-agent if specified in settings
            if self.config.settings and hasattr(self.config.settings, 'user_agent') and self.config.settings.user_agent:
                self._session.headers.update({'User-Agent': self.config.settings.user_agent})
                logger.debug(f"Using custom User-Agent: {self.config.settings.user_agent}")
            
            # Configure authentication if specified in settings
            if self.config.settings:
                # Bearer token authentication
                if hasattr(self.config.settings, 'auth_token') and self.config.settings.auth_token:
                    self._session.headers.update({'Authorization': f'Bearer {self.config.settings.auth_token}'})
                    logger.debug("Using Bearer token authentication")
                # Basic authentication
                elif (hasattr(self.config.settings, 'auth_username') and self.config.settings.auth_username and 
                      hasattr(self.config.settings, 'auth_password') and self.config.settings.auth_password):
                    from requests.auth import HTTPBasicAuth
                    self._session.auth = HTTPBasicAuth(self.config.settings.auth_username, self.config.settings.auth_password)
                    logger.debug(f"Using Basic authentication for user: {self.config.settings.auth_username}")
        
        return self._session
    
    @property
    def cache_dir(self) -> Path:
        """Get or create cache directory."""
        if self._cache_dir is None:
            if self.config.cache_dir:
                self._cache_dir = Path(self.config.cache_dir)
            else:
                self._cache_dir = Path.cwd() / ".cache" / "unii_data"
            self._cache_dir.mkdir(parents=True, exist_ok=True)
        return self._cache_dir
    
    @property
    def archive_dir(self) -> Path:
        """Get or create archive directory for old files."""
        archive_path = self.cache_dir / "archive"
        archive_path.mkdir(parents=True, exist_ok=True)
        return archive_path
    
    def get_remote_file_size(self) -> Optional[int]:
        """
        Get the size of the remote ZIP file without downloading it.
        
        Returns:
            File size in bytes, or None if unable to determine
        """
        try:
            # First try HEAD request
            response = self.session.head(self.config.url, timeout=30, allow_redirects=True)
            response.raise_for_status()
            
            content_length = response.headers.get('content-length')
            logger.debug(f"HEAD request headers: {dict(response.headers)}")
            
            if content_length and content_length.strip():
                size = int(content_length)
                if size > 0:
                    logger.debug(f"Remote file size from HEAD: {size} bytes")
                    return size
                else:
                    logger.warning("Remote server returned content-length of 0")
            else:
                logger.warning("Remote server did not provide content-length header in HEAD response")
            
            # If HEAD doesn't work, try a partial GET request to get content-length
            logger.debug("Trying partial GET request to determine file size")
            response = self.session.get(
                self.config.url, 
                headers={'Range': 'bytes=0-0'}, 
                timeout=30, 
                allow_redirects=True
            )
            
            # Check if server supports range requests
            if response.status_code == 206:  # Partial content
                content_range = response.headers.get('content-range')
                if content_range:
                    # Format: "bytes 0-0/total_size"
                    total_size = content_range.split('/')[-1]
                    if total_size.isdigit():
                        size = int(total_size)
                        logger.debug(f"Remote file size from range request: {size} bytes")
                        return size
            
            # Last resort: try a regular GET with stream=True and get content-length
            logger.debug("Trying streamed GET request to determine file size")
            response = self.session.get(self.config.url, stream=True, timeout=30, allow_redirects=True)
            response.raise_for_status()
            
            content_length = response.headers.get('content-length')
            if content_length and content_length.strip():
                size = int(content_length)
                if size > 0:
                    logger.debug(f"Remote file size from GET: {size} bytes")
                    # Close the stream since we only wanted the headers
                    response.close()
                    return size
                    
            # Close the stream
            response.close()
            logger.warning("Could not determine remote file size using any method")
            return None
                
        except requests.RequestException as e:
            # Provide detailed error information for HTTP issues
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "url": self.config.url,
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
            logger.warning(f"Could not get remote file size: {error_details['error_message']}")
            logger.debug(f"HTTP Error Details: {error_details}")
            
            # For 403 errors, provide specific guidance
            if hasattr(e, 'response') and e.response is not None and e.response.status_code == 403:
                logger.warning("403 Forbidden: The server is denying access. This could be due to:")
                logger.warning("  - Rate limiting or anti-bot protection")
                logger.warning("  - User-Agent restrictions")
                logger.warning("  - Geographic restrictions")
                logger.warning("  - API access permissions changed")
                
            return None
        except (ValueError, IndexError) as e:
            logger.warning(f"Error parsing remote file size: {e}")
            logger.debug(f"URL attempted: {self.config.url}")
            return None
    
    def archive_old_file(self, file_path: Path) -> Path:
        """
        Move an old file to the archive directory with timestamp.
        
        Args:
            file_path: Path to the file to archive
            
        Returns:
            Path where the file was archived
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"{file_path.stem}_{timestamp}{file_path.suffix}"
        archive_path = self.archive_dir / archive_name
        
        # Move the file to archive
        file_path.rename(archive_path)
        logger.info(f"Archived old file to: {archive_path}")
        
        return archive_path
    
    def get_cached_zip_path(self) -> Optional[Path]:
        """
        Get the path to the cached ZIP file if it exists.
        
        Returns:
            Path to cached ZIP file, or None if it doesn't exist
        """
        zip_path = self.cache_dir / "UNII_Data.zip"
        return zip_path if zip_path.exists() else None
    
    def download_zip(self, force_refresh: bool = False) -> Path:
        """
        Download the UNII data ZIP file.
        
        Args:
            force_refresh: If True, re-download even if cached file exists
            
        Returns:
            Path to the downloaded ZIP file
        """
        zip_path = self.cache_dir / "UNII_Data.zip"
        
        # Check if file exists and if we should check for updates
        if zip_path.exists() and not force_refresh:
            # Get remote file size to compare
            logger.debug(f"Checking if cached file needs update: {zip_path}")
            remote_size = self.get_remote_file_size()
            local_size = zip_path.stat().st_size
            
            logger.debug(f"Remote size: {remote_size}, Local size: {local_size}")
            
            if remote_size is not None:
                if remote_size == local_size:
                    logger.info(f"Using cached ZIP file (size unchanged): {zip_path}")
                    return zip_path
                else:
                    logger.info(f"Remote file size changed: {remote_size} bytes vs local {local_size} bytes")
                    logger.info("Archiving old file and downloading new version")
                    self.archive_old_file(zip_path)
                    # Continue to download new version below
            else:
                # If we can't get remote size, use cached file unless force_refresh
                logger.info(f"Using cached ZIP file (unable to check remote size): {zip_path}")
                return zip_path
        
        # Download the file (either first time, force_refresh, or size changed)        
        logger.info(f"Downloading UNII data from {self.config.url}")
        
        try:
            response = self.session.get(
                self.config.url, 
                stream=True, 
                timeout=self.config.timeout
            )
            response.raise_for_status()
            
            # Get file size for progress tracking
            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0
            last_progress_log = 0
            
            with open(zip_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=self.config.chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        if total_size > 0:
                            percent = (downloaded_size / total_size) * 100
                            # Log progress every 10% to avoid spam
                            if percent - last_progress_log >= 10:
                                logger.info(f"Download progress: {percent:.1f}%")
                                last_progress_log = percent
            
            logger.info(f"Successfully downloaded {downloaded_size} bytes to {zip_path}")
            return zip_path
            
        except requests.RequestException as e:
            # Provide detailed error information for download failures
            error_details = {
                "error_type": type(e).__name__,
                "error_message": str(e),
                "url": self.config.url,
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
            logger.error(f"Failed to download UNII data: {error_details['error_message']}")
            logger.debug(f"HTTP Error Details: {error_details}")
            
            # Provide specific guidance for common errors
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code == 403:
                    logger.error("403 Forbidden: Download access denied. The UNII data URL may have changed or requires authentication.")
                elif e.response.status_code == 404:
                    logger.error("404 Not Found: UNII data file not found. The download URL may have changed.")
                elif e.response.status_code == 429:
                    logger.error("429 Too Many Requests: Download rate limited. Wait before retrying.")
                elif e.response.status_code >= 500:
                    logger.error("Server Error: UNII data server is experiencing issues. Try again later.")
                    
            raise
        except Exception as e:
            logger.error(f"Unexpected error during download: {e}")
            raise
    
    def list_zip_contents(self, zip_path: Optional[Path] = None) -> List[str]:
        """
        List the contents of the UNII data ZIP file.
        
        Args:
            zip_path: Path to ZIP file. If None, uses cached file or downloads if needed.
            
        Returns:
            List of file names in the ZIP archive
        """
        if zip_path is None:
            # First try to use cached file
            zip_path = self.get_cached_zip_path()
            # If no cached file exists, then download
            if zip_path is None:
                zip_path = self.download_zip()
            
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                return zip_file.namelist()
        except zipfile.BadZipFile as e:
            logger.error(f"Invalid ZIP file: {e}")
            raise
    
    def extract_file(self, filename: str, zip_path: Optional[Path] = None) -> bytes:
        """
        Extract a specific file from the ZIP archive.
        
        Args:
            filename: Name of file to extract
            zip_path: Path to ZIP file. If None, uses cached file or downloads if needed.
            
        Returns:
            File contents as bytes
        """
        if zip_path is None:
            # First try to use cached file
            zip_path = self.get_cached_zip_path()
            # If no cached file exists, then download
            if zip_path is None:
                zip_path = self.download_zip()
            
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                return zip_file.read(filename)
        except KeyError:
            logger.error(f"File '{filename}' not found in ZIP archive")
            raise
        except zipfile.BadZipFile as e:
            logger.error(f"Invalid ZIP file: {e}")
            raise
    
    def load_csv_data(self, filename: str, zip_path: Optional[Path] = None, **pandas_kwargs) -> pd.DataFrame:
        """
        Load CSV data from the ZIP archive into a pandas DataFrame.
        
        Args:
            filename: Name of CSV file to load
            zip_path: Path to ZIP file. If None, uses cached file or downloads if needed.
            **pandas_kwargs: Additional arguments passed to pd.read_csv()
                           Common options:
                           - sep="|" or delimiter="|" for different delimiters
                           - encoding="latin-1" for different character encodings
                           - header=None for files without headers
                           - names=["col1", "col2"] for custom column names
                           - skiprows=1 to skip rows
                           - nrows=100 to limit rows loaded
            
        Returns:
            DataFrame containing the CSV data
            
        Examples:
            # Load with different delimiter
            df = client.load_csv_data("file.csv", sep="|")
            
            # Load with specific encoding
            df = client.load_csv_data("file.csv", encoding="latin-1")
            
            # Load with custom options
            df = client.load_csv_data("file.csv", sep="\\t", header=0, nrows=1000)
        """
        file_content = self.extract_file(filename, zip_path)
        
        # Try to decode with UTF-8 first, fallback to other encodings
        text_content = None
        encoding_used = None
        
        for encoding in ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']:
            try:
                text_content = file_content.decode(encoding)
                encoding_used = encoding
                break
            except UnicodeDecodeError:
                continue
        
        if text_content is None:
            # Last resort: decode with errors='replace'
            text_content = file_content.decode('utf-8', errors='replace')
            encoding_used = 'utf-8 (with errors replaced)'
            logger.warning(f"Had to decode {filename} with error replacement")
        
        logger.debug(f"Decoded {filename} using {encoding_used} encoding")
        
        # Use StringIO to read CSV from decoded text
        csv_data = io.StringIO(text_content)
        
        try:
            df = pd.read_csv(csv_data, **pandas_kwargs)
            logger.info(f"Loaded {len(df)} rows from {filename}")
            return df
        except Exception as e:
            # Provide helpful error message with common solutions
            error_msg = f"Failed to parse CSV file '{filename}': {e}"
            if "delimiter" in str(e).lower() or "separator" in str(e).lower():
                error_msg += "\\n  Try specifying a different delimiter: sep='|' or sep='\\t'"
            if "encoding" in str(e).lower():
                error_msg += f"\\n  Try a different encoding (currently using {encoding_used})"
            logger.error(error_msg)
            raise
    
    def extract_all(self, zip_path: Optional[Path] = None, extract_path: Optional[Path] = None) -> Path:
        """
        Extract all files from the ZIP archive.
        
        Args:
            zip_path: Path to ZIP file. If None, uses cached file or downloads if needed.
            extract_path: Where to extract files. If None, uses cache directory.
            
        Returns:
            Path to extraction directory
        """
        if zip_path is None:
            # First try to use cached file
            zip_path = self.get_cached_zip_path()
            # If no cached file exists, then download
            if zip_path is None:
                zip_path = self.download_zip()
            
        if extract_path is None:
            extract_path = self.cache_dir / "extracted"
            
        extract_path.mkdir(parents=True, exist_ok=True)
        
        try:
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                zip_file.extractall(extract_path)
                logger.info(f"Extracted all files to {extract_path}")
                return extract_path
        except zipfile.BadZipFile as e:
            logger.error(f"Invalid ZIP file: {e}")
            raise
    
    def list_archived_files(self) -> List[Dict[str, Any]]:
        """
        List all archived ZIP files with their metadata.
        
        Returns:
            List of dictionaries containing file info for each archived file
        """
        archived_files = []
        
        if self.archive_dir.exists():
            for archive_file in self.archive_dir.glob("UNII_Data_*.zip"):
                file_info = {
                    "filename": archive_file.name,
                    "path": archive_file,
                    "size_bytes": archive_file.stat().st_size,
                    "size_mb": round(archive_file.stat().st_size / (1024 * 1024), 2),
                    "modified_time": datetime.fromtimestamp(archive_file.stat().st_mtime),
                    "timestamp_from_name": archive_file.stem.split("_", 2)[-1] if "_" in archive_file.stem else None
                }
                archived_files.append(file_info)
        
        # Sort by modification time, newest first
        archived_files.sort(key=lambda x: x["modified_time"], reverse=True)
        return archived_files
    
    def get_data_info(self) -> Dict[str, Any]:
        """
        Get basic information about the UNII data archive.
        
        Returns:
            Dictionary with information about the ZIP contents and archives
        """
        # First try to use cached file, otherwise download
        zip_path = self.get_cached_zip_path()
        if zip_path is None:
            zip_path = self.download_zip()
            
        file_list = self.list_zip_contents(zip_path)
        archived_files = self.list_archived_files()
        
        info = {
            "zip_size_bytes": zip_path.stat().st_size,
            "zip_size_mb": round(zip_path.stat().st_size / (1024 * 1024), 2),
            "zip_modified": datetime.fromtimestamp(zip_path.stat().st_mtime),
            "file_count": len(file_list),
            "files": file_list,
            "csv_files": [f for f in file_list if f.endswith('.csv')],
            "txt_files": [f for f in file_list if f.endswith('.txt')],
            "other_files": [f for f in file_list if not (f.endswith('.csv') or f.endswith('.txt'))],
            "archive_count": len(archived_files),
            "archived_files": archived_files,
            "cache_dir": str(self.cache_dir),
            "archive_dir": str(self.archive_dir)
        }
        
        return info


# Convenience functions for quick access
def download_unii_data(cache_dir: Optional[str] = None, force_refresh: bool = False, settings: Optional[Any] = None) -> Path:
    """Convenience function to download UNII data."""
    config = UniiDataConfig(cache_dir=cache_dir, settings=settings)
    client = UniiDataClient(config)
    return client.download_zip(force_refresh=force_refresh)


def load_unii_csv(filename: str, cache_dir: Optional[str] = None, **pandas_kwargs) -> pd.DataFrame:
    """
    Convenience function to load a CSV from UNII data.
    
    Args:
        filename: Name of CSV file to load from the UNII archive
        cache_dir: Optional custom cache directory
        **pandas_kwargs: Additional arguments for pandas.read_csv()
                        - sep="|" for pipe-delimited files
                        - delimiter="\\t" for tab-delimited files
                        - encoding="latin-1" for different character encodings
                        
    Examples:
        # Load regular CSV
        df = load_unii_csv("substances.csv")
        
        # Load pipe-delimited file
        df = load_unii_csv("data.csv", sep="|")
        
        # Load with custom encoding and row limit
        df = load_unii_csv("data.csv", encoding="latin-1", nrows=1000)
    """
    config = UniiDataConfig(cache_dir=cache_dir)
    client = UniiDataClient(config)
    return client.load_csv_data(filename, **pandas_kwargs)


def get_unii_info(cache_dir: Optional[str] = None, settings: Optional[Any] = None) -> Dict[str, Any]:
    """Convenience function to get UNII data info."""
    config = UniiDataConfig(cache_dir=cache_dir, settings=settings)
    client = UniiDataClient(config)
    return client.get_data_info()


if __name__ == "__main__":
    # Example usage
    client = UniiDataClient()
    
    # Get info about the archive
    info = client.get_data_info()
    print("UNII Data Archive Info:")
    print(f"  Size: {info['zip_size_mb']} MB")
    print(f"  Files: {info['file_count']}")
    print(f"  CSV files: {len(info['csv_files'])}")
    
    if info['csv_files']:
        print("\nAvailable CSV files:")
        for csv_file in info['csv_files']:
            print(f"  - {csv_file}")
        
        # Load the first CSV file as an example
        first_csv = info['csv_files'][0]
        print(f"\nLoading sample data from {first_csv}...")
        try:
            df = client.load_csv_data(first_csv)
            print(f"  Loaded {len(df)} rows, {len(df.columns)} columns")
            print(f"  Columns: {list(df.columns)}")
            if len(df) > 0:
                print("  First few rows:")
                print(df.head())
        except Exception as e:
            print(f"  Error loading CSV: {e}")