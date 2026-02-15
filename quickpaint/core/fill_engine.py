"""
Fill Engine - Handles flood-fill operations for the Fill Paint Tool.

Provides:
- Flood-fill algorithm that respects zone boundaries
- Fill area calculation and preview
- Object placement for fill operations
"""
from typing import Optional, List, Set, Tuple, Dict
from collections import deque
from dataclasses import dataclass
from enum import Enum, auto

from PyQt6 import QtCore


# Maximum fill area before showing warning
MAX_FILL_AREA = 2048

# Overpaint size - extra tiles outside zone boundaries
OVERPAINT_SIZE = 4


class FillState(Enum):
    """States for the fill tool"""
    IDLE = auto()
    PREVIEW = auto()  # Showing fill area preview
    WAITING_CONFIRM = auto()  # Waiting for user to confirm large fill
    CONFIRMED = auto()  # Fill confirmed, ready to place


@dataclass
class FillResult:
    """Result of a fill operation"""
    positions: Set[Tuple[int, int]]  # Positions to fill
    exceeded_limit: bool  # True if area > MAX_FILL_AREA (stopped early)
    outside_zone: bool  # True if click was outside any zone
    interrupted: bool = False  # True if fill was stopped early at limit
    
    @property
    def count(self) -> int:
        return len(self.positions)


class FillEngine(QtCore.QObject):
    """
    Engine for flood-fill painting operations.
    
    Signals:
        fill_preview_updated: Emitted when fill preview changes (positions)
        fill_confirmed: Emitted when fill is confirmed (positions)
        fill_cancelled: Emitted when fill is cancelled
        fill_warning: Emitted when fill area exceeds limit (count)
    """
    
    # Signals
    fill_preview_updated = QtCore.pyqtSignal(list)  # List of (x, y) positions
    fill_confirmed = QtCore.pyqtSignal(list)  # List of (x, y) positions
    fill_cancelled = QtCore.pyqtSignal()
    fill_warning = QtCore.pyqtSignal(int)  # Number of tiles
    
    def __init__(self):
        super().__init__()
        
        self._state = FillState.IDLE
        self._fill_positions: Set[Tuple[int, int]] = set()
        self._fill_object_id: Optional[int] = None
        self._tileset_idx: int = 0
        self._layer: int = 1
        
        # Zone bounds callback - should return (x, y, width, height) or None
        self._get_zone_bounds = None
        
        # Tile occupied callback - should return True if tile is occupied
        self._is_tile_occupied = None
        
        # Stored state for continue_fill
        self._zone_bounds: Optional[Tuple[int, int, int, int]] = None
        self._start_pos: Optional[Tuple[int, int]] = None
    
    @property
    def state(self) -> FillState:
        return self._state
    
    @property
    def fill_positions(self) -> Set[Tuple[int, int]]:
        return self._fill_positions.copy()
    
    def set_fill_object(self, tileset: int, object_id: int, layer: int = 1):
        """
        Set the object to use for filling.
        
        Args:
            tileset: Tileset index
            object_id: Object ID to fill with
            layer: Layer to fill on
        """
        self._tileset_idx = tileset
        self._fill_object_id = object_id
        self._layer = layer
    
    def set_layer(self, layer: int):
        """
        Set the layer for fill area determination and placement.
        
        Args:
            layer: Layer index (0, 1, or 2)
        """
        self._layer = max(0, min(2, layer))
    
    def set_zone_bounds_callback(self, callback):
        """
        Set callback for getting zone bounds.
        
        Callback signature: (x, y) -> (zone_x, zone_y, zone_width, zone_height) or None
        """
        self._get_zone_bounds = callback
    
    def set_tile_occupied_callback(self, callback):
        """
        Set callback for checking if a tile is occupied.
        
        Callback signature: (x, y, layer) -> bool
        """
        self._is_tile_occupied = callback
    
    def start_fill(self, x: int, y: int, allow_outside_zone: bool = False) -> FillResult:
        """
        Start a fill operation at the given position.
        
        This calculates the fill area and shows a preview.
        
        Args:
            x: X coordinate (tile)
            y: Y coordinate (tile)
            allow_outside_zone: If True, allow fill outside zones (Shift+click)
            
        Returns:
            FillResult with fill positions and status
        """
        # Reset state
        self._fill_positions.clear()
        self._is_outside_zone_fill = False
        
        # Check if click is inside a zone
        zone_bounds = self._get_zone_bounds(x, y) if self._get_zone_bounds else None
        
        if zone_bounds is None:
            if not allow_outside_zone:
                # Outside any zone and not allowed
                result = FillResult(
                    positions=set(),
                    exceeded_limit=False,
                    outside_zone=True
                )
                self._state = FillState.IDLE
                return result
            else:
                # Outside zone but allowed - use a large bounding area
                # Use area centered on click position
                zone_bounds = (x - 100, y - 100, 200, 200)
                self._is_outside_zone_fill = True
        
        # Check if starting position is occupied
        if self._is_tile_occupied and self._is_tile_occupied(x, y, self._layer):
            # Can't start fill on occupied tile
            result = FillResult(
                positions=set(),
                exceeded_limit=False,
                outside_zone=False
            )
            self._state = FillState.IDLE
            return result
        
        # Perform flood fill with limit - stop at MAX_FILL_AREA to avoid long waits
        zone_x, zone_y, zone_w, zone_h = zone_bounds
        self._zone_bounds = zone_bounds  # Store for continue_fill
        self._start_pos = (x, y)  # Store for continue_fill
        
        self._fill_positions, interrupted = self._flood_fill(
            x, y,
            zone_x, zone_y,
            zone_x + zone_w, zone_y + zone_h,
            limit=MAX_FILL_AREA
        )
        
        result = FillResult(
            positions=self._fill_positions.copy(),
            exceeded_limit=interrupted,
            outside_zone=False,
            interrupted=interrupted
        )
        
        if self._fill_positions:
            if interrupted:
                if self._is_outside_zone_fill:
                    # Outside zone fill - auto-cancel at threshold (don't ask)
                    print(f"[FillEngine] Outside zone fill auto-cancelled at {len(self._fill_positions)} tiles")
                    self._fill_positions.clear()
                    self._state = FillState.IDLE
                    result = FillResult(
                        positions=set(),
                        exceeded_limit=True,
                        outside_zone=False,
                        interrupted=True
                    )
                    self.fill_cancelled.emit()
                else:
                    # Inside zone fill - ask user to confirm
                    # Don't apply overpaint yet - wait for full fill
                    self._state = FillState.WAITING_CONFIRM
                    self.fill_preview_updated.emit(list(self._fill_positions))
                    self.fill_warning.emit(len(self._fill_positions))
            else:
                # Complete fill - apply overpaint for zone edges (only for inside-zone fills)
                if not self._is_outside_zone_fill:
                    self._fill_positions = self._add_overpaint(
                        self._fill_positions, zone_x, zone_y, zone_w, zone_h
                    )
                result = FillResult(
                    positions=self._fill_positions.copy(),
                    exceeded_limit=False,
                    outside_zone=False,
                    interrupted=False
                )
                self._state = FillState.PREVIEW
                self.fill_preview_updated.emit(list(self._fill_positions))
        
        return result
    
    def confirm_fill(self) -> List[Tuple[int, int]]:
        """
        Confirm the current fill preview.
        
        Returns:
            List of positions that were filled
        """
        if self._state not in (FillState.PREVIEW, FillState.WAITING_CONFIRM):
            return []
        
        positions = list(self._fill_positions)
        self._state = FillState.CONFIRMED
        self.fill_confirmed.emit(positions)
        
        # Reset after confirmation
        self._fill_positions.clear()
        self._state = FillState.IDLE
        
        return positions
    
    def continue_fill(self) -> FillResult:
        """
        Continue a fill that was stopped at the limit.
        User has confirmed they want to proceed with the full fill.
        
        Returns:
            FillResult with all fill positions
        """
        if self._state != FillState.WAITING_CONFIRM:
            return FillResult(positions=set(), exceeded_limit=False, outside_zone=False)
        
        if not self._zone_bounds or not self._start_pos:
            return FillResult(positions=set(), exceeded_limit=False, outside_zone=False)
        
        # Continue the fill without limit
        zone_x, zone_y, zone_w, zone_h = self._zone_bounds
        x, y = self._start_pos
        
        self._fill_positions, _ = self._flood_fill(
            x, y,
            zone_x, zone_y,
            zone_x + zone_w, zone_y + zone_h,
            limit=None  # No limit - user confirmed
        )
        
        # Apply overpaint for zone edges
        if self._fill_positions:
            self._fill_positions = self._add_overpaint(
                self._fill_positions, zone_x, zone_y, zone_w, zone_h
            )
        
        result = FillResult(
            positions=self._fill_positions.copy(),
            exceeded_limit=False,
            outside_zone=False,
            interrupted=False
        )
        
        if self._fill_positions:
            self._state = FillState.PREVIEW
            self.fill_preview_updated.emit(list(self._fill_positions))
        
        return result
    
    def cancel_fill(self):
        """Cancel the current fill operation"""
        self._fill_positions.clear()
        self._state = FillState.IDLE
        self.fill_cancelled.emit()
        self.fill_preview_updated.emit([])
    
    def _flood_fill(self, start_x: int, start_y: int,
                    min_x: int, min_y: int,
                    max_x: int, max_y: int,
                    limit: int = None) -> Tuple[Set[Tuple[int, int]], bool]:
        """
        Perform flood fill from starting position within bounds.
        
        Uses BFS to find all connected empty tiles.
        Stops early if limit is reached.
        
        Args:
            start_x, start_y: Starting position
            min_x, min_y: Minimum bounds (inclusive)
            max_x, max_y: Maximum bounds (exclusive)
            limit: Maximum tiles to find before stopping (None = no limit)
            
        Returns:
            Tuple of (set of (x, y) positions to fill, interrupted flag)
        """
        filled = set()
        queue = deque([(start_x, start_y)])
        visited = {(start_x, start_y)}
        interrupted = False
        
        while queue:
            # Check if we've hit the limit
            if limit is not None and len(filled) >= limit:
                interrupted = True
                break
            
            x, y = queue.popleft()
            
            # Check bounds
            if x < min_x or x >= max_x or y < min_y or y >= max_y:
                continue
            
            # Check if occupied
            if self._is_tile_occupied and self._is_tile_occupied(x, y, self._layer):
                continue
            
            # Add to fill set
            filled.add((x, y))
            
            # Check 4-connected neighbors
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = x + dx, y + dy
                if (nx, ny) not in visited:
                    visited.add((nx, ny))
                    queue.append((nx, ny))
        
        return filled, interrupted
    
    def _add_overpaint(self, positions: Set[Tuple[int, int]], 
                       zone_x: int, zone_y: int, zone_w: int, zone_h: int) -> Set[Tuple[int, int]]:
        """
        Add overpaint tiles outside zone boundaries where fill touches the edge.
        
        For each edge of the zone that the fill area touches, adds OVERPAINT_SIZE
        tiles outside the zone. Also adds corner blocks where two edges meet.
        
        Args:
            positions: Current fill positions
            zone_x, zone_y: Zone top-left corner (tiles)
            zone_w, zone_h: Zone size (tiles)
            
        Returns:
            Expanded set of positions including overpaint
        """
        if not positions:
            return positions
        
        result = positions.copy()
        
        # Zone boundaries (flood fill uses exclusive max, so max edge is at zone_x + zone_w - 1)
        zone_left = zone_x
        zone_right = zone_x + zone_w - 1  # Inclusive right edge
        zone_top = zone_y
        zone_bottom = zone_y + zone_h - 1  # Inclusive bottom edge
        
        # Get positions that actually touch each edge
        left_edge_positions = {(x, y) for x, y in positions if x == zone_left}
        right_edge_positions = {(x, y) for x, y in positions if x == zone_right}
        top_edge_positions = {(x, y) for x, y in positions if y == zone_top}
        bottom_edge_positions = {(x, y) for x, y in positions if y == zone_bottom}
        
        # Debug: show zone bounds and which edges are touched
        print(f"[FillEngine] Overpaint: zone=({zone_x},{zone_y}), size=({zone_w},{zone_h})")
        print(f"[FillEngine] Overpaint: left={zone_left}, right={zone_right}, top={zone_top}, bottom={zone_bottom}")
        
        # Find actual min/max of fill positions for comparison
        if positions:
            min_x = min(x for x, y in positions)
            max_x = max(x for x, y in positions)
            min_y = min(y for x, y in positions)
            max_y = max(y for x, y in positions)
            print(f"[FillEngine] Overpaint: fill bounds x=[{min_x},{max_x}], y=[{min_y},{max_y}]")
        
        print(f"[FillEngine] Overpaint: touches left={len(left_edge_positions)}, right={len(right_edge_positions)}, top={len(top_edge_positions)}, bottom={len(bottom_edge_positions)}")
        
        # Add overpaint for left edge - only directly adjacent to touching positions
        for x, y in left_edge_positions:
            for dx in range(1, OVERPAINT_SIZE + 1):
                result.add((zone_left - dx, y))
        
        # Add overpaint for right edge
        for x, y in right_edge_positions:
            for dx in range(1, OVERPAINT_SIZE + 1):
                result.add((zone_right + dx, y))
        
        # Add overpaint for top edge
        for x, y in top_edge_positions:
            for dy in range(1, OVERPAINT_SIZE + 1):
                result.add((x, zone_top - dy))
        
        # Add overpaint for bottom edge
        for x, y in bottom_edge_positions:
            for dy in range(1, OVERPAINT_SIZE + 1):
                result.add((x, zone_bottom + dy))
        
        # Add corner blocks (4x4) where position touches BOTH edges (actual corner)
        # Top-left corner - positions at (zone_left, zone_top)
        if (zone_left, zone_top) in positions:
            for dx in range(1, OVERPAINT_SIZE + 1):
                for dy in range(1, OVERPAINT_SIZE + 1):
                    result.add((zone_left - dx, zone_top - dy))
        
        # Top-right corner - positions at (zone_right, zone_top)
        if (zone_right, zone_top) in positions:
            for dx in range(1, OVERPAINT_SIZE + 1):
                for dy in range(1, OVERPAINT_SIZE + 1):
                    result.add((zone_right + dx, zone_top - dy))
        
        # Bottom-left corner - positions at (zone_left, zone_bottom)
        if (zone_left, zone_bottom) in positions:
            for dx in range(1, OVERPAINT_SIZE + 1):
                for dy in range(1, OVERPAINT_SIZE + 1):
                    result.add((zone_left - dx, zone_bottom + dy))
        
        # Bottom-right corner - positions at (zone_right, zone_bottom)
        if (zone_right, zone_bottom) in positions:
            for dx in range(1, OVERPAINT_SIZE + 1):
                for dy in range(1, OVERPAINT_SIZE + 1):
                    result.add((zone_right + dx, zone_bottom + dy))
        
        print(f"[FillEngine] Overpaint: added {len(result) - len(positions)} tiles outside zone")
        return result
    
    def get_fill_placements(self) -> List[dict]:
        """
        Get placements for the confirmed fill.
        
        Merges tiles into vertical slices (columns) for efficiency.
        Each column is scanned for consecutive tiles and merged into
        single multi-tile objects.
        
        Returns:
            List of placement dictionaries with tileset, object_id, layer, x, y, width, height
        """
        if not self._fill_object_id:
            return []
        
        # Group positions by column (x coordinate)
        columns: Dict[int, List[int]] = {}
        for x, y in self._fill_positions:
            if x not in columns:
                columns[x] = []
            columns[x].append(y)
        
        # Sort each column and merge consecutive y values into vertical slices
        placements = []
        for x, y_values in columns.items():
            y_values.sort()
            
            # Find consecutive runs
            if not y_values:
                continue
            
            run_start = y_values[0]
            run_end = y_values[0]
            
            for i in range(1, len(y_values)):
                if y_values[i] == run_end + 1:
                    # Continue the run
                    run_end = y_values[i]
                else:
                    # End current run, create placement
                    placements.append({
                        'tileset': self._tileset_idx,
                        'object_id': self._fill_object_id,
                        'layer': self._layer,
                        'x': x,
                        'y': run_start,
                        'width': 1,
                        'height': run_end - run_start + 1
                    })
                    # Start new run
                    run_start = y_values[i]
                    run_end = y_values[i]
            
            # Don't forget the last run
            placements.append({
                'tileset': self._tileset_idx,
                'object_id': self._fill_object_id,
                'layer': self._layer,
                'x': x,
                'y': run_start,
                'width': 1,
                'height': run_end - run_start + 1
            })
        
        return placements


# Global instance
_fill_engine: Optional[FillEngine] = None


def get_fill_engine() -> FillEngine:
    """Get the global FillEngine instance"""
    global _fill_engine
    if _fill_engine is None:
        _fill_engine = FillEngine()
    return _fill_engine
