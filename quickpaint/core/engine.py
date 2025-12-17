"""
Painting Engine - Core painting logic with immediate and deferred modes

This module implements the main painting engine that coordinates:
- Immediate painting (paint while holding key)
- Deferred painting (outline preview, click to finalize)
- Bresenham interpolation for smooth strokes
- 8-neighbor auto-tiling with direction awareness
- Integration with Reggie's level system

Direction-based painting:
- The direction of the FIRST stroke determines which terrain type to paint
- Left-to-right or bottom-to-top → Paint TOP/LEFT walls (GROUND_LEFT)
- Right-to-left or top-to-bottom → Paint BOTTOM/RIGHT walls (CEILING_RIGHT)

RandTiles:
- RandTiles are automatically handled by Reggie's ObjectItem.updateObjCache()
- When CreateObject() is called, the resulting ObjectItem applies randomization
- No special handling needed in this engine

Future enhancements:
- Multi-tile object support: Use larger objects (e.g., 3x1 platforms) when painting
  long horizontal/vertical lines instead of repeating 1x1 tiles
"""
from typing import List, Tuple, Dict, Optional, Set, Callable
from enum import Enum
from dataclasses import dataclass, field
import math

from .brush import SmartBrush
from .painter import QuickPainter, PaintOperation, DrawMode
from .modes import SmartPaintMode, PaintingDirection
from .logging import log_engine


class PaintingMode(Enum):
    """Painting mode enumeration"""
    IMMEDIATE = "immediate"  # Paint immediately as mouse moves (holding paint key)
    DEFERRED = "deferred"    # Show outline, paint on click (not holding paint key)


class PaintingState(Enum):
    """Painting state enumeration"""
    IDLE = "idle"                    # Not painting
    WAITING_FOR_START = "waiting"    # Waiting for start object selection
    PAINTING_IMMEDIATE = "immediate" # Actively painting (immediate mode)
    PAINTING_DEFERRED = "deferred"   # Showing outline (deferred mode)


@dataclass
class ObjectPlacement:
    """Represents a single object placement in the level"""
    tileset: int
    object_id: int
    layer: int
    x: int
    y: int
    width: int = 1
    height: int = 1
    
    def __hash__(self):
        return hash((self.tileset, self.object_id, self.layer, self.x, self.y))
    
    def __eq__(self, other):
        if not isinstance(other, ObjectPlacement):
            return False
        return (self.tileset == other.tileset and 
                self.object_id == other.object_id and
                self.layer == other.layer and
                self.x == other.x and self.y == other.y)


@dataclass
class PaintingSession:
    """Tracks the current painting session state"""
    start_pos: Optional[Tuple[int, int]] = None
    current_pos: Optional[Tuple[int, int]] = None
    last_pos: Optional[Tuple[int, int]] = None
    stroke_path: List[Tuple[int, int]] = field(default_factory=list)
    pending_placements: List[ObjectPlacement] = field(default_factory=list)
    outline_positions: List[Tuple[int, int]] = field(default_factory=list)
    existing_tiles: Dict[Tuple[int, int, int], int] = field(default_factory=dict)
    placed_tiles: Set[Tuple[int, int, int]] = field(default_factory=set)
    
    # Direction tracking - determined by first stroke movement
    initial_direction: Optional[str] = None  # 'left_to_right', 'right_to_left', etc.
    painting_direction: PaintingDirection = field(default=PaintingDirection.AUTO)
    direction_locked: bool = False  # True once direction is determined
    
    # Tile type mapping for outline positions
    outline_tile_types: Dict[Tuple[int, int], str] = field(default_factory=dict)
    
    # Path dampening - tracks consecutive moves in same direction
    consecutive_direction_count: int = 0
    last_move_direction: Optional[str] = None  # 'horizontal' or 'vertical'
    pending_turn_count: int = 0  # Count of consecutive attempts to turn (for dampening)
    
    # Committed slope segments - list of (slope_type, origin_x, origin_y, covered_positions)
    committed_slopes: List = field(default_factory=list)
    # Index in stroke_path where uncommitted segment starts
    uncommitted_start_idx: int = 0
    
    # Slope mode - toggled with F1 key
    slope_mode: bool = False
    # Anchor position for slope mode (last committed tile position)
    slope_anchor: Optional[Tuple[int, int]] = None
    # Currently previewed slope (slope_type, origin_x, origin_y)
    preview_slope: Optional[Tuple[str, int, int]] = None
    # Path length when entering slope mode (to truncate on exit)
    slope_mode_path_length: int = 0
    # Allowed exit direction after slope ('left_to_right' or 'right_to_left')
    # None means no restriction
    slope_exit_direction: Optional[str] = None
    # Current direction at slope anchor (for determining top vs bottom slopes)
    # This is calculated from the last few moves when entering slope mode
    slope_current_direction: Optional[str] = None
    
    def reset(self):
        """Reset the session state"""
        self.start_pos = None
        self.current_pos = None
        self.last_pos = None
        self.stroke_path = []
        self.pending_placements = []
        self.outline_positions = []
        self.outline_tile_types = {}
        self.placed_tiles = set()
        self.initial_direction = None
        self.painting_direction = PaintingDirection.AUTO
        self.direction_locked = False
        self.consecutive_direction_count = 0
        self.last_move_direction = None
        self.pending_turn_count = 0
        self.committed_slopes = []
        self.uncommitted_start_idx = 0
        self.slope_mode = False
        self.slope_anchor = None
        self.preview_slope = None
        self.slope_mode_path_length = 0
        self.slope_exit_direction = None
        self.slope_current_direction = None
        # Note: existing_tiles is NOT reset - it persists across sessions


class PaintingEngine:
    """
    Core painting engine that manages painting operations.
    
    Supports two painting modes:
    1. Immediate Mode: Paint tiles as the mouse moves while holding the paint key
    2. Deferred Mode: Show outline preview, finalize on click
    
    Features:
    - Bresenham interpolation for smooth strokes without gaps
    - 8-neighbor auto-tiling for intelligent tile selection
    - Support for slopes (always placed full-size)
    - RandTiles support for varied terrain
    - Multi-tile object handling
    """
    
    def __init__(self):
        """Initialize the painting engine"""
        self.state = PaintingState.IDLE
        self.mode = PaintingMode.DEFERRED
        self.session = PaintingSession()
        
        # Current brush and layer
        self.brush: Optional[SmartBrush] = None
        self.tileset_idx: int = 0
        self.layer: int = 1  # Default to layer 1
        
        # Callbacks for integration with Reggie
        self.on_place_object: Optional[Callable[[ObjectPlacement], None]] = None
        self.on_outline_updated: Optional[Callable[[List[Tuple[int, int]]], None]] = None
        self.on_painting_finished: Optional[Callable[[List[ObjectPlacement]], None]] = None
        
        # Object search database for fast lookups
        self._object_database: Dict[Tuple[int, int, int], int] = {}
        
        # Path dampening settings
        # Higher values = more resistance to direction changes
        # 0 = no dampening, 3 = require 3 consecutive moves before changing direction
        self.dampening_factor: int = 3
    
    def set_brush(self, brush: SmartBrush):
        """Set the current brush"""
        self.brush = brush
        if brush:
            self.tileset_idx = {"Pa0": 0, "Pa1": 1, "Pa2": 2, "Pa3": 3}.get(brush.slot, 0)
            print(f"[PaintingEngine] Brush set: {brush.name}, tileset_idx={self.tileset_idx}")
            print(f"[PaintingEngine] Brush terrain: {brush.terrain}")
            print(f"[PaintingEngine] Brush terrain_assigned: {brush.terrain_assigned}")
    
    def set_layer(self, layer: int):
        """Set the current layer (0, 1, or 2)"""
        self.layer = max(0, min(2, layer))
    
    def set_mode(self, mode: PaintingMode):
        """Set the painting mode"""
        self.mode = mode
    
    def set_immediate_mode(self, immediate: bool):
        """Convenience method to set immediate or deferred mode"""
        self.mode = PaintingMode.IMMEDIATE if immediate else PaintingMode.DEFERRED
    
    def set_dampening_factor(self, factor: int):
        """
        Set the path dampening factor.
        
        Higher values = more resistance to direction changes.
        0 = no dampening (raw input)
        1-3 = light to heavy dampening
        
        Args:
            factor: Dampening factor (0-5 recommended)
        """
        self.dampening_factor = max(0, min(5, factor))
    
    def toggle_slope_mode(self) -> bool:
        """
        Toggle slope mode on/off (triggered by Shift key).
        
        When entering slope mode:
        - Commits the current path as regular terrain
        - Sets the anchor position to the last tile in the path
        - Enables slope preview based on mouse position
        
        When exiting slope mode:
        - Clears the slope preview
        - Returns to normal painting mode
        
        Returns:
            True if now in slope mode, False if exited slope mode
        """
        if not self.session.slope_mode:
            # Entering slope mode
            log_engine("Entering slope mode")
            
            # Commit current path as regular terrain first
            if self.session.stroke_path:
                # The anchor is the last position in the current path
                self.session.slope_anchor = self.session.stroke_path[-1]
                log_engine(f"Slope anchor set to {self.session.slope_anchor}")
                
                # Store the path length at entry - we'll truncate to this when exiting
                self.session.slope_mode_path_length = len(self.session.stroke_path)
                
                # Calculate current direction from the last move in the path
                # This determines whether we use top or bottom slopes
                if len(self.session.stroke_path) >= 2:
                    prev = self.session.stroke_path[-2]
                    curr = self.session.stroke_path[-1]
                    dx = curr[0] - prev[0]
                    dy = curr[1] - prev[1]
                    
                    if dx > 0:
                        self.session.slope_current_direction = 'left_to_right'
                    elif dx < 0:
                        self.session.slope_current_direction = 'right_to_left'
                    elif dy > 0:
                        self.session.slope_current_direction = 'top_to_bottom'
                    elif dy < 0:
                        self.session.slope_current_direction = 'bottom_to_top'
                    else:
                        self.session.slope_current_direction = self.session.initial_direction
                    
                    log_engine(f"Slope current direction: {self.session.slope_current_direction} (from last move dx={dx}, dy={dy})")
                else:
                    # Fall back to initial direction if path is too short
                    self.session.slope_current_direction = self.session.initial_direction
                    log_engine(f"Slope current direction: {self.session.slope_current_direction} (from initial)")
            
            self.session.slope_mode = True
            self.session.preview_slope = None
            
            # Update outline to show current state (no slope preview yet)
            self._update_outline()
            
            return True
        else:
            # Exiting slope mode
            log_engine("Exiting slope mode")
            
            # Determine exit direction based on last committed slope
            # Top slopes go RIGHT, so terrain must continue RIGHT (left_to_right)
            # Bottom slopes go LEFT, so terrain must continue LEFT (right_to_left)
            exit_direction = None
            if self.session.committed_slopes:
                last_slope_type = self.session.committed_slopes[-1][0]
                if 'top' in last_slope_type:
                    exit_direction = 'left_to_right'
                else:
                    exit_direction = 'right_to_left'
                log_engine(f"Slope exit direction set to {exit_direction} based on {last_slope_type}")
            
            self.session.slope_exit_direction = exit_direction
            
            # Reset stroke_path to continue from the final slope anchor
            # This prevents the accumulated mouse movements from creating staircases
            if self.session.slope_anchor:
                # Truncate path to what it was when entering slope mode
                if hasattr(self.session, 'slope_mode_path_length'):
                    self.session.stroke_path = self.session.stroke_path[:self.session.slope_mode_path_length]
                
                # Add the new anchor position as the continuation point
                self.session.stroke_path.append(self.session.slope_anchor)
                log_engine(f"Reset stroke_path to end at slope anchor {self.session.slope_anchor}, path_len={len(self.session.stroke_path)}")
            
            self.session.slope_mode = False
            self.session.slope_anchor = None
            self.session.preview_slope = None
            
            # Update outline to remove slope preview
            self._update_outline()
            
            return False
    
    def update_slope_preview(self, mouse_pos: Tuple[int, int]):
        """
        Update the slope preview based on mouse position relative to anchor.
        
        Called when in slope mode and mouse moves.
        Determines the best-fit slope based on angle, distance, and current mode.
        
        Slopes are ALWAYS horizontal objects:
        - LTR mode (left_to_right) → "top" slopes (ground)
        - RTL mode (right_to_left) → "bottom" slopes (ceiling)
        
        If in vertical mode (TTB/BTT), we need to break out with a corner first.
        
        Args:
            mouse_pos: Current mouse position in tile coordinates
        """
        if not self.session.slope_mode or not self.session.slope_anchor:
            return
        
        anchor_x, anchor_y = self.session.slope_anchor
        mouse_x, mouse_y = mouse_pos
        
        dx = mouse_x - anchor_x
        dy = mouse_y - anchor_y
        
        if dx == 0 and dy == 0:
            # Mouse at anchor - no slope preview
            self.session.preview_slope = None
            self._update_outline()
            return
        
        # Use current direction at slope anchor, not initial direction
        # This allows slopes to change from top to bottom after 90° turns
        current_dir = self.session.slope_current_direction or self.session.initial_direction
        
        # Slopes only work in horizontal mode
        # LTR → top slopes (can only go RIGHT, dx > 0)
        # RTL → bottom slopes (can only go LEFT, dx < 0)
        if current_dir == 'left_to_right':
            slope_category = 'top'
            # Top slopes can ONLY go to the right
            if dx <= 0:
                log_engine(f"Slope preview blocked: top slopes can only go RIGHT (dx={dx})")
                self.session.preview_slope = None
                self._update_outline()
                return
        elif current_dir == 'right_to_left':
            slope_category = 'bottom'
            # Bottom slopes can ONLY go to the left
            if dx >= 0:
                log_engine(f"Slope preview blocked: bottom slopes can only go LEFT (dx={dx})")
                self.session.preview_slope = None
                self._update_outline()
                return
        else:
            # Vertical mode (TTB/BTT) - need to break out with corner first
            # TODO: Implement corner + slope for breaking out of walls
            log_engine(f"Slope preview blocked: in vertical mode ({initial_dir})")
            self.session.preview_slope = None
            self._update_outline()
            return
        
        # Calculate angle from horizontal
        import math
        abs_dx = abs(dx)
        abs_dy = abs(dy)
        
        if abs_dx == 0:
            angle = 90.0
        else:
            angle = math.degrees(math.atan2(abs_dy, abs_dx))
        
        # Determine slope size based on angle
        # 45°+ = 1x1 (steep)
        # 20-45° = 2x1 (medium)
        # <20° = 4x1 (gentle)
        if angle >= 45:
            size = '1x1'
            width = 1
        elif angle >= 20:
            size = '2x1'
            width = 2
        else:
            size = '4x1'
            width = 4
        
        # Determine left/right based on vertical direction (up or down from horizontal)
        # With direction restrictions:
        # - Top slopes (dx > 0): up (dy < 0) → left (ascending), down (dy > 0) → right (descending)
        # - Bottom slopes (dx < 0): up (dy < 0) → left (ascending), down (dy > 0) → right (descending)
        #   NOTE: Bottom slopes have L/R SWAPPED compared to top slopes!
        
        if slope_category == 'top':
            # Top slopes go RIGHT (dx > 0)
            side = 'left' if dy < 0 else 'right'
            origin_x = anchor_x + 1  # Start after anchor
            # Y position: ascending (left) starts higher, descending (right) at anchor level
            origin_y = anchor_y - 1 if side == 'left' else anchor_y
        else:
            # Bottom slopes go LEFT (dx < 0)
            # L/R is SWAPPED for bottom slopes!
            side = 'left' if dy < 0 else 'right'
            origin_x = anchor_x - width  # End at anchor
            # Y position: ascending (left) starts higher, descending (right) at anchor level
            origin_y = anchor_y - 1 if side == 'left' else anchor_y
        
        slope_type = f"slope_{slope_category}_{size}_{side}"
        
        self.session.preview_slope = (slope_type, origin_x, origin_y)
        log_engine(f"Slope preview: {slope_type} at ({origin_x}, {origin_y}), angle={angle:.1f}°, dx={dx}, dy={dy}")
        
        self._update_outline()
    
    def commit_slope(self) -> bool:
        """
        Commit the currently previewed slope (triggered by right-click in slope mode).
        
        Returns:
            True if a slope was committed, False otherwise
        """
        if not self.session.slope_mode or not self.session.preview_slope:
            return False
        
        slope_type, origin_x, origin_y = self.session.preview_slope
        
        # Add to committed slopes
        # For now, covered_positions is empty since we're using explicit placement
        covered_positions = set()
        slope_info = (slope_type, origin_x, origin_y, covered_positions)
        self.session.committed_slopes.append(slope_info)
        
        log_engine(f"COMMITTED slope: {slope_type} at ({origin_x}, {origin_y})")
        
        # Update anchor to the end of the slope for next slope
        # The new anchor is at the far end of the slope
        # Parse slope dimensions from type
        if '4x1' in slope_type:
            width = 4
        elif '2x1' in slope_type:
            width = 2
        else:
            width = 1
        
        # Determine new anchor based on slope direction
        # The anchor should be at the LAST tile of the slope (not one past it)
        # because update_slope_preview adds +1 to get the next slope's origin
        # 
        # IMPORTANT: Terrain must connect to the ELEVATED part of the slope!
        # - Top slopes: ascending (left) ends HIGH, descending (right) ends LOW
        # - Bottom slopes: ascending (left) ends HIGH, descending (right) ends LOW
        #
        # For top slopes going RIGHT:
        #   - _left (ascending): exit at TOP-RIGHT of slope (origin_y, origin_x + width - 1)
        #   - _right (descending): exit at BOTTOM-RIGHT of slope (origin_y + 1, origin_x + width - 1)
        #
        # For bottom slopes going LEFT:
        #   - _left (ascending): exit at TOP-LEFT of slope (origin_y, origin_x)
        #   - _right (descending): exit at BOTTOM-LEFT of slope (origin_y + 1, origin_x)
        
        if 'top' in slope_type:
            # Top slopes go RIGHT - anchor at right edge
            new_anchor_x = origin_x + width - 1
            if 'left' in slope_type:
                # Ascending slope - ends at TOP (elevated part on right)
                new_anchor_y = origin_y
            else:
                # Descending slope - ends at BOTTOM (base on right)
                new_anchor_y = origin_y + 1
        else:
            # Bottom slopes go LEFT - anchor at left edge
            new_anchor_x = origin_x
            if 'left' in slope_type:
                # Ascending slope - ends at TOP (elevated part on left)
                new_anchor_y = origin_y
            else:
                # Descending slope - ends at BOTTOM (base on left)
                new_anchor_y = origin_y + 1
        
        self.session.slope_anchor = (new_anchor_x, new_anchor_y)
        self.session.preview_slope = None
        
        log_engine(f"New slope anchor: {self.session.slope_anchor}")
        
        self._update_outline()
        return True
    
    def update_object_database(self, database: Dict[Tuple[int, int, int], int]):
        """
        Update the object search database for fast tile lookups.
        
        Args:
            database: Dict mapping (x, y, layer) -> object_id
        """
        self._object_database = database
        self.session.existing_tiles = database.copy()
    
    def add_to_object_database(self, x: int, y: int, layer: int, object_id: int):
        """Add a single object to the database"""
        self._object_database[(x, y, layer)] = object_id
        self.session.existing_tiles[(x, y, layer)] = object_id
    
    def remove_from_object_database(self, x: int, y: int, layer: int):
        """Remove an object from the database"""
        key = (x, y, layer)
        self._object_database.pop(key, None)
        self.session.existing_tiles.pop(key, None)
    
    # =========================================================================
    # PAINTING OPERATIONS
    # =========================================================================
    
    def start_painting(self, pos: Tuple[int, int]) -> bool:
        """
        Start a painting operation at the given position.
        
        Args:
            pos: Starting position (x, y) in tile coordinates
        
        Returns:
            True if painting started successfully
        """
        if not self.brush:
            print("[PaintingEngine] No brush set, cannot start painting")
            return False
        
        print(f"[PaintingEngine] Starting painting at {pos}, mode={self.mode.value}")
        
        self.session.reset()
        self.session.start_pos = pos
        self.session.current_pos = pos
        self.session.last_pos = pos
        self.session.stroke_path = [pos]
        self.session.existing_tiles = self._object_database.copy()
        
        if self.mode == PaintingMode.IMMEDIATE:
            self.state = PaintingState.PAINTING_IMMEDIATE
            # Paint the first tile immediately
            self._paint_tile_at(pos)
        else:
            self.state = PaintingState.PAINTING_DEFERRED
            # Just update the outline
            self._update_outline()
        
        return True
    
    def update_painting(self, pos: Tuple[int, int]) -> bool:
        """
        Update the painting operation as the mouse moves.
        
        On the FIRST movement, determines the painting direction based on
        the direction of the stroke (left-to-right, top-to-bottom, etc.).
        
        Applies path dampening to reduce accidental direction changes.
        
        Args:
            pos: Current position (x, y) in tile coordinates
        
        Returns:
            True if update was processed
        """
        if self.state == PaintingState.IDLE:
            return False
        
        if not self.brush:
            return False
        
        # Skip if position hasn't changed
        if pos == self.session.current_pos:
            return True
        
        self.session.last_pos = self.session.current_pos
        self.session.current_pos = pos
        
        # Determine painting direction on FIRST movement
        if not self.session.direction_locked and self.session.start_pos:
            self._determine_painting_direction(self.session.start_pos, pos)
        
        # Build valid path from current stroke end to target position
        # This enforces all path invariants: 4-connectivity, no self-intersection,
        # no backtracking, and dampening as minimum run length
        if self.session.last_pos:
            # If target is same as last stroke point, nothing to do
            if self.session.stroke_path and pos == self.session.stroke_path[-1]:
                return True
            
            # Build path with all invariants enforced
            new_points = self._build_valid_path(pos)
            
            # Add all new points to stroke path
            for point in new_points:
                self.session.stroke_path.append(point)
            
        
        if self.state == PaintingState.PAINTING_IMMEDIATE:
            # Paint tiles along the interpolated path
            self._paint_interpolated_path()
        else:
            # Update the outline preview
            self._update_outline()
        
        return True
    
    def _build_valid_path(self, target: Tuple[int, int]) -> List[Tuple[int, int]]:
        """
        Build a valid path from the current stroke end to the target position.
        
        Enforces clean path invariants:
        1. 4-connectivity: Each tile is cardinally adjacent to the previous
        2. No self-intersection: Path cannot revisit any tile
        3. No backtracking: Cannot return to the tile we just came from
        4. Dampening: Track mouse direction attempts, require N attempts before allowing turn
        
        This makes lonely tiles, diagonal jumps, and blobs structurally impossible.
        
        Args:
            target: Target position to reach
        
        Returns:
            List of valid path points to add (may be empty if blocked)
        """
        if not self.session.stroke_path:
            return [target]
        
        path_set = set(self.session.stroke_path)
        current = self.session.stroke_path[-1]
        
        # Get the "previous" tile to prevent immediate backtracking
        prev_tile = self.session.stroke_path[-2] if len(self.session.stroke_path) >= 2 else None
        
        # Determine what direction the mouse is trying to go (based on target)
        dx = target[0] - current[0]
        dy = target[1] - current[1]
        
        if dx == 0 and dy == 0:
            return []  # Already at target
        
        # SLOPE EXIT DIRECTION ENFORCEMENT
        # After exiting slope mode, terrain can ONLY continue in the valid direction
        # Top slopes exit RIGHT (left_to_right), Bottom slopes exit LEFT (right_to_left)
        if self.session.slope_exit_direction:
            if self.session.slope_exit_direction == 'left_to_right':
                # Can only go RIGHT (dx > 0) - block left, up, down
                if dx <= 0:
                    log_engine(f"Slope exit blocked: must go RIGHT (dx={dx})")
                    return []
            elif self.session.slope_exit_direction == 'right_to_left':
                # Can only go LEFT (dx < 0) - block right, up, down
                if dx >= 0:
                    log_engine(f"Slope exit blocked: must go LEFT (dx={dx})")
                    return []
            # Clear the restriction after first valid move
            self.session.slope_exit_direction = None
        
        # Determine mouse's intended direction
        if abs(dx) >= abs(dy):
            mouse_direction = 'horizontal'
        else:
            mouse_direction = 'vertical'
        
        # Handle dampening: track direction change attempts
        direction_locked = False
        if self.dampening_factor > 0 and self.session.last_move_direction is not None:
            if mouse_direction != self.session.last_move_direction:
                # Mouse wants to turn - increment pending turn count
                self.session.pending_turn_count += 1
                
                if self.session.pending_turn_count < self.dampening_factor:
                    # Not enough turn attempts yet - lock to current direction
                    direction_locked = True
                else:
                    # Enough turn attempts - allow the turn, reset counter
                    self.session.pending_turn_count = 0
            else:
                # Mouse continuing in same direction - reset pending turn count
                self.session.pending_turn_count = 0
        
        result = []
        
        # Walk toward target one cardinal step at a time
        while current != target:
            dx = target[0] - current[0]
            dy = target[1] - current[1]
            
            if dx == 0 and dy == 0:
                break
            
            # Build candidate moves based on allowed direction
            # IMPORTANT: Only add moves in the allowed direction when dampening is active
            candidates = []
            
            if direction_locked:
                # Dampening is restricting us - only allow moves in current direction
                if self.session.last_move_direction == 'horizontal':
                    if dx > 0:
                        candidates.append((1, 0, 'horizontal'))
                    elif dx < 0:
                        candidates.append((-1, 0, 'horizontal'))
                    else:
                        # Can't make progress in locked direction - stop
                        break
                else:
                    if dy > 0:
                        candidates.append((0, 1, 'vertical'))
                    elif dy < 0:
                        candidates.append((0, -1, 'vertical'))
                    else:
                        # Can't make progress in locked direction - stop
                        break
            elif mouse_direction == 'horizontal':
                # Prefer horizontal movement
                if dx > 0:
                    candidates.append((1, 0, 'horizontal'))
                elif dx < 0:
                    candidates.append((-1, 0, 'horizontal'))
                # Add vertical as fallback if horizontal is blocked
                if dy > 0:
                    candidates.append((0, 1, 'vertical'))
                elif dy < 0:
                    candidates.append((0, -1, 'vertical'))
            else:
                # Prefer vertical movement
                if dy > 0:
                    candidates.append((0, 1, 'vertical'))
                elif dy < 0:
                    candidates.append((0, -1, 'vertical'))
                # Add horizontal as fallback if vertical is blocked
                if dx > 0:
                    candidates.append((1, 0, 'horizontal'))
                elif dx < 0:
                    candidates.append((-1, 0, 'horizontal'))
            
            # If no candidates, stop
            if not candidates:
                break
            
            # Try each candidate move
            moved = False
            for move_dx, move_dy, direction in candidates:
                next_pos = (current[0] + move_dx, current[1] + move_dy)
                
                # Check invariants
                if next_pos in path_set:
                    continue  # No self-intersection
                if next_pos == prev_tile:
                    continue  # No backtracking
                
                # Update direction tracking
                if self.session.last_move_direction is None:
                    self.session.last_move_direction = direction
                    self.session.consecutive_direction_count = 1
                elif direction == self.session.last_move_direction:
                    self.session.consecutive_direction_count += 1
                else:
                    # Direction changed in path
                    self.session.last_move_direction = direction
                    self.session.consecutive_direction_count = 1
                
                # Accept this move
                result.append(next_pos)
                path_set.add(next_pos)
                prev_tile = current
                current = next_pos
                moved = True
                break
            
            if not moved:
                # No valid move found - path is blocked
                break
        
        return result
    
    def _determine_painting_direction(self, start_pos: Tuple[int, int], curr_pos: Tuple[int, int]):
        """
        Determine the painting direction based on the first stroke movement.
        
        Direction mapping:
        - Left-to-right → GROUND_LEFT (paint top/left walls)
        - Right-to-left → CEILING_RIGHT (paint bottom/right walls)
        - Top-to-bottom → CEILING_RIGHT (paint bottom/right walls)
        - Bottom-to-top → GROUND_LEFT (paint top/left walls)
        
        Args:
            start_pos: Starting position
            curr_pos: Current position
        """
        # Use SmartPaintMode's direction detection
        initial_dir = SmartPaintMode.determine_initial_direction(start_pos, curr_pos)
        painting_dir = SmartPaintMode.get_default_painting_direction(initial_dir)
        
        self.session.initial_direction = initial_dir
        self.session.painting_direction = painting_dir
        self.session.direction_locked = True
        
        print(f"[PaintingEngine] Direction determined: {initial_dir} → {painting_dir.value}")
    
    def finish_painting(self, pos: Optional[Tuple[int, int]] = None) -> List[ObjectPlacement]:
        """
        Finish the painting operation.
        
        Args:
            pos: Final position (optional, uses current if not provided)
        
        Returns:
            List of ObjectPlacement objects that were placed
        """
        if self.state == PaintingState.IDLE:
            return []
        
        if pos:
            self.update_painting(pos)
        
        placements = []
        
        if self.state == PaintingState.PAINTING_DEFERRED:
            # Finalize deferred painting - place all pending tiles
            placements = self._finalize_deferred_painting()
        else:
            # Immediate mode - tiles already placed, just return what was placed
            placements = self.session.pending_placements.copy()
        
        print(f"[PaintingEngine] Finished painting, {len(placements)} objects placed")
        
        # Calculate terrain-aware modifications (self-connection check)
        # This is done immediately for self-connection
        terrain_mods, terrain_deletes = self.get_terrain_aware_modifications()
        if terrain_mods:
            placements.extend(terrain_mods)
            print(f"[PaintingEngine] Terrain-aware: {len(terrain_mods)} modifications added")
        
        # Store deletions for delayed application (100ms delay)
        self._pending_terrain_deletes = terrain_deletes
        
        # Notify callback
        if self.on_painting_finished:
            self.on_painting_finished(placements)
        
        self.state = PaintingState.IDLE
        return placements
    
    def get_pending_terrain_deletes(self) -> List[Tuple[int, int, int]]:
        """
        Get pending terrain deletions from terrain-aware brush.
        These should be applied after a short delay (100ms) for visual distinction.
        
        Returns:
            List of (x, y, layer) tuples to delete
        """
        return getattr(self, '_pending_terrain_deletes', [])
    
    def cancel_painting(self):
        """Cancel the current painting operation"""
        print("[PaintingEngine] Painting cancelled")
        self.state = PaintingState.IDLE
        self.session.reset()
        
        # Clear outline
        if self.on_outline_updated:
            self.on_outline_updated([])
    
    # =========================================================================
    # INTERNAL PAINTING METHODS
    # =========================================================================
    
    def _paint_tile_at(self, pos: Tuple[int, int]):
        """
        Paint a single tile at the given position using direction-aware auto-tiling.
        
        Uses the painting direction (determined by first stroke) to select
        appropriate terrain tiles (top/left vs bottom/right walls).
        
        Args:
            pos: Position (x, y) in tile coordinates
        """
        x, y = pos
        
        # Skip if already placed in this session
        if (x, y, self.layer) in self.session.placed_tiles:
            return
        
        # Get neighbors for context
        neighbors = QuickPainter.get_neighbors(x, y, self.layer, self.session.existing_tiles)
        has_neighbor_above = neighbors.get('top', False)
        has_neighbor_below = neighbors.get('bottom', False)
        
        # Determine tile type using 8-neighbor auto-tiling
        tile_type = QuickPainter.calculate_auto_tile_type(neighbors)
        
        # Filter based on painting direction
        if not SmartPaintMode.should_paint_terrain(
            tile_type, self.session.painting_direction,
            has_neighbor_above, has_neighbor_below
        ):
            # This terrain position shouldn't be painted based on direction
            # Still mark as placed to avoid re-checking
            self.session.placed_tiles.add((x, y, self.layer))
            return
        
        # Get tile ID from brush
        tile_id = self.brush.get_terrain_tile(tile_type)
        
        if tile_id is None:
            # No tile assigned for this terrain type
            self.session.placed_tiles.add((x, y, self.layer))
            return
        
        # Create placement
        placement = ObjectPlacement(
            tileset=self.tileset_idx,
            object_id=tile_id,
            layer=self.layer,
            x=x,
            y=y,
            width=1,
            height=1
        )
        
        # Track placement
        self.session.pending_placements.append(placement)
        self.session.placed_tiles.add((x, y, self.layer))
        self.session.existing_tiles[(x, y, self.layer)] = tile_id
        
        # In immediate mode, place the object right away
        if self.state == PaintingState.PAINTING_IMMEDIATE and self.on_place_object:
            self.on_place_object(placement)
        
        # Update neighbors that may need to change
        self._update_neighbor_tiles(x, y)
    
    def _paint_interpolated_path(self):
        """Paint tiles along the interpolated stroke path"""
        if not self.session.last_pos or not self.session.current_pos:
            return
        
        # Get interpolated points
        points = QuickPainter.bresenham_line(
            self.session.last_pos[0], self.session.last_pos[1],
            self.session.current_pos[0], self.session.current_pos[1]
        )
        
        # Paint each point (skip first as it was already painted)
        for point in points[1:]:
            self._paint_tile_at(point)
    
    def _update_neighbor_tiles(self, x: int, y: int):
        """
        Update neighboring tiles that may need to change due to new tile placement.
        
        Args:
            x, y: Position of the newly placed tile
        """
        # Check all 8 neighbors
        neighbors = [
            (x-1, y-1), (x, y-1), (x+1, y-1),
            (x-1, y),            (x+1, y),
            (x-1, y+1), (x, y+1), (x+1, y+1)
        ]
        
        for nx, ny in neighbors:
            key = (nx, ny, self.layer)
            
            # Only update if there's an existing tile at this position
            if key in self.session.existing_tiles:
                # Recalculate the tile type
                new_tile_id = QuickPainter.auto_tile_8neighbor(
                    nx, ny, self.layer, self.brush, self.session.existing_tiles
                )
                
                if new_tile_id is not None and new_tile_id != self.session.existing_tiles[key]:
                    # Tile needs to be updated
                    self.session.existing_tiles[key] = new_tile_id
                    
                    # In immediate mode, we'd need to update the existing object
                    # This is handled by the integration layer
    
    def _update_outline(self):
        """
        Update the outline preview for deferred mode using 8-neighbor corner detection
        and slope detection.
        
        The system works as follows:
        1. Initial tile type is based on stroke direction (top/bottom/left/right)
        2. Analyze path segments for slope detection (diagonal movement)
        3. When stroke turns 90°, place appropriate corner tile OR slope
        4. After corner/slope, continue with the new edge type
        
        Corner types:
        - Outer corners (convex): top_left, top_right, bottom_left, bottom_right
        - Inner corners (concave): inner_top_left, inner_top_right, inner_bottom_left, inner_bottom_right
        
        Slope types (when diagonal movement detected):
        - slope_top_*: Ground-level slopes
        - slope_bottom_*: Ceiling-level slopes
        """
        log_engine(f"_update_outline: path_len={len(self.session.stroke_path)}, initial_dir={self.session.initial_direction}, slope_mode={self.session.slope_mode}")
        
        if not self.session.start_pos or len(self.session.stroke_path) == 0:
            return
        
        # Slope detection is now DISABLED in normal mode
        # Slopes are only added via slope mode (F1 toggle)
        slope_segments = []
        
        # Add committed slopes
        slope_segments.extend(self.session.committed_slopes)
        log_engine(f"_update_outline: {len(self.session.committed_slopes)} committed slopes")
        
        # Add preview slope if in slope mode
        if self.session.slope_mode:
            log_engine(f"_update_outline: in slope mode, preview_slope={self.session.preview_slope}, anchor={self.session.slope_anchor}")
            if self.session.preview_slope:
                slope_type, origin_x, origin_y = self.session.preview_slope
                # Preview slope has empty covered_positions
                slope_segments.append((slope_type, origin_x, origin_y, set()))
                log_engine(f"_update_outline: added preview slope {slope_type} at ({origin_x}, {origin_y})")
        
        outline = []
        outline_tile_types = {}
        
        # Determine initial edge type based on stroke direction
        initial_dir = self.session.initial_direction
        if initial_dir == 'left_to_right':
            current_edge = 'top'
        elif initial_dir == 'right_to_left':
            current_edge = 'bottom'
        elif initial_dir == 'bottom_to_top':
            current_edge = 'left'
        elif initial_dir == 'top_to_bottom':
            current_edge = 'right'
        else:
            current_edge = 'top'
        
        # Track which direction we're currently moving
        current_move_dir = initial_dir
        
        path = self.session.stroke_path
        
        # Track positions covered by slopes (to skip them)
        # Use the path positions that the slope covers, not just the slope dimensions
        slope_covered_positions = set()
        for slope_info in slope_segments:
            slope_type, origin_x, origin_y, covered_path_positions = slope_info
            slope_covered_positions.update(covered_path_positions)
        
        if slope_covered_positions:
            log_engine(f"Slope covers {len(slope_covered_positions)} positions, path has {len(path)} positions")
        
        # If we have slopes that cover the entire path, ONLY show the slope
        if slope_segments and len(slope_covered_positions) == len(path):
            # Slope covers entire path - only show slope outline
            for slope_info in slope_segments:
                slope_type, origin_x, origin_y, covered_path_positions = slope_info
                outline.append((origin_x, origin_y))
                outline_tile_types[(origin_x, origin_y)] = slope_type
            
            self.session.outline_positions = outline
            self.session.outline_tile_types = outline_tile_types
            log_engine(f"_update_outline: slope-only mode, {len(outline)} positions")
            
            if self.on_outline_updated:
                self.on_outline_updated(outline)
            return
        
        # Add slope origins to outline (for partial slopes)
        for slope_info in slope_segments:
            slope_type, origin_x, origin_y, covered_path_positions = slope_info
            outline.append((origin_x, origin_y))
            outline_tile_types[(origin_x, origin_y)] = slope_type
        
        # Track the last non-slope position to detect slope exits
        last_non_slope_pos = None
        
        for i, pos in enumerate(path):
            x, y = pos
            
            # Skip positions covered by slopes
            if pos in slope_covered_positions:
                continue
            
            # Check if we just exited a slope (previous position was covered by slope)
            exiting_slope = False
            if i > 0 and path[i - 1] in slope_covered_positions:
                exiting_slope = True
            
            # Determine movement direction from previous to current position
            if i > 0 and not exiting_slope:
                prev_x, prev_y = path[i - 1]
                dx = x - prev_x
                dy = y - prev_y
                
                if dx > 0:
                    new_move_dir = 'left_to_right'
                elif dx < 0:
                    new_move_dir = 'right_to_left'
                elif dy > 0:
                    new_move_dir = 'top_to_bottom'
                elif dy < 0:
                    new_move_dir = 'bottom_to_top'
                else:
                    new_move_dir = current_move_dir
                
                # Check if direction changed (90° turn)
                if new_move_dir != current_move_dir:
                    # Determine corner type based on old edge and new direction
                    corner_type = self._get_corner_type(current_edge, current_move_dir, new_move_dir)
                    if corner_type:
                        # Place corner at PREVIOUS position (the turning point)
                        prev_pos = path[i - 1]
                        if prev_pos not in slope_covered_positions:
                            outline_tile_types[prev_pos] = corner_type
                    
                    # Update current edge based on new direction
                    current_edge = self._get_edge_after_turn(current_edge, current_move_dir, new_move_dir)
                    current_move_dir = new_move_dir
            elif exiting_slope:
                # After exiting a slope, continue with the same edge type
                # Don't treat the slope exit as a direction change
                # The slope handles the elevation change, terrain continues horizontally
                pass
            
            # Add current position with current edge type (may be overwritten by corner)
            if pos not in outline_tile_types:
                outline_tile_types[pos] = current_edge
            if pos not in outline:
                outline.append(pos)
        
        self.session.outline_positions = outline
        self.session.outline_tile_types = outline_tile_types
        log_engine(f"_update_outline: generated {len(outline)} positions, {len(slope_segments)} slopes")
        
        # Notify callback
        if self.on_outline_updated:
            self.on_outline_updated(outline)
    
    def _get_corner_type(self, current_edge: str, old_dir: str, new_dir: str) -> Optional[str]:
        """
        Determine the corner tile type when stroke direction changes.
        
        Based on the 8-neighbor system:
        - Outer corners: top_left, top_right, bottom_left, bottom_right
        - Inner corners: inner_top_left, inner_top_right, inner_bottom_left, inner_bottom_right
        
        Args:
            current_edge: Current edge type ('top', 'bottom', 'left', 'right')
            old_dir: Previous movement direction
            new_dir: New movement direction
        
        Returns:
            Corner tile type, or None if no corner needed
        """
        # Map: (current_edge, old_dir, new_dir) -> corner_type
        # 
        # From "top" going down:
        #   LTR -> top_to_bottom: top_right (outer), then right wall
        #   RTL -> top_to_bottom: top_left (outer), then left wall
        # From "top" going up:
        #   LTR -> bottom_to_top: inner_top_right, then left wall
        #   RTL -> bottom_to_top: inner_top_left, then right wall
        #
        # From "bottom" going down:
        #   LTR -> top_to_bottom: inner_bottom_right, then left wall
        #   RTL -> top_to_bottom: inner_bottom_left, then right wall
        # From "bottom" going up:
        #   LTR -> bottom_to_top: bottom_right (outer), then right wall
        #   RTL -> bottom_to_top: bottom_left (outer), then left wall
        #
        # From "left" to horizontal:
        #   bottom_to_top -> left_to_right: top_left (outer), then top
        #   bottom_to_top -> right_to_left: inner_bottom_right, then bottom
        #   top_to_bottom -> left_to_right: inner_top_right, then top
        #   top_to_bottom -> right_to_left: bottom_left (outer), then bottom
        #
        # From "right" to horizontal:
        #   bottom_to_top -> left_to_right: inner_bottom_left, then bottom
        #   bottom_to_top -> right_to_left: top_right (outer), then top
        #   top_to_bottom -> left_to_right: bottom_right (outer), then bottom
        #   top_to_bottom -> right_to_left: inner_top_left, then top
        
        corner_map = {
            # From top edge
            ('top', 'left_to_right', 'top_to_bottom'): 'top_right',
            ('top', 'left_to_right', 'bottom_to_top'): 'inner_top_right',
            ('top', 'right_to_left', 'top_to_bottom'): 'top_left',
            ('top', 'right_to_left', 'bottom_to_top'): 'inner_top_left',
            
            # From bottom edge
            ('bottom', 'left_to_right', 'top_to_bottom'): 'inner_bottom_right',
            ('bottom', 'left_to_right', 'bottom_to_top'): 'bottom_right',
            ('bottom', 'right_to_left', 'top_to_bottom'): 'inner_bottom_left',
            ('bottom', 'right_to_left', 'bottom_to_top'): 'bottom_left',
            
            # From left edge
            ('left', 'bottom_to_top', 'left_to_right'): 'top_left',
            ('left', 'bottom_to_top', 'right_to_left'): 'inner_bottom_right',
            ('left', 'top_to_bottom', 'left_to_right'): 'inner_top_right',
            ('left', 'top_to_bottom', 'right_to_left'): 'bottom_left',
            
            # From right edge
            ('right', 'bottom_to_top', 'left_to_right'): 'inner_bottom_left',
            ('right', 'bottom_to_top', 'right_to_left'): 'top_right',
            ('right', 'top_to_bottom', 'left_to_right'): 'inner_top_left',
            ('right', 'top_to_bottom', 'right_to_left'): 'bottom_right',
        }
        
        return corner_map.get((current_edge, old_dir, new_dir))
    
    def _get_edge_after_turn(self, current_edge: str, old_dir: str, new_dir: str) -> str:
        """
        Determine the new edge type after a 90° turn.
        
        Args:
            current_edge: Current edge type
            old_dir: Previous movement direction
            new_dir: New movement direction
        
        Returns:
            New edge type after the turn
        """
        # Map: (current_edge, old_dir, new_dir) -> new_edge
        edge_map = {
            # From top edge turning vertical
            ('top', 'left_to_right', 'top_to_bottom'): 'right',
            ('top', 'left_to_right', 'bottom_to_top'): 'left',
            ('top', 'right_to_left', 'top_to_bottom'): 'left',
            ('top', 'right_to_left', 'bottom_to_top'): 'right',
            
            # From bottom edge turning vertical
            ('bottom', 'left_to_right', 'top_to_bottom'): 'left',
            ('bottom', 'left_to_right', 'bottom_to_top'): 'right',
            ('bottom', 'right_to_left', 'top_to_bottom'): 'right',
            ('bottom', 'right_to_left', 'bottom_to_top'): 'left',
            
            # From left edge turning horizontal
            ('left', 'bottom_to_top', 'left_to_right'): 'top',
            ('left', 'bottom_to_top', 'right_to_left'): 'bottom',
            ('left', 'top_to_bottom', 'left_to_right'): 'top',
            ('left', 'top_to_bottom', 'right_to_left'): 'bottom',
            
            # From right edge turning horizontal
            ('right', 'bottom_to_top', 'left_to_right'): 'bottom',
            ('right', 'bottom_to_top', 'right_to_left'): 'top',
            ('right', 'top_to_bottom', 'left_to_right'): 'top',      # inner_top_right -> top
            ('right', 'top_to_bottom', 'right_to_left'): 'bottom',   # bottom_right -> bottom
        }
        
        return edge_map.get((current_edge, old_dir, new_dir), current_edge)
    
    def _get_slope_dimensions(self, slope_type: str) -> Tuple[int, int]:
        """Get slope dimensions (width, height) in tiles"""
        if '1x1' in slope_type:
            return (1, 2)
        elif '2x1' in slope_type:
            return (2, 2)
        elif '4x1' in slope_type:
            return (4, 2)
        return (1, 1)
    
    def _detect_slope_segments(self) -> List[Tuple[str, int, int, Set[Tuple[int, int]]]]:
        """
        Detect slope segments in the current stroke path.
        
        This method analyzes the UNCOMMITTED portion of the path and tries to
        commit slopes as fixed-size segments. Committed slopes are stored in
        session.committed_slopes and are not re-analyzed.
        
        IMPORTANT: The first tile must always be a straight edge (top/bottom/left/right)
        to establish the painting direction. Slopes are only allowed after that.
        
        Returns:
            List of (slope_type, origin_x, origin_y, covered_path_positions) tuples
            This includes both committed slopes and any pending slope for the current segment.
        """
        path = self.session.stroke_path
        
        # Start with already committed slopes
        all_slopes = list(self.session.committed_slopes)
        
        # RULE: First tile must be a straight edge to establish direction
        # Don't allow slopes until we have at least 2 tiles in the path
        # (first tile establishes direction)
        if len(path) < 2 or self.session.initial_direction is None:
            return all_slopes
        
        # Force first segment to be a straight edge before allowing slopes
        # Check if the first move was straight (not diagonal)
        if self.session.uncommitted_start_idx == 0:
            # First move determines if we can start slope detection
            first_dx = path[1][0] - path[0][0]
            first_dy = path[1][1] - path[0][1]
            
            # If first move is straight (only H or V, not both), commit it as first tile
            if first_dx == 0 or first_dy == 0:
                # First move is straight - commit it and allow slopes after
                self.session.uncommitted_start_idx = 2
                log_engine(f"First straight segment committed, uncommitted_start_idx=2")
            else:
                # First move is diagonal - don't allow slopes yet
                # Wait for a straight segment first
                return all_slopes
        
        # Get the uncommitted portion of the path
        uncommitted_path = path[self.session.uncommitted_start_idx:]
        
        if len(uncommitted_path) < 3:
            # Need at least 3 positions to form a slope (start + diagonal movement)
            return all_slopes
        
        # Analyze the uncommitted segment
        start_pos = uncommitted_path[0]
        end_pos = uncommitted_path[-1]
        
        total_dx = end_pos[0] - start_pos[0]
        total_dy = end_pos[1] - start_pos[1]
        
        # Only consider slopes if there's both horizontal and vertical movement
        if total_dx == 0 or total_dy == 0:
            # Pure horizontal or vertical movement - this is a straight segment
            # Advance uncommitted_start_idx to the end of this straight segment
            # so we don't keep re-analyzing it
            self.session.uncommitted_start_idx = len(path)
            return all_slopes
        
        # Check if the path forms a staircase pattern
        h_moves = 0
        v_moves = 0
        alternations = 0
        last_was_horizontal = None
        
        for i in range(1, len(uncommitted_path)):
            dx = uncommitted_path[i][0] - uncommitted_path[i-1][0]
            dy = uncommitted_path[i][1] - uncommitted_path[i-1][1]
            
            is_horizontal = (dx != 0)
            
            if is_horizontal:
                h_moves += 1
            else:
                v_moves += 1
            
            if last_was_horizontal is not None and is_horizontal != last_was_horizontal:
                alternations += 1
            
            last_was_horizontal = is_horizontal
        
        total_moves = h_moves + v_moves
        if total_moves < 2:
            return all_slopes
        
        alternation_ratio = alternations / (total_moves - 1) if total_moves > 1 else 0
        balance_ratio = min(h_moves, v_moves) / max(h_moves, v_moves) if max(h_moves, v_moves) > 0 else 0
        
        # Require staircase pattern
        if alternation_ratio < 0.3 or balance_ratio < 0.3:
            return all_slopes
        
        # Calculate angle from the overall displacement
        angle = math.degrees(math.atan2(abs(total_dy), abs(total_dx)))
        
        # Check if angle is in slope range (5-60 degrees from horizontal)
        if angle < 5 or angle > 60:
            return all_slopes
        
        # Determine slope size based on angle
        if angle >= 35:
            size = '1x1'
            required_width = 1
        elif angle >= 20:
            size = '2x1'
            required_width = 2
        else:
            size = '4x1'
            required_width = 4
        
        # Determine slope type based on direction
        initial_dir = self.session.initial_direction
        is_ground = initial_dir in ['left_to_right', 'right_to_left']
        
        # Determine which side is higher based on movement direction
        # "left" means higher on the left side (slope goes down to the right)
        # "right" means higher on the right side (slope goes down to the left)
        if total_dx > 0:
            # Moving right
            side = 'right' if total_dy > 0 else 'left'
        else:
            # Moving left
            side = 'left' if total_dy > 0 else 'right'
        
        slope_type = f"slope_{'top' if is_ground else 'bottom'}_{size}_{side}"
        
        # Slopes are ALWAYS horizontal objects - they connect left/right, never above/below
        # Check if the initial direction allows slopes:
        # - left_to_right or right_to_left: slopes are natural (ground/ceiling)
        # - top_to_bottom or bottom_to_top: slopes require a corner first (vertical wall)
        if initial_dir in ['top_to_bottom', 'bottom_to_top']:
            # Painting a vertical wall - slopes not allowed without corner
            # TODO: In the future, we could detect corners and allow slopes after them
            log_engine(f"Slope blocked: painting vertical wall ({initial_dir}), slopes need corner first")
            return all_slopes
        
        # Calculate slope origin from the START of the uncommitted segment
        # The origin depends on the direction of movement
        start_x, start_y = start_pos
        
        # For slopes, origin is the top-left corner of the slope footprint
        # We need to calculate this based on the direction of movement
        if total_dx > 0 and total_dy > 0:
            # Moving right and down - origin is at start
            origin_x = start_x
            origin_y = start_y
        elif total_dx > 0 and total_dy < 0:
            # Moving right and up - origin is above start
            origin_x = start_x
            origin_y = start_y + total_dy  # total_dy is negative
        elif total_dx < 0 and total_dy > 0:
            # Moving left and down - origin is to the left of start
            origin_x = start_x + total_dx  # total_dx is negative
            origin_y = start_y
        else:
            # Moving left and up - origin is to the left and above start
            origin_x = start_x + total_dx
            origin_y = start_y + total_dy
        
        # Clamp origin to the actual bounds of the uncommitted path
        min_x = min(p[0] for p in uncommitted_path)
        min_y = min(p[1] for p in uncommitted_path)
        origin_x = max(origin_x, min_x)
        origin_y = max(origin_y, min_y)
        
        # Check if the uncommitted segment is large enough to commit a slope
        path_width = abs(total_dx) + 1
        path_height = abs(total_dy) + 1
        
        # A slope requires: required_width horizontal moves + 1 vertical move
        # This means required_width + 1 + 1 = required_width + 2 positions in the path
        # (start position + required_width horizontal + 1 vertical)
        required_positions = required_width + 2  # e.g., 2x1 slope needs 4 positions
        
        # Check if we have enough moves to commit a slope
        # We need at least required_width horizontal moves and 1 vertical move
        can_commit = (h_moves >= required_width and v_moves >= 1 and 
                      len(uncommitted_path) >= required_positions)
        
        if can_commit:
            # Take the first required_positions from the uncommitted path
            # These form the slope segment
            slope_positions = uncommitted_path[:required_positions]
            
            # Calculate origin from the slope positions (top-left of bounding box)
            slope_min_x = min(p[0] for p in slope_positions)
            slope_min_y = min(p[1] for p in slope_positions)
            origin_x = slope_min_x
            origin_y = slope_min_y
            
            # The covered positions are all EXCEPT the last one
            # The last position is the connection point for the next segment
            # and should NOT be marked as covered (so terrain can connect there)
            covered_positions = set(slope_positions[:-1])
            slope_info = (slope_type, origin_x, origin_y, covered_positions)
            self.session.committed_slopes.append(slope_info)
            
            # Move uncommitted start to the LAST position of the slope
            # The last position is the connection point for the next segment
            self.session.uncommitted_start_idx += required_positions - 1
            
            all_slopes.append(slope_info)
            log_engine(f"COMMITTED slope: {slope_type} at ({origin_x}, {origin_y}), covers {len(covered_positions)} positions, last_pos={slope_positions[-1]}, uncommitted_start={self.session.uncommitted_start_idx}")
        else:
            # Show preview of pending slope (not committed yet)
            covered_positions = set(uncommitted_path)
            pending_slope = (slope_type, origin_x, origin_y, covered_positions)
            all_slopes.append(pending_slope)
            log_engine(f"Pending slope: {slope_type} at ({origin_x}, {origin_y}), h_moves={h_moves}, v_moves={v_moves}, need h={required_width}, v=1, pos={len(uncommitted_path)}/{required_positions}")
        
        return all_slopes
    
    def _finalize_deferred_painting(self) -> List[ObjectPlacement]:
        """
        Finalize deferred painting by placing all tiles in the outline.
        
        Uses the pre-calculated tile types from _update_outline.
        Merges consecutive tiles of the same type (top, bottom, left, right)
        into multi-tile objects for efficiency.
        Handles slope objects with their full dimensions.
        
        Note: Does NOT call on_place_object - the returned placements are
        passed to on_painting_finished which handles the actual placement.
        This prevents double placement.
        
        Returns:
            List of ObjectPlacement objects
        """
        placements = []
        tiles_by_pos = {}
        
        # First pass: handle slopes (they have fixed dimensions)
        for pos in self.session.outline_positions:
            x, y = pos
            
            # Skip if already placed
            if (x, y, self.layer) in self.session.placed_tiles:
                continue
            
            # Get the tile type from the stored mapping
            tile_type = self.session.outline_tile_types.get(pos, 'top')
            
            # Check if this is a slope
            if tile_type and tile_type.startswith('slope_'):
                # Get slope tile ID from brush
                tile_id = self.brush.get_slope_tile(tile_type)
                
                if tile_id is not None:
                    width, height = self._get_slope_dimensions(tile_type)
                    placement = ObjectPlacement(
                        tileset=self.tileset_idx,
                        object_id=tile_id,
                        layer=self.layer,
                        x=x,
                        y=y,
                        width=width,
                        height=height
                    )
                    placements.append(placement)
                    
                    # Mark all covered positions as placed
                    for dy in range(height):
                        for dx in range(width):
                            self.session.placed_tiles.add((x + dx, y + dy, self.layer))
            else:
                # Regular terrain tile - collect for merging
                tile_id = self.brush.get_terrain_tile(tile_type)
                
                if tile_id is not None:
                    tiles_by_pos[pos] = (tile_type, tile_id)
        
        # Merge consecutive terrain tiles into multi-tile objects
        terrain_placements = self._merge_consecutive_tiles(tiles_by_pos)
        placements.extend(terrain_placements)
        
        # Mark all terrain tiles as placed
        for placement in terrain_placements:
            for dx in range(placement.width):
                for dy in range(placement.height):
                    px, py = placement.x + dx, placement.y + dy
                    self.session.placed_tiles.add((px, py, self.layer))
                    self.session.existing_tiles[(px, py, self.layer)] = placement.object_id
        
        return placements
    
    def _merge_consecutive_tiles(self, tiles_by_pos: Dict[Tuple[int, int], Tuple[str, int]]) -> List[ObjectPlacement]:
        """
        Merge consecutive tiles of the same type into multi-tile objects.
        
        Only merges edge tiles (top, bottom, left, right) - corner tiles
        are always placed as single 1x1 objects.
        
        Args:
            tiles_by_pos: Dict mapping (x, y) -> (tile_type, tile_id)
        
        Returns:
            List of ObjectPlacement objects (some may be multi-tile)
        """
        placements = []
        processed = set()
        
        # Mergeable types and their merge directions
        # top/bottom/center merge horizontally, left/right merge vertically
        merge_directions = {
            'top': (1, 0),      # Merge horizontally (dx=1, dy=0)
            'bottom': (1, 0),   # Merge horizontally
            'left': (0, 1),     # Merge vertically (dx=0, dy=1)
            'right': (0, 1),    # Merge vertically
            'center': (1, 0),   # Merge horizontally (for blob interiors)
        }
        
        for pos, (tile_type, tile_id) in tiles_by_pos.items():
            if pos in processed:
                continue
            
            x, y = pos
            
            # Check if this tile type can be merged
            if tile_type in merge_directions:
                dx, dy = merge_directions[tile_type]
                
                # First, find the START of the run by looking backward
                start_x, start_y = x, y
                
                if dx > 0:  # Horizontal merge - look backward (decreasing x)
                    while (start_x - 1, y) in tiles_by_pos and (start_x - 1, y) not in processed:
                        prev_type, prev_id = tiles_by_pos[(start_x - 1, y)]
                        if prev_type == tile_type and prev_id == tile_id:
                            start_x -= 1
                        else:
                            break
                elif dy > 0:  # Vertical merge - look backward (decreasing y)
                    while (x, start_y - 1) in tiles_by_pos and (x, start_y - 1) not in processed:
                        prev_type, prev_id = tiles_by_pos[(x, start_y - 1)]
                        if prev_type == tile_type and prev_id == tile_id:
                            start_y -= 1
                        else:
                            break
                
                # Now find consecutive tiles from the start, going forward
                width = 1
                height = 1
                
                if dx > 0:  # Horizontal merge
                    processed.add((start_x, y))
                    nx = start_x + 1
                    while (nx, y) in tiles_by_pos and (nx, y) not in processed:
                        next_type, next_id = tiles_by_pos[(nx, y)]
                        if next_type == tile_type and next_id == tile_id:
                            width += 1
                            processed.add((nx, y))
                            nx += 1
                        else:
                            break
                    x = start_x  # Use the start position for placement
                
                elif dy > 0:  # Vertical merge
                    processed.add((x, start_y))
                    ny = start_y + 1
                    while (x, ny) in tiles_by_pos and (x, ny) not in processed:
                        next_type, next_id = tiles_by_pos[(x, ny)]
                        if next_type == tile_type and next_id == tile_id:
                            height += 1
                            processed.add((x, ny))
                            ny += 1
                        else:
                            break
                    y = start_y  # Use the start position for placement
                
                placement = ObjectPlacement(
                    tileset=self.tileset_idx,
                    object_id=tile_id,
                    layer=self.layer,
                    x=x,
                    y=y,
                    width=width,
                    height=height
                )
            else:
                # Non-mergeable tile (corners, center, etc.) - place as 1x1
                processed.add(pos)
                
                placement = ObjectPlacement(
                    tileset=self.tileset_idx,
                    object_id=tile_id,
                    layer=self.layer,
                    x=x,
                    y=y,
                    width=1,
                    height=1
                )
            
            placements.append(placement)
        
        return placements
    
    # =========================================================================
    # SLOPE PAINTING
    # =========================================================================
    
    def paint_slope(self, pos: Tuple[int, int], slope_type: str) -> Optional[ObjectPlacement]:
        """
        Paint a slope object at the given position.
        
        Slopes are always placed at full size and cannot be partial.
        
        Args:
            pos: Position (x, y) in tile coordinates (top-left of slope)
            slope_type: Slope type from brush (e.g., 'slope_top_1x1_left')
        
        Returns:
            ObjectPlacement if successful, None otherwise
        """
        if not self.brush:
            return None
        
        # Get slope object ID from brush
        slope_id = self.brush.get_slope_tile(slope_type)
        if slope_id is None:
            return None
        
        # Determine slope dimensions
        width, height = self._get_slope_dimensions(slope_type)
        
        x, y = pos
        
        # Create placement
        placement = ObjectPlacement(
            tileset=self.tileset_idx,
            object_id=slope_id,
            layer=self.layer,
            x=x,
            y=y,
            width=width,
            height=height
        )
        
        # Mark all tiles covered by the slope
        for dy in range(height):
            for dx in range(width):
                self.session.existing_tiles[(x + dx, y + dy, self.layer)] = slope_id
                self.session.placed_tiles.add((x + dx, y + dy, self.layer))
        
        # Place the object
        if self.on_place_object:
            self.on_place_object(placement)
        
        return placement
    
    def _get_slope_dimensions(self, slope_type: str) -> Tuple[int, int]:
        """
        Get the dimensions of a slope type.
        
        Args:
            slope_type: Slope type string
        
        Returns:
            (width, height) in tiles
        """
        if '1x1' in slope_type:
            return (1, 2)  # 1 wide, 2 tall (slope + base)
        elif '2x1' in slope_type:
            return (2, 2)  # 2 wide, 2 tall
        elif '4x1' in slope_type:
            return (4, 2)  # 4 wide, 2 tall
        return (1, 2)  # Default
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    def get_state(self) -> PaintingState:
        """Get the current painting state"""
        return self.state
    
    def is_painting(self) -> bool:
        """Check if currently painting"""
        return self.state != PaintingState.IDLE
    
    def get_outline(self) -> List[Tuple[int, int]]:
        """Get the current outline positions"""
        return self.session.outline_positions
    
    def get_outline_with_types(self) -> List[Tuple[int, int, str]]:
        """
        Get the current outline positions with their tile types.
        
        Returns:
            List of (x, y, tile_type) tuples where tile_type is one of:
            - Terrain: 'top', 'bottom', 'left', 'right', 'top_left', etc.
            - Slopes: 'slope_top_1x1_left', 'slope_top_2x1_right', etc.
        """
        result = []
        for pos in self.session.outline_positions:
            tile_type = self.session.outline_tile_types.get(pos, 'top')
            result.append((pos[0], pos[1], tile_type))
        return result
    
    def get_pending_placements(self) -> List[ObjectPlacement]:
        """Get the list of pending placements"""
        return self.session.pending_placements
    
    # =========================================================================
    # TERRAIN-AWARE BRUSH
    # =========================================================================
    
    def get_terrain_aware_modifications(self) -> Tuple[List[ObjectPlacement], List[Tuple[int, int, int]]]:
        """
        Calculate terrain-aware modifications after painting.
        
        This method checks:
        1. Self-connection: If first/last tiles of stroke connect within 8-neighbor,
           create missing corner tiles at the connection point.
        2. Existing terrain: Check neighboring tiles and:
           - Delete border tiles facing same way that are "outside" our terrain
           - Replace border tiles facing same way with center tiles if "inside"
           - Create corner tiles where 90° borders meet within 8-neighbor distance
        
        Returns:
            Tuple of (placements_to_add, positions_to_delete)
            - placements_to_add: New ObjectPlacement objects to create
            - positions_to_delete: (x, y, layer) tuples of tiles to remove
        """
        placements_to_add = []
        positions_to_delete = []
        
        if not self.session.outline_positions or len(self.session.outline_positions) < 2:
            return placements_to_add, positions_to_delete
        
        # Step 1: Self-connection check
        self_connection_mods = self._check_self_connection()
        placements_to_add.extend(self_connection_mods)
        
        # Step 2: Existing terrain check
        existing_mods, existing_deletes = self._check_existing_terrain()
        placements_to_add.extend(existing_mods)
        positions_to_delete.extend(existing_deletes)
        
        return placements_to_add, positions_to_delete
    
    def _check_self_connection(self) -> List[ObjectPlacement]:
        """
        Check if the first and last tiles of the stroke connect and need a corner.
        
        A corner is only needed when:
        1. First and last tiles are within 8-neighbor distance
        2. They are perpendicular edge types (e.g., 'top' and 'left')
        3. The first tile should become a corner to connect them
        
        This is specifically for closing loops - NOT for replacing all adjacent
        perpendicular tiles (those are already handled by the normal corner detection).
        
        Returns:
            List of ObjectPlacement for corner tiles to add
        """
        placements = []
        
        if len(self.session.outline_positions) < 4:
            return placements
        
        # Get first and last positions
        first_pos = self.session.outline_positions[0]
        last_pos = self.session.outline_positions[-1]
        
        first_type = self.session.outline_tile_types.get(first_pos, 'top')
        last_type = self.session.outline_tile_types.get(last_pos, 'top')
        
        # Only process edge tiles (not corners, not slopes)
        if first_type not in ['top', 'bottom', 'left', 'right']:
            return placements
        if last_type not in ['top', 'bottom', 'left', 'right']:
            return placements
        
        # Check if they're perpendicular
        if not self._are_perpendicular(first_type, last_type):
            return placements
        
        # Check if within 8-neighbor distance
        dx = abs(first_pos[0] - last_pos[0])
        dy = abs(first_pos[1] - last_pos[1])
        
        if dx > 1 or dy > 1:
            return placements  # Too far apart
        
        if dx == 0 and dy == 0:
            return placements  # Same position
        
        # Determine the corner position - where the two edges would meet
        # The corner is at the intersection of the two edge directions
        corner_pos = self._find_corner_position(first_pos, first_type, last_pos, last_type)
        
        if corner_pos is None:
            return placements
        
        # Determine corner type based on the two edge types
        corner_type = self._determine_corner_type_from_edges(first_type, last_type)
        
        if corner_type:
            x, y = corner_pos
            tile_id = self.brush.get_terrain_tile(corner_type)
            if tile_id is not None:
                placement = ObjectPlacement(
                    tileset=self.tileset_idx,
                    object_id=tile_id,
                    layer=self.layer,
                    x=x,
                    y=y,
                    width=1,
                    height=1
                )
                placements.append(placement)
                log_engine(f"Self-connection: Adding {corner_type} corner at ({x}, {y})")
        
        return placements
    
    def _find_corner_position(self, first_pos: Tuple[int, int], first_type: str,
                               last_pos: Tuple[int, int], last_type: str) -> Optional[Tuple[int, int]]:
        """
        Find the corner position where two perpendicular edges meet.
        
        The corner is at the intersection point of the two edge lines.
        For example:
        - 'top' edge at (5, 3) and 'left' edge at (4, 4) → corner at (4, 3)
        - 'top' edge at (5, 3) and 'right' edge at (6, 4) → corner at (6, 3)
        
        Args:
            first_pos: Position of first edge tile
            first_type: Type of first edge ('top', 'bottom', 'left', 'right')
            last_pos: Position of last edge tile
            last_type: Type of last edge
        
        Returns:
            (x, y) position for the corner, or None if can't determine
        """
        fx, fy = first_pos
        lx, ly = last_pos
        
        # Determine which is horizontal and which is vertical
        horizontal_types = {'top', 'bottom'}
        vertical_types = {'left', 'right'}
        
        if first_type in horizontal_types and last_type in vertical_types:
            # First is horizontal (top/bottom), last is vertical (left/right)
            # Corner x comes from vertical edge, y comes from horizontal edge
            corner_x = lx
            corner_y = fy
        elif first_type in vertical_types and last_type in horizontal_types:
            # First is vertical (left/right), last is horizontal (top/bottom)
            # Corner x comes from vertical edge, y comes from horizontal edge
            corner_x = fx
            corner_y = ly
        else:
            return None
        
        return (corner_x, corner_y)
    
    def _determine_corner_type_from_edges(self, type1: str, type2: str) -> Optional[str]:
        """
        Determine corner type from two perpendicular edge types.
        
        Args:
            type1: First edge type
            type2: Second edge type
        
        Returns:
            Corner type string ('top_left', 'top_right', etc.)
        """
        types = {type1, type2}
        
        if types == {'top', 'left'}:
            return 'top_left'
        elif types == {'top', 'right'}:
            return 'top_right'
        elif types == {'bottom', 'left'}:
            return 'bottom_left'
        elif types == {'bottom', 'right'}:
            return 'bottom_right'
        
        return None
    
    def _determine_corner_for_adjacent(self, tile_type: str, neighbor_type: str,
                                        pos: Tuple[int, int], 
                                        neighbor_pos: Tuple[int, int]) -> Optional[str]:
        """
        Determine if a tile should become a corner based on an adjacent perpendicular tile.
        
        Args:
            tile_type: Type of the tile we're checking
            neighbor_type: Type of the neighboring tile
            pos: Position of the tile we're checking
            neighbor_pos: Position of the neighbor
        
        Returns:
            Corner type string if this tile should become a corner, None otherwise
        """
        x, y = pos
        nx, ny = neighbor_pos
        
        # Determine relative position of neighbor
        dx = nx - x  # positive = neighbor is to the right
        dy = ny - y  # positive = neighbor is below
        
        # For a tile to become a corner, the neighbor must be in a position
        # that makes sense for the corner type
        
        if tile_type == 'top':
            # Top tile can become top_left or top_right
            if neighbor_type == 'left' and dx <= 0:
                # Left wall is to our left or diagonal-left → we become top_left
                return 'top_left'
            elif neighbor_type == 'right' and dx >= 0:
                # Right wall is to our right or diagonal-right → we become top_right
                return 'top_right'
        
        elif tile_type == 'bottom':
            # Bottom tile can become bottom_left or bottom_right
            if neighbor_type == 'left' and dx <= 0:
                return 'bottom_left'
            elif neighbor_type == 'right' and dx >= 0:
                return 'bottom_right'
        
        elif tile_type == 'left':
            # Left tile can become top_left or bottom_left
            if neighbor_type == 'top' and dy <= 0:
                # Top is above or diagonal-above → we become top_left
                return 'top_left'
            elif neighbor_type == 'bottom' and dy >= 0:
                return 'bottom_left'
        
        elif tile_type == 'right':
            # Right tile can become top_right or bottom_right
            if neighbor_type == 'top' and dy <= 0:
                return 'top_right'
            elif neighbor_type == 'bottom' and dy >= 0:
                return 'bottom_right'
        
        return None
    
    def _determine_corner_for_connection(self, first_type: str, last_type: str, 
                                          first_pos: Tuple[int, int], 
                                          last_pos: Tuple[int, int]) -> Optional[str]:
        """
        Determine the corner type needed to connect two edge types.
        
        Args:
            first_type: Tile type of first position in stroke
            last_type: Tile type of last position in stroke
            first_pos: (x, y) of first tile
            last_pos: (x, y) of last tile
        
        Returns:
            Corner type string, or None if no corner needed
        """
        # Only connect perpendicular edges
        horizontal_edges = {'top', 'bottom'}
        vertical_edges = {'left', 'right'}
        
        if first_type in horizontal_edges and last_type in vertical_edges:
            # First is horizontal, last is vertical
            # Corner goes at first position
            if first_type == 'top' and last_type == 'left':
                return 'top_left'
            elif first_type == 'top' and last_type == 'right':
                return 'top_right'
            elif first_type == 'bottom' and last_type == 'left':
                return 'bottom_left'
            elif first_type == 'bottom' and last_type == 'right':
                return 'bottom_right'
        elif first_type in vertical_edges and last_type in horizontal_edges:
            # First is vertical, last is horizontal
            if first_type == 'left' and last_type == 'top':
                return 'top_left'
            elif first_type == 'right' and last_type == 'top':
                return 'top_right'
            elif first_type == 'left' and last_type == 'bottom':
                return 'bottom_left'
            elif first_type == 'right' and last_type == 'bottom':
                return 'bottom_right'
        
        return None
    
    def _check_existing_terrain(self) -> Tuple[List[ObjectPlacement], List[Tuple[int, int, int]]]:
        """
        Check existing terrain around the painted stroke and make modifications.
        
        Rules:
        - Border tiles facing same way that are "outside" → delete
        - Border tiles facing same way that are "inside" → replace with center
        - Corner tiles check BOTH cardinal directions
        - 90° border tiles within 8-neighbor → create corner
        
        Returns:
            Tuple of (placements_to_add, positions_to_delete)
        """
        placements = []
        deletions = []
        positions_to_replace = set()  # Track positions we're replacing to avoid duplicates
        
        # Get all positions we just painted
        painted_positions = set(self.session.outline_positions)
        
        # Check each painted position's neighbors
        for pos in self.session.outline_positions:
            x, y = pos
            tile_type = self.session.outline_tile_types.get(pos, 'top')
            
            # Skip slopes
            if tile_type.startswith('slope_'):
                continue
            
            # Get all directions this tile type faces
            # For corners, this returns both cardinal directions
            border_directions = self._get_border_directions(tile_type)
            if not border_directions:
                continue
            
            for border_direction in border_directions:
                # Check the neighbor in the border direction (outside)
                outside_x = x + border_direction[0]
                outside_y = y + border_direction[1]
                outside_key = (outside_x, outside_y, self.layer)
                
                # Check the neighbor opposite to border direction (inside)
                inside_x = x - border_direction[0]
                inside_y = y - border_direction[1]
                inside_key = (inside_x, inside_y, self.layer)
                
                # Check if there's existing terrain outside that faces the same way
                if outside_key in self.session.existing_tiles:
                    existing_type = self._get_tile_type_at(outside_x, outside_y)
                    # Check if the existing tile has a border facing the same direction
                    if existing_type and self._has_border_facing(existing_type, border_direction):
                        if outside_key not in deletions:
                            deletions.append(outside_key)
                            log_engine(f"Terrain-aware: Delete {existing_type} at ({outside_x}, {outside_y}) - outside border")
                
                # Check if there's existing terrain inside that faces the same way
                if inside_key in self.session.existing_tiles and inside_key not in painted_positions:
                    if inside_key in positions_to_replace:
                        continue
                    existing_type = self._get_tile_type_at(inside_x, inside_y)
                    if existing_type and self._has_border_facing(existing_type, border_direction):
                        # Replace with center tile
                        # The placement will overwrite the old tile - no need to delete
                        # (deletion would remove the new center tile since it happens after placement)
                        center_id = self.brush.get_terrain_tile('center')
                        if center_id is not None:
                            placement = ObjectPlacement(
                                tileset=self.tileset_idx,
                                object_id=center_id,
                                layer=self.layer,
                                x=inside_x,
                                y=inside_y,
                                width=1,
                                height=1
                            )
                            placements.append(placement)
                            positions_to_replace.add(inside_key)
                            log_engine(f"Terrain-aware: Replace {existing_type} at ({inside_x}, {inside_y}) with center")
        
        # Check for 90° corner connections with existing terrain
        corner_placements = self._check_corner_connections()
        placements.extend(corner_placements)
        
        return placements, deletions
    
    def _get_border_directions(self, tile_type: str) -> List[Tuple[int, int]]:
        """
        Get all outward normal directions for a tile type.
        For edge tiles, returns one direction.
        For corner tiles, returns both cardinal directions.
        
        Args:
            tile_type: Tile type string
        
        Returns:
            List of (dx, dy) direction tuples
        """
        # Single edge tiles
        edge_directions = {
            'top': [(0, -1)],
            'bottom': [(0, 1)],
            'left': [(-1, 0)],
            'right': [(1, 0)],
        }
        
        # Corner tiles have two directions
        corner_directions = {
            'top_left': [(0, -1), (-1, 0)],      # faces up and left
            'top_right': [(0, -1), (1, 0)],     # faces up and right
            'bottom_left': [(0, 1), (-1, 0)],   # faces down and left
            'bottom_right': [(0, 1), (1, 0)],   # faces down and right
        }
        
        if tile_type in edge_directions:
            return edge_directions[tile_type]
        if tile_type in corner_directions:
            return corner_directions[tile_type]
        
        return []
    
    def _has_border_facing(self, tile_type: str, direction: Tuple[int, int]) -> bool:
        """
        Check if a tile type has a border facing the given direction.
        
        Args:
            tile_type: Tile type string
            direction: (dx, dy) direction tuple
        
        Returns:
            True if the tile has a border facing that direction
        """
        directions = self._get_border_directions(tile_type)
        return direction in directions
    
    def _get_border_direction(self, tile_type: str) -> Optional[Tuple[int, int]]:
        """
        Get the outward normal direction for a border tile type.
        
        Returns:
            (dx, dy) pointing outward from the terrain, or None if not a border
        """
        directions = {
            'top': (0, -1),      # Top border faces up (outside is above)
            'bottom': (0, 1),   # Bottom border faces down
            'left': (-1, 0),    # Left border faces left
            'right': (1, 0),    # Right border faces right
        }
        return directions.get(tile_type)
    
    def _get_tile_type_at(self, x: int, y: int) -> Optional[str]:
        """
        Get the tile type at a position from existing tiles using the brush's
        reverse lookup (object ID → tile type).
        
        Args:
            x, y: Tile coordinates
        
        Returns:
            Tile type string, or None if not found or not a known tile
        """
        key = (x, y, self.layer)
        if key not in self.session.existing_tiles:
            return None
        
        tile_id = self.session.existing_tiles[key]
        if tile_id is None:
            return None
        
        # Use brush's reverse lookup to get tile type from object ID
        if self.brush:
            return self.brush.get_tile_type_by_id(tile_id)
        
        return None
    
    def _check_corner_connections(self) -> List[ObjectPlacement]:
        """
        Check for 90° border tiles within 8-neighbor distance that need corners.
        
        Returns:
            List of ObjectPlacement for corner tiles to add
        """
        placements = []
        
        # Get all border tiles we painted
        border_tiles = {}
        for pos in self.session.outline_positions:
            tile_type = self.session.outline_tile_types.get(pos, 'top')
            if tile_type in ['top', 'bottom', 'left', 'right']:
                border_tiles[pos] = tile_type
        
        # Check each pair of border tiles for potential corner connections
        checked_pairs = set()
        
        for pos1, type1 in border_tiles.items():
            for pos2, type2 in border_tiles.items():
                if pos1 == pos2:
                    continue
                
                # Skip if already checked this pair
                pair_key = (min(pos1, pos2), max(pos1, pos2))
                if pair_key in checked_pairs:
                    continue
                checked_pairs.add(pair_key)
                
                # Check if they're perpendicular
                if not self._are_perpendicular(type1, type2):
                    continue
                
                # Check if within 8-neighbor distance
                dx = abs(pos1[0] - pos2[0])
                dy = abs(pos1[1] - pos2[1])
                
                if dx > 1 or dy > 1:
                    continue
                
                # Determine if there's a gap that needs a corner
                corner_pos = self._find_corner_gap(pos1, type1, pos2, type2)
                if corner_pos and corner_pos not in self.session.outline_positions:
                    corner_type = self._determine_corner_type(type1, type2, pos1, pos2)
                    if corner_type:
                        tile_id = self.brush.get_terrain_tile(corner_type)
                        if tile_id is not None:
                            placement = ObjectPlacement(
                                tileset=self.tileset_idx,
                                object_id=tile_id,
                                layer=self.layer,
                                x=corner_pos[0],
                                y=corner_pos[1],
                                width=1,
                                height=1
                            )
                            placements.append(placement)
                            log_engine(f"Corner connection: Adding {corner_type} at {corner_pos}")
        
        return placements
    
    def _are_perpendicular(self, type1: str, type2: str) -> bool:
        """Check if two border types are perpendicular (90° apart)"""
        horizontal = {'top', 'bottom'}
        vertical = {'left', 'right'}
        return (type1 in horizontal and type2 in vertical) or \
               (type1 in vertical and type2 in horizontal)
    
    def _find_corner_gap(self, pos1: Tuple[int, int], type1: str,
                         pos2: Tuple[int, int], type2: str) -> Optional[Tuple[int, int]]:
        """
        Find the position where a corner tile should be placed to connect
        two perpendicular border tiles.
        
        Returns:
            (x, y) position for corner, or None if no gap
        """
        x1, y1 = pos1
        x2, y2 = pos2
        
        # If they're diagonally adjacent, the corner goes at the diagonal position
        if abs(x1 - x2) == 1 and abs(y1 - y2) == 1:
            # They're diagonal - corner could go at either shared neighbor
            # Choose based on tile types
            if type1 in ['top', 'bottom']:
                # Horizontal tile - corner goes at same y as this tile
                return (x2, y1)
            else:
                # Vertical tile - corner goes at same x as this tile
                return (x1, y2)
        
        return None
    
    def _determine_corner_type(self, type1: str, type2: str,
                               pos1: Tuple[int, int], pos2: Tuple[int, int]) -> Optional[str]:
        """
        Determine the corner type for connecting two perpendicular borders.
        """
        types = {type1, type2}
        
        # Determine relative positions
        x1, y1 = pos1
        x2, y2 = pos2
        
        if 'top' in types and 'left' in types:
            return 'top_left'
        elif 'top' in types and 'right' in types:
            return 'top_right'
        elif 'bottom' in types and 'left' in types:
            return 'bottom_left'
        elif 'bottom' in types and 'right' in types:
            return 'bottom_right'
        
        return None
