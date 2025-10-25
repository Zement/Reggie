"""
Catalog Manager Module
Handles fetching, caching, and managing the patch catalog for Reggie
"""

import os
import json
import urllib.request
import urllib.error
import hashlib
from typing import Dict, List, Optional, Tuple


class CatalogManager:
    """
    Manages the patch catalog including fetching, caching, and version checking
    """
    
    # Catalog URLs
    REMOTE_CATALOG_URL = "https://raw.githubusercontent.com/Zement/Reggie/master/assets/catalog/patchcatalog.json"
    LOCAL_CATALOG_PATH = os.path.join("assets", "catalog", "patchcatalog.json")
    USER_CATALOG_PATH = os.path.join("assets", "catalog", "patchcatalog_user.json")
    
    def __init__(self):
        """Initialize the catalog manager"""
        self.catalog_entries: List[Dict] = []
        self.user_entries: List[Dict] = []
        self._ensure_catalog_directory()
    
    def _ensure_catalog_directory(self):
        """Ensure the catalog directory exists"""
        catalog_dir = os.path.dirname(self.LOCAL_CATALOG_PATH)
        if not os.path.exists(catalog_dir):
            os.makedirs(catalog_dir, exist_ok=True)
    
    def fetch_remote_catalog(self) -> bool:
        """
        Fetch the catalog from the remote URL and cache it locally
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Fetch from remote
            with urllib.request.urlopen(self.REMOTE_CATALOG_URL, timeout=10) as response:
                catalog_data = response.read()
            
            # Validate JSON
            catalog_json = json.loads(catalog_data)
            
            # Save to local cache
            with open(self.LOCAL_CATALOG_PATH, 'w', encoding='utf-8') as f:
                json.dump(catalog_json, f, indent=2)
            
            return True
            
        except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, OSError) as e:
            print(f"Failed to fetch remote catalog: {e}")
            return False
    
    def load_catalog(self, force_remote: bool = False) -> bool:
        """
        Load the catalog from cache or remote
        
        Args:
            force_remote: If True, always fetch from remote
        
        Returns:
            True if catalog was loaded successfully
        """
        # Try to fetch from remote if forced or if local cache doesn't exist
        if force_remote or not os.path.exists(self.LOCAL_CATALOG_PATH):
            if not self.fetch_remote_catalog():
                # If remote fetch fails and no local cache, return False
                if not os.path.exists(self.LOCAL_CATALOG_PATH):
                    return False
        
        # Load from local cache
        try:
            with open(self.LOCAL_CATALOG_PATH, 'r', encoding='utf-8') as f:
                self.catalog_entries = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            print(f"Failed to load local catalog: {e}")
            self.catalog_entries = []
            return False
        
        # Load user catalog if it exists
        if os.path.exists(self.USER_CATALOG_PATH):
            try:
                with open(self.USER_CATALOG_PATH, 'r', encoding='utf-8') as f:
                    self.user_entries = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                print(f"Failed to load user catalog: {e}")
                self.user_entries = []
        
        return True
    
    def get_all_entries(self) -> List[Dict]:
        """
        Get all catalog entries (official + user)
        
        Returns:
            List of catalog entry dictionaries
        """
        return self.catalog_entries + self.user_entries
    
    def get_entry_by_name(self, name: str) -> Optional[Dict]:
        """
        Find a catalog entry by patch name
        
        Args:
            name: The patch name to search for
        
        Returns:
            The catalog entry dict or None if not found
        """
        for entry in self.get_all_entries():
            if entry.get('name') == name:
                return entry
        return None
    
    def validate_entry(self, entry: Dict) -> Tuple[bool, str]:
        """
        Validate that a catalog entry has all required fields
        
        Args:
            entry: The catalog entry to validate
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = ['name', 'version', 'description', 'author']
        
        for field in required_fields:
            if field not in entry:
                return False, f"Missing required field: {field}"
        
        # Check that at least stage and patch URLs exist for Method 1
        if 'stage' not in entry or 'patch' not in entry:
            return False, "Missing stage or patch URL (required for Method 1)"
        
        return True, ""
    
    def calculate_file_hash(self, file_path: str) -> Optional[str]:
        """
        Calculate MD5 hash of a file
        
        Args:
            file_path: Path to the file
        
        Returns:
            MD5 hash string or None if file doesn't exist
        """
        if not os.path.exists(file_path):
            return None
        
        try:
            md5_hash = hashlib.md5()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)
            return md5_hash.hexdigest()
        except OSError:
            return None
    
    def get_installed_patches(self) -> List[str]:
        """
        Get list of installed patch names from reggiedata/patches
        
        Returns:
            List of patch names
        """
        patches_dir = os.path.join('reggiedata', 'patches')
        if not os.path.exists(patches_dir):
            return []
        
        installed = []
        try:
            for item in os.listdir(patches_dir):
                item_path = os.path.join(patches_dir, item)
                if os.path.isdir(item_path):
                    # Check if main.xml exists
                    main_xml = os.path.join(item_path, 'main.xml')
                    if os.path.exists(main_xml):
                        # Parse main.xml to get patch name
                        try:
                            from xml.etree import ElementTree as etree
                            tree = etree.parse(main_xml)
                            root = tree.getroot()
                            patch_name = root.get('name')
                            if patch_name:
                                installed.append(patch_name)
                        except Exception:
                            pass
        except OSError:
            pass
        
        return installed
    
    def is_patch_installed(self, patch_name: str) -> bool:
        """
        Check if a patch is installed
        
        Args:
            patch_name: Name of the patch
        
        Returns:
            True if installed, False otherwise
        """
        return patch_name in self.get_installed_patches()
    
    def get_installed_patch_version(self, patch_name: str) -> Optional[str]:
        """
        Get the version of an installed patch
        
        Args:
            patch_name: Name of the patch
        
        Returns:
            Version string or None if not installed
        """
        patches_dir = os.path.join('reggiedata', 'patches')
        if not os.path.exists(patches_dir):
            return None
        
        try:
            for item in os.listdir(patches_dir):
                item_path = os.path.join(patches_dir, item)
                if os.path.isdir(item_path):
                    main_xml = os.path.join(item_path, 'main.xml')
                    if os.path.exists(main_xml):
                        try:
                            from xml.etree import ElementTree as etree
                            tree = etree.parse(main_xml)
                            root = tree.getroot()
                            if root.get('name') == patch_name:
                                return root.get('version')
                        except Exception:
                            pass
        except OSError:
            pass
        
        return None
    
    def compare_versions(self, installed_version: str, catalog_version: str) -> int:
        """
        Compare two version strings
        
        Args:
            installed_version: Currently installed version
            catalog_version: Version from catalog
        
        Returns:
            -1 if installed < catalog (update available)
            0 if installed == catalog (up to date)
            1 if installed > catalog (newer than catalog)
        """
        # Simple version comparison (handles v1.2.3 format)
        def parse_version(v: str) -> tuple:
            # Remove 'v' prefix if present
            v = v.lstrip('v').lstrip('V')
            # Split by dots and convert to integers
            parts = []
            for part in v.split('.'):
                # Extract numeric part only
                numeric = ''
                for char in part:
                    if char.isdigit():
                        numeric += char
                    else:
                        break
                if numeric:
                    parts.append(int(numeric))
            return tuple(parts)
        
        try:
            installed_parts = parse_version(installed_version)
            catalog_parts = parse_version(catalog_version)
            
            # Pad shorter version with zeros
            max_len = max(len(installed_parts), len(catalog_parts))
            installed_parts = installed_parts + (0,) * (max_len - len(installed_parts))
            catalog_parts = catalog_parts + (0,) * (max_len - len(catalog_parts))
            
            if installed_parts < catalog_parts:
                return -1
            elif installed_parts > catalog_parts:
                return 1
            else:
                return 0
        except Exception:
            # If parsing fails, assume they're equal
            return 0
    
    def add_user_entry(self, entry: Dict) -> bool:
        """
        Add a custom entry to the user catalog
        
        Args:
            entry: The catalog entry to add
        
        Returns:
            True if successful
        """
        # Validate entry
        is_valid, error = self.validate_entry(entry)
        if not is_valid:
            print(f"Invalid catalog entry: {error}")
            return False
        
        # Add to user entries
        self.user_entries.append(entry)
        
        # Save to file
        try:
            with open(self.USER_CATALOG_PATH, 'w', encoding='utf-8') as f:
                json.dump(self.user_entries, f, indent=2)
            return True
        except OSError as e:
            print(f"Failed to save user catalog: {e}")
            return False
