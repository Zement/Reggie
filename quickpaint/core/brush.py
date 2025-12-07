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
    Supports three tileset categories based on slope availability.
    """
    
    def __init__(self, name: str, tileset_names: List[str], 
                 category: TilesetCategory = TilesetCategory.CAT3):
        """
        Initialize a SmartBrush.
        
        Args:
            name: Brush name (e.g., "Pa1_nohara")
            tileset_names: List of tileset names or regex patterns this brush applies to
            category: Tileset category (CAT1, CAT2, or CAT3)
        """
        self.name = name
        self.tileset_names = tileset_names
        self.category = category
        
        # Terrain positions: 13 total (center + 4 edges + 4 outer corners + 4 inner corners)
        self.terrain = {
            'center': 0,
            'top': 0,
            'bottom': 0,
            'left': 0,
            'right': 0,
            'top_left': 0,
            'top_right': 0,
            'bottom_left': 0,
            'bottom_right': 0,
            'inner_top_left': 0,
            'inner_top_right': 0,
            'inner_bottom_left': 0,
            'inner_bottom_right': 0,
        }
        
        # Track which terrain positions have been explicitly assigned
        # This allows us to distinguish between "unassigned (0)" and "assigned to object 0"
        self.terrain_assigned = set()
        
        # Slope types: 12 total (4 directions × 3 sizes)
        # CAT1: No slopes (all 0)
        # CAT2: Only 4x1 slopes
        # CAT3: All slopes (1x1, 2x1, 4x1)
        self.slopes = {
            'floor_up_1x1': 0,
            'floor_up_2x1': 0,
            'floor_up_4x1': 0,
            'floor_down_1x1': 0,
            'floor_down_2x1': 0,
            'floor_down_4x1': 0,
            'ceiling_up_1x1': 0,
            'ceiling_up_2x1': 0,
            'ceiling_up_4x1': 0,
            'ceiling_down_1x1': 0,
            'ceiling_down_2x1': 0,
            'ceiling_down_4x1': 0,
        }
    
    def get_terrain_tile(self, position: str) -> int:
        """
        Get tile object ID for a terrain position.
        
        Args:
            position: One of 'center', 'top', 'bottom', 'left', 'right',
                     'top_left', 'top_right', 'bottom_left', 'bottom_right',
                     'inner_top_left', 'inner_top_right', 'inner_bottom_left', 'inner_bottom_right'
        
        Returns:
            Tile object ID (0-255)
        """
        return self.terrain.get(position, 0)
    
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
    
    def get_slope_tile(self, slope_type: str) -> int:
        """
        Get tile object ID for a slope type.
        
        Args:
            slope_type: One of 'floor_up_1x1', 'floor_up_2x1', 'floor_up_4x1',
                       'floor_down_1x1', 'floor_down_2x1', 'floor_down_4x1',
                       'ceiling_up_1x1', 'ceiling_up_2x1', 'ceiling_up_4x1',
                       'ceiling_down_1x1', 'ceiling_down_2x1', 'ceiling_down_4x1'
        
        Returns:
            Tile object ID (0-255)
        """
        return self.slopes.get(slope_type, 0)
    
    def set_slope_tile(self, slope_type: str, tile_id: int) -> None:
        """
        Set tile object ID for a slope type.
        
        Args:
            slope_type: Slope type key
            tile_id: Tile object ID to set (0-255)
        """
        if slope_type in self.slopes:
            self.slopes[slope_type] = tile_id
    
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
        
        Returns:
            Dictionary with name, tileset_names, category, terrain, and slopes
        """
        return {
            'name': self.name,
            'tileset_names': self.tileset_names,
            'category': self.category.value,
            'terrain': self.terrain.copy(),
            'slopes': self.slopes.copy(),
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
        
        Args:
            data: Dictionary with 'name', 'tileset_names', 'category', 'terrain', 'slopes'
        
        Returns:
            SmartBrush instance
        """
        # Parse category from string
        category_str = data.get('category', 'cat3')
        try:
            category = TilesetCategory(category_str)
        except ValueError:
            category = TilesetCategory.CAT3
        
        brush = cls(data['name'], data.get('tileset_names', []), category)
        brush.terrain = data.get('terrain', brush.terrain)
        brush.slopes = data.get('slopes', brush.slopes)
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
