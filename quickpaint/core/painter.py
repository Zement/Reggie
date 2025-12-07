"""
Core painting engine - Bresenham interpolation, auto-tiling, and deferred painting
"""
from typing import List, Tuple, Dict, Optional, Set
from enum import Enum
import math

from .brush import SmartBrush


class DrawMode(Enum):
    """Drawing mode enumeration"""
    IMMEDIATE = "immediate"  # Draw immediately as mouse moves
    DEFERRED = "deferred"    # Show outline, draw on mouse release


class PaintOperation:
    """Represents a single paint operation (tile placement)"""
    
    def __init__(self, x: int, y: int, tile_id: int, layer: int = 0):
        """
        Initialize a paint operation.
        
        Args:
            x: Tile X coordinate
            y: Tile Y coordinate
            tile_id: Tile object ID to place
            layer: Layer index (0, 1, or 2)
        """
        self.x = x
        self.y = y
        self.tile_id = tile_id
        self.layer = layer
    
    def __eq__(self, other):
        if not isinstance(other, PaintOperation):
            return False
        return (self.x == other.x and self.y == other.y and 
                self.tile_id == other.tile_id and self.layer == other.layer)
    
    def __hash__(self):
        return hash((self.x, self.y, self.tile_id, self.layer))
    
    def __repr__(self):
        return f"PaintOp({self.x}, {self.y}, tile={self.tile_id}, layer={self.layer})"


class QuickPainter:
    """
    Core painting engine with Bresenham interpolation, auto-tiling, and deferred painting.
    """
    
    @staticmethod
    def bresenham_line(x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int, int]]:
        """
        Bresenham's line algorithm for coordinate interpolation.
        
        Generates all tile coordinates along a line from (x0, y0) to (x1, y1).
        This ensures smooth, continuous strokes without gaps.
        
        Args:
            x0: Starting X coordinate
            y0: Starting Y coordinate
            x1: Ending X coordinate
            y1: Ending Y coordinate
        
        Returns:
            List of (x, y) tuples representing all tiles along the line
        """
        points = []
        
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        
        if dx > dy:
            # More horizontal than vertical
            err = dx / 2.0
            y = y0
            for x in range(x0, x1 + sx, sx):
                points.append((x, y))
                err -= dy
                if err < 0:
                    y += sy
                    err += dx
        else:
            # More vertical than horizontal
            err = dy / 2.0
            x = x0
            for y in range(y0, y1 + sy, sy):
                points.append((x, y))
                err -= dx
                if err < 0:
                    x += sx
                    err += dy
        
        return points
    
    @staticmethod
    def get_neighbors(x: int, y: int, layer: int, 
                     existing_tiles: Dict[Tuple[int, int, int], int]) -> Dict[str, bool]:
        """
        Get the state of all 8 neighbors for a tile position.
        
        Args:
            x: Tile X coordinate
            y: Tile Y coordinate
            layer: Layer index
            existing_tiles: Dictionary of existing tiles {(x, y, layer): tile_id}
        
        Returns:
            Dictionary with keys like 'top', 'bottom', 'left', 'right',
            'top_left', 'top_right', 'bottom_left', 'bottom_right'
            Values are True if a tile exists at that position
        """
        neighbors = {
            'top': (x, y - 1, layer) in existing_tiles,
            'bottom': (x, y + 1, layer) in existing_tiles,
            'left': (x - 1, y, layer) in existing_tiles,
            'right': (x + 1, y, layer) in existing_tiles,
            'top_left': (x - 1, y - 1, layer) in existing_tiles,
            'top_right': (x + 1, y - 1, layer) in existing_tiles,
            'bottom_left': (x - 1, y + 1, layer) in existing_tiles,
            'bottom_right': (x + 1, y + 1, layer) in existing_tiles,
        }
        return neighbors
    
    @staticmethod
    def calculate_auto_tile_type(neighbors: Dict[str, bool]) -> str:
        """
        Determine the tile type based on 8-neighbor configuration.
        
        Uses bitmasking to determine which tile variant to use:
        - Bit 0 (0x01) = top_left
        - Bit 1 (0x02) = top
        - Bit 2 (0x04) = top_right
        - Bit 3 (0x08) = left
        - Bit 4 (0x10) = right
        - Bit 5 (0x20) = bottom_left
        - Bit 6 (0x40) = bottom
        - Bit 7 (0x80) = bottom_right
        
        Args:
            neighbors: Dictionary of neighbor states
        
        Returns:
            Tile type string ('center', 'top', 'bottom', 'left', 'right',
                            'top_left', 'top_right', 'bottom_left', 'bottom_right',
                            'inner_top_left', 'inner_top_right', 'inner_bottom_left', 'inner_bottom_right')
        """
        # Calculate bitmasking flag
        flag = 0
        if neighbors.get('top_left'): flag |= 0x01
        if neighbors.get('top'): flag |= 0x02
        if neighbors.get('top_right'): flag |= 0x04
        if neighbors.get('left'): flag |= 0x08
        if neighbors.get('right'): flag |= 0x10
        if neighbors.get('bottom_left'): flag |= 0x20
        if neighbors.get('bottom'): flag |= 0x40
        if neighbors.get('bottom_right'): flag |= 0x80
        
        # Determine tile type based on flag
        # This logic determines which tile variant to use based on neighbor configuration
        
        # All neighbors present = center
        if flag == 0xFF:
            return 'center'
        
        # Check for edges (single edge neighbor, no corners)
        if flag == 0x02:  # Only top
            return 'top'
        if flag == 0x40:  # Only bottom
            return 'bottom'
        if flag == 0x08:  # Only left
            return 'left'
        if flag == 0x10:  # Only right
            return 'right'
        
        # Check for outer corners (corner + two adjacent edges, or just corner + edges)
        if flag == 0x07 or flag == 0x0B:  # top_left + top + left (with/without corner)
            return 'top_left'
        if flag == 0x0E or flag == 0x0D:  # top_right + top + right (with/without corner)
            return 'top_right'
        if flag == 0x70 or flag == 0x68:  # bottom_left + bottom + left (with/without corner)
            return 'bottom_left'
        if flag == 0xE0 or flag == 0xD0:  # bottom_right + bottom + right (with/without corner)
            return 'bottom_right'
        
        # Check for inner corners (all neighbors except one corner)
        if flag == 0xFE:  # All except top_left
            return 'inner_top_left'
        if flag == 0xFD:  # All except top_right
            return 'inner_top_right'
        if flag == 0xDF:  # All except bottom_left
            return 'inner_bottom_left'
        if flag == 0xBF:  # All except bottom_right
            return 'inner_bottom_right'
        
        # Default to center for any other configuration
        return 'center'
    
    @staticmethod
    def auto_tile_8neighbor(x: int, y: int, layer: int, brush: SmartBrush,
                           existing_tiles: Dict[Tuple[int, int, int], int]) -> Optional[int]:
        """
        Determine the tile object ID to place at a position using 8-neighbor auto-tiling.
        
        Args:
            x: Tile X coordinate
            y: Tile Y coordinate
            layer: Layer index
            brush: SmartBrush with terrain tile mappings
            existing_tiles: Dictionary of existing tiles {(x, y, layer): tile_id}
        
        Returns:
            Tile object ID to place, or None if no suitable tile found
        """
        neighbors = QuickPainter.get_neighbors(x, y, layer, existing_tiles)
        tile_type = QuickPainter.calculate_auto_tile_type(neighbors)
        
        # Get the tile ID from the brush
        tile_id = brush.get_terrain_tile(tile_type)
        
        return tile_id if tile_id > 0 else None
    
    @staticmethod
    def detect_slope_type(prev_pos: Tuple[int, int], curr_pos: Tuple[int, int],
                         distance: int) -> Optional[str]:
        """
        Detect slope type based on mouse movement vector and distance.
        
        Analyzes the angle and distance of mouse movement to determine:
        - Slope orientation (floor/ceiling, up/down)
        - Slope size (1x1, 2x1, 4x1)
        
        Args:
            prev_pos: Previous mouse position (x, y)
            curr_pos: Current mouse position (x, y)
            distance: Distance traveled in pixels
        
        Returns:
            Slope type string or None if not a slope movement
        """
        dx = curr_pos[0] - prev_pos[0]
        dy = curr_pos[1] - prev_pos[1]
        
        if dx == 0 and dy == 0:
            return None
        
        # Calculate angle in degrees (0-360)
        angle = math.degrees(math.atan2(dy, dx))
        if angle < 0:
            angle += 360
        
        # Normalize angle to 0-90 range for easier comparison
        normalized_angle = angle % 90
        
        # Determine slope size based on distance
        if distance < 20:
            size = '1x1'
        elif distance < 40:
            size = '2x1'
        else:
            size = '4x1'
        
        # Determine slope orientation based on angle
        # 0-45°: Right/floor up
        # 45-90°: Down/floor down
        # 90-135°: Left/ceiling down
        # 135-180°: Up/ceiling up
        # 180-225°: Left/ceiling down
        # 225-270°: Up/ceiling up
        # 270-315°: Right/floor up
        # 315-360°: Down/floor down
        
        if 315 <= angle or angle < 45:
            # Moving right - floor up
            return f'floor_up_{size}'
        elif 45 <= angle < 135:
            # Moving down - floor down
            return f'floor_down_{size}'
        elif 135 <= angle < 225:
            # Moving left - ceiling down
            return f'ceiling_down_{size}'
        else:  # 225 <= angle < 315
            # Moving up - ceiling up
            return f'ceiling_up_{size}'
    
    @staticmethod
    def paint_path(path: List[Tuple[int, int]], layer: int, brush: SmartBrush,
                  mode: DrawMode = DrawMode.DEFERRED,
                  existing_tiles: Optional[Dict[Tuple[int, int, int], int]] = None) -> List[PaintOperation]:
        """
        Generate paint operations for a path using auto-tiling.
        
        Args:
            path: List of (x, y) tile coordinates
            layer: Layer index
            brush: SmartBrush with terrain tile mappings
            mode: Drawing mode (IMMEDIATE or DEFERRED)
            existing_tiles: Dictionary of existing tiles (for auto-tiling context)
        
        Returns:
            List of PaintOperation objects
        """
        if existing_tiles is None:
            existing_tiles = {}
        
        operations = []
        
        for x, y in path:
            # Auto-tile to determine which tile to place
            tile_id = QuickPainter.auto_tile_8neighbor(x, y, layer, brush, existing_tiles)
            
            if tile_id is not None:
                op = PaintOperation(x, y, tile_id, layer)
                operations.append(op)
                
                # Add to existing tiles for context of next tiles
                existing_tiles[(x, y, layer)] = tile_id
        
        return operations
    
    @staticmethod
    def paint_single_tile(path: List[Tuple[int, int]], layer: int, tile_id: int) -> List[PaintOperation]:
        """
        Generate paint operations for painting a single tile type along a path.
        
        Args:
            path: List of (x, y) tile coordinates
            layer: Layer index
            tile_id: Tile object ID to paint
        
        Returns:
            List of PaintOperation objects
        """
        operations = []
        
        for x, y in path:
            op = PaintOperation(x, y, tile_id, layer)
            operations.append(op)
        
        return operations
    
    @staticmethod
    def create_rectangle(start: Tuple[int, int], end: Tuple[int, int], 
                        layer: int, brush: SmartBrush) -> List[PaintOperation]:
        """
        Generate paint operations for a filled rectangle with auto-tiled borders.
        
        Args:
            start: Starting corner (x, y)
            end: Ending corner (x, y)
            layer: Layer index
            brush: SmartBrush with terrain tile mappings
        
        Returns:
            List of PaintOperation objects
        """
        x1, y1 = start
        x2, y2 = end
        
        # Normalize coordinates
        min_x = min(x1, x2)
        max_x = max(x1, x2)
        min_y = min(y1, y2)
        max_y = max(y1, y2)
        
        operations = []
        existing_tiles = {}
        
        # Draw rectangle outline and fill
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                # Auto-tile to determine which tile to place
                tile_id = QuickPainter.auto_tile_8neighbor(x, y, layer, brush, existing_tiles)
                
                if tile_id is not None:
                    op = PaintOperation(x, y, tile_id, layer)
                    operations.append(op)
                    existing_tiles[(x, y, layer)] = tile_id
        
        return operations
    
    @staticmethod
    def create_ellipse(start: Tuple[int, int], end: Tuple[int, int],
                      layer: int, brush: SmartBrush) -> List[PaintOperation]:
        """
        Generate paint operations for a filled ellipse with auto-tiled borders.
        
        Uses Midpoint Ellipse Algorithm for efficient ellipse generation.
        
        Args:
            start: Starting corner (x, y)
            end: Ending corner (x, y)
            layer: Layer index
            brush: SmartBrush with terrain tile mappings
        
        Returns:
            List of PaintOperation objects
        """
        x1, y1 = start
        x2, y2 = end
        
        # Calculate center and radii
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        rx = abs(x2 - x1) // 2
        ry = abs(y2 - y1) // 2
        
        if rx == 0 or ry == 0:
            return []
        
        operations = []
        existing_tiles = {}
        
        # Midpoint ellipse algorithm
        x = 0
        y = ry
        
        # Decision parameter for region 1
        d1 = (ry * ry) - (rx * rx * ry) + (rx * rx // 4)
        
        # Points in region 1
        while (rx * rx * y) >= (ry * ry * x):
            # Plot points in all 4 quadrants
            for px, py in [(cx + x, cy + y), (cx - x, cy + y),
                          (cx + x, cy - y), (cx - x, cy - y)]:
                tile_id = QuickPainter.auto_tile_8neighbor(px, py, layer, brush, existing_tiles)
                if tile_id is not None:
                    op = PaintOperation(px, py, tile_id, layer)
                    operations.append(op)
                    existing_tiles[(px, py, layer)] = tile_id
            
            if d1 < 0:
                d1 = d1 + (2 * ry * ry * x) + (ry * ry)
            else:
                d1 = d1 + (2 * ry * ry * x) - (2 * rx * rx * y) + (ry * ry)
            
            x += 1
        
        # Decision parameter for region 2
        d2 = ((ry * ry) * ((x + 0.5) ** 2)) + ((rx * rx) * ((y - 1) ** 2)) - (rx * rx * ry * ry)
        
        # Points in region 2
        while y >= 0:
            # Plot points in all 4 quadrants
            for px, py in [(cx + x, cy + y), (cx - x, cy + y),
                          (cx + x, cy - y), (cx - x, cy - y)]:
                tile_id = QuickPainter.auto_tile_8neighbor(px, py, layer, brush, existing_tiles)
                if tile_id is not None:
                    op = PaintOperation(px, py, tile_id, layer)
                    operations.append(op)
                    existing_tiles[(px, py, layer)] = tile_id
            
            if d2 > 0:
                d2 = d2 - (2 * rx * rx * y) + (rx * rx)
            else:
                d2 = d2 + (2 * ry * ry * x) - (2 * rx * rx * y) + (rx * rx)
            
            y -= 1
        
        return operations
