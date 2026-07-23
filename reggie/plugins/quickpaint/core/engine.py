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
    
    # Path dampening - deviation-based approach
    # Tracks how far the mouse has deviated perpendicular to the primary axis
    consecutive_direction_count: int = 0
    last_move_direction: Optional[str] = None  # 'horizontal' or 'vertical'
    pending_turn_count: int = 0  # Count of consecutive attempts to turn (for dampening)
    # Primary axis for dampening (set on first significant movement)
    primary_axis: Optional[str] = None  # 'horizontal' or 'vertical'
    # Last committed position on the primary axis (for deviation calculation)
    last_committed_pos: Optional[Tuple[int, int]] = None
    # Accumulated perpendicular deviation from primary axis
    perpendicular_deviation: int = 0
    
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
    # Inner corner type to place when branching slope from vertical terrain
    slope_inner_corner: Optional[str] = None
    
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
        self.primary_axis = None
        self.last_committed_pos = None
        self.perpendicular_deviation = 0
        self.committed_slopes = []
        self.uncommitted_start_idx = 0
        self.slope_mode = False
        self.slope_anchor = None
        self.preview_slope = None
        self.slope_mode_path_length = 0
        self.slope_exit_direction = None
        self.slope_current_direction = None
        self.slope_inner_corner = None
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
        
        # Empty slope regions - positions within slope object bounds that are empty (-1)
        # These positions should NOT receive new tiles when painting through slopes
        self._empty_slope_regions: Set[Tuple[int, int, int]] = set()
        
        # Path dampening settings
        # Higher values = more resistance to direction changes
        # 0 = no dampening, 2 = require 2 consecutive moves before changing direction
        self.dampening_factor: int = 2
    
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
        1-10 = light to heavy dampening
        
        Args:
            factor: Dampening factor (0-10 recommended)
        """
        self.dampening_factor = max(0, min(10, factor))
    
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
            
            # Suggest a default slope immediately so the user sees a preview
            self._suggest_default_slope()
            
            # Update outline to show current state with default slope suggestion
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
        
        # Determine slope category and validate direction
        # Horizontal modes: LTR → top slopes (go RIGHT), RTL → bottom slopes (go LEFT)
        # Vertical modes: Slopes can branch off from walls with inner corner conversion
        #   - Left wall (BTT): can branch RIGHT with top slopes (inner_bottom_right corner)
        #   - Left wall (TTB): can branch RIGHT with top slopes (inner_top_right corner)
        #   - Right wall (BTT): can branch LEFT with bottom slopes (inner_bottom_left corner)
        #   - Right wall (TTB): can branch LEFT with bottom slopes (inner_top_left corner)
        
        inner_corner_type = None  # Will be set if we need to convert anchor to inner corner
        
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
        elif current_dir == 'bottom_to_top':
            # Painting upward on a wall - can branch to slopes
            # Left wall (going up): can go RIGHT with top slopes
            # Right wall (going up): can go LEFT with bottom slopes
            if dx > 0:
                # Going right from wall → top slopes
                slope_category = 'top'
                inner_corner_type = 'inner_bottom_right'  # Wall was on left, slope goes right
            elif dx < 0:
                # Going left from wall → bottom slopes
                slope_category = 'bottom'
                inner_corner_type = 'inner_bottom_left'  # Wall was on right, slope goes left
            else:
                # dx == 0, no horizontal movement
                log_engine(f"Slope preview blocked: need horizontal movement from vertical wall")
                self.session.preview_slope = None
                self._update_outline()
                return
        elif current_dir == 'top_to_bottom':
            # Painting downward on a wall - can branch to slopes
            # Left wall (going down): can go RIGHT with top slopes
            # Right wall (going down): can go LEFT with bottom slopes
            if dx > 0:
                # Going right from wall → top slopes
                slope_category = 'top'
                inner_corner_type = 'inner_top_right'  # Wall was on left, slope goes right
            elif dx < 0:
                # Going left from wall → bottom slopes
                slope_category = 'bottom'
                inner_corner_type = 'inner_top_left'  # Wall was on right, slope goes left
            else:
                # dx == 0, no horizontal movement
                log_engine(f"Slope preview blocked: need horizontal movement from vertical wall")
                self.session.preview_slope = None
                self._update_outline()
                return
        else:
            log_engine(f"Slope preview blocked: unknown direction ({current_dir})")
            self.session.preview_slope = None
            self._update_outline()
            return
        
        # Store inner corner info for later use when committing
        self.session.slope_inner_corner = inner_corner_type
        
        # Calculate angle from horizontal
        import math
        abs_dx = abs(dx)
        abs_dy = abs(dy)
        
        if abs_dx == 0:
            angle = 90.0
        else:
            angle = math.degrees(math.atan2(abs_dy, abs_dx))
        
        # Determine left/right based on vertical direction (up or down from horizontal)
        # - Top slopes (dx > 0): up (dy < 0) → left (ascending), down (dy > 0) → right (descending)
        # - Bottom slopes (dx < 0): up (dy < 0) → left (ascending), down (dy > 0) → right (descending)
        side = 'left' if dy < 0 else 'right'
        
        # Get enabled slopes from brush
        enabled_slopes = self.brush.enabled_slopes if self.brush else set()
        
        # Determine slope size based on angle, but only use enabled slopes
        # Priority order based on angle:
        # 45°+ = prefer 1x1 (steep), fallback to 2x1, then 4x1
        # 20-45° = prefer 2x1 (medium), fallback to 1x1, then 4x1
        # <20° = prefer 4x1 (gentle), fallback to 2x1, then 1x1
        
        # Build candidate list based on angle preference
        if angle >= 45:
            size_candidates = ['1x1', '2x1', '4x1']
        elif angle >= 20:
            size_candidates = ['2x1', '1x1', '4x1']
        else:
            size_candidates = ['4x1', '2x1', '1x1']
        
        # Find the first enabled slope from candidates
        selected_size = None
        for size in size_candidates:
            candidate_type = f"slope_{slope_category}_{size}_{side}"
            if candidate_type in enabled_slopes:
                selected_size = size
                break
        
        if selected_size is None:
            # No enabled slope available for this direction
            log_engine(f"Slope preview blocked: no enabled {slope_category} slopes for side={side}")
            self.session.preview_slope = None
            self._update_outline()
            return
        
        # Get width for the selected slope
        width = {'1x1': 1, '2x1': 2, '4x1': 4}[selected_size]
        
        # Calculate origin based on slope category and selected size
        if slope_category == 'top':
            # Top slopes go RIGHT (dx > 0)
            origin_x = anchor_x + 1  # Start after anchor
            # Y position: ascending (left) starts higher, descending (right) at anchor level
            origin_y = anchor_y - 1 if side == 'left' else anchor_y
        else:
            # Bottom slopes go LEFT (dx < 0)
            origin_x = anchor_x - width  # End at anchor
            # Y position: ascending (left) starts higher, descending (right) at anchor level
            origin_y = anchor_y - 1 if side == 'left' else anchor_y
        
        slope_type = f"slope_{slope_category}_{selected_size}_{side}"
        
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
        
        # Safety check: only commit enabled slopes
        enabled_slopes = self.brush.enabled_slopes if self.brush else set()
        if slope_type not in enabled_slopes:
            log_engine(f"Slope commit blocked: {slope_type} is not enabled")
            return False
        
        # Handle inner corner conversion when branching from vertical terrain
        # This converts the anchor tile (last tile of the wall) to an inner corner
        if self.session.slope_inner_corner and self.session.slope_anchor:
            anchor_x, anchor_y = self.session.slope_anchor
            # Update the outline tile type at the anchor position to be an inner corner
            anchor_pos = (anchor_x, anchor_y)
            if anchor_pos in self.session.outline_tile_types:
                old_type = self.session.outline_tile_types[anchor_pos]
                self.session.outline_tile_types[anchor_pos] = self.session.slope_inner_corner
                log_engine(f"Converting anchor at {anchor_pos} from {old_type} to {self.session.slope_inner_corner}")
            # Clear the inner corner flag after using it
            self.session.slope_inner_corner = None
        
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
        
        # Suggest the next default slope immediately after committing
        self._suggest_default_slope()
        
        self._update_outline()
        return True
    
    def _suggest_default_slope(self):
        """
        Generate a default slope suggestion based on the current direction and anchor.
        Called when entering slope mode and after committing a slope, so the user
        immediately sees a preview without needing to move the mouse.
        """
        if not self.session.slope_anchor:
            return
        
        anchor_x, anchor_y = self.session.slope_anchor
        current_dir = self.session.slope_current_direction or self.session.initial_direction
        enabled_slopes = self.brush.enabled_slopes if self.brush else set()
        
        if not enabled_slopes:
            return
        
        # Determine slope category based on direction
        if current_dir == 'left_to_right':
            slope_category = 'top'
        elif current_dir == 'right_to_left':
            slope_category = 'bottom'
        else:
            # Vertical directions need mouse input to determine left/right branching
            return
        
        # Default side: 'left' (ascending) for first suggestion
        side = 'left'
        
        # Find the first enabled slope (prefer smallest: 1x1, then 2x1, then 4x1)
        for size in ['1x1', '2x1', '4x1']:
            candidate = f"slope_{slope_category}_{size}_{side}"
            if candidate in enabled_slopes:
                width = {'1x1': 1, '2x1': 2, '4x1': 4}[size]
                
                if slope_category == 'top':
                    origin_x = anchor_x + 1
                    origin_y = anchor_y - 1  # ascending
                else:
                    origin_x = anchor_x - width
                    origin_y = anchor_y - 1  # ascending
                
                self.session.preview_slope = (candidate, origin_x, origin_y)
                log_engine(f"Default slope suggestion: {candidate} at ({origin_x}, {origin_y})")
                return
        
        # Try 'right' (descending) if no 'left' slopes are enabled
        side = 'right'
        for size in ['1x1', '2x1', '4x1']:
            candidate = f"slope_{slope_category}_{size}_{side}"
            if candidate in enabled_slopes:
                width = {'1x1': 1, '2x1': 2, '4x1': 4}[size]
                
                if slope_category == 'top':
                    origin_x = anchor_x + 1
                    origin_y = anchor_y  # descending
                else:
                    origin_x = anchor_x - width
                    origin_y = anchor_y  # descending
                
                self.session.preview_slope = (candidate, origin_x, origin_y)
                log_engine(f"Default slope suggestion: {candidate} at ({origin_x}, {origin_y})")
                return
    
    def update_object_database(self, database: Dict[Tuple[int, int, int], int], 
                               empty_slope_regions: Set[Tuple[int, int, int]] = None):
        """
        Update the object search database for fast tile lookups.
        
        Args:
            database: Dict mapping (x, y, layer) -> object_id
            empty_slope_regions: Set of (x, y, layer) positions that are empty tiles
                                 within slope object bounds (should not receive new tiles)
        """
        self._object_database = database
        self.session.existing_tiles = database.copy()
        if empty_slope_regions is not None:
            self._empty_slope_regions = empty_slope_regions
    
    def set_empty_slope_regions(self, regions: Set[Tuple[int, int, int]]):
        """
        Set the empty slope regions.
        
        These are positions within slope object bounds that are empty (-1).
        QPT should not place new tiles at these positions.
        """
        self._empty_slope_regions = regions
    
    def is_in_empty_slope_region(self, x: int, y: int, layer: int) -> bool:
        """Check if a position is in an empty region of an existing slope object."""
        return (x, y, layer) in self._empty_slope_regions
    
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
        
        # Also block positions covered by committed slope objects (full canvas footprint)
        # Slopes occupy a rectangular area (width x height) that extends beyond the path
        slope_blocked = set()
        for slope_info in self.session.committed_slopes:
            slope_type, origin_x, origin_y, _ = slope_info
            width, height = self._get_slope_dimensions(slope_type)
            for dy in range(height):
                for dx in range(width):
                    slope_blocked.add((origin_x + dx, origin_y + dy))
        # Also include preview slope if in slope mode
        if self.session.slope_mode and self.session.preview_slope:
            slope_type, origin_x, origin_y = self.session.preview_slope
            width, height = self._get_slope_dimensions(slope_type)
            for dy in range(height):
                for dx in range(width):
                    slope_blocked.add((origin_x + dx, origin_y + dy))
        
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
        
        # Determine mouse's intended direction based on displacement from current position
        if abs(dx) >= abs(dy):
            mouse_direction = 'horizontal'
        else:
            mouse_direction = 'vertical'
        
        # DEVIATION-BASED DAMPENING
        # Instead of counting turn attempts, we track how far the mouse has deviated
        # from the primary axis. Only allow perpendicular movement when deviation
        # exceeds the dampening threshold.
        #
        # This ensures that small wiggles (e.g., 1 block up then back) don't create
        # bumps in the stroke when dampening is set high.
        
        # Set primary axis on first movement
        if self.session.primary_axis is None and self.dampening_factor > 0:
            self.session.primary_axis = mouse_direction
            self.session.last_committed_pos = current
            self.session.perpendicular_deviation = 0
        
        # Calculate perpendicular deviation from the primary axis
        direction_locked = False
        if self.dampening_factor > 0 and self.session.primary_axis is not None:
            if self.session.last_committed_pos:
                base_x, base_y = self.session.last_committed_pos
                
                if self.session.primary_axis == 'horizontal':
                    # Primary axis is horizontal - deviation is vertical distance
                    perpendicular_dist = abs(target[1] - base_y)
                else:
                    # Primary axis is vertical - deviation is horizontal distance
                    perpendicular_dist = abs(target[0] - base_x)
                
                # Check if deviation exceeds threshold
                if perpendicular_dist < self.dampening_factor:
                    # Deviation too small - lock to primary axis
                    direction_locked = True
                else:
                    # Deviation exceeds threshold - allow the turn, switch primary axis
                    self.session.primary_axis = 'vertical' if self.session.primary_axis == 'horizontal' else 'horizontal'
                    self.session.last_committed_pos = current
                    self.session.perpendicular_deviation = 0
        
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
                # Dampening is restricting us - only allow moves along primary axis
                if self.session.primary_axis == 'horizontal':
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
                if next_pos in slope_blocked:
                    continue  # No crossing through slope objects
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
        
        # Collect adjacent same-type tiles from existing terrain for cross-stroke merging
        adjacent_tiles, adjacent_deletes = self._collect_adjacent_existing_tiles(placements)
        if adjacent_tiles:
            placements.extend(adjacent_tiles)
            print(f"[PaintingEngine] Cross-stroke merge: {len(adjacent_tiles)} adjacent tiles collected")
        
        # Re-merge all placements to ensure optimal object count
        placements = self._remerge_placements(placements)
        
        # Store cross-stroke merge deletions for IMMEDIATE application (before new placements)
        # These must be applied before placing new merged objects to avoid splitting them
        self._pending_merge_deletes = adjacent_deletes
        
        # Store terrain-aware deletions for delayed application (100ms delay)
        # These are for outside/inside terrain modifications, not merge-related
        self._pending_terrain_deletes = terrain_deletes
        
        # Notify callback
        if self.on_painting_finished:
            self.on_painting_finished(placements)
        
        self.state = PaintingState.IDLE
        return placements
    
    def get_pending_merge_deletes(self) -> List[Tuple[int, int, int]]:
        """
        Get pending cross-stroke merge deletions.
        These MUST be applied BEFORE creating new placements to avoid splitting merged objects.
        
        Returns:
            List of (x, y, layer) tuples to delete
        """
        return getattr(self, '_pending_merge_deletes', [])
    
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
        skipped_empty_slope = 0
        
        # First pass: handle slopes (they have fixed dimensions)
        for pos in self.session.outline_positions:
            x, y = pos
            
            # Skip if already placed
            if (x, y, self.layer) in self.session.placed_tiles:
                continue
            
            # Skip if position is in an empty region of an existing slope object
            # This prevents ghost tiles when painting through large slope objects
            if (x, y, self.layer) in self._empty_slope_regions:
                skipped_empty_slope += 1
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
        
        if skipped_empty_slope > 0:
            print(f"[PaintingEngine] Skipped {skipped_empty_slope} positions in empty slope regions")
        
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
                # Don't check 'processed' here - find the true start regardless
                start_x, start_y = x, y
                
                if dx > 0:  # Horizontal merge - look backward (decreasing x)
                    while (start_x - 1, y) in tiles_by_pos:
                        prev_type, prev_id = tiles_by_pos[(start_x - 1, y)]
                        if prev_type == tile_type and prev_id == tile_id:
                            start_x -= 1
                        else:
                            break
                elif dy > 0:  # Vertical merge - look backward (decreasing y)
                    while (x, start_y - 1) in tiles_by_pos:
                        prev_type, prev_id = tiles_by_pos[(x, start_y - 1)]
                        if prev_type == tile_type and prev_id == tile_id:
                            start_y -= 1
                        else:
                            break
                
                # If the start position was already processed, this run was handled
                if dx > 0 and (start_x, y) in processed:
                    continue
                if dy > 0 and (x, start_y) in processed:
                    continue
                
                # Now find consecutive tiles from the start, going forward
                width = 1
                height = 1
                
                if dx > 0:  # Horizontal merge
                    processed.add((start_x, y))
                    nx = start_x + 1
                    while (nx, y) in tiles_by_pos:
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
                    while (x, ny) in tiles_by_pos:
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
    
    def _remerge_placements(self, placements: List[ObjectPlacement]) -> List[ObjectPlacement]:
        """
        Re-merge all placements to ensure optimal object count.
        
        This expands all placements back to individual tiles, then re-runs
        the merge logic. Useful after terrain-aware modifications that may
        have added individual tiles.
        
        Args:
            placements: List of ObjectPlacement objects (may include multi-tile)
        
        Returns:
            List of re-merged ObjectPlacement objects
        """
        if not placements:
            return placements
        
        # Expand all placements to individual tiles
        tiles_by_pos = {}
        slopes = []  # Keep slope placements separate (don't merge them)
        
        for placement in placements:
            # Check if this is a slope (width > 1 or height > 1 for non-edge tiles)
            # or if it's an edge tile that should be merged
            tile_type = self._get_tile_type_from_id(placement.object_id)
            
            if tile_type and tile_type.startswith('slope_'):
                # Keep slopes as-is
                slopes.append(placement)
            elif tile_type in ['top', 'bottom', 'left', 'right', 'center']:
                # Mergeable tile - expand to individual positions
                for dy in range(placement.height):
                    for dx in range(placement.width):
                        pos = (placement.x + dx, placement.y + dy)
                        tiles_by_pos[pos] = (tile_type, placement.object_id)
            else:
                # Corner or other non-mergeable - keep as individual
                pos = (placement.x, placement.y)
                if tile_type:
                    tiles_by_pos[pos] = (tile_type, placement.object_id)
                else:
                    # Unknown type, keep the placement as-is
                    slopes.append(placement)
        
        # Re-merge the tiles
        merged = self._merge_consecutive_tiles(tiles_by_pos)
        
        # Combine slopes and merged terrain
        return slopes + merged
    
    def _collect_adjacent_existing_tiles(self, placements: List[ObjectPlacement]) -> Tuple[List[ObjectPlacement], List[Tuple[int, int, int]]]:
        """
        Collect adjacent same-type tiles from existing terrain that should be merged.
        
        When individual strokes connect, we need to include adjacent same-type
        tiles from previous strokes in the merge to create single merged objects.
        
        Args:
            placements: Current stroke's placements
            
        Returns:
            Tuple of (placements for adjacent tiles, positions to delete)
        """
        adjacent_placements = []
        positions_to_delete = []
        processed_positions = set()
        
        # Get all positions in current placements
        current_positions = set()
        for p in placements:
            for dy in range(p.height):
                for dx in range(p.width):
                    current_positions.add((p.x + dx, p.y + dy))
        
        # Merge directions for each edge type
        merge_dirs = {
            'top': [(1, 0), (-1, 0)],      # Horizontal merge
            'bottom': [(1, 0), (-1, 0)],   # Horizontal merge
            'left': [(0, 1), (0, -1)],     # Vertical merge
            'right': [(0, 1), (0, -1)],    # Vertical merge
        }
        
        for p in placements:
            tile_type = self._get_tile_type_from_id(p.object_id)
            if not tile_type or tile_type not in merge_dirs:
                continue
            
            # Check all positions in this placement
            for dy in range(p.height):
                for dx in range(p.width):
                    pos = (p.x + dx, p.y + dy)
                    
                    # Check adjacent positions in merge direction
                    for ddx, ddy in merge_dirs[tile_type]:
                        adj_pos = (pos[0] + ddx, pos[1] + ddy)
                        
                        # Skip if already in current stroke or already processed
                        if adj_pos in current_positions or adj_pos in processed_positions:
                            continue
                        
                        # Check if there's existing terrain at this position
                        adj_key = (adj_pos[0], adj_pos[1], self.layer)
                        if adj_key not in self._object_database:
                            continue
                        
                        # Get the existing tile type
                        existing_type = self._get_tile_type_from_database(adj_pos[0], adj_pos[1])
                        if existing_type != tile_type:
                            continue
                        
                        # Same type - collect all connected tiles in this direction
                        connected = self._collect_connected_tiles(adj_pos, tile_type, current_positions, processed_positions)
                        for conn_pos in connected:
                            processed_positions.add(conn_pos)
                            positions_to_delete.append((conn_pos[0], conn_pos[1], self.layer))
                            
                            # Create placement for this tile
                            tile_id = self.brush.get_terrain_tile(tile_type)
                            if tile_id is not None:
                                adjacent_placements.append(ObjectPlacement(
                                    tileset=self.tileset_idx,
                                    object_id=tile_id,
                                    layer=self.layer,
                                    x=conn_pos[0],
                                    y=conn_pos[1],
                                    width=1,
                                    height=1
                                ))
        
        return adjacent_placements, positions_to_delete
    
    def _collect_connected_tiles(self, start_pos: Tuple[int, int], tile_type: str,
                                  exclude_positions: set, already_collected: set) -> List[Tuple[int, int]]:
        """
        Collect all connected tiles of the same type starting from a position.
        
        Uses flood-fill in the merge direction to find all connected same-type tiles.
        """
        collected = []
        to_check = [start_pos]
        checked = set()
        
        # Merge directions
        if tile_type in ['top', 'bottom']:
            directions = [(1, 0), (-1, 0)]
        else:
            directions = [(0, 1), (0, -1)]
        
        while to_check:
            pos = to_check.pop(0)
            if pos in checked or pos in exclude_positions or pos in already_collected:
                continue
            checked.add(pos)
            
            # Check if this position has the same tile type
            pos_key = (pos[0], pos[1], self.layer)
            if pos_key not in self._object_database:
                continue
            
            existing_type = self._get_tile_type_from_database(pos[0], pos[1])
            if existing_type != tile_type:
                continue
            
            collected.append(pos)
            
            # Add adjacent positions in merge direction
            for dx, dy in directions:
                next_pos = (pos[0] + dx, pos[1] + dy)
                if next_pos not in checked:
                    to_check.append(next_pos)
        
        return collected
    
    def _get_tile_type_from_id(self, tile_id: int) -> Optional[str]:
        """
        Get the tile type string from a tile ID by reverse-lookup in the brush.
        
        Args:
            tile_id: The tile object ID
        
        Returns:
            Tile type string or None if not found
        """
        if not self.brush:
            return None
        
        # Use SmartBrush's built-in reverse lookup
        return self.brush.get_tile_type_by_id(tile_id)
    
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
        
        # Step 1: Self-connection check (within same stroke)
        self_connection_mods = self._check_self_connection()
        placements_to_add.extend(self_connection_mods)
        
        # Step 2: Existing terrain connection check (connect to previous strokes)
        existing_connection_mods = self._check_existing_terrain_connection()
        placements_to_add.extend(existing_connection_mods)
        
        # Collect positions modified by connection checks (Steps 1 & 2).
        # These positions are "protected" - Step 3 should not delete or replace
        # existing terrain at these positions, since the connection logic already
        # handled them (e.g. S-shape corners, U-turn corners).
        connection_positions = set()
        for p in self_connection_mods + existing_connection_mods:
            connection_positions.add((p.x, p.y, p.layer))
        
        # Step 3: Existing terrain check (delete/replace overlapping terrain)
        existing_mods, existing_deletes = self._check_existing_terrain(connection_positions)
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
        
        # Get first and last EDGE positions (skip slopes)
        edge_types = {'top', 'bottom', 'left', 'right'}
        first_pos = None
        first_type = None
        for pos in self.session.outline_positions:
            t = self.session.outline_tile_types.get(pos, 'top')
            if t in edge_types:
                first_pos, first_type = pos, t
                break
        
        last_pos = None
        last_type = None
        for pos in reversed(self.session.outline_positions):
            t = self.session.outline_tile_types.get(pos, 'top')
            if t in edge_types:
                last_pos, last_type = pos, t
                break
        
        if not first_pos or not last_pos or first_pos == last_pos:
            return placements
        
        dx = abs(first_pos[0] - last_pos[0])
        dy = abs(first_pos[1] - last_pos[1])
        
        if self._are_perpendicular(first_type, last_type):
            # 90° connection: single corner
            if dx > 1 or dy > 1:
                return placements  # Too far apart
            
            corner_pos = self._find_corner_position(first_pos, first_type, last_pos, last_type)
            if corner_pos is None:
                return placements
            
            corner_type = self._determine_self_connection_corner(first_pos, first_type, last_pos, last_type)
            
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
        
        elif self._are_parallel(first_type, last_type):
            # 180° connection: two corners (U-turn or S-shape)
            parallel_placements = self._check_parallel_self_connection(
                first_pos, first_type, last_pos, last_type
            )
            placements.extend(parallel_placements)
        
        return placements
    
    def _check_parallel_self_connection(self, first_pos: Tuple[int, int], first_type: str,
                                         last_pos: Tuple[int, int], last_type: str) -> List[ObjectPlacement]:
        """
        Handle 180° self-connection where first and last tiles are parallel.
        
        The two endpoints must be within 8-neighbor distance (max 1 tile apart).
        The two corners are placed immediately adjacent, on the same row or column.
        
        Two sub-cases:
          a. U-turn (same type, e.g. top+top, cardinally adjacent): two same-kind corners
          b. S-shape (opposite type, e.g. top+bottom, diagonally adjacent): asymmetric corners
        
        For self-connections:
          - Same type = U-turn (stroke goes out and comes back on same side)
          - Opposite type = S-shape (stroke transitions from one side to the other)
        
        Args:
            first_pos: Position of the first edge tile
            first_type: Edge type of the first tile
            last_pos: Position of the last edge tile
            last_type: Edge type of the last tile
        
        Returns:
            List of ObjectPlacement for the two corner tiles
        """
        placements = []
        fx, fy = first_pos
        lx, ly = last_pos
        
        # The two endpoints must be within 8-neighbor distance
        dx = abs(fx - lx)
        dy = abs(fy - ly)
        if dx > 1 or dy > 1:
            return placements
        if dx == 0 and dy == 0:
            return placements
        
        horizontal_types = {'top', 'bottom'}
        both_horizontal = first_type in horizontal_types and last_type in horizontal_types
        
        # Collinear detection: same-type edges adjacent along the edge direction
        # are straight-line extensions, not corners. No modification needed.
        if first_type == last_type:
            if both_horizontal and fy == ly:
                # Same horizontal edge type on the same row → straight line
                return placements
            elif not both_horizontal and fx == lx:
                # Same vertical edge type on the same column → straight line
                return placements
        
        # S-shape vs U-turn detection for self-connections:
        # - U-turn: opposite types (top+bottom) that are CARDINALLY adjacent
        # - S-shape: same types on different row/column (diagonal), OR
        #            opposite types that are DIAGONALLY adjacent
        is_diagonal = (dx == 1 and dy == 1)
        is_cardinal = (dx == 0 or dy == 0)
        
        if first_type != last_type:
            # Opposite types: S-shape if diagonal, U-turn if cardinal
            is_s_shape = is_diagonal
        else:
            # Same type, different row/column → S-shape (collinear already excluded above)
            is_s_shape = True
        
        # Determine the connecting wall direction from the stroke path.
        # The stroke departs from first_pos in one direction; the opening
        # (where the two corners go) is on the opposite side.
        path = self.session.stroke_path
        if len(path) < 2:
            return placements
        
        dx_first = path[1][0] - path[0][0]
        dy_first = path[1][1] - path[0][1]
        
        if both_horizontal:
            # Horizontal edges → connecting wall direction is vertical
            # Stroke departs right → opening is left, and vice versa
            if dx_first > 0:
                wall_type = 'left'
            elif dx_first < 0:
                wall_type = 'right'
            else:
                return placements
        else:
            # Vertical edges → connecting wall direction is horizontal
            # Stroke departs down → opening is top, and vice versa
            if dy_first > 0:
                wall_type = 'top'
            elif dy_first < 0:
                wall_type = 'bottom'
            else:
                return placements
        
        if is_s_shape:
            # S-shape self-connection: opposite types (e.g. top+bottom), diagonally adjacent
            # Delegate to the S-shape handler, treating first_pos as "endpoint" and last_pos as "existing"
            return self._handle_s_shape_self_connection(
                first_pos, first_type, last_pos, last_type,
                wall_type, both_horizontal
            )
        
        # U-turn: same type (e.g. top+top), cardinally adjacent
        # Both corners replace the endpoint edge tiles.
        # For 180° connections:
        #   - Horizontal (top+bottom): outer if top has lower y, inner if bottom has lower y
        #   - Vertical (left+right): outer if left has lower x, inner if right has lower x
        # Corner name = edge_type + wall_type (no left↔right swap for inner, unlike 90°)
        
        if both_horizontal:
            # Find which is top and which is bottom
            top_pos = first_pos if first_type == 'top' else last_pos
            bottom_pos = first_pos if first_type == 'bottom' else last_pos
            # Outer: top above bottom (lower y). Inner: bottom above top.
            is_outer = top_pos[1] < bottom_pos[1]
        else:
            # Find which is left and which is right
            left_pos = first_pos if first_type == 'left' else last_pos
            right_pos = first_pos if first_type == 'right' else last_pos
            # Outer: left has lower x than right. Inner: right has lower x.
            is_outer = left_pos[0] < right_pos[0]
        
        # Corner name directly combines edge_type and wall_type
        outer_lookup = {
            ('top', 'right'): 'top_right', ('right', 'top'): 'top_right',
            ('top', 'left'): 'top_left', ('left', 'top'): 'top_left',
            ('bottom', 'right'): 'bottom_right', ('right', 'bottom'): 'bottom_right',
            ('bottom', 'left'): 'bottom_left', ('left', 'bottom'): 'bottom_left',
        }
        # For 180° inner corners:
        #   Horizontal (top/bottom + left/right wall): direct combination
        #   Vertical (left/right + top/bottom wall): both components flipped
        inner_lookup = {
            ('top', 'right'): 'inner_top_right', ('top', 'left'): 'inner_top_left',
            ('bottom', 'right'): 'inner_bottom_right', ('bottom', 'left'): 'inner_bottom_left',
            ('right', 'top'): 'inner_bottom_left', ('right', 'bottom'): 'inner_top_left',
            ('left', 'top'): 'inner_bottom_right', ('left', 'bottom'): 'inner_top_right',
        }
        
        lookup = outer_lookup if is_outer else inner_lookup
        corner1_type = lookup.get((first_type, wall_type))
        corner2_type = lookup.get((last_type, wall_type))
        
        log_engine(f"Parallel self-connection: first={first_type}@{first_pos}, "
                   f"last={last_type}@{last_pos}, wall={wall_type}, is_outer={is_outer}")
        
        for ctype, cpos, etype in [
            (corner1_type, first_pos, first_type),
            (corner2_type, last_pos, last_type)
        ]:
            if ctype:
                tile_id = self.brush.get_terrain_tile(ctype)
                if tile_id is not None:
                    placement = ObjectPlacement(
                        tileset=self.tileset_idx,
                        object_id=tile_id,
                        layer=self.layer,
                        x=cpos[0],
                        y=cpos[1],
                        width=1,
                        height=1
                    )
                    placements.append(placement)
                    self.session.outline_tile_types[cpos] = ctype
                    log_engine(f"Self-connection (180°): Converting {etype} at {cpos} to {ctype}")
        
        return placements
    
    def _handle_s_shape_self_connection(self, first_pos: Tuple[int, int], first_type: str,
                                         last_pos: Tuple[int, int], last_type: str,
                                         wall_type: str, both_horizontal: bool) -> List[ObjectPlacement]:
        """
        Handle S-shaped 180° self-connection where first and last tiles have opposite types.
        
        For self-connections, opposite types (e.g. top+bottom) mean the stroke transitions
        from one terrain side to the other, creating an S-shape.
        
        Uses the same logic as _handle_s_shape_endpoint but adapted for self-connections
        where both tiles are part of the current stroke.
        
        The corner behavior follows the same pattern:
          - Same-side: tight corner = standard, open corner = swap both
          - Opposite-side: one corner deleted, other = center (fill)
        
        For self-connection S-shapes, we determine same-side vs opposite-side using
        the first tile's edge type and the relative position of the two tiles.
        """
        placements = []
        fx, fy = first_pos
        lx, ly = last_pos
        
        # For self-connection S-shapes, the "endpoint" analogy:
        # first_pos is the start of the stroke, last_pos is the end
        # We use first_type to determine same-side vs opposite-side
        # (same logic as _handle_s_shape_endpoint but with first_type as the reference)
        
        same_type = (first_type == last_type)
        
        if same_type:
            # Same-type S-shapes (e.g. top+top): ALWAYS same-side.
            # Both edges face the same way. The first corner (start of stroke)
            # is always the tight corner (standard), and the last corner (end
            # of stroke) is always the open corner (swap both).
            # is_outer depends on which tile is closer to the edge direction.
            is_same_side = True
            first_is_open = False  # first is always tight for same-type
            
            if both_horizontal:
                if first_type == 'top':
                    # outer if first is above last (terrain opens downward)
                    is_outer = (fy < ly)
                else:  # bottom
                    # outer if first is below last (terrain opens upward)
                    is_outer = (fy > ly)
            else:
                if first_type == 'left':
                    # outer if first is to the left of last
                    is_outer = (fx < lx)
                else:  # right
                    # outer if first is to the right of last
                    is_outer = (fx > lx)
        else:
            # Opposite-type S-shapes (e.g. top+bottom): determine same-side vs opposite-side
            if both_horizontal:
                if first_type == 'top':
                    is_same_side = (ly < fy)
                else:  # bottom
                    is_same_side = (ly > fy)
                is_outer = (first_type == 'top')
            else:
                if first_type == 'left':
                    is_same_side = (lx < fx)
                else:  # right
                    is_same_side = (lx > fx)
                is_outer = (first_type == 'left')
            first_is_open = False  # Not used for opposite-type
        
        # Standard corner lookups
        outer_lookup = {
            ('top', 'right'): 'top_right', ('top', 'left'): 'top_left',
            ('bottom', 'right'): 'bottom_right', ('bottom', 'left'): 'bottom_left',
            ('right', 'top'): 'top_right', ('right', 'bottom'): 'bottom_right',
            ('left', 'top'): 'top_left', ('left', 'bottom'): 'bottom_left',
        }
        inner_lookup = {
            ('top', 'right'): 'inner_top_right', ('top', 'left'): 'inner_top_left',
            ('bottom', 'right'): 'inner_bottom_right', ('bottom', 'left'): 'inner_bottom_left',
            ('right', 'top'): 'inner_bottom_left', ('right', 'bottom'): 'inner_top_left',
            ('left', 'top'): 'inner_bottom_right', ('left', 'bottom'): 'inner_top_right',
        }
        swap_both = {
            'top_left': 'inner_top_right', 'top_right': 'inner_top_left',
            'bottom_left': 'inner_bottom_right', 'bottom_right': 'inner_bottom_left',
            'inner_top_left': 'top_right', 'inner_top_right': 'top_left',
            'inner_bottom_left': 'bottom_right', 'inner_bottom_right': 'bottom_left',
        }
        
        standard_lookup = outer_lookup if is_outer else inner_lookup
        first_standard = standard_lookup.get((first_type, wall_type))
        last_standard = standard_lookup.get((last_type, wall_type))
        
        if is_same_side:
            # Same-side: tight corner = standard, open corner = swap both
            if same_type:
                # For same-type S-shapes, first_is_open determines which is open/tight
                if first_is_open:
                    first_corner = swap_both.get(first_standard) if first_standard else None
                    last_corner = last_standard
                else:
                    first_corner = first_standard
                    last_corner = swap_both.get(last_standard) if last_standard else None
            else:
                # For opposite-type S-shapes, first is tight, last is open
                first_corner = first_standard
                last_corner = swap_both.get(last_standard) if last_standard else None
            
            log_engine(f"S-shape self-connection (same-side): first={first_type}@{first_pos}, "
                       f"last={last_type}@{last_pos}, wall={wall_type}, is_outer={is_outer}, "
                       f"same_type={same_type}, first_is_open={first_is_open if same_type else 'N/A'}, "
                       f"first_corner={first_corner}, last_corner={last_corner}")
        else:
            # Opposite-side: first = deleted, last = center (fill)
            first_corner = None
            last_corner = 'center'
            
            log_engine(f"S-shape self-connection (opposite-side): first={first_type}@{first_pos}, "
                       f"last={last_type}@{last_pos}, wall={wall_type}, is_outer={is_outer}, "
                       f"first_corner=DELETED, last_corner=center(fill)")
        
        for ctype, cpos, etype in [
            (first_corner, first_pos, first_type),
            (last_corner, last_pos, last_type)
        ]:
            if ctype:
                tile_id = self.brush.get_terrain_tile(ctype)
                if tile_id is not None:
                    placement = ObjectPlacement(
                        tileset=self.tileset_idx,
                        object_id=tile_id,
                        layer=self.layer,
                        x=cpos[0],
                        y=cpos[1],
                        width=1,
                        height=1
                    )
                    placements.append(placement)
                    self.session.outline_tile_types[cpos] = ctype
                    log_engine(f"S-shape self-connection (180°): Converting {etype} at {cpos} to {ctype}")
        
        return placements
    
    def _check_parallel_endpoint_connection(self, endpoint_pos: Tuple[int, int], endpoint_type: str,
                                             existing_pos: Tuple[int, int], existing_type: str,
                                             is_last_endpoint: bool) -> List[ObjectPlacement]:
        """
        Handle 180° connection between a stroke endpoint and existing parallel terrain.
        
        The endpoint and existing terrain are parallel (both horizontal or both vertical)
        and within 8-neighbor distance. Two corners are placed: one replacing the endpoint
        tile, one at the existing terrain position.
        
        Two sub-cases:
          a. U-turn (opposite types, e.g. top+bottom): cardinal adjacency, two standard corners
          b. S-shape (same types, e.g. top+top): diagonal adjacency, asymmetric corners
        
        For S-shapes, the corner behavior depends on whether the edge faces toward or away
        from the step direction:
          - Same-side (edge faces toward step): tight corner = standard, open corner = swap both
          - Opposite-side (edge faces away from step): one corner deleted, other = center (fill)
        
        Args:
            endpoint_pos: Position of the stroke endpoint
            endpoint_type: Edge type of the endpoint
            existing_pos: Position of the existing parallel terrain
            existing_type: Edge type of the existing terrain
            is_last_endpoint: True if this is the last tile of the stroke
        
        Returns:
            List of ObjectPlacement for the two corner tiles, or empty list
        """
        placements = []
        ex, ey = endpoint_pos
        nx, ny = existing_pos
        
        horizontal_types = {'top', 'bottom'}
        both_horizontal = endpoint_type in horizontal_types and existing_type in horizontal_types
        is_s_shape = (endpoint_type == existing_type)
        
        # Collinear detection: same-type edges on the same row (horizontal) or
        # same column (vertical) are straight-line extensions, not corners.
        if is_s_shape:
            if both_horizontal and ey == ny:
                return placements
            elif not both_horizontal and ex == nx:
                return placements
        
        wall_type = None
        
        if both_horizontal:
            # Horizontal edges → wall is vertical (left or right)
            # Use x-offset to determine wall side when tiles are offset
            if nx < ex:
                wall_type = 'left'
            elif nx > ex:
                wall_type = 'right'
            else:
                # Same column — use stroke path to determine wall side
                path = self.session.stroke_path
                if len(path) < 2:
                    return placements
                if is_last_endpoint:
                    dx_end = path[-1][0] - path[-2][0]
                else:
                    dx_end = path[1][0] - path[0][0]
                # Opening is opposite to stroke direction at this endpoint
                if is_last_endpoint:
                    wall_type = 'right' if dx_end > 0 else 'left' if dx_end < 0 else None
                else:
                    wall_type = 'left' if dx_end > 0 else 'right' if dx_end < 0 else None
        else:
            # Vertical edges → wall is horizontal (top or bottom)
            if ny < ey:
                wall_type = 'top'
            elif ny > ey:
                wall_type = 'bottom'
            else:
                # Same row — use stroke path to determine wall side
                path = self.session.stroke_path
                if len(path) < 2:
                    return placements
                if is_last_endpoint:
                    dy_end = path[-1][1] - path[-2][1]
                else:
                    dy_end = path[1][1] - path[0][1]
                if is_last_endpoint:
                    wall_type = 'bottom' if dy_end > 0 else 'top' if dy_end < 0 else None
                else:
                    wall_type = 'top' if dy_end > 0 else 'bottom' if dy_end < 0 else None
        
        if not wall_type:
            return placements
        
        if is_s_shape:
            # For S-shapes in the same column/row, the wall_type from stroke direction
            # is correct when the endpoint is the "tight" tile (upper for horizontal,
            # left for vertical). When the endpoint is the "open" tile (lower/right),
            # the wall needs to be flipped.
            if both_horizontal and ex == nx:
                endpoint_is_lower = (ey > ny)
                if endpoint_is_lower:
                    wall_type = 'left' if wall_type == 'right' else 'right'
            elif not both_horizontal and ey == ny:
                endpoint_is_righter = (ex > nx)
                if endpoint_is_righter:
                    wall_type = 'top' if wall_type == 'bottom' else 'bottom'
            # S-shape: same edge types, diagonally adjacent
            return self._handle_s_shape_endpoint(
                endpoint_pos, endpoint_type, existing_pos, existing_type,
                wall_type, both_horizontal, is_last_endpoint
            )
        
        # U-turn: opposite edge types (top+bottom or left+right)
        # Corner 1 replaces the endpoint tile
        # Corner 2 goes at the existing terrain position
        # For 180° connections:
        #   - Horizontal (top+bottom): outer if top has lower y, inner if bottom has lower y
        #   - Vertical (left+right): outer if left has lower x, inner if right has lower x
        # Corner name = edge_type + wall_type (no left↔right swap for inner, unlike 90°)
        
        if both_horizontal:
            top_pos = endpoint_pos if endpoint_type == 'top' else existing_pos
            bottom_pos = endpoint_pos if endpoint_type == 'bottom' else existing_pos
            is_outer = top_pos[1] < bottom_pos[1]
        else:
            left_pos = endpoint_pos if endpoint_type == 'left' else existing_pos
            right_pos = endpoint_pos if endpoint_type == 'right' else existing_pos
            is_outer = left_pos[0] < right_pos[0]
        
        outer_lookup = {
            ('top', 'right'): 'top_right', ('right', 'top'): 'top_right',
            ('top', 'left'): 'top_left', ('left', 'top'): 'top_left',
            ('bottom', 'right'): 'bottom_right', ('right', 'bottom'): 'bottom_right',
            ('bottom', 'left'): 'bottom_left', ('left', 'bottom'): 'bottom_left',
        }
        # For 180° inner corners:
        #   Horizontal (top/bottom + left/right wall): direct combination
        #   Vertical (left/right + top/bottom wall): both components flipped
        inner_lookup = {
            ('top', 'right'): 'inner_top_right', ('top', 'left'): 'inner_top_left',
            ('bottom', 'right'): 'inner_bottom_right', ('bottom', 'left'): 'inner_bottom_left',
            ('right', 'top'): 'inner_bottom_left', ('right', 'bottom'): 'inner_top_left',
            ('left', 'top'): 'inner_bottom_right', ('left', 'bottom'): 'inner_top_right',
        }
        
        lookup = outer_lookup if is_outer else inner_lookup
        corner1_type = lookup.get((endpoint_type, wall_type))
        corner2_type = lookup.get((existing_type, wall_type))
        
        is_cardinal = (ex == nx or ey == ny)
        log_engine(f"Parallel endpoint connection (U-turn): endpoint={endpoint_type}@{endpoint_pos}, "
                   f"existing={existing_type}@{existing_pos}, wall={wall_type}, is_outer={is_outer}, "
                   f"cardinal={is_cardinal}, is_last={is_last_endpoint}, "
                   f"corner1={corner1_type}@endpoint, corner2={corner2_type}@existing")
        
        if corner1_type:
            tile_id = self.brush.get_terrain_tile(corner1_type)
            if tile_id is not None:
                placement = ObjectPlacement(
                    tileset=self.tileset_idx,
                    object_id=tile_id,
                    layer=self.layer,
                    x=ex,
                    y=ey,
                    width=1,
                    height=1
                )
                placements.append(placement)
                self.session.outline_tile_types[endpoint_pos] = corner1_type
                log_engine(f"Existing terrain connection (180°): Converting {endpoint_type} at {endpoint_pos} to {corner1_type}")
        
        if corner2_type:
            tile_id = self.brush.get_terrain_tile(corner2_type)
            if tile_id is not None:
                placement = ObjectPlacement(
                    tileset=self.tileset_idx,
                    object_id=tile_id,
                    layer=self.layer,
                    x=nx,
                    y=ny,
                    width=1,
                    height=1
                )
                placements.append(placement)
                log_engine(f"Existing terrain connection (180°): Converting {existing_type} at {existing_pos} to {corner2_type}")
        
        return placements
    
    def _handle_s_shape_endpoint(self, endpoint_pos: Tuple[int, int], endpoint_type: str,
                                  existing_pos: Tuple[int, int], existing_type: str,
                                  wall_type: str, both_horizontal: bool,
                                  is_last_endpoint: bool) -> List[ObjectPlacement]:
        """
        Handle S-shaped 180° connection where both edges are the same type.
        
        S-shapes occur when two parallel edges of the same type (e.g. top+top) are
        diagonally adjacent. The connecting wall creates an S-shape.
        
        Two sub-cases based on whether the edge faces toward or away from the step:
        
        Same-side (edge faces toward step direction):
          - Tight corner (closer to wall) = standard outer/inner corner
          - Open corner (farther from wall) = swap both inner/outer AND left/right
        
        Opposite-side (edge faces away from step direction):
          - One corner = deleted (no tile placed)
          - Other corner = center (fill tile)
        
        Horizontal cases (top+top or bottom+bottom):
          - top+top, existing above: same-side → top=swap, bottom=correct
          - top+top, existing below: opposite-side → top=delete, bottom=fill
          - bottom+bottom, existing above: opposite-side → top=fill, bottom=delete
          - bottom+bottom, existing below: same-side → top=correct, bottom=swap
        
        Vertical cases (left+left or right+right):
          - left+left, existing left: same-side → left=swap, right=correct
          - left+left, existing right: opposite-side → left=delete, right=fill
          - right+right, existing left: opposite-side → left=fill, right=delete
          - right+right, existing right: same-side → left=correct, right=swap
        """
        placements = []
        ex, ey = endpoint_pos
        nx, ny = existing_pos
        
        # Same-type S-shapes are ALWAYS same-side (both edges face the same way).
        # The distinction is which tile is "open" (swap-both) vs "tight" (standard).
        #
        # Position-based rule (independent of which tile is endpoint/existing):
        #   Horizontal: upper tile (lower y) = tight, lower tile (higher y) = open
        #   Vertical: left tile (lower x) = tight, right tile (higher x) = open
        
        is_same_side = True  # Always same-side for same-type edges
        
        if both_horizontal:
            endpoint_is_open = (ey > ny)  # endpoint is open if it's the lower tile
        else:
            endpoint_is_open = (ex > nx)  # endpoint is open if it's the right tile
        
        # Outer vs inner is fixed based on edge type:
        #   top+top: outer (ground). bottom+bottom: inner (ceiling).
        #   left+left: outer. right+right: inner.
        if both_horizontal:
            is_outer = (endpoint_type == 'top')
        else:
            is_outer = (endpoint_type == 'left')
        
        # Standard corner lookup (same as U-turn outer)
        outer_lookup = {
            ('top', 'right'): 'top_right', ('top', 'left'): 'top_left',
            ('bottom', 'right'): 'bottom_right', ('bottom', 'left'): 'bottom_left',
            ('right', 'top'): 'top_right', ('right', 'bottom'): 'bottom_right',
            ('left', 'top'): 'top_left', ('left', 'bottom'): 'bottom_left',
        }
        # Standard inner corner lookup (same as U-turn inner)
        inner_lookup = {
            ('top', 'right'): 'inner_top_right', ('top', 'left'): 'inner_top_left',
            ('bottom', 'right'): 'inner_bottom_right', ('bottom', 'left'): 'inner_bottom_left',
            ('right', 'top'): 'inner_bottom_left', ('right', 'bottom'): 'inner_top_left',
            ('left', 'top'): 'inner_bottom_right', ('left', 'bottom'): 'inner_top_right',
        }
        
        # "Swap both" lookup: swap inner↔outer AND left↔right
        swap_both = {
            'top_left': 'inner_top_right', 'top_right': 'inner_top_left',
            'bottom_left': 'inner_bottom_right', 'bottom_right': 'inner_bottom_left',
            'inner_top_left': 'top_right', 'inner_top_right': 'top_left',
            'inner_bottom_left': 'bottom_right', 'inner_bottom_right': 'bottom_left',
        }
        
        # Both tiles have the same edge type, so (edge_type, wall) gives the
        # same standard corner for both. The tight corner keeps this standard,
        # the open corner gets swap-both (which naturally produces the correct
        # complementary corner). This matches the self-connection handler.
        standard_lookup = outer_lookup if is_outer else inner_lookup
        endpoint_standard = standard_lookup.get((endpoint_type, wall_type))
        existing_standard = standard_lookup.get((existing_type, wall_type))
        
        if is_same_side:
            # Same-side S-shape: tight corner = standard, open corner = swap both
            # The tile in the direction the edge faces = open (swap both)
            # The tile opposite to the edge direction = tight (standard)
            
            if endpoint_is_open:
                endpoint_corner = swap_both.get(endpoint_standard) if endpoint_standard else None
                existing_corner = existing_standard  # tight = correct
            else:
                endpoint_corner = endpoint_standard  # tight = correct
                existing_corner = swap_both.get(existing_standard) if existing_standard else None
            
            log_engine(f"S-shape endpoint (same-side): endpoint={endpoint_type}@{endpoint_pos}, "
                       f"existing={existing_type}@{existing_pos}, wall={wall_type}, is_outer={is_outer}, "
                       f"endpoint_is_open={endpoint_is_open}, "
                       f"endpoint_corner={endpoint_corner}, existing_corner={existing_corner}")
        else:
            # Opposite-side S-shape: one corner deleted, other = center (fill)
            # The corner in the direction the edge faces = deleted (no tile)
            # The corner opposite to the edge direction = center (fill)
            #
            # For horizontal:
            #   top+top, existing below: top(endpoint)=delete, bottom(existing)=fill
            #   bottom+bottom, existing above: top(existing)=fill, bottom(endpoint)=delete
            # For vertical:
            #   left+left, existing right: left(endpoint)=delete, right(existing)=fill
            #   right+right, existing left: left(existing)=fill, right(endpoint)=delete
            #
            # The endpoint is always the "deleted" one (it faces away from the step),
            # and the existing is always the "fill" one.
            
            endpoint_corner = None  # deleted
            existing_corner = 'center'  # fill
            
            log_engine(f"S-shape endpoint (opposite-side): endpoint={endpoint_type}@{endpoint_pos}, "
                       f"existing={existing_type}@{existing_pos}, wall={wall_type}, is_outer={is_outer}, "
                       f"endpoint_corner=DELETED, existing_corner=center(fill)")
        
        # Place endpoint corner (corner 1)
        if endpoint_corner:
            tile_id = self.brush.get_terrain_tile(endpoint_corner)
            if tile_id is not None:
                placement = ObjectPlacement(
                    tileset=self.tileset_idx,
                    object_id=tile_id,
                    layer=self.layer,
                    x=ex,
                    y=ey,
                    width=1,
                    height=1
                )
                placements.append(placement)
                self.session.outline_tile_types[endpoint_pos] = endpoint_corner
                log_engine(f"S-shape (180°): Converting {endpoint_type} at {endpoint_pos} to {endpoint_corner}")
        
        # Place existing corner (corner 2)
        if existing_corner:
            tile_id = self.brush.get_terrain_tile(existing_corner)
            if tile_id is not None:
                placement = ObjectPlacement(
                    tileset=self.tileset_idx,
                    object_id=tile_id,
                    layer=self.layer,
                    x=nx,
                    y=ny,
                    width=1,
                    height=1
                )
                placements.append(placement)
                log_engine(f"S-shape (180°): Converting {existing_type} at {existing_pos} to {existing_corner}")
        
        return placements
    
    def _check_existing_terrain_connection(self) -> List[ObjectPlacement]:
        """
        Check if the first and last tiles of the stroke connect to existing terrain
        from previous strokes. If so, convert the endpoint to a corner tile.
        
        This handles the case where a user draws a rectangle with 4 separate strokes -
        each stroke's first tile overlaps with the previous stroke's last tile,
        and should become a corner if the directions are perpendicular.
        
        Returns:
            List of ObjectPlacement for corner tiles to replace edge tiles
        """
        placements = []
        
        if len(self.session.outline_positions) < 1:
            return placements
        
        # Find first and last EDGE positions (skip slopes and corners)
        edge_types = {'top', 'bottom', 'left', 'right'}
        
        first_pos = None
        first_type = None
        for pos in self.session.outline_positions:
            t = self.session.outline_tile_types.get(pos, 'top')
            if t in edge_types:
                first_pos, first_type = pos, t
                break
        
        if first_pos:
            corner_placements = self._check_endpoint_connection(first_pos, first_type, is_last_endpoint=False)
            placements.extend(corner_placements)
        
        # Check last edge position (only if different from first)
        last_pos = None
        last_type = None
        for pos in reversed(self.session.outline_positions):
            t = self.session.outline_tile_types.get(pos, 'top')
            if t in edge_types:
                last_pos, last_type = pos, t
                break
        
        if last_pos and last_pos != first_pos:
            corner_placements = self._check_endpoint_connection(last_pos, last_type, is_last_endpoint=True)
            placements.extend(corner_placements)
        
        return placements
    
    def _check_endpoint_connection(self, pos: Tuple[int, int], tile_type: str,
                                    is_last_endpoint: bool = True) -> List[ObjectPlacement]:
        """
        Check if a stroke endpoint should become a corner based on adjacent existing terrain.
        
        Handles four cases:
        1. Overlapping perpendicular: endpoint and existing terrain at same position → corner
        2. Neighbor perpendicular: endpoint near perpendicular existing terrain → corner at gap
        3. Overlapping parallel: endpoint overlaps parallel existing terrain → two corners (180°)
        4. Neighbor parallel: endpoint near parallel existing terrain → two corners (180°)
        
        Args:
            pos: Position of the endpoint
            tile_type: Type of the endpoint tile ('top', 'bottom', 'left', 'right')
            is_last_endpoint: True if this is the last tile of the stroke, False if first
        
        Returns:
            List of ObjectPlacement for corner tiles
        """
        x, y = pos
        
        # Determine if endpoint is horizontal or vertical
        horizontal_types = {'top', 'bottom'}
        vertical_types = {'left', 'right'}
        endpoint_is_horizontal = tile_type in horizontal_types
        
        # CASE 0: Check for OVERLAPPING perpendicular terrain at the SAME position
        # This handles the case where the new stroke starts on top of existing terrain
        # NOTE: We use _object_database here, NOT existing_tiles, because existing_tiles
        # is modified during _finalize_deferred_painting() BEFORE this check runs.
        # _object_database still has the original tiles from previous strokes.
        same_pos_key = (x, y, self.layer)
        if same_pos_key in self._object_database:
            existing_type = self._get_tile_type_from_database(x, y)
            if existing_type and existing_type in ['top', 'bottom', 'left', 'right']:
                if self._are_perpendicular(tile_type, existing_type):
                    # Determine inner vs outer corner based on the stroke direction
                    # We need to look at where the stroke is going FROM this position
                    corner_type = self._determine_corner_for_overlap(tile_type, existing_type, pos)
                    
                    if corner_type:
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
                            log_engine(f"Existing terrain connection (overlap): Converting {tile_type} at ({x}, {y}) to {corner_type} (overlapping {existing_type})")
                            self.session.outline_tile_types[pos] = corner_type
                            return [placement]
        
        # Check all 8 neighbors for existing terrain
        # Cardinal neighbors first, then diagonals — this ensures parallel
        # connections (U-turns) prefer cardinal adjacency over diagonal
        neighbor_offsets = [
            (0, -1), (0, 1), (-1, 0), (1, 0),   # cardinal
            (-1, -1), (1, -1), (-1, 1), (1, 1),  # diagonal
        ]
        
        for dx, dy in neighbor_offsets:
            nx, ny = x + dx, y + dy
            neighbor_key = (nx, ny, self.layer)
            
            # Skip if no existing terrain at this neighbor
            if neighbor_key not in self._object_database:
                continue
            
            # Skip if this neighbor is part of the current stroke
            if (nx, ny) in self.session.outline_positions:
                continue
            
            # Get the type of the existing terrain
            # Use _object_database (not existing_tiles) for consistency with Case 0
            existing_type = self._get_tile_type_from_database(nx, ny)
            if not existing_type or existing_type.startswith('slope_'):
                continue
            
            # Skip corners and inner corners - only connect to edges
            if existing_type not in ['top', 'bottom', 'left', 'right']:
                continue
            
            if self._are_perpendicular(tile_type, existing_type):
                # 90° connection: single corner
                corner_pos = self._find_corner_position(pos, tile_type, (nx, ny), existing_type)
                if corner_pos is None:
                    continue
                
                cx, cy = corner_pos
                if abs(cx - x) > 1 or abs(cy - y) > 1:
                    continue
                if abs(cx - nx) > 1 or abs(cy - ny) > 1:
                    continue
                
                corner_type = self._determine_corner_for_endpoint(
                    tile_type, existing_type, pos, (nx, ny), corner_pos,
                    is_last_endpoint=is_last_endpoint
                )
                
                if corner_type:
                    tile_id = self.brush.get_terrain_tile(corner_type)
                    if tile_id is not None:
                        placement = ObjectPlacement(
                            tileset=self.tileset_idx,
                            object_id=tile_id,
                            layer=self.layer,
                            x=cx,
                            y=cy,
                            width=1,
                            height=1
                        )
                        
                        if corner_pos == pos:
                            self.session.outline_tile_types[pos] = corner_type
                            log_engine(f"Existing terrain connection: Converting {tile_type} at ({x}, {y}) to {corner_type} (adjacent to {existing_type} at ({nx}, {ny}))")
                        else:
                            log_engine(f"Existing terrain connection (gap): Placing {corner_type} at ({cx}, {cy}) to connect {tile_type} at ({x}, {y}) with {existing_type} at ({nx}, {ny})")
                        
                        return [placement]
            
            elif self._are_parallel(tile_type, existing_type):
                # 180° connection: two corners (U-turn or S-shape)
                result = self._check_parallel_endpoint_connection(
                    pos, tile_type, (nx, ny), existing_type, is_last_endpoint
                )
                if result:
                    return result
        
        return []
    
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
    
    def _determine_self_connection_corner(self, first_pos: Tuple[int, int], first_type: str,
                                           last_pos: Tuple[int, int], last_type: str) -> Optional[str]:
        """
        Determine corner type for self-connection based on stroke direction.
        
        Uses the stroke's last segment direction and the direction needed to reach
        the first position to determine if it's a CW (outer) or CCW (inner) turn.
        
        Args:
            first_pos: Position of the first tile in the stroke
            first_type: Edge type of the first tile
            last_pos: Position of the last tile in the stroke
            last_type: Edge type of the last tile
        
        Returns:
            Corner type string (inner or outer)
        """
        # Use stroke_path (raw path, not reordered by slopes) for direction inference
        path = self.session.stroke_path
        
        # Get the direction of the last segment of the stroke
        if len(path) >= 2:
            dx_last = path[-1][0] - path[-2][0]
            dy_last = path[-1][1] - path[-2][1]
            
            if dx_last > 0:
                old_dir = 'left_to_right'
            elif dx_last < 0:
                old_dir = 'right_to_left'
            elif dy_last > 0:
                old_dir = 'top_to_bottom'
            else:
                old_dir = 'bottom_to_top'
        else:
            old_dir = 'left_to_right' if last_type in ['top', 'bottom'] else 'top_to_bottom'
        
        # Get direction of the first segment (how the stroke started)
        if len(path) >= 2:
            dx_first = path[1][0] - path[0][0]
            dy_first = path[1][1] - path[0][1]
            
            if dx_first > 0:
                new_dir = 'left_to_right'
            elif dx_first < 0:
                new_dir = 'right_to_left'
            elif dy_first > 0:
                new_dir = 'top_to_bottom'
            else:
                new_dir = 'bottom_to_top'
        else:
            new_dir = 'left_to_right' if first_type in ['top', 'bottom'] else 'top_to_bottom'
        
        # Determine if this is a CW or CCW turn
        cw_turns = {
            ('left_to_right', 'top_to_bottom'),
            ('top_to_bottom', 'right_to_left'),
            ('right_to_left', 'bottom_to_top'),
            ('bottom_to_top', 'left_to_right'),
        }
        is_cw = (old_dir, new_dir) in cw_turns
        
        # Get base corner type from edge types
        # For CCW (inner), swap left↔right in the corner name
        types = {first_type, last_type}
        
        if types == {'top', 'left'}:
            return 'top_left' if is_cw else 'inner_top_right'
        elif types == {'top', 'right'}:
            return 'top_right' if is_cw else 'inner_top_left'
        elif types == {'bottom', 'left'}:
            return 'bottom_left' if is_cw else 'inner_bottom_right'
        elif types == {'bottom', 'right'}:
            return 'bottom_right' if is_cw else 'inner_bottom_left'
        
        return None
    
    def _determine_corner_for_adjacent(self, tile_type: str, neighbor_type: str,
                                        pos: Tuple[int, int], 
                                        neighbor_pos: Tuple[int, int]) -> Optional[str]:
        """
        Determine if a tile should become a corner based on an adjacent perpendicular tile.
        
        Handles both OUTER corners (CW drawing, convex) and INNER corners (CCW drawing, concave).
        
        The key insight:
        - Outer corner: neighbor is on the "expected" side (e.g., left wall to the left of top edge)
        - Inner corner: neighbor is on the "opposite" side (e.g., left wall to the right of top edge)
        
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
        
        # For each tile type, determine if we need an outer or inner corner
        # based on where the perpendicular neighbor is located
        
        if tile_type == 'top':
            # Top edge faces upward (outside is above)
            if neighbor_type == 'left':
                if dx <= 0:
                    # Left wall is to our left → outer corner (CW: ground to left wall)
                    return 'top_left'
                else:
                    # Left wall is to our right → inner corner (CCW: ground to left wall)
                    return 'inner_top_left'
            elif neighbor_type == 'right':
                if dx >= 0:
                    # Right wall is to our right → outer corner (CW: left wall to ground via right)
                    return 'top_right'
                else:
                    # Right wall is to our left → inner corner (CCW: ceiling to right wall)
                    return 'inner_top_right'
        
        elif tile_type == 'bottom':
            # Bottom edge faces downward (outside is below)
            if neighbor_type == 'left':
                if dx <= 0:
                    # Left wall is to our left → outer corner
                    return 'bottom_left'
                else:
                    # Left wall is to our right → inner corner (CCW: left wall to ceiling)
                    return 'inner_bottom_left'
            elif neighbor_type == 'right':
                if dx >= 0:
                    # Right wall is to our right → outer corner
                    return 'bottom_right'
                else:
                    # Right wall is to our left → inner corner (CCW: ceiling to right wall)
                    return 'inner_bottom_right'
        
        elif tile_type == 'left':
            # Left edge faces leftward (outside is to the left)
            if neighbor_type == 'top':
                if dy <= 0:
                    # Top is above → outer corner
                    return 'top_left'
                else:
                    # Top is below → inner corner (CCW: right wall to ground)
                    return 'inner_top_left'
            elif neighbor_type == 'bottom':
                if dy >= 0:
                    # Bottom is below → outer corner
                    return 'bottom_left'
                else:
                    # Bottom is above → inner corner
                    return 'inner_bottom_left'
        
        elif tile_type == 'right':
            # Right edge faces rightward (outside is to the right)
            if neighbor_type == 'top':
                if dy <= 0:
                    # Top is above → outer corner
                    return 'top_right'
                else:
                    # Top is below → inner corner
                    return 'inner_top_right'
            elif neighbor_type == 'bottom':
                if dy >= 0:
                    # Bottom is below → outer corner
                    return 'bottom_right'
                else:
                    # Bottom is above → inner corner
                    return 'inner_bottom_right'
        
        return None
    
    def _determine_corner_for_endpoint(self, endpoint_type: str, existing_type: str,
                                        endpoint_pos: Tuple[int, int],
                                        existing_pos: Tuple[int, int],
                                        corner_pos: Tuple[int, int],
                                        is_last_endpoint: bool = True) -> Optional[str]:
        """
        Determine corner type for a stroke endpoint connecting to existing terrain
        at a gap position (non-overlapping).
        
        Pure geometry approach based on the player-side angle at the corner:
        
        Each edge has an "inside" (player side):
          top (ground): player is below (+y)
          bottom (ceiling): player is above (-y)
          left (left wall): player is to the right (+x)
          right (right wall): player is to the left (-x)
        
        Check if the corner is on the inside of the endpoint's edge:
          - If yes → outer corner (270° player-side angle, convex)
          - If no  → inner corner (90° player-side angle, concave)
        
        This is drawing-order independent — it only depends on the geometric
        relationship between the corner position and the endpoint position.
        
        Args:
            endpoint_type: Type of the stroke endpoint ('top', 'bottom', 'left', 'right')
            existing_type: Type of the existing terrain edge
            endpoint_pos: Position of the stroke endpoint
            existing_pos: Position of the existing terrain
            corner_pos: Computed corner position
            is_last_endpoint: True if this is the last tile of the stroke, False if first
        
        Returns:
            Corner type string (outer or inner with left↔right swap)
        """
        nx, ny = existing_pos
        cx, cy = corner_pos
        ex, ey = endpoint_pos
        
        # Player-side angle approach (drawing-order independent).
        #
        # Each edge has an "inside" (player side) direction:
        #   top (ground): player below (+y)
        #   bottom (ceiling): player above (-y)
        #   left (left wall): player to the right (+x)
        #   right (right wall): player to the left (-x)
        #
        # For perpendicular edges meeting at a corner, check BOTH edges:
        #   1. Is the endpoint on the inside of the existing edge?
        #   2. Is the existing terrain on the inside of the endpoint edge?
        #
        # For diagonal neighbors, both checks agree (one axis differs).
        # For side-by-side neighbors (same row/column), one check has equal
        # coordinates (strict inequality → False), so we use OR to ensure
        # the other check catches it.
        #
        # Outer corner (270° player-side angle): at least one check is True
        # Inner corner (90° player-side angle): both checks are False
        
        # Check 1: endpoint on inside of existing edge
        endpoint_on_inside_of_existing = {
            'top': ey > ny,      # ground: player below → endpoint below existing
            'bottom': ey < ny,   # ceiling: player above → endpoint above existing
            'left': ex > nx,     # left wall: player right → endpoint right of existing
            'right': ex < nx,    # right wall: player left → endpoint left of existing
        }
        
        # Check 2: existing on inside of endpoint edge
        existing_on_inside_of_endpoint = {
            'top': ny > ey,      # ground: player below → existing below endpoint
            'bottom': ny < ey,   # ceiling: player above → existing above endpoint
            'left': nx > ex,     # left wall: player right → existing right of endpoint
            'right': nx < ex,    # right wall: player left → existing left of endpoint
        }
        
        check1 = endpoint_on_inside_of_existing.get(existing_type, False)
        check2 = existing_on_inside_of_endpoint.get(endpoint_type, False)
        is_outer = check1 or check2
        
        # Outer corner lookup
        outer_lookup = {
            ('top', 'right'): 'top_right',
            ('right', 'top'): 'top_right',
            ('top', 'left'): 'top_left',
            ('left', 'top'): 'top_left',
            ('bottom', 'right'): 'bottom_right',
            ('right', 'bottom'): 'bottom_right',
            ('bottom', 'left'): 'bottom_left',
            ('left', 'bottom'): 'bottom_left',
        }
        
        # Inner corner lookup: swap outer→inner AND left↔right
        inner_lookup = {
            ('top', 'right'): 'inner_top_left',
            ('right', 'top'): 'inner_top_left',
            ('top', 'left'): 'inner_top_right',
            ('left', 'top'): 'inner_top_right',
            ('bottom', 'right'): 'inner_bottom_left',
            ('right', 'bottom'): 'inner_bottom_left',
            ('bottom', 'left'): 'inner_bottom_right',
            ('left', 'bottom'): 'inner_bottom_right',
        }
        
        lookup = outer_lookup if is_outer else inner_lookup
        corner_type = lookup.get((endpoint_type, existing_type))
        
        log_engine(f"Endpoint corner (geometry): endpoint={endpoint_type}@{endpoint_pos}, "
                   f"existing={existing_type}@{existing_pos}, corner@{corner_pos}, "
                   f"check1={check1}, check2={check2}, is_outer={is_outer} -> {corner_type}")
        
        return corner_type
    
    def _determine_corner_for_overlap(self, new_type: str, existing_type: str, 
                                       pos: Tuple[int, int]) -> Optional[str]:
        """
        Determine corner type when the new stroke overlaps with existing perpendicular terrain.
        
        Uses the same logic as _get_corner_type by inferring the "old direction" of
        existing terrain from which way it extends from the overlap position.
        
        Args:
            new_type: Type of the new stroke's edge at this position
            existing_type: Type of the existing terrain's edge at this position
            pos: The overlapping position
        
        Returns:
            Corner type string (inner or outer)
        """
        x, y = pos
        
        # Find the new stroke direction by looking at the next position
        stroke_positions = self.session.outline_positions
        try:
            idx = stroke_positions.index(pos)
        except ValueError:
            return None
        
        # Determine new stroke direction
        if idx < len(stroke_positions) - 1:
            next_pos = stroke_positions[idx + 1]
            stroke_dx = next_pos[0] - x
            stroke_dy = next_pos[1] - y
        elif idx > 0:
            prev_pos = stroke_positions[idx - 1]
            stroke_dx = x - prev_pos[0]
            stroke_dy = y - prev_pos[1]
        else:
            return None
        
        # Convert to direction enum
        if stroke_dx > 0:
            new_dir = 'left_to_right'
        elif stroke_dx < 0:
            new_dir = 'right_to_left'
        elif stroke_dy > 0:
            new_dir = 'top_to_bottom'
        elif stroke_dy < 0:
            new_dir = 'bottom_to_top'
        else:
            return None
        
        # Infer the "old direction" of existing terrain by checking neighbors
        # Look for adjacent tiles of the same type to see which way terrain extends
        old_dir = self._infer_terrain_direction(pos, existing_type)
        if old_dir is None:
            return None
        
        # Determine corner based on edge types and turn direction
        # For overlapping strokes, we need to consider:
        # 1. Which edge types meet (existing_type + new_type from function params)
        # 2. Whether the turn is clockwise (outer) or counter-clockwise (inner)
        #
        # Turn direction is determined by: old_dir → new_dir
        # CW turns: left_to_right→top_to_bottom, top_to_bottom→right_to_left,
        #           right_to_left→bottom_to_top, bottom_to_top→left_to_right
        # CCW turns: the opposites
        
        # Determine if this is a CW or CCW turn
        cw_turns = {
            ('left_to_right', 'top_to_bottom'),
            ('top_to_bottom', 'right_to_left'),
            ('right_to_left', 'bottom_to_top'),
            ('bottom_to_top', 'left_to_right'),
        }
        is_cw = (old_dir, new_dir) in cw_turns
        
        # Direct mapping based on edge pairs and turn direction
        # For overlapping strokes, CW turns (per cw_turns) actually produce INNER corners
        # because both strokes are going "away" from the corner position.
        # This is the opposite of continuous strokes where CW = outer.
        corner_map = {
            # Horizontal existing + vertical new
            ('top', 'left', True): 'inner_top_right',  # ground extends right, right wall goes down
            ('top', 'left', False): 'top_left',        # outer corner
            ('top', 'right', True): 'inner_top_left',  # ground extends right, left wall goes down
            ('top', 'right', False): 'top_right',      # outer corner
            ('bottom', 'left', True): 'inner_bottom_right', # ceiling extends right, right wall goes up
            ('bottom', 'left', False): 'bottom_left',  # outer corner
            ('bottom', 'right', True): 'inner_bottom_left', # ceiling extends right, left wall goes up
            ('bottom', 'right', False): 'bottom_right', # outer corner
            
            # Vertical existing + horizontal new
            # Note: 'left' edge = right wall, 'right' edge = left wall
            ('left', 'top', True): 'inner_top_right',  # right wall extends down, ground goes right
            ('left', 'top', False): 'top_left',        # outer corner
            ('left', 'bottom', True): 'inner_bottom_right', # right wall extends up, ceiling goes right
            ('left', 'bottom', False): 'bottom_left',  # outer corner
            ('right', 'top', True): 'inner_top_left',  # left wall extends down, ground goes right
            ('right', 'top', False): 'top_right',      # outer corner
            ('right', 'bottom', True): 'inner_bottom_left', # left wall extends up, ceiling goes right
            ('right', 'bottom', False): 'bottom_right', # outer corner
        }
        
        corner_type = corner_map.get((existing_type, new_type, is_cw))
        log_engine(f"Overlap corner: existing={existing_type}, old_dir={old_dir}, new_dir={new_dir} -> {corner_type}")
        return corner_type
    
    def _infer_terrain_direction(self, pos: Tuple[int, int], tile_type: str) -> Optional[str]:
        """
        Infer the painting direction of existing terrain by checking which way it extends.
        
        The direction represents how a continuous stroke would have ARRIVED at this position.
        This is the opposite of which way the terrain extends.
        
        For horizontal terrain (top/bottom): check left/right neighbors
        For vertical terrain (left/right): check up/down neighbors
        
        Args:
            pos: Position of the terrain tile
            tile_type: Type of the terrain ('top', 'bottom', 'left', 'right')
        
        Returns:
            Inferred direction ('left_to_right', 'right_to_left', etc.) or None
        """
        x, y = pos
        
        # NOTE: We use _object_database here, NOT existing_tiles, because existing_tiles
        # is modified during _finalize_deferred_painting() BEFORE this check runs.
        
        if tile_type in ['top', 'bottom']:
            # Horizontal terrain - check left and right neighbors
            left_key = (x - 1, y, self.layer)
            right_key = (x + 1, y, self.layer)
            
            has_left = left_key in self._object_database
            has_right = right_key in self._object_database
            
            if has_right and not has_left:
                # Terrain extends to the right, so this is the left end
                # The stroke was painted LEFT-TO-RIGHT (going right)
                return 'left_to_right'
            elif has_left and not has_right:
                # Terrain extends to the left, so this is the right end
                # The stroke was painted RIGHT-TO-LEFT (going left)
                return 'right_to_left'
            elif has_left and has_right:
                # Middle of terrain - can't determine direction clearly
                return 'left_to_right'  # Default
            else:
                # Single tile - default
                return 'left_to_right'
        
        elif tile_type in ['left', 'right']:
            # Vertical terrain - check up and down neighbors
            up_key = (x, y - 1, self.layer)
            down_key = (x, y + 1, self.layer)
            
            has_up = up_key in self._object_database
            has_down = down_key in self._object_database
            
            if has_down and not has_up:
                # Terrain extends downward, so this is the top end
                # The stroke was painted TOP-TO-BOTTOM (going down)
                return 'top_to_bottom'
            elif has_up and not has_down:
                # Terrain extends upward, so this is the bottom end
                # The stroke was painted BOTTOM-TO-TOP (going up)
                return 'bottom_to_top'
            elif has_up and has_down:
                # Middle of terrain
                return 'top_to_bottom'  # Default
            else:
                # Single tile
                return 'top_to_bottom'
        
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
    
    def _check_existing_terrain(self, connection_positions: set = None) -> Tuple[List[ObjectPlacement], List[Tuple[int, int, int]]]:
        """
        Check existing terrain around the painted stroke and make modifications.
        
        Rules:
        - Border tiles facing same way that are "outside" → delete
        - Border tiles facing same way that are "inside" → replace with center
        - Corner tiles check BOTH cardinal directions
        - 90° border tiles within 8-neighbor → create corner
        
        Positions in connection_positions are protected from deletion/replacement
        because they were already handled by the connection logic (Steps 1 & 2).
        
        Args:
            connection_positions: Set of (x, y, layer) positions modified by
                connection checks that should not be deleted or replaced.
        
        Returns:
            Tuple of (placements_to_add, positions_to_delete)
        """
        placements = []
        deletions = []
        positions_to_replace = set()  # Track positions we're replacing to avoid duplicates
        if connection_positions is None:
            connection_positions = set()
        
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
                # Skip positions that are part of the current stroke or were modified by connection logic
                if outside_key in self.session.existing_tiles and outside_key not in connection_positions and (outside_x, outside_y) not in painted_positions:
                    existing_type = self._get_tile_type_at(outside_x, outside_y)
                    # Check if the existing tile has a border facing the same direction
                    if existing_type and self._has_border_facing(existing_type, border_direction):
                        # Skip if both the painted tile and existing tile are the same
                        # simple edge type. Two parallel same-type edges 1 tile apart
                        # represent separate terrain segments (S-shape) that should coexist.
                        simple_edges = {'top', 'bottom', 'left', 'right'}
                        if existing_type in simple_edges and tile_type == existing_type:
                            log_engine(f"Terrain-aware: Skip delete {existing_type} at ({outside_x}, {outside_y}) - same edge type coexistence")
                        elif outside_key not in deletions:
                            deletions.append(outside_key)
                            log_engine(f"Terrain-aware: Delete {existing_type} at ({outside_x}, {outside_y}) - outside border")
                
                # Check if there's existing terrain inside that faces the same way
                if inside_key in self.session.existing_tiles and (inside_x, inside_y) not in painted_positions and inside_key not in connection_positions:
                    if inside_key in positions_to_replace:
                        continue
                    existing_type = self._get_tile_type_at(inside_x, inside_y)
                    if existing_type and self._has_border_facing(existing_type, border_direction):
                        # Skip if both are the same simple edge type (S-shape coexistence)
                        simple_edges = {'top', 'bottom', 'left', 'right'}
                        if existing_type in simple_edges and tile_type == existing_type:
                            log_engine(f"Terrain-aware: Skip replace {existing_type} at ({inside_x}, {inside_y}) - same edge type coexistence")
                            continue
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
    
    def _get_tile_type_from_database(self, x: int, y: int) -> Optional[str]:
        """
        Get the tile type at a position from the object database (not existing_tiles).
        
        This is used when we need to check ORIGINAL tiles from previous strokes,
        before the current stroke's tiles were added to existing_tiles.
        
        Args:
            x, y: Tile coordinates
        
        Returns:
            Tile type string, or None if not found or not a known tile
        """
        key = (x, y, self.layer)
        if key not in self._object_database:
            return None
        
        tile_id = self._object_database[key]
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
    
    def _are_parallel(self, type1: str, type2: str) -> bool:
        """Check if two border types are parallel (same or opposite direction)"""
        horizontal = {'top', 'bottom'}
        vertical = {'left', 'right'}
        return (type1 in horizontal and type2 in horizontal) or \
               (type1 in vertical and type2 in vertical)
    
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
