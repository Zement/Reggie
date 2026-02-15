"""
Reggie Integration Hook - Connects QPT to Reggie's core systems
"""
from typing import Optional, List, Tuple
from PyQt6 import QtWidgets, QtCore, QtGui

# Defer all imports to avoid QWidget creation before QApplication is ready
# These will be imported inside methods when needed


class ReggieQuickPaintHook:
    """
    Main integration hook for Quick Paint Tool in Reggie.
    
    Handles:
    - Mouse event interception
    - Outline rendering
    - Operation execution
    - Level integration
    - Hotkey overlay display
    """
    
    def __init__(self):
        """Initialize the QPT hook"""
        self.palette: Optional[QtWidgets.QWidget] = None  # Will be QuickPaintPalette after initialization
        self.outline_items: List = []
        self.is_active = False
        self.hotkey_overlay = None
        self._main_window = None
    
    def initialize(self, main_window):
        """
        Initialize QPT and add to Reggie's sidebar.
        
        Args:
            main_window: Reggie's main window
        
        Returns:
            QuickPaintPalette widget
        """
        # Import here to avoid QWidget creation before QApplication is ready
        from quickpaint.ui.reggie_integration import QuickPaintPalette
        
        self._main_window = main_window
        self.palette = QuickPaintPalette()
        self.is_active = True
        self.fill_preview_items = []
        
        # Set up fill engine callbacks
        self._setup_fill_engine()
        
        # Connect fill signals to visualization and placement
        fill_tab = self.palette.get_fill_paint_tab()
        fill_tab.fill_confirmed.connect(self.apply_fill)
        
        # Connect fill engine signals for preview visualization
        from quickpaint.core.fill_engine import get_fill_engine
        fill_engine = get_fill_engine()
        fill_engine.fill_preview_updated.connect(self._on_fill_preview_updated)
        fill_engine.fill_cancelled.connect(self.clear_fill_preview)
        
        # Create hotkey overlay (defer to after window is fully initialized)
        QtCore.QTimer.singleShot(500, self._create_hotkey_overlay)
        
        # Connect tool changes to update overlay
        from quickpaint.core.tool_manager import get_tool_manager
        tool_manager = get_tool_manager()
        tool_manager.tool_changed.connect(self._on_tool_changed_for_overlay)
        
        return self.palette
    
    def _create_hotkey_overlay(self):
        """Create and position the hotkey overlay"""
        try:
            from quickpaint.ui.hotkey_overlay import create_hotkey_overlay
            import globals_
            
            if globals_.mainWindow:
                self.hotkey_overlay = create_hotkey_overlay(globals_.mainWindow)
                if self.hotkey_overlay:
                    self._update_overlay_position()
                    print("[QPT] Hotkey overlay created")
                    
                    # Check if QPT tab is currently active and show overlay
                    if (hasattr(globals_.mainWindow, 'qpt_palette') and 
                        globals_.mainWindow.qpt_palette and 
                        hasattr(globals_.mainWindow, 'creationTabs')):
                        for i in range(globals_.mainWindow.creationTabs.count()):
                            if globals_.mainWindow.creationTabs.widget(i) == globals_.mainWindow.qpt_palette:
                                if globals_.mainWindow.creationTabs.currentIndex() == i:
                                    self.show_hotkey_overlay()
                                    print("[QPT] Hotkey overlay shown (QPT tab active)")
                                break
        except Exception as e:
            print(f"[QPT] Error creating hotkey overlay: {e}")
    
    def _update_overlay_position(self):
        """Update overlay position based on view geometry"""
        if not self.hotkey_overlay:
            return
        
        import globals_
        if globals_.mainWindow and hasattr(globals_.mainWindow, 'view') and globals_.mainWindow.view:
            view_geo = globals_.mainWindow.view.geometry()
            self.hotkey_overlay.position_overlay(view_geo)
    
    def _on_tool_changed_for_overlay(self, new_tool, old_tool):
        """Update overlay when tool changes"""
        if not self.hotkey_overlay:
            return
        
        from quickpaint.core.tool_manager import ToolType
        
        if new_tool == ToolType.QPT_SMART_PAINT:
            self.hotkey_overlay.set_active_tool("qpt")
        elif new_tool == ToolType.QPT_SINGLE_TILE:
            self.hotkey_overlay.set_active_tool("single_tile")
        elif new_tool == ToolType.QPT_ERASER:
            self.hotkey_overlay.set_active_tool("eraser")
        elif new_tool == ToolType.QPT_SHAPE_CREATOR:
            self.hotkey_overlay.set_active_tool("shape_creator")
        elif new_tool == ToolType.FILL_PAINT:
            self.hotkey_overlay.set_active_tool("fill")
        elif new_tool == ToolType.DECO_FILL:
            self.hotkey_overlay.set_active_tool("deco")
        else:
            self.hotkey_overlay.set_active_tool(None)
    
    def show_hotkey_overlay(self):
        """Show the hotkey overlay"""
        if self.hotkey_overlay:
            self._update_overlay_position()
            self.hotkey_overlay.show_overlay()
    
    def hide_hotkey_overlay(self):
        """Hide the hotkey overlay"""
        if self.hotkey_overlay:
            self.hotkey_overlay.hide_overlay()
    
    def _on_fill_preview_updated(self, positions: list):
        """Handle fill preview update from engine"""
        self.clear_fill_preview()
        
        if not positions:
            return
        
        import globals_
        
        # Blue color for fill preview
        pen = QtGui.QPen(QtGui.QColor(60, 100, 200))  # Blue
        pen.setWidth(2)
        brush = QtGui.QBrush(QtGui.QColor(60, 100, 200, 80))  # Semi-transparent blue
        
        # Create visual fill preview items
        for x, y in positions:
            rect = QtCore.QRectF(x * 24, y * 24, 24, 24)
            rect_item = QtWidgets.QGraphicsRectItem(rect)
            rect_item.setPen(pen)
            rect_item.setBrush(brush)
            globals_.mainWindow.scene.addItem(rect_item)
            self.fill_preview_items.append(rect_item)
        
        print(f"[QPT Hook] Fill preview: {len(positions)} tiles")
    
    def _setup_fill_engine(self):
        """Set up callbacks for the fill engine"""
        from quickpaint.core.fill_engine import get_fill_engine
        
        fill_engine = get_fill_engine()
        fill_engine.set_zone_bounds_callback(self._get_zone_bounds)
        fill_engine.set_tile_occupied_callback(self._is_tile_occupied)
    
    def _get_zone_bounds(self, tile_x: int, tile_y: int):
        """
        Get zone bounds for a tile position.
        
        Args:
            tile_x, tile_y: Tile coordinates
            
        Returns:
            (zone_x, zone_y, zone_width, zone_height) in tiles, or None if outside zones
        """
        import globals_
        
        if not hasattr(globals_, 'Area') or globals_.Area is None:
            print(f"[Fill] No Area available")
            return None
        
        # Zone coordinates are in Reggie internal units (1 block = 16 pixels)
        # Tiles are 24 pixels = 16 internal units * 1.5 display scale
        # So: tile * 24 / 1.5 = tile * 16 internal units
        internal_x = tile_x * 16
        internal_y = tile_y * 16
        
        print(f"[Fill] Checking zones for tile ({tile_x}, {tile_y}) = internal ({internal_x}, {internal_y})")
        print(f"[Fill] Area has {len(globals_.Area.zones)} zones")
        
        # Check each zone in the current area
        for i, zone in enumerate(globals_.Area.zones):
            # Zone objx/objy/width/height are in internal units
            zx = zone.objx
            zy = zone.objy
            zw = zone.width
            zh = zone.height
            
            print(f"[Fill] Zone {i}: pos=({zx}, {zy}), size=({zw}, {zh}), bounds=({zx}-{zx+zw}, {zy}-{zy+zh})")
            
            # Check if point is inside zone (using internal units)
            if zx <= internal_x < zx + zw and zy <= internal_y < zy + zh:
                # Convert zone bounds to tile coordinates
                # tile = internal_unit / 16
                zone_tx = zx // 16
                zone_ty = zy // 16
                zone_tw = zw // 16
                zone_th = zh // 16
                print(f"[Fill] Found matching zone {i}: tiles ({zone_tx}, {zone_ty}, {zone_tw}, {zone_th})")
                return (zone_tx, zone_ty, zone_tw, zone_th)
        
        print(f"[Fill] Point internal ({internal_x}, {internal_y}) is outside all zones")
        return None  # Outside all zones
    
    def _is_tile_occupied(self, tile_x: int, tile_y: int, layer: int) -> bool:
        """
        Check if a tile position is occupied by a FOREIGN object.
        
        For Fill Tool: empty, fill tiles, and deco tiles are NOT considered occupied.
        For Deco Tool: same logic applies.
        Foreign objects (different tileset/type) ARE considered occupied.
        
        Args:
            tile_x, tile_y: Tile coordinates
            layer: Layer number
            
        Returns:
            True if occupied by a foreign object
        """
        tile_type = self._get_tile_type(tile_x, tile_y, layer)
        # Only foreign objects block the fill area
        return tile_type == 'foreign'
    
    def _get_tile_type(self, tile_x: int, tile_y: int, layer: int) -> str:
        """
        Get the type of tile at a position.
        
        Uses RenderObject to detect empty tiles within slope objects.
        Positions with tile value -1 are empty even if inside object bounds.
        
        Returns:
            'empty' - no object at this position (or empty tile in slope)
            'fill' - the assigned fill tile is at this position
            'deco' - a deco object (from any deco container) is at this position
            'foreign' - some other object is at this position
        """
        import globals_
        from tiles import RenderObject
        
        if not hasattr(globals_, 'Area') or globals_.Area is None:
            return 'empty'
        
        if not hasattr(globals_.Area, 'layers') or globals_.Area.layers is None:
            return 'empty'
        
        # Get fill object info
        fill_tab = self.palette.get_fill_paint_tab() if self.palette else None
        fill_tileset = fill_tab._tileset_idx if fill_tab else None
        fill_object_id = fill_tab._fill_object_id if fill_tab else None
        
        # Get deco object info (all containers)
        deco_objects = set()  # Set of (tileset, object_id) tuples
        if fill_tab:
            for container in fill_tab._deco_containers:
                tileset, obj_id, _, _ = container.get_object_info()
                if obj_id is not None:
                    deco_objects.add((tileset, obj_id))
        
        # Check objects in the specified layer
        try:
            layer_objs = globals_.Area.layers[layer]
            for obj in layer_objs:
                obj_x = obj.objx
                obj_y = obj.objy
                obj_w = obj.width
                obj_h = obj.height
                
                if obj_x <= tile_x < obj_x + obj_w and obj_y <= tile_y < obj_y + obj_h:
                    # Position is within object bounds - check if actually filled
                    # Use RenderObject to detect empty tiles in slope objects
                    tile_array = RenderObject(obj.tileset, obj.type, obj_w, obj_h)
                    
                    # Get the tile value at this position within the object
                    dx = tile_x - obj_x
                    dy = tile_y - obj_y
                    tile_value = tile_array[dy][dx] if dy < len(tile_array) and dx < len(tile_array[dy]) else -1
                    
                    if tile_value == -1:
                        # This is an empty tile within the object (e.g., slope triangle)
                        # Continue checking other objects at this position
                        continue
                    
                    # Object covers this tile - determine type
                    obj_tileset = obj.tileset
                    obj_type = obj.type
                    
                    # Check if it's the fill tile
                    if fill_tileset is not None and fill_object_id is not None:
                        if obj_tileset == fill_tileset and obj_type == fill_object_id:
                            return 'fill'
                    
                    # Check if it's a deco tile
                    if (obj_tileset, obj_type) in deco_objects:
                        return 'deco'
                    
                    # It's a foreign object
                    return 'foreign'
        except (IndexError, AttributeError):
            pass
        
        return 'empty'
    
    def handle_mouse_press(self, event) -> bool:
        """
        Handle mouse press event.
        
        Uses RIGHT MOUSE BUTTON for painting (left is used by Reggie's selection).
        
        Args:
            event: Qt mouse event
        
        Returns:
            True if event was handled by QPT
        """
        if not self.palette:
            return False
        
        is_painting = self.palette.is_painting()
        is_fill_active = self.palette.is_fill_active()
        
        # Check if Single Tile or Eraser mode is active (these don't require Start/Stop)
        is_simple_brush_active = False
        from quickpaint.core.tool_manager import get_tool_manager, ToolType
        tool_manager = get_tool_manager()
        if tool_manager.active_tool in (ToolType.QPT_SINGLE_TILE, ToolType.QPT_ERASER):
            is_simple_brush_active = True
        
        # Map Qt button to our button codes (1=left, 2=right, 3=middle)
        button_map = {
            QtCore.Qt.MouseButton.LeftButton: 1,
            QtCore.Qt.MouseButton.RightButton: 2,
            QtCore.Qt.MouseButton.MiddleButton: 3,
        }
        button = button_map.get(event.button(), 0)
        
        # Only handle right mouse button for painting
        if button != 2:
            return False
        
        # Convert screen coordinates to tile coordinates
        import globals_
        pos = globals_.mainWindow.view.mapToScene(event.pos().x(), event.pos().y())
        tile_x = int(pos.x() / 24)
        tile_y = int(pos.y() / 24)
        
        # Check for Fill Tool first
        if is_fill_active:
            if self.palette.handle_mouse_event("press", (tile_x, tile_y), button):
                self.update_fill_preview()
                return True
            return False
        
        # Single Tile and Eraser modes are always active when their tool is selected
        if is_simple_brush_active:
            if self.palette.handle_mouse_event("press", (tile_x, tile_y), button):
                return True
            return False
        
        # Then check for SmartPaint painting (requires Start/Stop)
        if not is_painting:
            return False
        
        # Use button 2 (right) as the draw button
        if self.palette.handle_mouse_event("press", (tile_x, tile_y), button):
            self.update_outline()
            return True
        
        return False
    
    def handle_mouse_move(self, event) -> bool:
        """
        Handle mouse move event.
        
        Args:
            event: Qt mouse event
        
        Returns:
            True if event was handled by QPT
        """
        if not self.palette:
            return False
        
        # Check if Single Tile or Eraser mode is active
        from quickpaint.core.tool_manager import get_tool_manager, ToolType
        tool_manager = get_tool_manager()
        is_simple_brush_active = tool_manager.active_tool in (ToolType.QPT_SINGLE_TILE, ToolType.QPT_ERASER)
        
        # For simple brushes, check if a stroke is in progress
        quick_paint_tab = self.palette.get_quick_paint_tab()
        simple_brush_in_progress = is_simple_brush_active and getattr(quick_paint_tab, '_simple_brush_active', False)
        
        if not self.palette.is_painting() and not simple_brush_in_progress:
            return False
        
        # Convert screen coordinates to tile coordinates
        import globals_
        pos = globals_.mainWindow.view.mapToScene(event.pos().x(), event.pos().y())
        tile_x = int(pos.x() / 24)
        tile_y = int(pos.y() / 24)
        
        result = self.palette.handle_mouse_event("move", (tile_x, tile_y))
        if result:
            if not is_simple_brush_active:
                self.update_outline()
            return True
        
        # Still return True to consume the event when painting is active
        # This prevents Reggie from handling the move event
        return True
    
    def handle_mouse_release(self, event) -> bool:
        """
        Handle mouse release event.
        
        Args:
            event: Qt mouse event
        
        Returns:
            True if event was handled by QPT
        """
        if not self.palette:
            return False
        
        # Map Qt button to our button codes
        button_map = {
            QtCore.Qt.MouseButton.LeftButton: 1,
            QtCore.Qt.MouseButton.RightButton: 2,
            QtCore.Qt.MouseButton.MiddleButton: 3,
        }
        button = button_map.get(event.button(), 0)
        
        # Only handle right mouse button
        if button != 2:
            return False
        
        # Check if Single Tile or Eraser mode is active
        from quickpaint.core.tool_manager import get_tool_manager, ToolType
        tool_manager = get_tool_manager()
        is_simple_brush_active = tool_manager.active_tool in (ToolType.QPT_SINGLE_TILE, ToolType.QPT_ERASER)
        
        # For simple brushes, check if a stroke is in progress
        quick_paint_tab = self.palette.get_quick_paint_tab()
        simple_brush_in_progress = is_simple_brush_active and getattr(quick_paint_tab, '_simple_brush_active', False)
        
        if not self.palette.is_painting() and not simple_brush_in_progress:
            return False
        
        # Convert screen coordinates to tile coordinates
        import globals_
        pos = globals_.mainWindow.view.mapToScene(event.pos().x(), event.pos().y())
        tile_x = int(pos.x() / 24)
        tile_y = int(pos.y() / 24)
        
        if self.palette.handle_mouse_event("release", (tile_x, tile_y), button):
            if not is_simple_brush_active:
                # In deferred mode, don't clear the outline on release - it should persist
                # Only clear in immediate mode (where painting finishes on release)
                from quickpaint.ui.events import PaintingState
                tab = self.palette.get_quick_paint_tab()
                if tab and tab.mouse_handler and tab.mouse_handler.state == PaintingState.IDLE:
                    self.clear_outline()
                else:
                    # Deferred mode: update outline to keep it visible
                    self.update_outline()
            # NOTE: apply_operations() removed - placements are now handled via
            # the on_painting_ended signal in reggie_integration.py to avoid
            # double placement
            return True
        
        return False
    
    def handle_key_press(self, key: int) -> bool:
        """
        Handle key press event.
        
        Args:
            key: Qt key code
        
        Returns:
            True if event was handled by QPT
        """
        if not self.palette:
            return False
        
        from PyQt6.QtCore import Qt
        
        # Check for hotkeys (Q, S, C, E, F, D) - these work even when not painting
        # Convert enum to int for comparison since event.key() returns int
        hotkeys = [Qt.Key.Key_Q.value, Qt.Key.Key_S.value, Qt.Key.Key_C.value, 
                   Qt.Key.Key_E.value, Qt.Key.Key_F.value, Qt.Key.Key_D.value]
        if key in hotkeys:
            if self.palette.handle_hotkey(key):
                return True
        
        # Check for F1 (slope mode toggle) - forward to mouse handler
        if key == Qt.Key.Key_F1.value:
            tab = self.palette.get_quick_paint_tab()
            if tab and hasattr(tab, 'mouse_handler'):
                # Convert back to Qt.Key enum for the handler
                if tab.mouse_handler.on_key_press(Qt.Key.Key_F1):
                    return True
        
        # Check for ESC in Fill Tool
        if key == Qt.Key.Key_Escape.value:
            fill_tab = self.palette.get_fill_paint_tab()
            if fill_tab and fill_tab.handle_key_event(key):
                print(f"[QPT Hook] ESC handled by Fill Tool, clearing fill preview")
                self.clear_fill_preview()
                return True
        
        # Check for F2 in Fill Tool (clear fill area)
        if key == Qt.Key.Key_F2.value:
            fill_tab = self.palette.get_fill_paint_tab()
            if fill_tab and fill_tab.handle_key_event(key):
                print(f"[QPT Hook] F2 handled by Fill Tool, clearing fill area")
                self.clear_fill_preview()
                return True
        
        # Check for F3 (toggle hotkey overlay)
        if key == Qt.Key.Key_F3.value:
            if self.hotkey_overlay:
                if self.hotkey_overlay.isVisible():
                    self.hotkey_overlay.hide_overlay()
                    print("[QPT Hook] Hotkey overlay hidden (F3)")
                else:
                    self.hotkey_overlay.show_overlay()
                    print("[QPT Hook] Hotkey overlay shown (F3)")
                return True
        
        # Forward to QPT if painting
        if not self.palette.is_painting():
            return False
        
        # Forward to the palette's key handler
        tab = self.palette.get_quick_paint_tab()
        if tab and tab.mouse_handler:
            if tab.mouse_handler.on_key_press(key):
                if key == Qt.Key.Key_Escape.value:
                    print(f"[QPT Hook] ESC key handled, clearing outline")
                    self.clear_outline()
                else:
                    # For other keys (like Shift for slope mode), update outline
                    print(f"[QPT Hook] Key {key} handled, updating outline")
                    self.update_outline()
                return True
        
        return False
    
    def update_outline(self):
        """Update the outline visualization"""
        self.clear_outline()
        
        outline_with_types = self.palette.get_outline_with_types()
        if not outline_with_types:
            return
        
        import globals_
        
        # Track positions already covered by slopes to avoid duplicate rendering
        covered_positions = set()
        
        # Create visual outline items
        for x, y, tile_type in outline_with_types:
            # Skip if this position is covered by a slope
            if (x, y) in covered_positions:
                continue
            
            # Determine dimensions based on tile type
            if tile_type and tile_type.startswith('slope_'):
                # Slope object - get dimensions and draw detailed outline
                width_tiles, height_tiles = self._get_slope_dimensions(tile_type)
                
                # Mark covered positions
                for dy in range(height_tiles):
                    for dx in range(width_tiles):
                        covered_positions.add((x + dx, y + dy))
                
                # Draw detailed slope outline with triangle and base
                self._draw_slope_outline(x, y, tile_type, width_tiles)
                continue
            
            # Regular terrain tile - render tile-type-specific pixmap
            pixmap = self._render_tile_type_pixmap(tile_type)
            pixmap_item = QtWidgets.QGraphicsPixmapItem(pixmap)
            pixmap_item.setPos(x * 24, y * 24)
            pixmap_item.setZValue(50000)  # Above most items
            
            # Add to scene and track
            globals_.mainWindow.scene.addItem(pixmap_item)
            self.outline_items.append(pixmap_item)
    
    def _render_tile_type_pixmap(self, tile_type: str) -> QtGui.QPixmap:
        """
        Render a 24x24 pixmap for a terrain tile type, matching the tile picker's
        visual style (grass blades, corners, edges, inner corners).
        
        Args:
            tile_type: Terrain position type (e.g. 'top', 'bottom_left', 'inner_top_right')
        
        Returns:
            24x24 QPixmap with the tile-type-specific outline
        """
        outline_color = QtGui.QColor(0, 255, 0, 255)   # Green
        inner_color = QtGui.QColor(0, 200, 0, 120)       # Faint green fill
        
        pixmap = QtGui.QPixmap(24, 24)
        pixmap.fill(QtCore.Qt.GlobalColor.transparent)
        
        painter = QtGui.QPainter(pixmap)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        
        if tile_type == 'top':
            painter.fillRect(1, 1, 23, 23, inner_color)
            pen = QtGui.QPen(outline_color)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(2, 2, 22, 2)
            # Grass blades
            painter.drawLine(6, 2, 5, 6)
            painter.drawLine(5, 6, 7, 2)
            painter.drawLine(12, 2, 11, 6)
            painter.drawLine(11, 6, 13, 2)
            painter.drawLine(18, 2, 17, 6)
            painter.drawLine(17, 6, 19, 2)
        
        elif tile_type == 'bottom':
            painter.fillRect(1, 1, 23, 23, inner_color)
            pen = QtGui.QPen(outline_color)
            pen.setWidth(4)
            painter.setPen(pen)
            painter.drawLine(4, 22, 22, 22)
        
        elif tile_type == 'left':
            painter.fillRect(4, 1, 23, 23, inner_color)
            pen = QtGui.QPen(outline_color)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(4, 2, 4, 22)
        
        elif tile_type == 'right':
            painter.fillRect(1, 1, 20, 23, inner_color)
            pen = QtGui.QPen(outline_color)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(20, 2, 20, 22)
        
        elif tile_type == 'center':
            painter.fillRect(1, 1, 23, 23, inner_color)
        
        elif tile_type == 'top_left':
            painter.fillRect(4, 3, 23, 23, inner_color)
            pen = QtGui.QPen(outline_color)
            pen.setWidth(2)
            painter.setPen(pen)
            path = QtGui.QPainterPath()
            path.moveTo(4, 22)
            path.lineTo(4, 8)
            path.arcTo(4, 2, 8, 8, 180, -90)
            path.lineTo(22, 2)
            painter.drawPath(path)
            # Grass blades
            painter.drawLine(10, 2, 9, 6)
            painter.drawLine(9, 6, 11, 2)
            painter.drawLine(17, 2, 16, 6)
            painter.drawLine(16, 6, 18, 2)
        
        elif tile_type == 'top_right':
            painter.fillRect(1, 3, 20, 23, inner_color)
            pen = QtGui.QPen(outline_color)
            pen.setWidth(2)
            painter.setPen(pen)
            path = QtGui.QPainterPath()
            path.moveTo(20, 22)
            path.lineTo(20, 8)
            path.arcTo(12, 2, 8, 8, 0, 90)
            path.lineTo(2, 2)
            painter.drawPath(path)
            # Grass blades
            painter.drawLine(7, 2, 6, 6)
            painter.drawLine(6, 6, 8, 2)
            painter.drawLine(15, 2, 14, 6)
            painter.drawLine(14, 6, 16, 2)
        
        elif tile_type == 'bottom_left':
            painter.fillRect(4, 1, 23, 20, inner_color)
            pen = QtGui.QPen(outline_color)
            pen.setWidth(2)
            painter.setPen(pen)
            path = QtGui.QPainterPath()
            path.moveTo(4, 2)
            path.lineTo(4, 16)
            path.arcTo(4, 14, 8, 8, 180, 90)
            path.lineTo(22, 22)
            painter.drawPath(path)
        
        elif tile_type == 'bottom_right':
            painter.fillRect(1, 1, 20, 20, inner_color)
            pen = QtGui.QPen(outline_color)
            pen.setWidth(2)
            painter.setPen(pen)
            path = QtGui.QPainterPath()
            path.moveTo(20, 2)
            path.lineTo(20, 16)
            path.arcTo(12, 14, 8, 8, 0, -90)
            path.lineTo(2, 22)
            painter.drawPath(path)
        
        elif tile_type == 'inner_top_left':
            painter.fillRect(1, 1, 23, 23, inner_color)
            pen = QtGui.QPen(outline_color)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(12, 2, 22, 2)
            painter.drawLine(14, 2, 13, 6)
            painter.drawLine(13, 6, 15, 2)
            painter.drawLine(20, 2, 19, 6)
            painter.drawLine(19, 6, 21, 2)
        
        elif tile_type == 'inner_top_right':
            painter.fillRect(1, 1, 23, 23, inner_color)
            pen = QtGui.QPen(outline_color)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.drawLine(2, 2, 12, 2)
            painter.drawLine(5, 2, 4, 6)
            painter.drawLine(4, 6, 6, 2)
            painter.drawLine(10, 2, 9, 6)
            painter.drawLine(9, 6, 11, 2)
        
        elif tile_type == 'inner_bottom_left':
            painter.fillRect(1, 1, 23, 23, inner_color)
            pen = QtGui.QPen(outline_color)
            pen.setWidth(4)
            painter.setPen(pen)
            painter.drawLine(14, 22, 22, 22)
        
        elif tile_type == 'inner_bottom_right':
            painter.fillRect(1, 1, 23, 23, inner_color)
            pen = QtGui.QPen(outline_color)
            pen.setWidth(4)
            painter.setPen(pen)
            painter.drawLine(4, 22, 12, 22)
        
        else:
            # Unknown type - fallback to simple dashed green rectangle
            pen = QtGui.QPen(outline_color)
            pen.setWidth(2)
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.drawRect(1, 1, 22, 22)
        
        painter.end()
        return pixmap
    
    def _get_slope_dimensions(self, slope_type: str) -> tuple:
        """Get slope dimensions (width, height) in tiles"""
        if '1x1' in slope_type:
            return (1, 2)
        elif '2x1' in slope_type:
            return (2, 2)
        elif '4x1' in slope_type:
            return (4, 2)
        return (1, 1)
    
    def _draw_slope_outline(self, x: int, y: int, slope_type: str, width_tiles: int):
        """
        Draw a detailed slope outline showing the elevation triangle and base blocks.
        
        Slope structure:
        - Top row: elevation triangle (sloped part)
        - Bottom row: base blocks (solid rectangular part)
        
        For "left" slopes: triangle is higher on the left
        For "right" slopes: triangle is higher on the right
        For "top" slopes: triangle on top, base on bottom
        For "bottom" slopes: base on top, triangle on bottom
        """
        import globals_
        
        px = x * 24  # Pixel x
        py = y * 24  # Pixel y
        width_px = width_tiles * 24
        height_px = 48  # 2 tiles high
        
        pen = QtGui.QPen(QtCore.Qt.GlobalColor.cyan)
        pen.setWidth(2)
        pen.setStyle(QtCore.Qt.PenStyle.DashLine)
        
        # Determine slope orientation
        is_top = 'top' in slope_type
        is_left = 'left' in slope_type  # Higher on left side
        
        # Create polygon points for the slope shape
        # The shape shows: triangle (elevation) + rectangle (base)
        polygon = QtGui.QPolygonF()
        
        if is_top:
            # Top slopes: triangle on top, base on bottom
            if is_left:
                # "left" = ascending slope (going up when moving right)
                # Triangle: LOW on left, HIGH on right (slope goes UP)
                polygon.append(QtCore.QPointF(px, py + 24))  # Top-left (low point)
                polygon.append(QtCore.QPointF(px, py + height_px))  # Bottom-left
                polygon.append(QtCore.QPointF(px + width_px, py + height_px))  # Bottom-right
                polygon.append(QtCore.QPointF(px + width_px, py))  # Top-right (high point)
                polygon.append(QtCore.QPointF(px, py + 24))  # Back to top-left (diagonal)
            else:
                # "right" = descending slope (going down when moving right)
                # Triangle: HIGH on left, LOW on right (slope goes DOWN)
                polygon.append(QtCore.QPointF(px, py))  # Top-left (high point)
                polygon.append(QtCore.QPointF(px, py + height_px))  # Bottom-left
                polygon.append(QtCore.QPointF(px + width_px, py + height_px))  # Bottom-right
                polygon.append(QtCore.QPointF(px + width_px, py + 24))  # Top-right (low point)
                polygon.append(QtCore.QPointF(px, py))  # Back to top-left (diagonal)
        else:
            # Bottom slopes: base on top, triangle on bottom
            if is_left:
                # "left" = ascending slope (going up when moving left)
                # Triangle on bottom: LOW on right, HIGH on left
                polygon.append(QtCore.QPointF(px, py))  # Top-left
                polygon.append(QtCore.QPointF(px, py + 24))  # Bottom-left (low point)
                polygon.append(QtCore.QPointF(px + width_px, py + height_px))  # Bottom-right (high point)
                polygon.append(QtCore.QPointF(px + width_px, py))  # Top-right
                polygon.append(QtCore.QPointF(px, py))  # Back to top-left
            else:
                # "right" = descending slope (going down when moving left)
                # Triangle on bottom: HIGH on right, LOW on left
                polygon.append(QtCore.QPointF(px, py))  # Top-left
                polygon.append(QtCore.QPointF(px, py + height_px))  # Bottom-left (high point)
                polygon.append(QtCore.QPointF(px + width_px, py + 24))  # Bottom-right (low point)
                polygon.append(QtCore.QPointF(px + width_px, py))  # Top-right
                polygon.append(QtCore.QPointF(px, py))  # Back to top-left
        
        # Create polygon item
        polygon_item = QtWidgets.QGraphicsPolygonItem(polygon)
        polygon_item.setPen(pen)
        polygon_item.setBrush(QtGui.QBrush(QtCore.Qt.GlobalColor.transparent))
        
        # Add to scene and track
        globals_.mainWindow.scene.addItem(polygon_item)
        self.outline_items.append(polygon_item)
        
        # Also draw a horizontal line separating triangle from base
        separator_y = py + 24 if is_top else py + 24
        line_item = QtWidgets.QGraphicsLineItem(px, separator_y, px + width_px, separator_y)
        line_item.setPen(pen)
        globals_.mainWindow.scene.addItem(line_item)
        self.outline_items.append(line_item)
    
    def clear_outline(self):
        """Clear the outline visualization"""
        import globals_
        for item in self.outline_items:
            globals_.mainWindow.scene.removeItem(item)
        self.outline_items.clear()
    
    # =========================================================================
    # FILL PREVIEW VISUALIZATION
    # =========================================================================
    
    def update_fill_preview(self):
        """Update the fill preview visualization"""
        self.clear_fill_preview()
        
        if not self.palette:
            return
        
        fill_positions = self.palette.get_fill_preview()
        if not fill_positions:
            return
        
        import globals_
        
        # Blue color for fill preview
        pen = QtGui.QPen(QtGui.QColor(60, 100, 200))  # Blue
        pen.setWidth(2)
        brush = QtGui.QBrush(QtGui.QColor(60, 100, 200, 80))  # Semi-transparent blue
        
        # Create visual fill preview items
        for x, y in fill_positions:
            rect = QtCore.QRectF(x * 24, y * 24, 24, 24)
            rect_item = QtWidgets.QGraphicsRectItem(rect)
            rect_item.setPen(pen)
            rect_item.setBrush(brush)
            globals_.mainWindow.scene.addItem(rect_item)
            self.fill_preview_items.append(rect_item)
    
    def clear_fill_preview(self):
        """Clear the fill preview visualization"""
        if not hasattr(self, 'fill_preview_items'):
            self.fill_preview_items = []
            return
        
        import globals_
        for item in self.fill_preview_items:
            try:
                globals_.mainWindow.scene.removeItem(item)
            except RuntimeError:
                # Item already deleted - ignore
                pass
        self.fill_preview_items.clear()
    
    def apply_fill(self, positions: list):
        """
        Apply fill operation - place objects at all fill positions.
        
        Merges positions into vertical slices for efficiency.
        
        Args:
            positions: List of (x, y) tile positions to fill
        """
        if not positions:
            return
        
        import globals_
        from dirty import SetDirty
        
        # Get fill object ID, tileset, and layer from fill tab
        fill_tab = self.palette.get_fill_paint_tab()
        if fill_tab:
            fill_object_id = fill_tab._fill_object_id if fill_tab._fill_object_id is not None else 0
            fill_tileset = fill_tab._tileset_idx if fill_tab._tileset_idx is not None else 0
            current_layer = fill_tab.get_current_layer()
        else:
            fill_object_id = 0
            fill_tileset = 0
            current_layer = 1
        
        print(f"[QPT Hook] Applying fill: {len(positions)} tiles, tileset={fill_tileset}, object={fill_object_id}, layer={current_layer}")
        
        # Filter to only empty positions
        empty_positions = []
        skipped_count = 0
        for x, y in positions:
            tile_type = self._get_tile_type(x, y, current_layer)
            if tile_type == 'empty':
                empty_positions.append((x, y))
            else:
                skipped_count += 1
        
        # Merge positions into vertical slices (by column)
        merged_placements = self._merge_fill_positions(empty_positions)
        
        print(f"[QPT Hook] Merged {len(empty_positions)} positions into {len(merged_placements)} vertical slices")
        
        # Create merged objects
        placed_count = 0
        for placement in merged_placements:
            self.paint_at_position(
                placement['x'], placement['y'], 
                fill_object_id, current_layer, 
                tileset=fill_tileset,
                width=placement['width'], 
                height=placement['height']
            )
            placed_count += 1
        
        # Clear the preview
        self.clear_fill_preview()
        
        # Mark level as dirty
        if placed_count > 0:
            SetDirty()
        
        # Update the scene
        globals_.mainWindow.scene.update()
        
        print(f"[QPT Hook] Fill complete: {placed_count} merged objects placed, {skipped_count} skipped")
    
    def _merge_fill_positions(self, positions: list) -> list:
        """
        Merge fill positions into optimized rectangles.
        
        First creates vertical slices (columns), then merges horizontally
        adjacent slices that have the same top (y) and height.
        
        Args:
            positions: List of (x, y) positions
            
        Returns:
            List of placement dicts with x, y, width, height
        """
        if not positions:
            return []
        
        # Group positions by column (x coordinate)
        columns = {}
        for x, y in positions:
            if x not in columns:
                columns[x] = []
            columns[x].append(y)
        
        # Sort each column and merge consecutive y values into vertical slices
        vertical_slices = []
        for x, y_values in columns.items():
            y_values.sort()
            
            if not y_values:
                continue
            
            run_start = y_values[0]
            run_end = y_values[0]
            
            for i in range(1, len(y_values)):
                if y_values[i] == run_end + 1:
                    # Continue the run
                    run_end = y_values[i]
                else:
                    # End current run, create slice
                    vertical_slices.append({
                        'x': x,
                        'y': run_start,
                        'width': 1,
                        'height': run_end - run_start + 1
                    })
                    # Start new run
                    run_start = y_values[i]
                    run_end = y_values[i]
            
            # Don't forget the last run
            vertical_slices.append({
                'x': x,
                'y': run_start,
                'width': 1,
                'height': run_end - run_start + 1
            })
        
        # Now merge horizontally adjacent slices with same y and height
        # Group slices by (y, height) for efficient merging
        slice_groups = {}
        for s in vertical_slices:
            key = (s['y'], s['height'])
            if key not in slice_groups:
                slice_groups[key] = []
            slice_groups[key].append(s)
        
        # Merge adjacent slices in each group
        placements = []
        for (y, height), slices in slice_groups.items():
            # Sort by x coordinate
            slices.sort(key=lambda s: s['x'])
            
            if not slices:
                continue
            
            # Merge consecutive x values
            run_start_x = slices[0]['x']
            run_end_x = slices[0]['x']
            
            for i in range(1, len(slices)):
                if slices[i]['x'] == run_end_x + 1:
                    # Continue the run (adjacent column)
                    run_end_x = slices[i]['x']
                else:
                    # End current run, create merged placement
                    placements.append({
                        'x': run_start_x,
                        'y': y,
                        'width': run_end_x - run_start_x + 1,
                        'height': height
                    })
                    # Start new run
                    run_start_x = slices[i]['x']
                    run_end_x = slices[i]['x']
            
            # Don't forget the last run
            placements.append({
                'x': run_start_x,
                'y': y,
                'width': run_end_x - run_start_x + 1,
                'height': height
            })
        
        return placements
    
    def apply_operations(self):
        """Apply painting operations to the level"""
        if not self.palette:
            return
        
        tab = self.palette.get_quick_paint_tab()
        if not tab or not tab.mouse_handler:
            return
        
        operations = tab.mouse_handler.get_operations()
        if not operations:
            return
        
        # Get current layer and paint type
        import globals_
        current_layer = globals_.CurrentLayer
        current_paint_type = globals_.CurrentPaintType
        
        # Apply each operation
        for op in operations:
            self.apply_operation(op, current_layer)
        
        # Mark level as dirty
        from dirty import SetDirty
        SetDirty()
        
        # Update the scene
        globals_.mainWindow.scene.update()
    
    def apply_operation(self, op, layer: int):
        """
        Apply a single painting operation.
        
        Args:
            op: PaintOperation to apply
            layer: Layer to paint on
        """
        if op.tile_id == 0:
            # Eraser operation - remove object at position
            self.erase_at_position(op.x, op.y, layer)
        else:
            # Paint operation - create object
            self.paint_at_position(op.x, op.y, op.tile_id, layer)
    
    def paint_at_position(self, x: int, y: int, tile_id: int, layer: int, tileset: int = None, width: int = 1, height: int = 1):
        """
        Paint an object at a specific position.
        
        Args:
            x, y: Tile coordinates
            tile_id: Tile object ID
            layer: Layer to paint on
            tileset: Tileset index (uses CurrentPaintType if None)
            width: Object width in tiles (default 1)
            height: Object height in tiles (default 1)
        """
        try:
            import globals_
            
            # Use provided tileset or default to current
            paint_type = tileset if tileset is not None else globals_.CurrentPaintType
            
            # Create the object with specified dimensions
            obj = globals_.mainWindow.CreateObject(
                paint_type,
                tile_id,
                layer,
                x, y,
                width, height
            )
        
        except Exception as e:
            print(f"Error painting at ({x}, {y}): {str(e)}")
    
    def erase_at_position(self, x: int, y: int, layer: int):
        """
        Erase object at a specific position.
        If the position is part of a larger object, split the object and
        only remove the specified tile.
        
        Args:
            x, y: Tile coordinates
            layer: Layer to erase from
        """
        try:
            import globals_
            layer_obj = globals_.Area.layers[layer]
            
            # Find objects that COVER this tile position (not just start at it)
            to_process = []
            for obj in layer_obj:
                # Check if (x, y) is within this object's bounds
                if (obj.objx <= x < obj.objx + obj.width and
                    obj.objy <= y < obj.objy + obj.height):
                    to_process.append(obj)
            
            # Process each object that covers this position
            for obj in to_process:
                obj_x, obj_y = obj.objx, obj.objy
                obj_w, obj_h = obj.width, obj.height
                obj_type = obj.type
                obj_tileset = obj.tileset
                
                # Remove the original object
                layer_obj.remove(obj)
                globals_.mainWindow.scene.removeItem(obj)
                
                # If it's a 1x1 object, we're done
                if obj_w == 1 and obj_h == 1:
                    continue
                
                # Otherwise, recreate the parts that should remain
                # We need to create individual 1x1 tiles for all positions except (x, y)
                for dy in range(obj_h):
                    for dx in range(obj_w):
                        tile_x = obj_x + dx
                        tile_y = obj_y + dy
                        
                        # Skip the position we want to delete
                        if tile_x == x and tile_y == y:
                            continue
                        
                        # Create a 1x1 replacement tile
                        new_obj = globals_.mainWindow.CreateObject(
                            tileset=obj_tileset,
                            object_num=obj_type,
                            layer=layer,
                            x=tile_x,
                            y=tile_y,
                            width=1,
                            height=1
                        )
                
                print(f"[QPT Hook] Split {obj_w}x{obj_h} object at ({obj_x}, {obj_y}), removed tile at ({x}, {y})")
        
        except Exception as e:
            print(f"Error erasing at ({x}, {y}): {str(e)}")
    
    def is_painting(self) -> bool:
        """Check if QPT is currently painting"""
        return self.palette and self.palette.is_painting()
    
    def apply_pending_deletes(self):
        """
        Apply pending terrain-aware deletions.
        Called after a 100ms delay for visual distinction.
        """
        if not self.palette:
            return
        
        tab = self.palette.get_quick_paint_tab()
        if not tab or not tab.mouse_handler:
            return
        
        # Get pending deletions from the engine
        engine = tab.mouse_handler.engine
        pending_deletes = engine.get_pending_terrain_deletes()
        
        if not pending_deletes:
            return
        
        import globals_
        from dirty import SetDirty
        
        deleted_count = 0
        for x, y, layer in pending_deletes:
            self.erase_at_position(x, y, layer)
            deleted_count += 1
        
        if deleted_count > 0:
            print(f"[QPT Hook] Terrain-aware: Deleted {deleted_count} tiles")
            SetDirty()
            globals_.mainWindow.scene.update()


# Global instance - created lazily on first use
_qpt_hook = None

def _get_qpt_hook():
    """Get or create the global QPT hook instance"""
    global _qpt_hook
    if _qpt_hook is None:
        _qpt_hook = ReggieQuickPaintHook()
    return _qpt_hook


def initialize_qpt(main_window):
    """
    Initialize Quick Paint Tool in Reggie.
    
    Args:
        main_window: Reggie's main window
    
    Returns:
        QuickPaintPalette widget to add to sidebar
    """
    return _get_qpt_hook().initialize(main_window)


def handle_qpt_mouse_press(event) -> bool:
    """Handle mouse press for QPT"""
    return _get_qpt_hook().handle_mouse_press(event)


def handle_qpt_mouse_move(event) -> bool:
    """Handle mouse move for QPT"""
    return _get_qpt_hook().handle_mouse_move(event)


def handle_qpt_mouse_release(event) -> bool:
    """Handle mouse release for QPT"""
    return _get_qpt_hook().handle_mouse_release(event)


def handle_qpt_key_press(key: int) -> bool:
    """Handle key press for QPT (e.g., ESC to cancel)"""
    return _get_qpt_hook().handle_key_press(key)


def update_qpt_outline():
    """Update the QPT outline visualization"""
    _get_qpt_hook().update_outline()


def apply_terrain_aware_deletes():
    """
    Apply pending terrain-aware deletions after a delay.
    Called via QTimer after 100ms to make the deletion visually distinct.
    """
    _get_qpt_hook().apply_pending_deletes()


def get_tile_type(tile_x: int, tile_y: int, layer: int) -> str:
    """
    Get the type of tile at a position.
    
    Returns:
        'empty' - no object at this position
        'fill' - the assigned fill tile is at this position
        'deco' - a deco object (from any deco container) is at this position
        'foreign' - some other object is at this position
    """
    return _get_qpt_hook()._get_tile_type(tile_x, tile_y, layer)


def show_hotkey_overlay():
    """Show the QPT hotkey overlay"""
    _get_qpt_hook().show_hotkey_overlay()


def hide_hotkey_overlay():
    """Hide the QPT hotkey overlay"""
    _get_qpt_hook().hide_hotkey_overlay()
