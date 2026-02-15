"""
Mouse Event Handler - Handles mouse events for painting operations

This module provides the bridge between Qt mouse events and the painting engine.
Supports both immediate and deferred painting modes.
"""
from typing import Optional, Tuple, List
from enum import Enum
from PyQt6 import QtCore, QtGui

from quickpaint.core.painter import PaintOperation
from quickpaint.core.engine import PaintingEngine, ObjectPlacement, PaintingMode, PaintingState as EngineState
from quickpaint.core.brush import SmartBrush


class PaintingState(Enum):
    """Painting state enumeration (legacy compatibility)"""
    IDLE = "idle"
    PAINTING = "painting"
    DEFERRED = "deferred"


class MouseEventHandler(QtCore.QObject):
    """
    Handles mouse events for painting operations.
    
    Supports two painting modes:
    1. Immediate Mode: Hold paint key while drawing - tiles are placed immediately
    2. Deferred Mode: Draw path, then click to finalize - shows outline preview
    
    Features:
    - Bresenham interpolation for smooth strokes
    - 8-neighbor auto-tiling
    - Start object selection for deferred mode
    """
    
    # Signals
    painting_started = QtCore.pyqtSignal()
    painting_ended = QtCore.pyqtSignal(list)  # List of ObjectPlacement
    outline_updated = QtCore.pyqtSignal(list)  # List of outline positions
    object_placed = QtCore.pyqtSignal(object)  # Single ObjectPlacement
    
    def __init__(self, parent=None):
        """
        Initialize the mouse event handler.
        
        Args:
            parent: Parent object
        """
        super().__init__(parent)
        
        # Create painting engine
        self.engine = PaintingEngine()
        
        # Connect engine callbacks
        self.engine.on_outline_updated = self._on_outline_updated
        self.engine.on_place_object = self._on_place_object
        self.engine.on_painting_finished = self._on_painting_finished
        
        # Legacy compatibility
        self.state = PaintingState.IDLE
        self.brush: Optional[SmartBrush] = None
        self.mode = "SmartPaint"
        
        # Painting state
        self.start_pos: Optional[Tuple[int, int]] = None
        self.current_pos: Optional[Tuple[int, int]] = None
        self.stroke_path: List[Tuple[int, int]] = []
        self.operations: List[PaintOperation] = []
        self.outline: List[Tuple[int, int]] = []
        
        # Deferred mode state
        self.start_object: Optional[Tuple[int, int]] = None  # Position of start object
        self.is_immediate_mode: bool = False  # True when paint key is held
    
    def set_brush(self, brush: SmartBrush):
        """
        Set the brush for painting.
        
        Args:
            brush: SmartBrush instance
        """
        self.brush = brush
        self.engine.set_brush(brush)
        # Reset deferred mode state when brush is set (new painting session)
        self.start_object = None
        self.state = PaintingState.IDLE
    
    def set_mode(self, mode: str):
        """
        Set the painting mode.
        
        Args:
            mode: Mode name ("SmartPaint", "SingleTile", "ShapeCreator")
        """
        self.mode = mode
    
    def set_layer(self, layer: int):
        """
        Set the layer for painting.
        
        Args:
            layer: Layer index (0, 1, or 2)
        """
        self.engine.set_layer(layer)
    
    def set_immediate_mode(self, immediate: bool):
        """
        Set whether to use immediate painting mode.
        
        Args:
            immediate: True for immediate mode (paint while holding key),
                      False for deferred mode (outline preview)
        """
        self.is_immediate_mode = immediate
        self.engine.set_immediate_mode(immediate)
    
    def update_object_database(self, database, empty_slope_regions=None):
        """
        Update the object database for auto-tiling context.
        
        Args:
            database: Dict mapping (x, y, layer) -> object_id
            empty_slope_regions: Set of (x, y, layer) positions that are empty tiles
                                 within slope object bounds
        """
        self.engine.update_object_database(database, empty_slope_regions)
    
    # =========================================================================
    # ENGINE CALLBACKS
    # =========================================================================
    
    def _on_outline_updated(self, positions: List[Tuple[int, int]]):
        """Callback when outline is updated"""
        self.outline = positions
        self.outline_updated.emit(positions)
    
    def _on_place_object(self, placement: ObjectPlacement):
        """Callback when an object is placed"""
        self.object_placed.emit(placement)
    
    def _on_painting_finished(self, placements: List[ObjectPlacement]):
        """Callback when painting is finished"""
        self.painting_ended.emit(placements)
    
    # =========================================================================
    # MOUSE EVENT HANDLERS
    # =========================================================================
    
    def on_mouse_press(self, pos: Tuple[int, int], button: int, draw_button: int = 2) -> bool:
        """
        Handle mouse press event.
        
        In immediate mode: Start painting immediately
        In deferred mode: 
            - Right click (draw_button=2): Set start object or finalize if already have start
            - Other button: Cancel current path and clear start object
        
        Args:
            pos: Mouse position (x, y) in tile coordinates
            button: Mouse button that was pressed (1=left, 2=right, 3=middle)
            draw_button: The button assigned for drawing (default: 2=right)
        
        Returns:
            True if event was handled, False otherwise
        """
        print(f"[MouseEventHandler] on_mouse_press: pos={pos}, button={button}, draw_button={draw_button}")
        print(f"[MouseEventHandler] brush={self.brush is not None}, state={self.state}, is_immediate={self.is_immediate_mode}")
        
        if not self.brush:
            print("[MouseEventHandler] No brush set, ignoring press")
            return False
        
        # In slope mode, mouse press is handled differently (commit happens on release)
        if self.engine.session.slope_mode:
            # Don't start new painting in slope mode - just return
            return True
        
        # In deferred mode, non-draw button cancels the path
        if not self.is_immediate_mode and button != draw_button:
            if self.state == PaintingState.DEFERRED or self.start_object is not None:
                print("[MouseEventHandler] Non-draw button pressed, cancelling deferred path")
                self.cancel_painting()
                return True
            return False
        
        # Only handle draw button for painting
        if button != draw_button:
            print(f"[MouseEventHandler] Button {button} != draw_button {draw_button}, ignoring")
            return False
        
        print(f"[MouseEventHandler] Starting painting at {pos}")
        self.start_pos = pos
        self.current_pos = pos
        self.stroke_path = [pos]
        
        if self.is_immediate_mode:
            # Immediate mode: start painting right away
            self.state = PaintingState.PAINTING
            self.engine.start_painting(pos)
        else:
            # Deferred mode
            if self.start_object is None:
                # First click: set start object
                self.start_object = pos
                self.state = PaintingState.DEFERRED
                self.engine.start_painting(pos)
            else:
                # Second click: finalize the path from start to here
                self.engine.finish_painting(pos)
                # The clicked position becomes the new start object
                self.start_object = pos
                self.engine.start_painting(pos)
        
        self.painting_started.emit()
        return True
    
    def on_key_press(self, key: int) -> bool:
        """
        Handle key press event.
        
        ESC key cancels the current deferred painting path.
        Shift key toggles slope mode.
        
        Args:
            key: Qt key code
        
        Returns:
            True if event was handled, False otherwise
        """
        from PyQt6.QtCore import Qt
        
        if key == Qt.Key.Key_Escape:
            if self.state == PaintingState.DEFERRED or self.start_object is not None:
                print("[MouseEventHandler] ESC pressed, cancelling deferred path")
                self.cancel_painting()
                return True
        
        if key == Qt.Key.Key_F1:
            if self.state == PaintingState.DEFERRED:
                # Toggle slope mode
                in_slope_mode = self.engine.toggle_slope_mode()
                print(f"[MouseEventHandler] F1 pressed, slope_mode={in_slope_mode}")
                self.outline_updated.emit()
                return True
        
        return False
    
    def on_mouse_move(self, pos: Tuple[int, int]) -> bool:
        """
        Handle mouse move event.
        
        Args:
            pos: Mouse position (x, y) in tile coordinates
        
        Returns:
            True if event was handled, False otherwise
        """
        if self.state == PaintingState.IDLE:
            # Don't log this - it's expected before first click
            return False
        
        if not self.brush:
            print(f"[MouseEventHandler] on_mouse_move: no brush set")
            return False
        
        # Reduced logging - only log occasionally to avoid spam
        # if pos != self.current_pos:
        #     print(f"[MouseEventHandler] on_mouse_move: pos={pos}, state={self.state}")
        
        self.current_pos = pos
        
        # Check if in slope mode - update slope preview instead of path
        if self.engine.session.slope_mode:
            self.engine.update_slope_preview(pos)
            self.outline_updated.emit()
            return True
        
        # Add to stroke path if position changed
        if pos not in self.stroke_path:
            self.stroke_path.append(pos)
        
        # Update the engine
        self.engine.update_painting(pos)
        
        return True
    
    def on_mouse_release(self, pos: Tuple[int, int], button: int, draw_button: int = 2) -> bool:
        """
        Handle mouse release event.
        
        In immediate mode: Finish painting
        In deferred mode: Does nothing (painting continues until next click)
        
        Args:
            pos: Mouse position (x, y) in tile coordinates
            button: Mouse button
            draw_button: The button assigned for drawing (default: 2=right)
        
        Returns:
            True if event was handled, False otherwise
        """
        print(f"[MouseEventHandler] on_mouse_release: pos={pos}, button={button}, draw_button={draw_button}")
        
        if self.state == PaintingState.IDLE or not self.brush:
            return False
        
        if button != draw_button:
            return False
        
        # Check if in slope mode - right-click commits the slope
        if self.engine.session.slope_mode:
            if self.engine.commit_slope():
                print(f"[MouseEventHandler] Slope committed, updating outline")
                self.outline_updated.emit()
            return True
        
        if self.is_immediate_mode:
            # Immediate mode: finish painting on release
            print(f"[MouseEventHandler] Finishing immediate painting at {pos}")
            placements = self.engine.finish_painting(pos)
            self.state = PaintingState.IDLE
        # Deferred mode: don't finish on release, wait for next click
        
        return True
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    @staticmethod
    def get_rectangle_outline(x1: int, y1: int, x2: int, y2: int) -> List[Tuple[int, int]]:
        """
        Get rectangle outline positions.
        
        Args:
            x1, y1: Start position
            x2, y2: End position
        
        Returns:
            List of outline positions
        """
        outline = []
        min_x, max_x = min(x1, x2), max(x1, x2)
        min_y, max_y = min(y1, y2), max(y1, y2)
        
        # Top and bottom edges
        for x in range(min_x, max_x + 1):
            outline.append((x, min_y))
            outline.append((x, max_y))
        
        # Left and right edges
        for y in range(min_y, max_y + 1):
            outline.append((min_x, y))
            outline.append((max_x, y))
        
        return list(set(outline))  # Remove duplicates
    
    def is_painting(self) -> bool:
        """Check if currently painting"""
        return self.state != PaintingState.IDLE or self.engine.is_painting()
    
    def cancel_painting(self):
        """Cancel current painting operation"""
        self.state = PaintingState.IDLE
        self.stroke_path = []
        self.operations = []
        self.outline = []
        self.start_object = None
        self.engine.cancel_painting()
    
    def reset_start_object(self):
        """Reset the start object for deferred mode"""
        self.start_object = None
        self.engine.cancel_painting()
    
    def get_operations(self) -> List[PaintOperation]:
        """Get the list of painting operations (legacy)"""
        return self.operations
    
    def get_outline(self) -> List[Tuple[int, int]]:
        """Get the current outline"""
        return self.engine.get_outline()
    
    def get_outline_with_types(self) -> List[Tuple[int, int, str]]:
        """Get the current outline with tile types"""
        return self.engine.get_outline_with_types()
    
    def get_pending_placements(self) -> List[ObjectPlacement]:
        """Get the list of pending object placements"""
        return self.engine.get_pending_placements()
