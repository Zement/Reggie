"""
Canvas-based Tile Picker Widget - Displays terrain objects in a grid for selection
Similar to the original Reggie tile picker
"""
import random
from typing import Dict, Optional, Tuple, List
from PyQt6 import QtWidgets, QtCore, QtGui

from quickpaint.core.brush import SmartBrush, TilesetCategory
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
    
    # CAT1 terrain object layout - 6x8 grid with hardcoded positions
    # Each cell contains (object_id, position_type)
    CAT1_LAYOUT = [
        # Row 1: Top Left, Top, Top, Top, Top, Top Right
        [('top_left', 'top_left'), ('top', 'top'), ('top', 'top'), ('top', 'top'), ('top', 'top'), ('top_right', 'top_right')],
        # Row 2: Left, Center, Center, Center, Center, Right
        [('left', 'left'), ('center', 'center'), ('center', 'center'), ('center', 'center'), ('center', 'center'), ('right', 'right')],
        # Row 3: Left, Ceiling Left Inner, Ceiling, Ceiling, Ceiling Right Inner, Right
        [('left', 'left'), ('inner_bottom_left', 'inner_bottom_left'), ('bottom', 'bottom'), ('bottom', 'bottom'), ('inner_bottom_right', 'inner_bottom_right'), ('right', 'right')],
        # Row 4: Left, Right, Nothing, Nothing, Left, Right
        [('left', 'left'), ('right', 'right'), (None, None), (None, None), ('left', 'left'), ('right', 'right')],
        # Row 5: Left, Right, Nothing, Nothing, Left, Right
        [('left', 'left'), ('right', 'right'), (None, None), (None, None), ('left', 'left'), ('right', 'right')],
        # Row 6: Left, Top Left Inner, Top, Top, Top Right Inner, Right
        [('left', 'left'), ('inner_top_left', 'inner_top_left'), ('top', 'top'), ('top', 'top'), ('inner_top_right', 'inner_top_right'), ('right', 'right')],
        # Row 7: Left, Center, Center, Center, Center, Right
        [('left', 'left'), ('center', 'center'), ('center', 'center'), ('center', 'center'), ('center', 'center'), ('right', 'right')],
        # Row 8: Bottom Left, Bottom, Bottom, Bottom, Bottom, Bottom Right
        [('bottom_left', 'bottom_left'), ('bottom', 'bottom'), ('bottom', 'bottom'), ('bottom', 'bottom'), ('bottom', 'bottom'), ('bottom_right', 'bottom_right')],
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
        self.category = TilesetCategory.CAT1 if brush else TilesetCategory.CAT1
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
    
    def init_ui(self):
        """Initialize the UI"""
        self.setMinimumHeight(200)
        self.setMaximumHeight(200)
        self.setStyleSheet("QGraphicsView { background-color: #2a2a2a; border: 1px solid #555; }")
        
        # Draw empty grid placeholder
        self.draw_empty_grid()
    
    def draw_empty_grid(self):
        """Draw an empty 6x8 grid with tile position outlines"""
        self.scene.clear()
        self.tile_map.clear()
        
        # Draw tile position outlines for each cell in the CAT1 layout
        self._draw_tile_outlines()
        
        # Set scene rect to match 6x8 grid at 24x24 cells
        self.scene.setSceneRect(0, 0, 6 * 24, 8 * 24)
        self.fitInView(self.scene.sceneRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        
        print("[QPT] Empty grid with tile outlines drawn")
    
    def _draw_tile_outlines(self):
        """Draw minimalistic tile position outlines using QPaint with grass details"""
        # Colors: Color 2 (80% opaque gray) for outlines, Color 3 (50% opaque gray) for inner tiles
        outline_color = QtGui.QColor(128, 128, 128, 204)  # 80% opaque gray
        inner_color = QtGui.QColor(128, 128, 128, 127)    # 50% opaque gray
        
        # Iterate through CAT1_LAYOUT and draw outlines for each position
        for row_idx, row in enumerate(self.CAT1_LAYOUT):
            for col_idx, (position_type, _) in enumerate(row):
                if position_type is None:
                    continue
                
                x = col_idx * 24
                y = row_idx * 24
                
                # Create a pixmap for this cell
                pixmap = QtGui.QPixmap(24, 24)
                pixmap.fill(QtCore.Qt.GlobalColor.transparent)
                
                painter = QtGui.QPainter(pixmap)
                painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
                
                # Draw based on position type
                if position_type == 'center':
                    # Center: empty (transparent)
                    pass
                elif position_type == 'top':
                    # Top edge: horizontal line with grass blades
                    pen = QtGui.QPen(outline_color)
                    pen.setWidth(2)
                    painter.setPen(pen)
                    painter.drawLine(2, 4, 22, 4)  # Main edge line
                    
                    # Draw grass blades (3 blades = 6 strokes)
                    painter.drawLine(6, 2, 8, 4)
                    painter.drawLine(8, 4, 10, 2)
                    painter.drawLine(12, 2, 14, 4)
                    painter.drawLine(14, 4, 16, 2)
                    painter.drawLine(18, 2, 20, 4)
                    painter.drawLine(20, 4, 22, 2)
                
                elif position_type == 'bottom':
                    # Bottom edge: horizontal line with grass blades
                    pen = QtGui.QPen(outline_color)
                    pen.setWidth(2)
                    painter.setPen(pen)
                    painter.drawLine(2, 20, 22, 20)  # Main edge line
                    
                    # Draw grass blades
                    painter.drawLine(6, 22, 8, 20)
                    painter.drawLine(8, 20, 10, 22)
                    painter.drawLine(12, 22, 14, 20)
                    painter.drawLine(14, 20, 16, 22)
                    painter.drawLine(18, 22, 20, 20)
                    painter.drawLine(20, 20, 22, 22)
                
                elif position_type in ['left', 'right']:
                    # Side edges: vertical line
                    pen = QtGui.QPen(outline_color)
                    pen.setWidth(2)
                    painter.setPen(pen)
                    
                    if position_type == 'left':
                        painter.drawLine(4, 2, 4, 22)
                    else:  # right
                        painter.drawLine(20, 2, 20, 22)
                
                elif position_type == 'top_left':
                    # Top-left corner: diagonal with rounded corner and grass
                    pen = QtGui.QPen(outline_color)
                    pen.setWidth(2)
                    painter.setPen(pen)
                    
                    # Draw diagonal with rounded corner
                    path = QtGui.QPainterPath()
                    path.moveTo(4, 22)
                    path.lineTo(4, 8)
                    path.arcTo(4, 2, 8, 8, 180, 90)  # Rounded corner
                    path.lineTo(22, 2)
                    painter.drawPath(path)
                    
                    # Grass blade
                    painter.drawLine(20, 2, 22, 4)
                    painter.drawLine(22, 4, 20, 6)
                
                elif position_type == 'top_right':
                    # Top-right corner: diagonal with rounded corner and grass
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
                    
                    # Grass blade
                    painter.drawLine(4, 2, 2, 4)
                    painter.drawLine(2, 4, 4, 6)
                
                elif position_type == 'bottom_left':
                    # Bottom-left corner: diagonal with rounded corner and grass
                    pen = QtGui.QPen(outline_color)
                    pen.setWidth(2)
                    painter.setPen(pen)
                    
                    # Draw diagonal with rounded corner
                    path = QtGui.QPainterPath()
                    path.moveTo(4, 2)
                    path.lineTo(4, 16)
                    path.arcTo(4, 14, 8, 8, 180, -90)  # Rounded corner
                    path.lineTo(22, 22)
                    painter.drawPath(path)
                    
                    # Grass blade
                    painter.drawLine(20, 22, 22, 20)
                    painter.drawLine(22, 20, 20, 18)
                
                elif position_type == 'bottom_right':
                    # Bottom-right corner: diagonal with rounded corner and grass
                    pen = QtGui.QPen(outline_color)
                    pen.setWidth(2)
                    painter.setPen(pen)
                    
                    # Draw diagonal with rounded corner
                    path = QtGui.QPainterPath()
                    path.moveTo(20, 2)
                    path.lineTo(20, 16)
                    path.arcTo(12, 14, 8, 8, 0, -90)  # Rounded corner
                    path.lineTo(2, 22)
                    painter.drawPath(path)
                    
                    # Grass blade
                    painter.drawLine(4, 22, 2, 20)
                    painter.drawLine(2, 20, 4, 18)
                
                elif position_type in ['inner_top_left', 'inner_top_right', 'inner_bottom_left', 'inner_bottom_right']:
                    # Inner tiles: solid fill
                    painter.fillRect(4, 4, 16, 16, inner_color)
                
                painter.end()
                
                # Add pixmap to scene
                item = self.scene.addPixmap(pixmap)
                item.setPos(x, y)
    
    def draw_object_grid(self):
        """Draw the full CAT1 terrain object grid (6x8)"""
        if not globals_.ObjectDefinitions or not globals_.Tiles:
            return
        
        if self.is_drawing:
            print("[QPT] Canvas is already drawing, skipping redraw")
            return
        
        self.is_drawing = True
        print(f"[QPT] Drawing full CAT1 grid for tileset {self.tileset_idx}")
        
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
        
        # Draw the full 6x8 grid
        for row_idx, row in enumerate(self.CAT1_LAYOUT):
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
        self.fitInView(self.scene.sceneRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        
        self.is_drawing = False
        print(f"[QPT] ✓ Full CAT1 grid drawn for tileset {self.tileset_idx}")
    
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
    
    def render_object(self, tileset_idx: int, obj_id: int) -> Optional[QtGui.QPixmap]:
        """
        Render an object preview pixmap.
        For the tile picker, we cap the size to 1x1 to fit in the grid.
        
        Args:
            tileset_idx: Tileset index (0-3)
            obj_id: Object ID
        
        Returns:
            QPixmap with the rendered object, or None if rendering fails
        """
        try:
            obj_defs = globals_.ObjectDefinitions[tileset_idx]
            if not obj_defs or obj_id >= len(obj_defs) or obj_defs[obj_id] is None:
                return None
            
            obj_def = obj_defs[obj_id]
            
            # For tile picker display, cap size to 1x1 to fit in grid
            display_width = min(obj_def.width, 1)
            display_height = min(obj_def.height, 1)
            
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
        self.category = brush.category
    
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
        
        # Build position_grid_map from CAT1_LAYOUT to ensure all positions are correctly mapped
        position_grid_map = {}
        for row_idx, row in enumerate(self.CAT1_LAYOUT):
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
        
        # Draw assigned objects (only draw positions that have been explicitly assigned)
        for position_type in self.brush.terrain_assigned:
            obj_id = self.brush.terrain[position_type]
            
            if obj_id >= 0 and obj_id < len(obj_defs) and obj_defs[obj_id] is not None:
                # Get grid positions for this position type
                grid_positions = position_grid_map.get(position_type, [])
                if not isinstance(grid_positions, list):
                    grid_positions = [grid_positions]
                
                print(f"[QPT] Drawing position_type={position_type}, obj_id={obj_id}, grid_positions={grid_positions}")
                
                # Draw object at each grid position for this type
                for grid_x, grid_y in grid_positions:
                    pixmap = self.render_object(self.tileset_idx, obj_id)
                    
                    if pixmap and not pixmap.isNull():
                        print(f"[QPT]   ✓ Drew object {obj_id} at grid ({grid_x}, {grid_y})")
                        item = self.scene.addPixmap(pixmap)
                        item.setPos(grid_x * 24, grid_y * 24)
                        self.tile_map[(grid_x, grid_y)] = (obj_id, position_type)
                    else:
                        print(f"[QPT]   ✗ Failed to render object {obj_id} at grid ({grid_x}, {grid_y})")
        
        # Set scene rect to fit the grid
        self.scene.setSceneRect(0, 0, 6 * 24, 8 * 24)
        self.fitInView(self.scene.sceneRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        
        self.is_drawing = False
        print(f"[QPT] ✓ Canvas display updated")
    
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
        
        # Set scene rect
        self.scene.setSceneRect(0, 0, 500, 300)
        self.fitInView(self.scene.sceneRect(), QtCore.Qt.AspectRatioMode.KeepAspectRatio)
        
        self.is_drawing = False
        print(f"[QPT] ✓ Objects drawn for position: {position_type}")
    
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
            if tile_id > 0:
                tiles[pos] = tile_id
        
        return tiles
