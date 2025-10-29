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
    REMOTE_CATALOG_URL = "https://sourceforge.net/projects/reggie-patch-catalog/files/assets/catalog/patchcatalog.json"
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
    
    def fetch_remote_catalog(self) -> Tuple[bool, Optional[str]]:
        """
        Fetch the catalog from the remote URL and cache it locally
        
        Returns:
            Tuple of (success, error_message)
        """
        try:
            print(f"[Catalog] Fetching from: {self.REMOTE_CATALOG_URL}")
            
            # Download directly to a temporary file using urlretrieve (same as download_manager)
            temp_path = self.LOCAL_CATALOG_PATH + '.tmp'
            urllib.request.urlretrieve(self.REMOTE_CATALOG_URL, temp_path)
            print(f"[Catalog] Downloaded to temporary file")
            
            # Validate JSON
            with open(temp_path, 'r', encoding='utf-8') as f:
                catalog_json = json.load(f)
            print(f"[Catalog] Parsed JSON with {len(catalog_json)} entries")
            
            # Move temp file to final location
            if os.path.exists(self.LOCAL_CATALOG_PATH):
                os.remove(self.LOCAL_CATALOG_PATH)
            os.rename(temp_path, self.LOCAL_CATALOG_PATH)
            print(f"[Catalog] Saved to: {self.LOCAL_CATALOG_PATH}")
            
            return True, None
            
        except urllib.error.HTTPError as e:
            error_msg = f"HTTP Error {e.code}: {e.reason}"
            print(f"[Catalog] {error_msg}")
            # Clean up temp file if it exists
            temp_path = self.LOCAL_CATALOG_PATH + '.tmp'
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False, error_msg
        except urllib.error.URLError as e:
            error_msg = f"URL Error: {e.reason}"
            print(f"[Catalog] {error_msg}")
            # Clean up temp file if it exists
            temp_path = self.LOCAL_CATALOG_PATH + '.tmp'
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False, error_msg
        except json.JSONDecodeError as e:
            error_msg = f"JSON Parse Error: {str(e)}"
            print(f"[Catalog] {error_msg}")
            # Clean up temp file if it exists
            temp_path = self.LOCAL_CATALOG_PATH + '.tmp'
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False, error_msg
        except OSError as e:
            error_msg = f"File Error: {str(e)}"
            print(f"[Catalog] {error_msg}")
            # Clean up temp file if it exists
            temp_path = self.LOCAL_CATALOG_PATH + '.tmp'
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected Error: {str(e)}"
            print(f"[Catalog] {error_msg}")
            import traceback
            traceback.print_exc()
            # Clean up temp file if it exists
            temp_path = self.LOCAL_CATALOG_PATH + '.tmp'
            if os.path.exists(temp_path):
                os.remove(temp_path)
            return False, error_msg
    
    def load_catalog(self, force_remote: bool = False) -> Tuple[bool, Optional[str]]:
        """
        Load the catalog from cache or remote
        
        Args:
            force_remote: If True, always fetch from remote
        
        Returns:
            Tuple of (success, error_message)
        """
        print(f"[Catalog] load_catalog called, force_remote={force_remote}")
        print(f"[Catalog] LOCAL_CATALOG_PATH={self.LOCAL_CATALOG_PATH}")
        print(f"[Catalog] Local cache exists: {os.path.exists(self.LOCAL_CATALOG_PATH)}")
        
        fetch_error = None
        
        # Try to fetch from remote if forced or if local cache doesn't exist
        if force_remote or not os.path.exists(self.LOCAL_CATALOG_PATH):
            print(f"[Catalog] Attempting to fetch from remote...")
            fetch_success, fetch_error = self.fetch_remote_catalog()
            if not fetch_success:
                # If remote fetch fails and no local cache, return False
                if not os.path.exists(self.LOCAL_CATALOG_PATH):
                    print(f"[Catalog] Remote fetch failed and no local cache exists")
                    return False, fetch_error
                print(f"[Catalog] Remote fetch failed but local cache exists, using cache")
        
        # Load from local cache
        try:
            print(f"[Catalog] Loading from local cache: {self.LOCAL_CATALOG_PATH}")
            with open(self.LOCAL_CATALOG_PATH, 'r', encoding='utf-8') as f:
                self.catalog_entries = json.load(f)
            print(f"[Catalog] Loaded {len(self.catalog_entries)} entries from cache")
        except (OSError, json.JSONDecodeError) as e:
            error_msg = f"Failed to load local catalog: {str(e)}"
            print(f"[Catalog] {error_msg}")
            self.catalog_entries = []
            return False, error_msg
        
        # Load user catalog if it exists
        if os.path.exists(self.USER_CATALOG_PATH):
            try:
                with open(self.USER_CATALOG_PATH, 'r', encoding='utf-8') as f:
                    self.user_entries = json.load(f)
                print(f"[Catalog] Loaded {len(self.user_entries)} user entries")
            except (OSError, json.JSONDecodeError) as e:
                print(f"[Catalog] Failed to load user catalog: {e}")
                self.user_entries = []
        
        # Return success, and include fetch error if there was one (but we still loaded from cache)
        return True, fetch_error
    
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
        
        # Check that at least stage URL exists for Method 1 (patch is optional)
        if 'stage' not in entry:
            return False, "Missing stage URL (required for Method 1)"
        
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
