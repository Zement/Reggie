"""
Mouse Event Handler - Handles mouse events for painting operations
"""
from typing import Optional, Tuple, List
from enum import Enum
from PyQt5 import QtCore, QtGui

from quickpaint.core.painter import PaintOperation
from quickpaint.core.modes import SmartPaintMode, SingleTileMode, ShapeCreator, EraserBrush, PaintingDirection
from quickpaint.core.brush import SmartBrush


class PaintingState(Enum):
    """Painting state enumeration"""
    IDLE = "idle"
    PAINTING = "painting"
    DEFERRED = "deferred"


class MouseEventHandler(QtCore.QObject):
    """
    Handles mouse events for painting operations.
    
    Supports:
    - Immediate painting (paint as mouse moves)
    - Deferred painting (show outline, paint on release)
    - Multiple painting modes (SmartPaint, SingleTile, ShapeCreator)
    - Eraser brush
    """
    
    # Signals
    painting_started = QtCore.pyqtSignal()
    painting_ended = QtCore.pyqtSignal(list)  # List of PaintOperation
    outline_updated = QtCore.pyqtSignal(list)  # List of outline positions
    
    def __init__(self, parent=None):
        """
        Initialize the mouse event handler.
        
        Args:
            parent: Parent object
        """
        super().__init__(parent)
        self.state = PaintingState.IDLE
        self.brush: Optional[SmartBrush] = None
        self.mode = "SmartPaint"
        self.painting_direction = PaintingDirection.AUTO
        
        # Painting state
        self.start_pos: Optional[Tuple[int, int]] = None
        self.current_pos: Optional[Tuple[int, int]] = None
        self.stroke_path: List[Tuple[int, int]] = []
        self.operations: List[PaintOperation] = []
        self.outline: List[Tuple[int, int]] = []
        
        # Mode instances
        self.smart_paint = SmartPaintMode()
        self.single_tile = SingleTileMode()
        self.shape_creator = ShapeCreator()
        self.eraser = EraserBrush()
    
    def set_brush(self, brush: SmartBrush):
        """
        Set the brush for painting.
        
        Args:
            brush: SmartBrush instance
        """
        self.brush = brush
    
    def set_mode(self, mode: str):
        """
        Set the painting mode.
        
        Args:
            mode: Mode name ("SmartPaint", "SingleTile", "ShapeCreator", "Eraser")
        """
        self.mode = mode
    
    def set_painting_direction(self, direction: PaintingDirection):
        """
        Set the painting direction for SmartPaint mode.
        
        Args:
            direction: PaintingDirection enum value
        """
        self.painting_direction = direction
    
    def on_mouse_press(self, pos: Tuple[int, int], button: int) -> bool:
        """
        Handle mouse press event.
        
        Args:
            pos: Mouse position (x, y) in tile coordinates
            button: Mouse button (1=left, 2=right, 3=middle)
        
        Returns:
            True if event was handled, False otherwise
        """
        if not self.brush:
            return False
        
        # Only handle left mouse button
        if button != 1:
            return False
        
        self.start_pos = pos
        self.current_pos = pos
        self.stroke_path = [pos]
        self.operations = []
        self.outline = []
        
        self.state = PaintingState.DEFERRED
        self.painting_started.emit()
        
        return True
    
    def on_mouse_move(self, pos: Tuple[int, int]) -> bool:
        """
        Handle mouse move event.
        
        Args:
            pos: Mouse position (x, y) in tile coordinates
        
        Returns:
            True if event was handled, False otherwise
        """
        if self.state == PaintingState.IDLE or not self.brush:
            return False
        
        self.current_pos = pos
        
        # Add to stroke path if position changed
        if pos not in self.stroke_path:
            self.stroke_path.append(pos)
        
        # Update painting based on mode
        if self.state == PaintingState.PAINTING:
            # Immediate painting mode
            self.update_immediate_painting()
        elif self.state == PaintingState.DEFERRED:
            # Deferred painting mode - show outline
            self.update_deferred_outline()
        
        return True
    
    def on_mouse_release(self, pos: Tuple[int, int], button: int) -> bool:
        """
        Handle mouse release event.
        
        Args:
            pos: Mouse position (x, y) in tile coordinates
            button: Mouse button
        
        Returns:
            True if event was handled, False otherwise
        """
        if self.state == PaintingState.IDLE or not self.brush:
            return False
        
        if button != 1:
            return False
        
        # Finalize painting
        self.finalize_painting()
        
        self.state = PaintingState.IDLE
        self.painting_ended.emit(self.operations)
        
        return True
    
    def update_immediate_painting(self):
        """Update painting for immediate mode (paint as mouse moves)"""
        if not self.brush or not self.start_pos or not self.current_pos:
            return
        
        # Get operations based on mode
        if self.mode == "SmartPaint":
            ops = self.smart_paint.paint_smart_path(
                self.start_pos,
                self.current_pos,
                self.brush,
                self.painting_direction,
                existing_tiles={}
            )
            self.operations.extend(ops)
        elif self.mode == "SingleTile":
            ops = self.single_tile.paint_path(
                self.stroke_path,
                self.brush
            )
            self.operations.extend(ops)
        elif self.mode == "ShapeCreator":
            # Shape creator uses deferred mode
            pass
    
    def update_deferred_outline(self):
        """Update outline for deferred mode"""
        if not self.brush or not self.start_pos or not self.current_pos:
            return
        
        # Calculate outline based on mode
        if self.mode == "SmartPaint":
            ops = self.smart_paint.paint_smart_path(
                self.start_pos,
                self.current_pos,
                self.brush,
                self.painting_direction,
                existing_tiles={}
            )
            self.outline = [(op.x, op.y) for op in ops]
        elif self.mode == "SingleTile":
            ops = self.single_tile.paint_path(
                self.stroke_path,
                self.brush
            )
            self.outline = [(op.x, op.y) for op in ops]
        elif self.mode == "ShapeCreator":
            # Shape creator outline
            if self.start_pos and self.current_pos:
                # Simple rectangle outline
                x1, y1 = self.start_pos
                x2, y2 = self.current_pos
                self.outline = self.get_rectangle_outline(x1, y1, x2, y2)
        
        self.outline_updated.emit(self.outline)
    
    def finalize_painting(self):
        """Finalize the painting operation"""
        if not self.brush or not self.start_pos or not self.current_pos:
            return
        
        # Get final operations based on mode
        if self.mode == "SmartPaint":
            self.operations = self.smart_paint.paint_smart_path(
                self.start_pos,
                self.current_pos,
                self.brush,
                self.painting_direction,
                existing_tiles={}
            )
        elif self.mode == "SingleTile":
            self.operations = self.single_tile.paint_path(
                self.stroke_path,
                self.brush
            )
        elif self.mode == "ShapeCreator":
            if self.start_pos and self.current_pos:
                x1, y1 = self.start_pos
                x2, y2 = self.current_pos
                self.operations = self.shape_creator.create_rectangle(
                    x1, y1, x2, y2,
                    self.brush
                )
    
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
        return self.state != PaintingState.IDLE
    
    def cancel_painting(self):
        """Cancel current painting operation"""
        self.state = PaintingState.IDLE
        self.stroke_path = []
        self.operations = []
        self.outline = []
    
    def get_operations(self) -> List[PaintOperation]:
        """Get the list of painting operations"""
        return self.operations
    
    def get_outline(self) -> List[Tuple[int, int]]:
        """Get the current outline"""
        return self.outline
