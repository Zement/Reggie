"""
Download Manager Module
Handles asynchronous downloading and extraction of patch files
"""

import os
import urllib.request
import urllib.error
import zipfile
import shutil
import re
from typing import Optional, Tuple

from PyQt6 import QtCore
from PyQt6.QtCore import QThread, pyqtSignal


def parse_sourceforge_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse a Sourceforge URL to extract the ZIP download URL and the path within the ZIP
    
    Format: https://sourceforge.net/projects/PROJECT/files/PATH/TO/FILE.zip/download/PATH/WITHIN/ZIP
    or: https://sourceforge.net/projects/PROJECT/files/PATH/TO/FILE.zip/PATH/WITHIN/ZIP
    
    Args:
        url: Sourceforge URL with embedded zip path and internal path
    
    Returns:
        Tuple of (zip_download_url, subfolder_path) or (None, None) if not a valid Sourceforge URL
    """
    print(f"[parse_sourceforge_url] Input: {url}")
    
    if 'sourceforge.net' not in url:
        print(f"[parse_sourceforge_url] Not a Sourceforge URL")
        return None, None
    
    # Find the .zip in the URL
    zip_index = url.find('.zip')
    if zip_index == -1:
        print(f"[parse_sourceforge_url] No .zip found in URL")
        return None, None
    
    # Extract base ZIP URL (everything up to and including .zip)
    zip_base_url = url[:zip_index + 4]  # +4 to include '.zip'
    
    # Everything after .zip is the path
    remainder = url[zip_index + 4:]
    
    # Check if /download is present and remove it
    if remainder.startswith('/download/'):
        subfolder = remainder[10:]  # Remove '/download/'
    elif remainder.startswith('/download'):
        subfolder = remainder[9:].lstrip('/')  # Remove '/download' and any leading slashes
    elif remainder.startswith('/'):
        subfolder = remainder[1:]  # Remove leading slash
    else:
        subfolder = remainder
    
    # Sourceforge requires /download suffix for direct downloads
    zip_download_url = zip_base_url + '/download'
    
    print(f"[parse_sourceforge_url] Parsed:")
    print(f"  zip_download_url: {zip_download_url}")
    print(f"  subfolder: {subfolder}")
    
    return zip_download_url, subfolder


def normalize_catalog_url(url: str, zip_file: str = None) -> str:
    """
    Convert a relative path or full URL to a full Sourceforge URL
    
    Args:
        url: Either a relative path (e.g., "/Newer_W_1.30/NewerSMBW/Stages") 
             or a full Sourceforge URL
        zip_file: Optional explicit ZIP filename (e.g., "newer_w_1.30.zip")
    
    Returns:
        Full Sourceforge URL with embedded zip path and internal path
    """
    print(f"[normalize_catalog_url] Input: {url}, zip_file: {zip_file}")
    
    # If it's already a full URL, return as-is
    if url.startswith('http://') or url.startswith('https://'):
        print(f"[normalize_catalog_url] Already full URL, returning as-is")
        return url
    
    # If it's a relative path, convert to full Sourceforge URL
    if url.startswith('/'):
        # Use explicit zip_file if provided, otherwise derive from first folder
        if zip_file:
            zip_name = zip_file
            print(f"[normalize_catalog_url] Using explicit zip_file: {zip_name}")
        else:
            # Extract the first folder name as the zip file name
            # E.g., "/Newer_W_1.30/NewerSMBW/Stages" -> "Newer_W_1.30" -> "newer_w_1.30.zip"
            parts = url.strip('/').split('/', 1)
            if parts:
                zip_folder = parts[0]
                # Convert to lowercase and add .zip extension
                zip_name = zip_folder.lower().replace(' ', '%20') + '.zip'
                print(f"[normalize_catalog_url] Derived zip_name from path: {zip_name}")
        
        # Format: https://sourceforge.net/projects/reggie-patch-catalog/files/assets/patches/ZIP_NAME.zip/PATH
        base_url = f"https://sourceforge.net/projects/reggie-patch-catalog/files/assets/patches/{zip_name}"
        result = base_url + url
        print(f"[normalize_catalog_url] Converted relative path:")
        print(f"  base_url: {base_url}")
        print(f"  result: {result}")
        return result
    
    print(f"[normalize_catalog_url] No conversion needed, returning: {url}")
    return url


def github_folder_to_zip_url(url: str, zip_file: str = None) -> Tuple[Optional[str], Optional[str]]:
    """
    Convert a URL (Sourceforge) to a downloadable ZIP URL and extract the subfolder path
    
    Args:
        url: Sourceforge URL with embedded paths (can be relative or absolute)
        zip_file: Optional explicit ZIP filename (e.g., "newer_w_1.30.zip")
    
    Returns:
        Tuple of (zip_url, subfolder_path) or (None, None) if not a valid URL
    """
    # First normalize the URL (convert relative paths to full Sourceforge URLs)
    url = normalize_catalog_url(url, zip_file)
    
    # Try Sourceforge format
    zip_url, subfolder = parse_sourceforge_url(url)
    if zip_url:
        return zip_url, subfolder
    
    return None, None


def extract_folder_name_from_url(url: str) -> Optional[str]:
    """
    Extract the final folder name from a URL
    
    Args:
        url: URL with folder path
    
    Returns:
        Folder name or None
    """
    # Remove trailing slash
    url = url.rstrip('/')
    
    # Extract last component
    parts = url.split('/')
    if parts:
        return parts[-1]
    
    return None


class DownloadThread(QThread):
    """
    Thread for downloading files asynchronously
    """
    
    # Signals
    progress = pyqtSignal(int)  # Progress percentage (0-100)
    finished = pyqtSignal(bool, str)  # Success, message/error
    status_changed = pyqtSignal(str)  # Status message
    
    def __init__(self, url: str, destination: str, parent=None):
        """
        Initialize download thread
        
        Args:
            url: URL to download from
            destination: Local file path to save to
            parent: Parent QObject
        """
        super().__init__(parent)
        self.url = url
        self.destination = destination
        self._is_cancelled = False
    
    def cancel(self):
        """Cancel the download"""
        self._is_cancelled = True
    
    def run(self):
        """Run the download"""
        try:
            self.status_changed.emit(f"Downloading from {self.url}...")
            
            # Ensure destination directory exists
            dest_dir = os.path.dirname(self.destination)
            if dest_dir and not os.path.exists(dest_dir):
                os.makedirs(dest_dir, exist_ok=True)
            
            # Download with progress tracking
            def reporthook(block_num, block_size, total_size):
                if self._is_cancelled:
                    raise Exception("Download cancelled")
                
                if total_size > 0:
                    downloaded = block_num * block_size
                    percent = min(int((downloaded / total_size) * 100), 100)
                    self.progress.emit(percent)
            
            urllib.request.urlretrieve(self.url, self.destination, reporthook)
            
            if not self._is_cancelled:
                self.progress.emit(100)
                self.finished.emit(True, f"Downloaded successfully")
            
        except Exception as e:
            if not self._is_cancelled:
                self.finished.emit(False, f"Download failed: {str(e)}")


class ExtractThread(QThread):
    """
    Thread for extracting zip files asynchronously
    """
    
    # Signals
    progress = pyqtSignal(int)  # Progress percentage (0-100)
    finished = pyqtSignal(bool, str)  # Success, message/error
    status_changed = pyqtSignal(str)  # Status message
    
    def __init__(self, zip_path: str, extract_to: str, parent=None):
        """
        Initialize extraction thread
        
        Args:
            zip_path: Path to zip file
            extract_to: Directory to extract to
            parent: Parent QObject
        """
        super().__init__(parent)
        self.zip_path = zip_path
        self.extract_to = extract_to
        self._is_cancelled = False
    
    def cancel(self):
        """Cancel the extraction"""
        self._is_cancelled = True
    
    def run(self):
        """Run the extraction"""
        try:
            self.status_changed.emit(f"Extracting {os.path.basename(self.zip_path)}...")
            
            # Ensure destination directory exists
            if not os.path.exists(self.extract_to):
                os.makedirs(self.extract_to, exist_ok=True)
            
            # Extract zip file
            with zipfile.ZipFile(self.zip_path, 'r') as zip_ref:
                file_list = zip_ref.namelist()
                total_files = len(file_list)
                
                for i, file in enumerate(file_list):
                    if self._is_cancelled:
                        raise Exception("Extraction cancelled")
                    
                    zip_ref.extract(file, self.extract_to)
                    
                    # Update progress
                    percent = int(((i + 1) / total_files) * 100)
                    self.progress.emit(percent)
            
            if not self._is_cancelled:
                self.progress.emit(100)
                self.finished.emit(True, "Extracted successfully")
            
        except Exception as e:
            if not self._is_cancelled:
                self.finished.emit(False, f"Extraction failed: {str(e)}")


class DownloadManager:
    """
    Manages downloads and extractions for patch catalog
    """
    
    def __init__(self):
        """Initialize the download manager"""
        self.active_downloads = {}
        self.active_extractions = {}
    
    def download_file(self, url: str, destination: str, callback=None) -> DownloadThread:
        """
        Start downloading a file
        
        Args:
            url: URL to download from
            destination: Local file path to save to
            callback: Optional callback function(success, message)
        
        Returns:
            DownloadThread instance
        """
        thread = DownloadThread(url, destination)
        
        if callback:
            thread.finished.connect(callback)
        
        # Track active download
        self.active_downloads[url] = thread
        
        # Clean up when finished
        def cleanup():
            if url in self.active_downloads:
                del self.active_downloads[url]
        
        thread.finished.connect(cleanup)
        thread.start()
        
        return thread
    
    def extract_zip(self, zip_path: str, extract_to: str, callback=None) -> ExtractThread:
        """
        Start extracting a zip file
        
        Args:
            zip_path: Path to zip file
            extract_to: Directory to extract to
            callback: Optional callback function(success, message)
        
        Returns:
            ExtractThread instance
        """
        thread = ExtractThread(zip_path, extract_to)
        
        if callback:
            thread.finished.connect(callback)
        
        # Track active extraction
        self.active_extractions[zip_path] = thread
        
        # Clean up when finished
        def cleanup():
            if zip_path in self.active_extractions:
                del self.active_extractions[zip_path]
        
        thread.finished.connect(cleanup)
        thread.start()
        
        return thread
    
    def cancel_download(self, thread: DownloadThread):
        """
        Cancel a specific download thread
        
        Args:
            thread: The DownloadThread to cancel
        """
        if thread:
            thread.cancel()
    
    def cancel_all(self):
        """Cancel all active downloads and extractions"""
        for thread in list(self.active_downloads.values()):
            thread.cancel()
        
        for thread in list(self.active_extractions.values()):
            thread.cancel()
    
    def is_busy(self) -> bool:
        """Check if any downloads or extractions are active"""
        return len(self.active_downloads) > 0 or len(self.active_extractions) > 0
