"""
Painting modes - Smart Paint, Single-Tile, and Shape Creator
"""
from typing import List, Tuple, Dict, Optional, Union
from enum import Enum
import math

from .brush import SmartBrush
from .painter import QuickPainter, PaintOperation, DrawMode


class PaintingDirection(Enum):
    """Painting direction enumeration"""
    AUTO = "auto"              # Determined by initial mouse movement
    GROUND_LEFT = "ground/left"  # Paint ground/left terrain
    CEILING_RIGHT = "ceiling/right"  # Paint ceiling/right terrain


class SmartPaintMode:
    """
    Mode A: Smart Paint (Outline & Slopes)
    
    Intelligently paints terrain based on mouse movement direction.
    Supports both immediate and deferred painting modes.
    """
    
    @staticmethod
    def determine_initial_direction(prev_pos: Tuple[int, int], 
                                   curr_pos: Tuple[int, int]) -> str:
        """
        Determine the initial painting direction from mouse movement.
        
        Args:
            prev_pos: Previous mouse position (x, y)
            curr_pos: Current mouse position (x, y)
        
        Returns:
            Direction string: 'left_to_right', 'right_to_left', 'top_to_bottom', 'bottom_to_top'
        """
        dx = curr_pos[0] - prev_pos[0]
        dy = curr_pos[1] - prev_pos[1]
        
        # Determine dominant direction
        if abs(dx) > abs(dy):
            # Horizontal movement is dominant
            if dx > 0:
                return 'left_to_right'
            else:
                return 'right_to_left'
        else:
            # Vertical movement is dominant
            if dy > 0:
                return 'top_to_bottom'
            else:
                return 'bottom_to_top'
    
    @staticmethod
    def get_default_painting_direction(initial_direction: str) -> PaintingDirection:
        """
        Get the default painting direction based on initial mouse movement.
        
        Args:
            initial_direction: Initial direction from determine_initial_direction()
        
        Returns:
            PaintingDirection enum value
        """
        if initial_direction in ['left_to_right', 'bottom_to_top']:
            # Left-to-right or bottom-to-top: paint ground/left
            return PaintingDirection.GROUND_LEFT
        else:
            # Right-to-left or top-to-bottom: paint ceiling/right
            return PaintingDirection.CEILING_RIGHT
    
    @staticmethod
    def should_paint_terrain(terrain_position: str, 
                            painting_direction: PaintingDirection,
                            has_neighbor_above: bool,
                            has_neighbor_below: bool) -> bool:
        """
        Determine if a terrain position should be painted based on direction and context.
        
        Args:
            terrain_position: Terrain position ('top', 'bottom', 'left', 'right', 'center', etc.)
            painting_direction: Current painting direction
            has_neighbor_above: Whether there's terrain above the current position
            has_neighbor_below: Whether there's terrain below the current position
        
        Returns:
            True if this terrain position should be painted
        """
        # Note: For SmartPaint border painting, we use direction-based tile selection
        # in _update_outline, not this function. This function is kept for compatibility
        # with other painting modes that may use auto-tile-type calculation.
        
        if painting_direction == PaintingDirection.AUTO:
            # Auto mode: paint all terrain
            return True
        
        if painting_direction == PaintingDirection.GROUND_LEFT:
            # Paint ground/left: top, left, and related corners
            if terrain_position in ['top', 'left', 'top_left', 'top_right']:
                return True
            # Exception: if there's terrain above, paint bottom instead
            if has_neighbor_above and terrain_position in ['bottom', 'bottom_left', 'bottom_right']:
                return True
            return False
        
        else:  # CEILING_RIGHT
            # Paint ceiling/right: bottom, right, and related corners
            if terrain_position in ['bottom', 'right', 'bottom_left', 'bottom_right']:
                return True
            # Exception: if there's terrain below, paint top instead
            if has_neighbor_below and terrain_position in ['top', 'top_left', 'top_right']:
                return True
            return False
    
    @staticmethod
    def paint_smart_path(path: List[Tuple[int, int]], 
                        layer: int,
                        brush: SmartBrush,
                        painting_direction: PaintingDirection = PaintingDirection.AUTO,
                        existing_tiles: Optional[Dict[Tuple[int, int, int], int]] = None,
                        mode: DrawMode = DrawMode.DEFERRED) -> List[PaintOperation]:
        """
        Paint a path using smart auto-tiling with direction awareness.
        
        Args:
            path: List of (x, y) tile coordinates
            layer: Layer index
            brush: SmartBrush with terrain tile mappings
            painting_direction: Direction to paint (GROUND_LEFT, CEILING_RIGHT, or AUTO)
            existing_tiles: Dictionary of existing tiles
            mode: Drawing mode (IMMEDIATE or DEFERRED)
        
        Returns:
            List of PaintOperation objects
        """
        if existing_tiles is None:
            existing_tiles = {}
        
        operations = []
        
        for x, y in path:
            # Get neighbors
            neighbors = QuickPainter.get_neighbors(x, y, layer, existing_tiles)
            
            # Check for terrain above and below
            has_neighbor_above = neighbors.get('top', False)
            has_neighbor_below = neighbors.get('bottom', False)
            
            # Determine which terrain to paint
            tile_type = QuickPainter.calculate_auto_tile_type(neighbors)
            
            # Filter terrain based on painting direction
            if not SmartPaintMode.should_paint_terrain(tile_type, painting_direction, 
                                                       has_neighbor_above, has_neighbor_below):
                continue
            
            # Get tile ID from brush
            tile_id = brush.get_terrain_tile(tile_type)
            
            if tile_id is not None:
                op = PaintOperation(x, y, tile_id, layer)
                operations.append(op)
                existing_tiles[(x, y, layer)] = tile_id
        
        return operations
    
    @staticmethod
    def paint_smart_with_slopes(path: List[Tuple[int, int]],
                               layer: int,
                               brush: SmartBrush,
                               painting_direction: PaintingDirection = PaintingDirection.AUTO,
                               existing_tiles: Optional[Dict[Tuple[int, int, int], int]] = None) -> List[PaintOperation]:
        """
        Paint a path with smart auto-tiling and slope detection.
        
        Analyzes the path to detect slopes and place appropriate slope tiles.
        
        Args:
            path: List of (x, y) tile coordinates
            layer: Layer index
            brush: SmartBrush with terrain and slope tile mappings
            painting_direction: Direction to paint
            existing_tiles: Dictionary of existing tiles
        
        Returns:
            List of PaintOperation objects
        """
        if existing_tiles is None:
            existing_tiles = {}
        
        operations = []
        
        # First pass: detect slopes in the path
        for i in range(len(path) - 1):
            curr_pos = path[i]
            next_pos = path[i + 1]
            
            # Calculate distance and angle
            dx = next_pos[0] - curr_pos[0]
            dy = next_pos[1] - curr_pos[1]
            distance = math.sqrt(dx*dx + dy*dy)
            
            # Detect slope type
            slope_type = QuickPainter.detect_slope_type(curr_pos, next_pos, int(distance))
            
            if slope_type:
                # Get slope tile ID from brush
                slope_tile_id = brush.get_slope_tile(slope_type)
                
                if slope_tile_id is not None:
                    op = PaintOperation(curr_pos[0], curr_pos[1], slope_tile_id, layer)
                    operations.append(op)
                    existing_tiles[(curr_pos[0], curr_pos[1], layer)] = slope_tile_id
        
        # Second pass: fill in terrain with auto-tiling
        terrain_ops = SmartPaintMode.paint_smart_path(path, layer, brush, 
                                                      painting_direction, existing_tiles)
        operations.extend(terrain_ops)
        
        return operations


class SingleTileMode:
    """
    Mode B: Single-Tile Mode
    
    Simple mode that paints a single tile type along the drawn path.
    No auto-tiling, no slope detection.
    """
    
    @staticmethod
    def paint_single_tile(path: List[Tuple[int, int]],
                         layer: int,
                         tile_id: int) -> List[PaintOperation]:
        """
        Paint a single tile type along a path.
        
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


class ShapeCreator:
    """
    Mode C: Shape Creator (Island Maker)
    
    Creates pre-defined shapes with auto-tiling.
    Supports rectangles, ellipses, and custom paths.
    """
    
    @staticmethod
    def create_rectangle(start: Tuple[int, int],
                        end: Tuple[int, int],
                        layer: int,
                        brush: SmartBrush) -> List[PaintOperation]:
        """
        Create a filled rectangle with auto-tiled borders.
        
        Args:
            start: Starting corner (x, y)
            end: Ending corner (x, y)
            layer: Layer index
            brush: SmartBrush with terrain tile mappings
        
        Returns:
            List of PaintOperation objects
        """
        return QuickPainter.create_rectangle(start, end, layer, brush)
    
    @staticmethod
    def create_ellipse(start: Tuple[int, int],
                      end: Tuple[int, int],
                      layer: int,
                      brush: SmartBrush) -> List[PaintOperation]:
        """
        Create a filled ellipse with auto-tiled borders.
        
        Args:
            start: Starting corner (x, y)
            end: Ending corner (x, y)
            layer: Layer index
            brush: SmartBrush with terrain tile mappings
        
        Returns:
            List of PaintOperation objects
        """
        return QuickPainter.create_ellipse(start, end, layer, brush)
    
    @staticmethod
    def create_from_path(path: List[Tuple[int, int]],
                        layer: int,
                        brush: SmartBrush) -> List[PaintOperation]:
        """
        Create a shape from a custom path (list of points).
        
        The path defines the outline of the shape, which is then filled
        with auto-tiling applied to the borders.
        
        Args:
            path: List of (x, y) tile coordinates defining the shape outline
            layer: Layer index
            brush: SmartBrush with terrain tile mappings
        
        Returns:
            List of PaintOperation objects
        """
        # Use QuickPainter's path painting with auto-tiling
        return QuickPainter.paint_path(path, layer, brush, DrawMode.DEFERRED)


class EraserBrush:
    """
    Special brush for erasing terrain/objects.
    
    Removes tiles at specified positions.
    """
    
    @staticmethod
    def erase_path(path: List[Tuple[int, int]],
                  layer: int) -> List[PaintOperation]:
        """
        Erase tiles along a path.
        
        Creates PaintOperation objects with tile_id = 0 (erase marker).
        
        Args:
            path: List of (x, y) tile coordinates to erase
            layer: Layer index
        
        Returns:
            List of PaintOperation objects with tile_id = 0
        """
        operations = []
        
        for x, y in path:
            # Use tile_id = 0 to indicate erasure
            op = PaintOperation(x, y, 0, layer)
            operations.append(op)
        
        return operations
    
    @staticmethod
    def erase_rectangle(start: Tuple[int, int],
                       end: Tuple[int, int],
                       layer: int) -> List[PaintOperation]:
        """
        Erase a rectangular area.
        
        Args:
            start: Starting corner (x, y)
            end: Ending corner (x, y)
            layer: Layer index
        
        Returns:
            List of PaintOperation objects with tile_id = 0
        """
        x1, y1 = start
        x2, y2 = end
        
        # Normalize coordinates
        min_x = min(x1, x2)
        max_x = max(x1, x2)
        min_y = min(y1, y2)
        max_y = max(y1, y2)
        
        operations = []
        
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                op = PaintOperation(x, y, 0, layer)
                operations.append(op)
        
        return operations
    
    @staticmethod
    def erase_ellipse(start: Tuple[int, int],
                     end: Tuple[int, int],
                     layer: int) -> List[PaintOperation]:
        """
        Erase an elliptical area.
        
        Args:
            start: Starting corner (x, y)
            end: Ending corner (x, y)
            layer: Layer index
        
        Returns:
            List of PaintOperation objects with tile_id = 0
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
                op = PaintOperation(px, py, 0, layer)
                operations.append(op)
            
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
                op = PaintOperation(px, py, 0, layer)
                operations.append(op)
            
            if d2 > 0:
                d2 = d2 - (2 * rx * rx * y) + (rx * rx)
            else:
                d2 = d2 + (2 * ry * ry * x) - (2 * rx * rx * y) + (rx * rx)
            
            y -= 1
        
        return operations
