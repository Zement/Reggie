"""
Canvas-based Tile Picker Widget - Displays terrain objects in a grid for selection
Similar to the original Reggie tile picker
"""
import random
from typing import Dict, Optional, Tuple, List
from PyQt6 import QtWidgets, QtCore, QtGui

from quickpaint.core.brush import SmartBrush
from tiles import RenderObject
import globals_


class TilePickerCanvas(QtWidgets.QGraphicsView):
    """
    Canvas-based tile picker that displays terrain objects in a grid.
    Allows clicking on objects to assign them to position types.
    Similar to the original Reggie tile picker.
    """
    
    # Signal emitted when a tile is selected: (tile_id, position_type)
    tile_selected = QtCore.pyqtSignal(int, str)
    
    # Unified terrain object layout - 6x8 grid + slope objects on the right
    # Slopes are placed at their full size with origin at top-left
    # Each cell contains (object_id, position_type)
    TERRAIN_LAYOUT = [
        # Row 1: Top Left, Top, Top, Top, Top, Top Right | 1x1 slopes (2 tall) | 2x1 slopes (2 tall) | 4x1 slopes (2 tall)
        [('top_left', 'top_left'), ('top', 'top'), ('top', 'top'), ('top', 'top'), ('top', 'top'), ('top_right', 'top_right'), 
        ('slope_top_1x1_left', 'slope_top_1x1_left'), ('slope_top_1x1_right', 'slope_top_1x1_right'), ('slope_top_4x1_left', 'slope_top_4x1_left'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('slope_top_4x1_right', 'slope_top_4x1_right'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered')],
        # Row 2: Left, Center, Center, Center, Center, Right | 1x1 base | 2x1 base | 4x1 base
        [('left', 'left'), ('center', 'center'), ('center', 'center'), ('center', 'center'), ('center', 'center'), ('right', 'right'),
        ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered')],
        # Row 3: Left, Inner Bottom Left, Bottom, Bottom, Inner Bottom Right, Right | 1x1 top | 2x1 top | 4x1 top
        [('left', 'left'), ('inner_bottom_left', 'inner_bottom_left'), ('bottom', 'bottom'), ('bottom', 'bottom'), ('inner_bottom_right', 'inner_bottom_right'), ('right', 'right'),
        (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None)],
        # Row 4: Left, Right, Nothing, Nothing, Left, Right | 1x1 base | 2x1 base | 4x1 base
        [('left', 'left'), ('right', 'right'), (None, None), (None, None), ('left', 'left'), ('right', 'right'),
        ('slope_bottom_1x1_left', 'slope_bottom_1x1_left'), ('slope_bottom_1x1_right', 'slope_bottom_1x1_right'), ('slope_bottom_4x1_left', 'slope_bottom_4x1_left'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('slope_bottom_4x1_right', 'slope_bottom_4x1_right'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered')],
        # Row 5: Left, Right, Nothing, Nothing, Left, Right | 1x1 top right | 2x1 top right | 4x1 top right
        [('left', 'left'), ('right', 'right'), (None, None), (None, None), ('left', 'left'), ('right', 'right'),
        ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered')],
        # Row 6: Left, Inner Top Left, Top, Top, Inner Top Right, Right | 1x1 bottom left | 2x1 bottom left | 4x1 bottom left
        [('left', 'left'), ('inner_top_left', 'inner_top_left'), ('top', 'top'), ('top', 'top'), ('inner_top_right', 'inner_top_right'), ('right', 'right'),
        (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None), (None, None)],
        # Row 7: Left, Center, Center, Center, Center, Right | 1x1 bottom base | 2x1 bottom base | 4x1 bottom base
        [('left', 'left'), ('center', 'center'), ('center', 'center'), ('center', 'center'), ('center', 'center'), ('right', 'right'),
        ('slope_top_2x1_left', 'slope_top_2x1_left'), ('floor_covered', 'floor_covered'), ('slope_top_2x1_right', 'slope_top_2x1_right'), ('floor_covered', 'floor_covered'), ('slope_bottom_2x1_left', 'slope_bottom_2x1_left'), ('floor_covered', 'floor_covered'), ('slope_bottom_2x1_right', 'slope_bottom_2x1_right'), ('floor_covered', 'floor_covered'), (None, None), (None, None)],
        # Row 8: Bottom Left, Bottom, Bottom, Bottom, Bottom, Bottom Right | 1x1 bottom right | 2x1 bottom right | 4x1 bottom right
        [('bottom_left', 'bottom_left'), ('bottom', 'bottom'), ('bottom', 'bottom'), ('bottom', 'bottom'), ('bottom', 'bottom'), ('bottom_right', 'bottom_right'),
        ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), ('floor_covered', 'floor_covered'), (None, None), (None, None)]
    ]
    
    def __init__(self, brush: SmartBrush = None, parent=None):
        """
        Initialize the tile picker canvas.
        
        Args:
            brush: SmartBrush instance to display
            parent: Parent widget
        """
        super().__init__(parent)
        self.brush = brush
        self.tileset_idx = 0  # Default to Pa0
        self.scene = QtWidgets.QGraphicsScene()
        self.setScene(self.scene)
        
        # Object grid settings
        self.object_size = 24  # Base tile size
        self.tile_map: Dict[Tuple[int, int], Tuple[int, str]] = {}  # (x, y) -> (object_id, position_type)
        
        # Track selected position type
        self.selected_position_type: Optional[str] = None
        
        # Flag to prevent redrawing while interacting
        self.is_drawing = False
        
        # Enable mouse tracking
        self.setMouseTracking(True)
        
        self.init_ui()
    
    def get_current_layout(self):
        """Get the unified terrain layout with slopes"""
        return self.TERRAIN_LAYOUT
    
    def get_grid_dimensions(self):
        """Get the grid dimensions for the current category"""
        layout = self.get_current_layout()
        height = len(layout)
        width = len(layout[0]) if layout else 0
        return width, height
    
    def init_ui(self):
        """Initialize the UI"""
        self.setMinimumHeight(200)
        self.setMaximumHeight(200)
        self.setStyleSheet("QGraphicsView { background-color: #2a2a2a; border: 1px solid #555; }")
        
        # Draw empty grid placeholder
        self.draw_empty_grid()
        
        # Add status indicator and clear button to the scene
        self._add_ui_elements()
    
    def draw_empty_grid(self):
        """Draw an empty grid with tile position outlines based on current category"""
        self.scene.clear()
        self.tile_map.clear()
        
        # Draw tile position outlines for each cell in the current layout
        self._draw_tile_outlines()
        
        # Redraw status indicator after clearing
        self._add_ui_elements()
        
        # Get grid dimensions for current category
        width, height = self.get_grid_dimensions()
        
        # Set scene rect to match grid dimensions at 24x24 cells
        self.scene.setSceneRect(0, 0, width * 24, height * 24)
        # Reset transform to prevent scaling - display at 1:1 pixel ratio
        self.resetTransform()
        
        print(f"[QPT] Empty grid ({width}x{height}) with tile outlines drawn")
    
    def _draw_tile_outlines(self):
        """Draw minimalistic tile position outlines using QPaint with grass details"""
        # Colors: Color 2 (80% opaque gray) for outlines, Color 3 (50% opaque gray) for inner tiles
        outline_color = QtGui.QColor(128, 128, 128, 204)  # 80% opaque gray
        inner_color = QtGui.QColor(128, 128, 128, 127)    # 50% opaque gray
        faint_color = QtGui.QColor(128, 128, 128, 16)     # Very faint gray for disabled slopes
        
        # Get the current layout
        current_layout = self.get_current_layout()
        
        # Get enabled slopes from brush (if available)
        enabled_slopes = getattr(self.brush, 'enabled_slopes', None) if self.brush else None
        if enabled_slopes is None:
            enabled_slopes = set()  # All slopes enabled by default
        
        # Helper function to get pixmap size for a position type
        def get_pixmap_size(pos_type):
            """Return (width, height) for pixmap based on position type"""
            if pos_type and 'slope' in pos_type:
                if '1x1' in pos_type:
                    return (24, 48)  # 1x1 slope + base
                elif '2x1' in pos_type:
                    return (48, 48)  # 2x1 slope + base
                elif '4x1' in pos_type:
                    return (96, 48)  # 4x1 slope + base
            return (24, 24)  # Regular terrain tile
        
        # Iterate through current layout and draw outlines for each position
        for row_idx, row in enumerate(current_layout):
            for col_idx, (position_type, _) in enumerate(row):
                if position_type is None:
                    continue
                
                # Determine pixmap size based on position type
                pixmap_width, pixmap_height = get_pixmap_size(position_type)
                
                # Calculate position (slopes may span multiple grid cells)
                x = col_idx * 24
                y = row_idx * 24
                
                # Create a pixmap for this cell
                pixmap = QtGui.QPixmap(pixmap_width, pixmap_height)
                pixmap.fill(QtCore.Qt.GlobalColor.transparent)
                
                painter = QtGui.QPainter(pixmap)
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                
                # Draw based on position type
                if position_type == 'center':
                    painter.fillRect(1, 1, 23, 23, inner_color)

                elif position_type == 'top':
                    painter.fillRect(1, 1, 23, 23, inner_color)
                    # Top edge: horizontal line with grass blades going downward
                    pen = QtGui.QPen(outline_color)
                    pen.setWidth(2)
                    painter.setPen(pen)
                    painter.drawLine(2, 2, 22, 2)  # Main edge line at top
                    
                    # Draw grass blades going downward (3 blades = 6 strokes)
                    painter.drawLine(6, 2, 5, 6)
                    painter.drawLine(5, 6, 7, 2)
                    painter.drawLine(12, 2, 11, 6)
                    painter.drawLine(11, 6, 13, 2)
                    painter.drawLine(18, 2, 17, 6)
                    painter.drawLine(17, 6, 19, 2)
                
                elif position_type == 'bottom':
                    painter.fillRect(1, 1, 23, 23, inner_color)
                    # Bottom edge: horizontal line with increased zig-zag verticality
                    pen = QtGui.QPen(outline_color)
                    pen.setWidth(4)
                    painter.setPen(pen)
                    painter.drawLine(4, 22, 22, 22)  # Main edge line at bottom
                
                elif position_type in ['left', 'right']:
                    # Side edges: vertical line
                    pen = QtGui.QPen(outline_color)
                    pen.setWidth(2)
                    painter.setPen(pen)
                    
                    if position_type == 'left':
                        painter.fillRect(4, 1, 23, 23, inner_color)
                        painter.drawLine(4, 2, 4, 22)
                    else:  # right
                        painter.fillRect(1, 1, 20, 23, inner_color)
                        painter.drawLine(20, 2, 20, 22)
                
                elif position_type == 'top_left':
                    painter.fillRect(4, 3, 23, 23, inner_color)
                    # Top-left corner: diagonal with rounded corner and grass blades
                    pen = QtGui.QPen(outline_color)
                    pen.setWidth(2)
                    painter.setPen(pen)
                    
                    # Draw diagonal with rounded corner (mirror of top_right)
                    path = QtGui.QPainterPath()
                    path.moveTo(4, 22)
                    path.lineTo(4, 8)
                    path.arcTo(4, 2, 8, 8, 180, -90)  # Rounded corner
                    path.lineTo(22, 2)
                    painter.drawPath(path)
                    
                    # Grass blades (2 blades = 4 strokes) - mirrored from top_right
                    painter.drawLine(10, 2, 9, 6)
                    painter.drawLine(9, 6, 11, 2)
                    painter.drawLine(17, 2, 16, 6)
                    painter.drawLine(16, 6, 18, 2)
                
                elif position_type == 'top_right':
                    painter.fillRect(1, 3, 20, 23, inner_color)
                    # Top-right corner: diagonal with rounded corner and grass blades
                    pen = QtGui.QPen(outline_color)
                    pen.setWidth(2)
                    painter.setPen(pen)
                    
                    # Draw diagonal with rounded corner
                    path = QtGui.QPainterPath()
                    path.moveTo(20, 22)
                    path.lineTo(20, 8)
                    path.arcTo(12, 2, 8, 8, 0, 90)  # Rounded corner
                    path.lineTo(2, 2)
                    painter.drawPath(path)
                    
                    # Grass blades (2 blades = 4 strokes)
                    painter.drawLine(7, 2, 6, 6)
                    painter.drawLine(6, 6, 8, 2)
                    painter.drawLine(15, 2, 14, 6)
                    painter.drawLine(14, 6, 16, 2)
                
                elif position_type == 'bottom_left':
                    painter.fillRect(4, 1, 23, 20, inner_color)
                    # Bottom-left corner: diagonal with rounded corner (flipped from bottom_right)
                    pen = QtGui.QPen(outline_color)
                    pen.setWidth(2)
                    painter.setPen(pen)
                    
                    # Draw diagonal with rounded corner
                    path = QtGui.QPainterPath()
                    path.moveTo(4, 2)
                    path.lineTo(4, 16)
                    path.arcTo(4, 14, 8, 8, 180, 90)  # Rounded corner
                    path.lineTo(22, 22)
                    painter.drawPath(path)
                
                elif position_type == 'bottom_right':
                    painter.fillRect(1, 1, 20, 20, inner_color)
                    # Bottom-right corner: same as top_right but rotated 90 degrees counter-clockwise
                    pen = QtGui.QPen(outline_color)
                    pen.setWidth(2)
                    painter.setPen(pen)
                    
                    # Draw diagonal with rounded corner (rotated 90 degrees from top_right)
                    path = QtGui.QPainterPath()
                    path.moveTo(20, 2)
                    path.lineTo(20, 16)
                    path.arcTo(12, 14, 8, 8, 0, -90)  # Rounded corner
                    path.lineTo(2, 22)
                    painter.drawPath(path)
                
                elif position_type in ['inner_top_left', 'inner_top_right', 'inner_bottom_left', 'inner_bottom_right']:
                    # Inner tiles: solid fill with horizontal stroke indicator
                    painter.fillRect(1, 1, 23, 23, inner_color)
                    
                    # Add horizontal stroke indicator at intersection (12px width = half tile)
                    pen = QtGui.QPen(outline_color)
                    pen.setWidth(2)
                    painter.setPen(pen)
                    
                    if position_type == 'inner_top_left':
                        # Horizontal line at center, right half
                        painter.drawLine(12, 2, 22, 2)
                        # Draw grass blades going downward (3 blades = 6 strokes)
                        painter.drawLine(14, 2, 13, 6)
                        painter.drawLine(13, 6, 15, 2)
                        painter.drawLine(20, 2, 19, 6)
                        painter.drawLine(19, 6, 21, 2)
                    elif position_type == 'inner_top_right':
                        # Horizontal line at center, left half
                        painter.drawLine(2, 2, 12, 2)
                        # Draw grass blades going downward (3 blades = 6 strokes)
                        painter.drawLine(5, 2, 4, 6)
                        painter.drawLine(4, 6, 6, 2)
                        painter.drawLine(10, 2, 9, 6)
                        painter.drawLine(9, 6, 11, 2)
                    elif position_type == 'inner_bottom_left':
                        # Horizontal line at center, right half
                        pen = QtGui.QPen(outline_color)
                        pen.setWidth(4)
                        painter.setPen(pen)
                        painter.drawLine(14, 22, 22, 22)
                    elif position_type == 'inner_bottom_right':
                        # Horizontal line at center, left half
                        pen = QtGui.QPen(outline_color)
                        pen.setWidth(4)
                        painter.setPen(pen)
                        painter.drawLine(4, 22, 12, 22)
                
                # Slope tiles - origin tiles (top-left of slope object)
                elif position_type in ['slope_top_1x1_left', 'slope_top_1x1_right',
                                       'slope_top_2x1_left', 'slope_top_2x1_right',
                                       'slope_top_4x1_left', 'slope_top_4x1_right',
                                       'slope_bottom_1x1_left', 'slope_bottom_1x1_right',
                                       'slope_bottom_2x1_left', 'slope_bottom_2x1_right',
                                       'slope_bottom_4x1_left', 'slope_bottom_4x1_right']:
                    # Check if this slope is enabled
                    is_enabled = position_type in enabled_slopes
                    
                    # Use appropriate color based on enabled state
                    tile_color = inner_color if is_enabled else faint_color 
                    
                    # Draw slope based on type
                    if position_type == 'slope_top_1x1_left':
                        painter.fillRect(0, 0, pixmap_width, pixmap_height, tile_color)
                        # Draw filled triangle for slope
                        triangle = QtGui.QPolygonF([
                            QtCore.QPointF(0, 24),    # bottom-left
                            QtCore.QPointF(24, 0),   # top-right
                            QtCore.QPointF(24, 24)   # bottom-right
                        ])
                        path = QtGui.QPainterPath()
                        path.addPolygon(triangle)
                        painter.fillPath(path, tile_color)
                        painter.fillRect(0, 24, 24, 28, (inner_color if is_enabled else faint_color))
                        pen = QtGui.QPen(outline_color if is_enabled else faint_color)
                        pen.setWidth(2)
                        painter.setPen(pen)
                        painter.drawLine(0, 24, 24, 0)  # Diagonal from bottom-left to top-right
                        painter.drawLine(0, 24, 0, 48)
                        painter.drawLine(0, 48, 24, 48)
                        painter.drawLine(24, 0, 24, 48)
                        
                    elif position_type == 'slope_top_1x1_right':
                        painter.fillRect(0, 0, pixmap_width, pixmap_height, tile_color)
                        # Draw filled triangle for slope
                        triangle = QtGui.QPolygonF([
                            QtCore.QPointF(0, 0),     # top-left
                            QtCore.QPointF(24, 24),   # bottom-right
                            QtCore.QPointF(0, 24)    # bottom-left
                        ])
                        path = QtGui.QPainterPath()
                        path.addPolygon(triangle)
                        painter.fillPath(path, tile_color)
                        painter.fillRect(0, 24, 24, 28, (inner_color if is_enabled else faint_color))
                        pen = QtGui.QPen(outline_color if is_enabled else faint_color)
                        pen.setWidth(2)
                        painter.setPen(pen)
                        painter.drawLine(0, 0, 24, 24)  # Diagonal from top-left to bottom-right
                        painter.drawLine(0, 0, 0, 48)
                        painter.drawLine(0, 48, 24, 48)
                        painter.drawLine(24, 24, 24, 48)
                        
                    elif position_type == 'slope_top_2x1_left':
                        painter.fillRect(0, 0, pixmap_width, pixmap_height, tile_color)
                        # Draw filled triangle for slope
                        triangle = QtGui.QPolygonF([
                            QtCore.QPointF(0, 24),    # bottom-left
                            QtCore.QPointF(48, 0),   # top-right
                            QtCore.QPointF(48, 24)   # bottom-right
                        ])
                        path = QtGui.QPainterPath()
                        path.addPolygon(triangle)
                        painter.fillPath(path, tile_color)
                        # Draw base block
                        painter.fillRect(0, 24, 48, 24, (inner_color if is_enabled else faint_color))
                        # Draw border lines for base block
                        pen = QtGui.QPen(outline_color if is_enabled else faint_color)
                        pen.setWidth(2)
                        painter.setPen(pen)
                        painter.drawLine(0, 24, 48, 0)  # Diagonal from bottom-left to top-right
                        painter.drawLine(0, 24, 0, 48)  # Left edge
                        painter.drawLine(0, 48, 48, 48)  # Bottom edge
                        painter.drawLine(48, 0, 48, 48)  # Right edge
                        
                    elif position_type == 'slope_top_2x1_right':
                        painter.fillRect(0, 0, pixmap_width, pixmap_height, tile_color)
                        # Draw filled triangle for slope
                        triangle = QtGui.QPolygonF([
                            QtCore.QPointF(0, 0),     # top-left
                            QtCore.QPointF(48, 24),   # bottom-right
                            QtCore.QPointF(0, 24)    # bottom-left
                        ])
                        path = QtGui.QPainterPath()
                        path.addPolygon(triangle)
                        painter.fillPath(path, tile_color)
                        # Draw base block
                        painter.fillRect(0, 24, 48, 24, (inner_color if is_enabled else faint_color))
                        # Draw border lines for base block
                        pen = QtGui.QPen(outline_color if is_enabled else faint_color)
                        pen.setWidth(2)
                        painter.setPen(pen)
                        painter.drawLine(0, 0, 48, 24)  # Diagonal from top-left to bottom-right
                        painter.drawLine(0, 0, 0, 48)  # Left edge
                        painter.drawLine(0, 48, 48, 48)  # Bottom edge
                        painter.drawLine(48, 24, 48, 48)  # Right edge
                        
                    elif position_type == 'slope_top_4x1_left':
                        painter.fillRect(0, 0, pixmap_width, pixmap_height, tile_color)
                        # Draw filled triangle for slope
                        triangle = QtGui.QPolygonF([
                            QtCore.QPointF(0, 24),    # bottom-left
                            QtCore.QPointF(96, 0),   # top-right
                            QtCore.QPointF(96, 24)   # bottom-right
                        ])
                        path = QtGui.QPainterPath()
                        path.addPolygon(triangle)
                        painter.fillPath(path, tile_color)
                        # Draw base block
                        painter.fillRect(0, 24, 96, 24, (inner_color if is_enabled else faint_color))
                        # Draw border lines for base block
                        pen = QtGui.QPen(outline_color if is_enabled else faint_color)
                        pen.setWidth(2)
                        painter.setPen(pen)
                        painter.drawLine(0, 24, 96, 0)  # Diagonal from bottom-left to top-right
                        painter.drawLine(0, 24, 0, 48)  # Left edge
                        painter.drawLine(0, 48, 96, 48)  # Bottom edge
                        painter.drawLine(96, 0, 96, 48)  # Right edge
                        
                    elif position_type == 'slope_top_4x1_right':
                        painter.fillRect(0, 0, pixmap_width, pixmap_height, tile_color)
                        # Draw filled triangle for slope
                        triangle = QtGui.QPolygonF([
                            QtCore.QPointF(0, 0),     # top-left
                            QtCore.QPointF(96, 24),   # bottom-right
                            QtCore.QPointF(0, 24)    # bottom-left
                        ])
                        path = QtGui.QPainterPath()
                        path.addPolygon(triangle)
                        painter.fillPath(path, tile_color)
                        # Draw base block
                        painter.fillRect(0, 24, 96, 24, (inner_color if is_enabled else faint_color))
                        # Draw border lines for base block
                        pen = QtGui.QPen(outline_color if is_enabled else faint_color)
                        pen.setWidth(2)
                        painter.setPen(pen)
                        painter.drawLine(0, 0, 96, 24)  # Diagonal from top-left to bottom-right
                        painter.drawLine(0, 0, 0, 48)  # Left edge
                        painter.drawLine(0, 48, 96, 48)  # Bottom edge
                        painter.drawLine(96, 24, 96, 48)  # Right edge
                        
                    elif position_type == 'slope_bottom_1x1_left':
                        painter.fillRect(0, 0, pixmap_width, pixmap_height, tile_color)
                        # Draw base block (top part for bottom slopes)
                        painter.fillRect(0, 0, 24, 24, (inner_color if is_enabled else faint_color))
                        # Draw filled triangle for slope (bottom part)
                        triangle = QtGui.QPolygonF([
                            QtCore.QPointF(0, 24),    # top-left
                            QtCore.QPointF(24, 24),   # bottom-right
                            QtCore.QPointF(24, 48)    # bottom-left
                        ])
                        path = QtGui.QPainterPath()
                        path.addPolygon(triangle)
                        painter.fillPath(path, tile_color)
                        # Draw border lines
                        pen = QtGui.QPen(outline_color if is_enabled else faint_color)
                        pen.setWidth(2)
                        painter.setPen(pen)
                        painter.drawLine(0, 24, 24, 48)  # Diagonal from top-left to bottom-right
                        painter.drawLine(0, 0, 0, 24)  # Left edge
                        painter.drawLine(0, 0, 24, 0)  # Top edge
                        painter.drawLine(24, 0, 24, 48)  # Right edge
                        
                    elif position_type == 'slope_bottom_1x1_right':
                        painter.fillRect(0, 0, pixmap_width, pixmap_height, tile_color)
                        # Draw base block (top part for bottom slopes)
                        painter.fillRect(0, 0, 24, 24, (inner_color if is_enabled else faint_color))
                        # Draw filled triangle for slope (bottom part)
                        triangle = QtGui.QPolygonF([
                            QtCore.QPointF(0, 24),    # bottom-left
                            QtCore.QPointF(0, 48),   # top-right
                            QtCore.QPointF(24, 24)   # bottom-right
                        ])
                        path = QtGui.QPainterPath()
                        path.addPolygon(triangle)
                        painter.fillPath(path, tile_color)
                        # Draw border lines
                        pen = QtGui.QPen(outline_color if is_enabled else faint_color)
                        pen.setWidth(2)
                        painter.setPen(pen)
                        painter.drawLine(0, 48, 24, 24)  # Diagonal from bottom-left to top-right
                        painter.drawLine(0, 0, 0, 48)  # Left edge
                        painter.drawLine(0, 0, 24, 0)  # Top edge
                        painter.drawLine(24, 0, 24, 24)  # Right edge
                        
                    elif position_type == 'slope_bottom_2x1_left':
                        painter.fillRect(0, 0, pixmap_width, pixmap_height, tile_color)
                        # Draw base block (top part for bottom slopes)
                        painter.fillRect(0, 0, 48, 24, (inner_color if is_enabled else faint_color))
                        # Draw filled triangle for slope (bottom part)
                        triangle = QtGui.QPolygonF([
                            QtCore.QPointF(0, 24),    # top-left
                            QtCore.QPointF(48, 24),   # bottom-right
                            QtCore.QPointF(48, 48)    # bottom-left
                        ])
                        path = QtGui.QPainterPath()
                        path.addPolygon(triangle)
                        painter.fillPath(path, tile_color)
                        # Draw border lines
                        pen = QtGui.QPen(outline_color if is_enabled else faint_color)
                        pen.setWidth(2)
                        painter.setPen(pen)
                        painter.drawLine(0, 24, 48, 48)  # Diagonal from top-left to bottom-right
                        painter.drawLine(0, 0, 0, 24)  # Left edge
                        painter.drawLine(0, 0, 48, 0)  # Top edge
                        painter.drawLine(48, 0, 48, 48)  # Right edge
                        
                    elif position_type == 'slope_bottom_2x1_right':
                        painter.fillRect(0, 0, pixmap_width, pixmap_height, tile_color)
                        # Draw base block (top part for bottom slopes)
                        painter.fillRect(0, 0, 48, 24, (inner_color if is_enabled else faint_color))
                        # Draw filled triangle for slope (bottom part)
                        triangle = QtGui.QPolygonF([
                            QtCore.QPointF(0, 48),    # bottom-left
                            QtCore.QPointF(48, 24),   # top-right
                            QtCore.QPointF(0, 24)   # bottom-right
                        ])
                        path = QtGui.QPainterPath()
                        path.addPolygon(triangle)
                        painter.fillPath(path, tile_color)
                        # Draw border lines
                        pen = QtGui.QPen(outline_color if is_enabled else faint_color)
                        pen.setWidth(2)
                        painter.setPen(pen)
                        painter.drawLine(0, 48, 48, 24)  # Diagonal from bottom-left to top-right
                        painter.drawLine(0, 0, 0, 48)  # Left edge
                        painter.drawLine(0, 0, 48, 0)  # Top edge
                        painter.drawLine(48, 0, 48, 24)  # Right edge
                        
                    elif position_type == 'slope_bottom_4x1_left':
                        painter.fillRect(0, 0, pixmap_width, pixmap_height, tile_color)
                        # Draw base block (top part for bottom slopes)
                        painter.fillRect(0, 0, 96, 24, (inner_color if is_enabled else faint_color))
                        # Draw filled triangle for slope (bottom part)
                        triangle = QtGui.QPolygonF([
                            QtCore.QPointF(0, 24),    # top-left
                            QtCore.QPointF(96, 48),   # bottom-right
                            QtCore.QPointF(96, 24)    # bottom-left
                        ])
                        path = QtGui.QPainterPath()
                        path.addPolygon(triangle)
                        painter.fillPath(path, tile_color)
                        # Draw border lines
                        pen = QtGui.QPen(outline_color if is_enabled else faint_color)
                        pen.setWidth(2)
                        painter.setPen(pen)
                        painter.drawLine(0, 24, 96, 48)  # Diagonal from top-left to bottom-right
                        painter.drawLine(0, 0, 0, 24)  # Left edge
                        painter.drawLine(0, 0, 96, 0)  # Top edge
                        painter.drawLine(96, 0, 96, 48)  # Right edge
                        
                    elif position_type == 'slope_bottom_4x1_right':
                        painter.fillRect(0, 0, pixmap_width, pixmap_height, tile_color)
                        # Draw base block (top part for bottom slopes)
                        painter.fillRect(0, 0, 96, 24, (inner_color if is_enabled else faint_color))
                        # Draw filled triangle for slope (bottom part)
                        triangle = QtGui.QPolygonF([
                            QtCore.QPointF(0, 48),    # bottom-left
                            QtCore.QPointF(96, 24),   # top-right
                            QtCore.QPointF(0, 24)   # bottom-right
                        ])
                        path = QtGui.QPainterPath()
                        path.addPolygon(triangle)
                        painter.fillPath(path, tile_color)
                        # Draw border lines
                        pen = QtGui.QPen(outline_color if is_enabled else faint_color)
                        pen.setWidth(2)
                        painter.setPen(pen)
                        painter.drawLine(0, 48, 96, 24)  # Diagonal from bottom-left to top-right
                        painter.drawLine(0, 0, 0, 48)  # Left edge
                        painter.drawLine(0, 0, 96, 0)  # Top edge
                        painter.drawLine(96, 0, 96, 24)  # Right edge
                
                # Covered tiles (part of slope objects)
                elif position_type == 'floor_covered':
                    # Draw covered tile with faint color (no additional fill needed)
                    pass
                    
                painter.end()
                
                # Add pixmap to scene
                item = self.scene.addPixmap(pixmap)
                item.setPos(x, y)
    
    def draw_object_grid(self):
        """Draw the full terrain object grid with current layout"""
        if not globals_.ObjectDefinitions or not globals_.Tiles:
            return
        
        if self.is_drawing:
            print("[QPT] Canvas is already drawing, skipping redraw")
            return
        
        self.is_drawing = True
        print(f"[QPT] Drawing full terrain grid for tileset {self.tileset_idx}")
        
        self.scene.clear()
        self.tile_map.clear()
        
        obj_defs = globals_.ObjectDefinitions[self.tileset_idx]
        if not obj_defs:
            return
        
        # Map position types to object IDs
        position_to_obj_id = {
            'top_left': 0,
            'top': 1,
            'top_right': 2,
            'left': 3,
            'center': 5,
            'right': 7,
            'inner_top_left': 4,
            'inner_top_right': 6,
            'inner_bottom_left': 8,
            'inner_bottom_right': 10,
            'bottom_left': 11,
            'bottom': 12,
            'bottom_right': 13,
        }
        
        # Draw the grid using current layout
        current_layout = self.get_current_layout()
        for row_idx, row in enumerate(current_layout):
            x = 0
            for col_idx, (position_type, position_label) in enumerate(row):
                if position_type is None:
                    # Empty cell
                    x += 1
                    continue
                
                # Get the object ID for this position
                obj_id = position_to_obj_id.get(position_type)
                
                if obj_id is not None and obj_id < len(obj_defs) and obj_defs[obj_id] is not None:
                    pixmap = self.render_object(self.tileset_idx, obj_id)
                    
                    if pixmap and not pixmap.isNull():
                        item = self.scene.addPixmap(pixmap)
                        item.setPos(x * 24, row_idx * 24)
                        self.tile_map[(x, row_idx)] = (obj_id, position_type)
                        
                        obj_def = obj_defs[obj_id]
                        x += obj_def.width
                    else:
                        x += 1
                else:
                    x += 1
        
        # Set scene rect to fit the grid
        self.scene.setSceneRect(0, 0, 6 * 24, 8 * 24)
        # Reset transform to prevent scaling - display at 1:1 pixel ratio
        self.resetTransform()
        
        self.is_drawing = False
        print(f"[QPT] OK: Full CAT1 grid drawn for tileset {self.tileset_idx}")
    
    def find_object_for_position(self, position_type: str) -> Optional[int]:
        """
        Find an object ID that represents the given position type.
        Uses a mapping of position types to object IDs.
        
        Args:
            position_type: The position type (e.g., 'center', 'top')
        
        Returns:
            Object ID or None
        """
        # Mapping of position types to typical object IDs in CAT1
        # These are educated guesses based on typical tileset structure
        position_to_obj = {
            'top_left': 0,
            'top': 1,
            'top_right': 2,
            'left': 3,
            'inner_top_left': 4,
            'center': 5,
            'inner_top_right': 6,
            'right': 7,
            'inner_bottom_left': 8,
            'inner_bottom_right': 9,
            'bottom_left': 10,
            'bottom': 11,
            'bottom_right': 12,
        }
        
        return position_to_obj.get(position_type)
    
    def render_object(self, tileset_idx: int, obj_id: int, cap_size: bool = True) -> Optional[QtGui.QPixmap]:
        """
        Render an object preview pixmap.
        For the tile picker, we cap the size to 1x1 to fit in the grid, except for slopes which render at full size.
        
        Args:
            tileset_idx: Tileset index (0-3)
            obj_id: Object ID
            cap_size: If True, cap non-slope objects to 1x1 (24x24 px) for the tile picker grid
        
        Returns:
            QPixmap with the rendered object, or None if rendering fails
        """
        try:
            obj_defs = globals_.ObjectDefinitions[tileset_idx]
            if not obj_defs or obj_id >= len(obj_defs) or obj_defs[obj_id] is None:
                return None
            
            obj_def = obj_defs[obj_id]
            
            # For tile picker display, cap size to 1x1 to fit in grid
            # Slopes render at full size (handled separately)
            if cap_size:
                display_width = 1
                display_height = 1
            else:
                display_width = obj_def.width
                display_height = obj_def.height
            
            # Render the object using Reggie's RenderObject function
            obj_render = RenderObject(tileset_idx, obj_id, obj_def.width, obj_def.height, True)
            
            # Apply randomization for RandTiles (similar to levelitems.py randomise method)
            if globals_.TilesetInfo:
                tileset_name = self.get_tileset_name(tileset_idx)
                print(f"[QPT] Tileset name: {tileset_name}, TilesetInfo keys: {list(globals_.TilesetInfo.keys())}")
                
                if tileset_name in globals_.TilesetInfo:
                    tileset_info = globals_.TilesetInfo[tileset_name]
                    print(f"[QPT] Found tileset info for {tileset_name}")
                    
                    # Randomize tiles in the object
                    for y in range(len(obj_render)):
                        for x in range(len(obj_render[y])):
                            tile = obj_render[y][x] & 0xFF
                            
                            try:
                                tiles, direction, special = tileset_info[tile]
                                print(f"[QPT] Randomizing tile {tile} -> {tiles}")
                            except (KeyError, TypeError):
                                continue
                            
                            # Skip special top tiles
                            if special & 0b01:
                                continue
                            
                            tiles_ = tiles[:]
                            
                            # Check neighbors for direction
                            if direction & 0b01 and x > 0:
                                try:
                                    tiles_.remove(obj_render[y][x-1] & 0xFF)
                                except ValueError:
                                    pass
                            
                            if direction & 0b10 and y > 0:
                                try:
                                    tiles_.remove(obj_render[y-1][x] & 0xFF)
                                except ValueError:
                                    pass
                            
                            if not tiles_:
                                tiles_ = tiles
                            
                            # Choose a random tile
                            choice = (tileset_idx << 8) | random.choice(tiles_)
                            obj_render[y][x] = choice
                            
                            # Handle special bottom tiles
                            if special & 0b10 and y > 0:
                                obj_render[y - 1][x] = choice - 0x10
            
            # Create pixmap - only show the first 1x1 tile
            pm = QtGui.QPixmap(display_width * 24, display_height * 24)
            pm.fill(QtCore.Qt.GlobalColor.transparent)
            
            # Paint the object (only first 1x1)
            painter = QtGui.QPainter()
            painter.begin(pm)
            
            tiles_drawn = 0
            for y in range(display_height):
                for x in range(display_width):
                    if y < len(obj_render) and x < len(obj_render[y]):
                        tile_num = obj_render[y][x]
                        print(f"[QPT]     Tile at ({x},{y}): tile_num={tile_num} (0x{tile_num:04x})")
                        if tile_num > 0:
                            tile = globals_.Tiles[tile_num]
                            if tile is None:
                                print(f"[QPT]       Tile {tile_num} is None, using OVERRIDE_UNKNOWN")
                                painter.drawPixmap(x * 24, y * 24, globals_.Overrides[globals_.OVERRIDE_UNKNOWN].getCurrentTile())
                                tiles_drawn += 1
                            elif isinstance(tile.main, QtGui.QImage):
                                print(f"[QPT]       Drawing tile {tile_num} as QImage")
                                painter.drawImage(x * 24, y * 24, tile.main)
                                tiles_drawn += 1
                            else:
                                print(f"[QPT]       Drawing tile {tile_num} as QPixmap")
                                painter.drawPixmap(x * 24, y * 24, tile.main)
                                tiles_drawn += 1
                        else:
                            print(f"[QPT]       Tile {tile_num} is 0 or negative, skipping")
            
            painter.end()
            print(f"[QPT]   Rendered pixmap with {tiles_drawn} tiles")
            return pm
            
        except Exception as e:
            print(f"Error rendering object for tileset {tileset_idx}, object {obj_id}: {e}")
            return None
    
    def get_tileset_name(self, tileset_idx: int) -> str:
        """Get the tileset name from index"""
        # Try to get the actual tileset name from Reggie's TilesetFilesLoaded
        if hasattr(globals_, 'TilesetFilesLoaded') and globals_.TilesetFilesLoaded[tileset_idx]:
            full_path = globals_.TilesetFilesLoaded[tileset_idx]
            # Extract base name from path (e.g., "U:/ORIG\Texture\Pa1_nohara.arc" -> "Pa1_nohara")
            import os
            base_name = os.path.splitext(os.path.basename(full_path))[0]
            print(f"[QPT] Extracted tileset name: {base_name} from {full_path}")
            return base_name
        
        # Fallback to standard names
        names = ["Pa0", "Pa1", "Pa2", "Pa3"]
        return names[tileset_idx] if tileset_idx < len(names) else f"Pa{tileset_idx}"
    
    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Handle mouse press to select an object and assign it to selected position"""
        print(f"[QPT] Canvas mousePressEvent at {event.pos()}")
        
        if not self.selected_position_type:
            print("[QPT] No position type selected, ignoring click")
            return
        
        pos = self.mapToScene(event.pos())
        print(f"[QPT] Scene position: {pos}")
        
        # Find which object was clicked
        for (grid_x, grid_y), (obj_id, grid_position_type) in self.tile_map.items():
            # Get the object to determine its size
            obj_defs = globals_.ObjectDefinitions[self.tileset_idx]
            if obj_defs and obj_id < len(obj_defs) and obj_defs[obj_id]:
                obj_def = obj_defs[obj_id]
                obj_width = obj_def.width * 24
                obj_height = obj_def.height * 24
                
                # Check if click is within this object's bounds
                if (grid_x * 24 <= pos.x() < grid_x * 24 + obj_width and
                    grid_y * 24 <= pos.y() < grid_y * 24 + obj_height):
                    
                    print(f"[QPT] Clicked on object {obj_id} (grid position: {grid_position_type})")
                    print(f"[QPT] Assigning to selected position: {self.selected_position_type}")
                    # Emit signal with selected object and the SELECTED position type (not grid position)
                    self.tile_selected.emit(obj_id, self.selected_position_type)
                    break
    
    def set_brush(self, brush: SmartBrush):
        """
        Set the brush.
        
        Args:
            brush: SmartBrush instance
        """
        self.brush = brush
    
    def set_tileset(self, tileset_idx: int):
        """
        Set the tileset to display.
        
        Args:
            tileset_idx: Tileset index (0-3)
        """
        self.tileset_idx = tileset_idx
        print(f"[QPT] Canvas tileset set to {tileset_idx}")
    
    def set_selected_position(self, position_type: str):
        """
        Set the currently selected position type (e.g., 'center', 'top').
        
        Args:
            position_type: Position identifier
        """
        self.selected_position_type = position_type
    
    def update_canvas_display(self):
        """
        Update the canvas to show all currently assigned objects in the CAT1 grid layout.
        Only shows objects that have been assigned to positions.
        """
        if not self.brush or not globals_.ObjectDefinitions or not globals_.Tiles:
            return
        
        if self.is_drawing:
            print("[QPT] Canvas is already drawing, skipping update")
            return
        
        self.is_drawing = True
        print(f"[QPT] Updating canvas display for tileset {self.tileset_idx}")
        
        self.scene.clear()
        self.tile_map.clear()
        
        # First, redraw the tile position outlines
        self._draw_tile_outlines()
        
        obj_defs = globals_.ObjectDefinitions[self.tileset_idx]
        if not obj_defs:
            return
        
        # Build position_grid_map from current layout to ensure all positions are correctly mapped
        position_grid_map = {}
        current_layout = self.get_current_layout()
        for row_idx, row in enumerate(current_layout):
            col_idx = 0
            for position_type, position_label in row:
                if position_type is not None:
                    if position_type not in position_grid_map:
                        position_grid_map[position_type] = []
                    position_grid_map[position_type].append((col_idx, row_idx))
                col_idx += 1
        
        # Convert single-item lists to tuples for consistency
        for key in position_grid_map:
            if len(position_grid_map[key]) == 1:
                position_grid_map[key] = position_grid_map[key][0]
        
        print(f"[QPT] Position grid map: {position_grid_map}")
        
        # Draw assigned terrain objects
        for position_type in self.brush.terrain_assigned:
            obj_id = self.brush.terrain[position_type]
            
            if obj_id is not None and obj_id >= 0 and obj_id < len(obj_defs) and obj_defs[obj_id] is not None:
                # Get grid positions for this position type
                grid_positions = position_grid_map.get(position_type, [])
                if not isinstance(grid_positions, list):
                    grid_positions = [grid_positions]
                
                print(f"[QPT] Drawing position_type={position_type}, obj_id={obj_id}, grid_positions={grid_positions}")
                
                # Draw object at each grid position for this type
                for grid_x, grid_y in grid_positions:
                    pixmap = self.render_object(self.tileset_idx, obj_id)
                    
                    if pixmap and not pixmap.isNull():
                        print(f"[QPT]   OK: Drew object {obj_id} at grid ({grid_x}, {grid_y})")
                        item = self.scene.addPixmap(pixmap)
                        item.setPos(grid_x * 24, grid_y * 24)
                        self.tile_map[(grid_x, grid_y)] = (obj_id, position_type)
                    else:
                        print(f"[QPT]   ✗ Failed to render object {obj_id} at grid ({grid_x}, {grid_y})")
        
        # Helper function to get slope dimensions
        def get_slope_dimensions(slope_type):
            """Return (width, height) for slope type"""
            if '1x1' in slope_type:
                return (1, 2)  # 1 wide, 2 tall (slope + base)
            elif '2x1' in slope_type:
                return (2, 2)  # 2 wide, 2 tall (slope + base)
            elif '4x1' in slope_type:
                return (4, 2)  # 4 wide, 2 tall (slope + base)
            return (1, 2)
        
        # Draw assigned slope objects
        for slope_type in self.brush.slopes_assigned:
            obj_id = self.brush.slopes[slope_type]
            
            if obj_id is not None and obj_id >= 0 and obj_id < len(obj_defs) and obj_defs[obj_id] is not None:
                # Get grid position for this slope type
                grid_position = position_grid_map.get(slope_type)
                if grid_position:
                    if not isinstance(grid_position, list):
                        grid_position = [grid_position]
                    
                    print(f"[QPT] Drawing slope_type={slope_type}, obj_id={obj_id}, grid_positions={grid_position}")
                    
                    # Draw slope object at grid position (slopes render at full size)
                    for grid_x, grid_y in grid_position:
                        pixmap = self.render_object(self.tileset_idx, obj_id, cap_size=False)
                        
                        if pixmap and not pixmap.isNull():
                            print(f"[QPT]   OK: Drew slope {obj_id} at grid ({grid_x}, {grid_y})")
                            item = self.scene.addPixmap(pixmap)
                            item.setPos(grid_x * 24, grid_y * 24)
                            self.tile_map[(grid_x, grid_y)] = (obj_id, slope_type)
                            
                            # Mark all tiles that this slope spans as occupied
                            slope_width, slope_height = get_slope_dimensions(slope_type)
                            for dy in range(slope_height):
                                for dx in range(slope_width):
                                    self.tile_map[(grid_x + dx, grid_y + dy)] = (obj_id, slope_type)
                        else:
                            print(f"[QPT]   ✗ Failed to render slope {obj_id} at grid ({grid_x}, {grid_y})")
        
        # Set scene rect to fit the full grid (16x8)
        width, height = self.get_grid_dimensions()
        self.scene.setSceneRect(0, 0, width * 24, height * 24)
        # Reset transform to prevent scaling - display at 1:1 pixel ratio
        self.resetTransform()
        
        self.is_drawing = False
        print(f"[QPT] OK: Canvas display updated")
    
    def draw_position_objects(self, position_type: str):
        """
        Draw only the objects that match the selected position type.
        
        Args:
            position_type: The position type to display (e.g., 'center', 'top', 'top_left')
        """
        if not globals_.ObjectDefinitions or not globals_.Tiles:
            return
        
        if self.is_drawing:
            print("[QPT] Canvas is already drawing, skipping redraw")
            return
        
        self.is_drawing = True
        print(f"[QPT] Drawing objects for position: {position_type}")
        
        self.scene.clear()
        self.tile_map.clear()
        
        obj_defs = globals_.ObjectDefinitions[self.tileset_idx]
        if not obj_defs:
            return
        
        # Map position types to their object IDs in CAT1
        position_to_objects = {
            'top_left': [0],
            'top': [1],
            'top_right': [2],
            'left': [3, 7],  # Left appears in multiple rows
            'inner_top_left': [4],
            'center': [5, 9],  # Center appears in multiple rows
            'inner_top_right': [6],
            'right': [7],
            'inner_bottom_left': [8],
            'inner_bottom_right': [10],
            'bottom_left': [11],
            'bottom': [12],
            'bottom_right': [13],
        }
        
        # Get the object IDs for this position
        obj_ids = position_to_objects.get(position_type, [])
        
        x = 0
        y = 0
        
        # Draw each object for this position
        for obj_id in obj_ids:
            if obj_id < len(obj_defs) and obj_defs[obj_id] is not None:
                pixmap = self.render_object(self.tileset_idx, obj_id)
                
                if pixmap and not pixmap.isNull():
                    item = self.scene.addPixmap(pixmap)
                    item.setPos(x * 24, y * 24)
                    self.tile_map[(x, y)] = (obj_id, position_type)
                    
                    obj_def = obj_defs[obj_id]
                    x += obj_def.width
                    
                    # Move to next row if we have multiple objects
                    if x > 200:  # Arbitrary width limit
                        x = 0
                        y += obj_def.height + 1
        
        # Set scene rect to fit content without scaling
        self.scene.setSceneRect(self.scene.itemsBoundingRect())
        # Reset transform to prevent scaling - objects should display at 1:1 pixel ratio
        self.resetTransform()
        
        self.is_drawing = False
        print(f"[QPT] OK: Objects drawn for position: {position_type}")
    
    def get_selected_tiles(self) -> Dict[str, int]:
        """
        Get all selected tiles from the brush.
        
        Returns:
            Dictionary mapping position to object_id
        """
        if not self.brush:
            return {}
        
        tiles = {}
        
        # Get terrain tiles
        for pos in ['center', 'top', 'bottom', 'left', 'right', 'top_left', 'top_right', 'bottom_left', 'bottom_right', 'inner_top_left', 'inner_top_right', 'inner_bottom_left', 'inner_bottom_right']:
            tile_id = self.brush.get_terrain_tile(pos)
            if tile_id is not None:
                tiles[pos] = tile_id
        
        return tiles
    
    def _add_ui_elements(self):
        """Add status indicator circle and clear button to the view"""
        # Only create clear button once
        if not hasattr(self, 'clear_button'):
            # Clear button (bottom right, hovering)
            self.clear_button = QtWidgets.QPushButton("CLEAR")
            self.clear_button.setStyleSheet("QPushButton { background-color: #555; color: white; border: 1px solid #888; padding: 2px; font-size: 9px; }")
            self.clear_button.clicked.connect(self.clear_all_tiles)
            self.clear_button.setParent(self)  # Set parent to this view
        
        # Position the button
        self._position_clear_button()
        self.clear_button.show()
        
        # Create status indicator as a custom widget overlay
        if not hasattr(self, 'status_indicator'):
            self.status_indicator = QtWidgets.QLabel()
            self.status_indicator.setParent(self)
            self.status_indicator.setFixedSize(16, 16)
            self.status_indicator.setStyleSheet("border-radius: 8px; border: 1px solid gray;")
        
        # Position at top-left of the view (not scene)
        self.status_indicator.move(5, 5)
        self.status_indicator.show()
        
        # Update the status color
        self.update_status_indicator()
    
    def _position_clear_button(self):
        """Position the clear button at the bottom right of the view"""
        # This will be repositioned when the view is resized
        view_rect = self.viewport().rect()
        button_width = 60
        button_height = 20
        x = view_rect.width() - button_width - 5
        y = view_rect.height() - button_height - 5
        self.clear_button.setGeometry(x, y, button_width, button_height)
    
    def resizeEvent(self, event):
        """Handle view resize to reposition the clear button"""
        super().resizeEvent(event)
        if hasattr(self, 'clear_button'):
            self._position_clear_button()
    
    def update_status_indicator(self):
        """Update the status indicator circle based on assignment completion"""
        if not self.brush or not hasattr(self, 'status_indicator'):
            return
        
        # Check if all required terrain tiles are assigned
        required_positions = ['center', 'top', 'bottom', 'left', 'right', 'top_left', 'top_right', 'bottom_left', 'bottom_right', 'inner_top_left', 'inner_top_right', 'inner_bottom_left', 'inner_bottom_right']
        terrain_assigned = all(pos in self.brush.terrain_assigned for pos in required_positions)
        
        # Check if all enabled slopes are assigned
        enabled_slopes = self.brush.enabled_slopes
        slopes_assigned = all(slope in self.brush.slopes_assigned for slope in enabled_slopes) if enabled_slopes else True
        
        # All assigned only if both terrain and slopes are assigned
        all_assigned = terrain_assigned and slopes_assigned
        
        # Set color: green if all assigned, red if not
        color = "#00ff00" if all_assigned else "#ff0000"  # Green or Red
        self.status_indicator.setStyleSheet(f"background-color: {color}; border-radius: 8px; border: 1px solid gray;")
        
        status_text = "OK: All assigned" if all_assigned else "⚠ Incomplete"
        print(f"[QPT] Status: {status_text} (terrain={terrain_assigned}, slopes={slopes_assigned})")
    
    def clear_all_tiles(self):
        """Clear all assigned tiles (terrain and slopes) from the brush and canvas"""
        if not self.brush:
            return
        
        print("[QPT] Clearing all assigned tiles...")
        
        # Clear all terrain assignments
        for pos in ['center', 'top', 'bottom', 'left', 'right', 'top_left', 'top_right', 'bottom_left', 'bottom_right', 'inner_top_left', 'inner_top_right', 'inner_bottom_left', 'inner_bottom_right']:
            self.brush.terrain[pos] = None
        
        # Clear the terrain_assigned set
        self.brush.terrain_assigned.clear()
        
        # Clear all slope assignments
        for slope_name in self.brush.slopes:
            self.brush.slopes[slope_name] = None
        
        # Clear the slopes_assigned set
        self.brush.slopes_assigned.clear()
        
        # Redraw the canvas
        self.draw_empty_grid()
        self.update_status_indicator()
        
        print("[QPT] OK: All tiles and slopes cleared")
    
    def mousePressEvent(self, event):
        """
        Handle mouse clicks on the tile picker canvas.
        Clicking on a cell assigns the selected object to that position.
        """
        if not self.brush:
            print("[QPT] No brush selected, cannot assign tiles")
            return
        
        # Get the scene position from the view position
        scene_pos = self.mapToScene(event.pos())
        
        # Calculate grid coordinates (each cell is 24x24)
        grid_x = int(scene_pos.x() // 24)
        grid_y = int(scene_pos.y() // 24)
        
        print(f"[QPT] Clicked on grid cell ({grid_x}, {grid_y})")
        
        # Get grid dimensions for current category
        width, height = self.get_grid_dimensions()
        
        # Check if the click is within the grid bounds
        if grid_x < 0 or grid_x >= width or grid_y < 0 or grid_y >= height:
            print(f"[QPT] Click outside grid bounds ({width}x{height})")
            return
        
        # Get the position type from the current layout
        current_layout = self.get_current_layout()
        if grid_y >= len(current_layout):
            return
        
        row = current_layout[grid_y]
        if grid_x >= len(row):
            return
        
        position_type, _ = row[grid_x]
        
        if position_type is None:
            print(f"[QPT] No position type at ({grid_x}, {grid_y})")
            return
        
        print(f"[QPT] Position type at ({grid_x}, {grid_y}): {position_type}")
        
        # Emit the signal to notify the parent widget
        self.tile_selected.emit(grid_x * 24 + grid_y * 24, position_type)
        
        # Call the parent's handler if available
        parent = self.parent()
        if parent and hasattr(parent, 'on_tile_selected_from_canvas'):
            parent.on_tile_selected_from_canvas(position_type)
