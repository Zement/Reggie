"""
SmartBrush - Data structure mapping logical positions to tile object IDs
"""
from typing import Dict, List, Optional
import json
from enum import Enum


class TilesetCategory(Enum):
    """Tileset category enumeration based on slope support"""
    CAT1 = "cat1"  # Only vertical/horizontal tiles, no slopes
    CAT2 = "cat2"  # Vertical/horizontal tiles + 4x1 slopes only
    CAT3 = "cat3"  # Vertical/horizontal tiles + all slopes (1x1, 2x1, 4x1)


class SmartBrush:
    """
    SmartBrush represents a terrain brush with terrain and slope tile mappings.
    
    Maps terrain positions and slope types to tile object IDs for a specific tileset.
    Supports regex-based tileset name matching for batch preset linking.
    """
    
    def __init__(self, name: str, tileset_names: List[str], 
                 slot: str = "Pa0", painting_mode: str = "SmartPaint"):
        """
        Initialize a SmartBrush.
        
        Args:
            name: Brush name (e.g., "Pa1_nohara")
            tileset_names: List of tileset names or regex patterns this brush applies to
            slot: Tileset slot ("Pa0", "Pa1", "Pa2", "Pa3")
            painting_mode: Painting mode ("SmartPaint", "SingleTile", "ShapeCreator")
        """
        self.name = name
        self.tileset_names = tileset_names
        self.slot = slot
        self.painting_mode = painting_mode
        self.priority = 0  # Priority 0-9, higher = loaded first
        
        # Terrain positions: 13 total (center + 4 edges + 4 outer corners + 4 inner corners)
        # None = unassigned, 0-255 = object ID
        self.terrain = {
            'center': None,
            'top': None,
            'bottom': None,
            'left': None,
            'right': None,
            'top_left': None,
            'top_right': None,
            'bottom_left': None,
            'bottom_right': None,
            'inner_top_left': None,
            'inner_top_right': None,
            'inner_bottom_left': None,
            'inner_bottom_right': None,
        }
        
        # Track which terrain positions have been explicitly assigned
        self.terrain_assigned = set()
        
        # Slope types: 12 total (3 sizes, left and right, with top (ground) and bottom (ceiling) variants)
        # None = unassigned, 0-255 = object ID
        self.slopes = {
            'slope_top_1x1_left': None,
            'slope_top_1x1_right': None,
            'slope_top_2x1_left': None,
            'slope_top_2x1_right': None,
            'slope_top_4x1_left': None,
            'slope_top_4x1_right': None,
            'slope_bottom_1x1_left': None,
            'slope_bottom_1x1_right': None,
            'slope_bottom_2x1_left': None,
            'slope_bottom_2x1_right': None,
            'slope_bottom_4x1_left': None,
            'slope_bottom_4x1_right': None,
        }
        
        # Track which slopes are enabled (on/off flags)
        # All slopes enabled by default
        self.enabled_slopes = set(self.slopes.keys())
        
        # Track which slopes have been explicitly assigned
        self.slopes_assigned = set()
    
    def get_terrain_tile(self, position: str) -> Optional[int]:
        """
        Get tile object ID for a terrain position.
        
        Args:
            position: One of 'center', 'top', 'bottom', 'left', 'right',
                     'top_left', 'top_right', 'bottom_left', 'bottom_right',
                     'inner_top_left', 'inner_top_right', 'inner_bottom_left', 'inner_bottom_right'
        
        Returns:
            Tile object ID (0-255), or None if unassigned
        """
        return self.terrain.get(position, None)
    
    def get_tile_type_by_id(self, tile_id: int) -> Optional[str]:
        """
        Reverse lookup: Get terrain type from tile object ID.
        
        Args:
            tile_id: Tile object ID to look up
        
        Returns:
            Terrain type string (e.g., 'top', 'left', 'top_left'), or None if not found
        """
        for position, obj_id in self.terrain.items():
            if obj_id == tile_id:
                return position
        # Also check slopes
        for slope_type, obj_id in self.slopes.items():
            if obj_id == tile_id:
                return slope_type
        return None
    
    def set_terrain_tile(self, position: str, tile_id: int) -> None:
        """
        Set tile object ID for a terrain position.
        
        Args:
            position: Terrain position key
            tile_id: Tile object ID to set (0-255)
        """
        if position in self.terrain:
            self.terrain[position] = tile_id
            self.terrain_assigned.add(position)
    
    def get_slope_tile(self, slope_type: str) -> Optional[int]:
        """
        Get tile object ID for a slope type.
        
        Args:
            slope_type: One of 'slope_top_1x1_left', 'slope_top_1x1_right', etc.
        
        Returns:
            Tile object ID (0-255), or None if unassigned
        """
        return self.slopes.get(slope_type, None)
    
    def set_slope_tile(self, slope_type: str, tile_id: int) -> None:
        """
        Set tile object ID for a slope type.
        
        Args:
            slope_type: Slope type key
            tile_id: Tile object ID to set (0-255)
        """
        if slope_type in self.slopes:
            self.slopes[slope_type] = tile_id
            self.slopes_assigned.add(slope_type)
    
    def copy(self) -> 'SmartBrush':
        """
        Create a deep copy of this brush.
        
        Returns:
            New SmartBrush instance with copied data
        """
        new_brush = SmartBrush(self.name, self.tileset_names[:], self.slot, self.painting_mode)
        new_brush.priority = self.priority
        new_brush.terrain = self.terrain.copy()
        new_brush.terrain_assigned = self.terrain_assigned.copy()
        new_brush.slopes = self.slopes.copy()
        new_brush.slopes_assigned = self.slopes_assigned.copy()
        new_brush.enabled_slopes = self.enabled_slopes.copy()
        return new_brush
    
    def matches_tileset(self, tileset_name: str) -> bool:
        """
        Check if this brush applies to the given tileset.
        Supports regex patterns in tileset_names.
        
        Args:
            tileset_name: Name of the tileset (e.g., "Pa1_nohara")
        
        Returns:
            True if this brush applies to the tileset
        """
        if not self.tileset_names:
            return False
        
        import re
        
        for pattern in self.tileset_names:
            try:
                # Try to match as regex pattern
                if re.match(pattern, tileset_name):
                    return True
            except re.error:
                # If regex fails, try exact match
                if pattern == tileset_name:
                    return True
        
        return False
    
    def to_json(self) -> Dict:
        """
        Serialize to JSON-compatible dictionary.
        
        Slope values: -1 = disabled (flag OFF), null = empty/unassigned, 0-255 = object ID
        Terrain values: null = empty/unassigned, 0-255 = object ID
        
        Returns:
            Dictionary with name, tileset_names, slot, painting_mode, terrain, and slopes
        """
        # Convert slopes: disabled slopes get -1, enabled but empty get null, assigned get their ID
        slopes_json = {}
        for slope_name, obj_id in self.slopes.items():
            if slope_name not in self.enabled_slopes:
                slopes_json[slope_name] = -1  # Disabled (flag OFF)
            elif obj_id is None:
                slopes_json[slope_name] = None  # Enabled but empty
            else:
                slopes_json[slope_name] = obj_id  # Assigned object ID (0-255)
        
        return {
            'name': self.name,
            'tileset_names': self.tileset_names,
            'slot': self.slot,
            'painting_mode': self.painting_mode,
            'priority': self.priority,
            'terrain': self.terrain.copy(),
            'slopes': slopes_json,
        }
    
    def to_json_string(self) -> str:
        """
        Serialize to JSON string.
        
        Returns:
            JSON string representation
        """
        return json.dumps(self.to_json(), indent=2)
    
    @classmethod
    def from_json(cls, data: Dict) -> 'SmartBrush':
        """
        Deserialize from JSON dictionary.
        
        Slope values: -1 = disabled, 0 = empty/unassigned, 1-255 = object ID
        
        Args:
            data: Dictionary with 'name', 'tileset_names', 'slot', 'painting_mode', 'terrain', 'slopes'
        
        Returns:
            SmartBrush instance
        """
        slot = data.get('slot', 'Pa0')
        painting_mode = data.get('painting_mode', 'SmartPaint')
        priority = data.get('priority', 0)
        
        brush = cls(data['name'], data.get('tileset_names', []), slot, painting_mode)
        brush.priority = max(0, min(9, priority))  # Clamp to 0-9
        # Note: Don't directly assign terrain here - let the loop below handle it
        # brush.terrain = data.get('terrain', brush.terrain)  # BUG: This skips terrain_assigned
        
        # Parse slopes: -1 means disabled, null/None means empty, 0-255 are object IDs
        slopes_data = data.get('slopes', {})
        enabled_slopes = set()
        
        for slope_name, value in slopes_data.items():
            if slope_name in brush.slopes:
                if value == -1:
                    # Slope is disabled (flag OFF)
                    brush.slopes[slope_name] = None
                elif value is None:
                    # Slope is enabled but empty/unassigned
                    brush.slopes[slope_name] = None
                    enabled_slopes.add(slope_name)
                else:
                    # Slope is enabled and assigned (0-255 are valid object IDs)
                    brush.slopes[slope_name] = value
                    enabled_slopes.add(slope_name)
                    brush.slopes_assigned.add(slope_name)
        
        brush.enabled_slopes = enabled_slopes
        
        # Parse terrain: null/None means empty, 0-255 are object IDs
        terrain_data = data.get('terrain', {})
        for pos, obj_id in terrain_data.items():
            if pos in brush.terrain:
                if obj_id is not None:
                    brush.terrain[pos] = obj_id
                    brush.terrain_assigned.add(pos)
                else:
                    brush.terrain[pos] = None
        
        print(f"[SmartBrush] from_json: loaded terrain={brush.terrain}, assigned={brush.terrain_assigned}")
        return brush
    
    @classmethod
    def from_json_string(cls, json_str: str) -> 'SmartBrush':
        """
        Deserialize from JSON string.
        
        Args:
            json_str: JSON string representation
        
        Returns:
            SmartBrush instance
        """
        data = json.loads(json_str)
        return cls.from_json(data)
    
    def __repr__(self) -> str:
        return f"SmartBrush(name='{self.name}', tilesets={self.tileset_names})"
    
    def __str__(self) -> str:
        return self.name
