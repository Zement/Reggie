"""
Preset management - Load, save, and manage SmartBrush presets
"""
import os
import json
import re
from typing import Dict, List, Optional
from pathlib import Path

from .brush import SmartBrush


class PresetManager:
    """
    Manages SmartBrush presets - both builtin and user-defined.
    Supports regex patterns for matching multiple tilesets to the same preset.
    """
    
    def __init__(self, builtin_dir: str, user_dir: str):
        """
        Initialize the preset manager.
        
        Args:
            builtin_dir: Path to builtin presets (e.g., 'assets/qpt/builtin')
            user_dir: Path to user presets (e.g., 'assets/qpt/presets')
        """
        self.builtin_dir = Path(builtin_dir)
        self.user_dir = Path(user_dir)
        
        # Create user directory if it doesn't exist
        self.user_dir.mkdir(parents=True, exist_ok=True)
        
        # Cache for loaded presets
        self._builtin_cache: Dict[str, SmartBrush] = {}
        self._user_cache: Dict[str, SmartBrush] = {}
    
    def load_builtin_presets(self) -> Dict[str, SmartBrush]:
        """
        Load all builtin presets from the builtin directory.
        
        Returns:
            Dictionary mapping preset names to SmartBrush instances
        """
        if self._builtin_cache:
            return self._builtin_cache
        
        presets = {}
        
        if not self.builtin_dir.exists():
            return presets
        
        for json_file in self.builtin_dir.glob('*.json'):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    brush = SmartBrush.from_json(data)
                    presets[brush.name] = brush
            except Exception as e:
                print(f"Error loading builtin preset {json_file}: {e}")
        
        self._builtin_cache = presets
        return presets
    
    def load_user_presets(self) -> Dict[str, SmartBrush]:
        """
        Load all user-defined presets from the user directory.
        
        Returns:
            Dictionary mapping preset names to SmartBrush instances
        """
        if self._user_cache:
            return self._user_cache
        
        presets = {}
        
        if not self.user_dir.exists():
            return presets
        
        for json_file in self.user_dir.glob('*.json'):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    brush = SmartBrush.from_json(data)
                    presets[brush.name] = brush
            except Exception as e:
                print(f"Error loading user preset {json_file}: {e}")
        
        self._user_cache = presets
        return presets
    
    def get_all_presets(self) -> Dict[str, SmartBrush]:
        """
        Get all presets (builtin + user), with user presets overriding builtin.
        
        Returns:
            Dictionary mapping preset names to SmartBrush instances
        """
        all_presets = {}
        all_presets.update(self.load_builtin_presets())
        all_presets.update(self.load_user_presets())
        return all_presets
    
    def get_preset(self, name: str) -> Optional[SmartBrush]:
        """
        Get a preset by name.
        
        Args:
            name: Preset name
        
        Returns:
            SmartBrush instance or None if not found
        """
        all_presets = self.get_all_presets()
        return all_presets.get(name)
    
    def get_preset_for_tileset(self, tileset_name: str) -> Optional[SmartBrush]:
        """
        Get the best matching preset for a tileset.
        Checks all presets and returns the first one that matches the tileset name.
        Supports regex patterns in preset tileset_names.
        
        Args:
            tileset_name: Name of the tileset (e.g., "Pa1_nohara")
        
        Returns:
            SmartBrush instance or None if no match found
        """
        all_presets = self.get_all_presets()
        
        # First, try to find an exact match by preset name
        if tileset_name in all_presets:
            return all_presets[tileset_name]
        
        # Then, try to find a preset that matches the tileset
        for preset in all_presets.values():
            if preset.matches_tileset(tileset_name):
                return preset
        
        return None
    
    def save_preset(self, brush: SmartBrush) -> bool:
        """
        Save a preset to the user directory.
        
        Args:
            brush: SmartBrush instance to save
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Ensure user directory exists
            self.user_dir.mkdir(parents=True, exist_ok=True)
            
            # Save to file
            file_path = self.user_dir / f"{brush.name}.json"
            with open(file_path, 'w') as f:
                json.dump(brush.to_json(), f, indent=2)
            
            # Update cache
            self._user_cache[brush.name] = brush
            
            return True
        except Exception as e:
            print(f"Error saving preset {brush.name}: {e}")
            return False
    
    def delete_preset(self, name: str) -> bool:
        """
        Delete a user-defined preset.
        
        Args:
            name: Preset name to delete
        
        Returns:
            True if successful, False otherwise
        """
        try:
            file_path = self.user_dir / f"{name}.json"
            
            if file_path.exists():
                file_path.unlink()
                
                # Update cache
                if name in self._user_cache:
                    del self._user_cache[name]
                
                return True
            
            return False
        except Exception as e:
            print(f"Error deleting preset {name}: {e}")
            return False
    
    def list_builtin_presets(self) -> List[str]:
        """
        List all builtin preset names.
        
        Returns:
            List of preset names
        """
        return list(self.load_builtin_presets().keys())
    
    def list_user_presets(self) -> List[str]:
        """
        List all user-defined preset names.
        
        Returns:
            List of preset names
        """
        return list(self.load_user_presets().keys())
    
    def list_all_presets(self) -> List[str]:
        """
        List all preset names (builtin + user).
        
        Returns:
            List of preset names
        """
        return list(self.get_all_presets().keys())
    
    def clear_cache(self) -> None:
        """Clear the preset cache (forces reload on next access)."""
        self._builtin_cache.clear()
        self._user_cache.clear()
