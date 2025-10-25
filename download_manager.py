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


def parse_github_url(url: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse a GitHub URL to extract owner, repo, and branch
    
    Args:
        url: GitHub URL (e.g., https://github.com/owner/repo/tree/branch/path)
    
    Returns:
        Tuple of (owner, repo, branch) or (None, None, None) if not a GitHub URL
    """
    # Match GitHub tree URLs
    match = re.match(r'https://github\.com/([^/]+)/([^/]+)/tree/([^/]+)', url)
    if match:
        return match.group(1), match.group(2), match.group(3)
    
    # Match GitHub blob URLs (for single files)
    match = re.match(r'https://github\.com/([^/]+)/([^/]+)/blob/([^/]+)', url)
    if match:
        return match.group(1), match.group(2), match.group(3)
    
    # Match basic GitHub repo URLs
    match = re.match(r'https://github\.com/([^/]+)/([^/]+)/?$', url)
    if match:
        return match.group(1), match.group(2), 'main'
    
    return None, None, None


def github_folder_to_zip_url(url: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Convert a GitHub folder URL to a downloadable ZIP URL and extract the subfolder path
    
    Args:
        url: GitHub folder URL
    
    Returns:
        Tuple of (zip_url, subfolder_path) or (None, None) if not a GitHub URL
    """
    owner, repo, branch = parse_github_url(url)
    if not owner or not repo or not branch:
        return None, None
    
    # Extract the subfolder path from the URL
    # e.g., https://github.com/owner/repo/tree/branch/path/to/folder -> path/to/folder
    match = re.match(r'https://github\.com/[^/]+/[^/]+/tree/[^/]+/(.+)', url)
    subfolder = match.group(1) if match else ''
    
    # Create ZIP download URL
    zip_url = f'https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.zip'
    
    return zip_url, subfolder


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
    
    def cancel_all(self):
        """Cancel all active downloads and extractions"""
        for thread in list(self.active_downloads.values()):
            thread.cancel()
        
        for thread in list(self.active_extractions.values()):
            thread.cancel()
    
    def is_busy(self) -> bool:
        """Check if any downloads or extractions are active"""
        return len(self.active_downloads) > 0 or len(self.active_extractions) > 0
