import zipfile
import io
import pandas as pd
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from datetime import datetime
from http_client import StreamingHttpClient

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


class UniiDataClient(StreamingHttpClient):
    """
    Simple client to download and load data from FDA UNII Data ZIP archive.

    The UNII (Unique Ingredient Identifier) database contains substance information
    from the FDA's Global Substance Registration System (GSRS).

    Extends StreamingHttpClient to provide streaming downloads and UNII-specific
    functionality like ZIP extraction, CSV parsing, and caching.
    """

    def __init__(self, config: Optional[UniiDataConfig] = None):
        self.config = config or UniiDataConfig()

        # Extract authentication settings
        user_agent = None
        auth_token = None
        auth_username = None
        auth_password = None

        if self.config.settings:
            user_agent = getattr(self.config.settings, 'user_agent', None)
            auth_token = getattr(self.config.settings, 'auth_token', None)
            auth_username = getattr(self.config.settings, 'auth_username', None)
            auth_password = getattr(self.config.settings, 'auth_password', None)

        # Initialize parent StreamingHttpClient with configuration
        super().__init__(
            user_agent=user_agent,
            timeout=self.config.timeout,
            auth_token=auth_token,
            auth_username=auth_username,
            auth_password=auth_password,
        )

        self._cache_dir = None
    
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

        Uses the parent class's get_remote_file_size method.

        Returns:
            File size in bytes, or None if unable to determine
        """
        return super().get_remote_file_size(self.config.url, timeout=30)
    
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

        # Download the file using parent class's streaming download method
        logger.info(f"Downloading UNII data from {self.config.url}")
        self.download_file(
            url=self.config.url,
            destination=zip_path,
            chunk_size=self.config.chunk_size,
            timeout=self.config.timeout
        )

        return zip_path
    
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
