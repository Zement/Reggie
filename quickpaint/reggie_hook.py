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
    """
    
    def __init__(self):
        """Initialize the QPT hook"""
        self.palette: Optional[QtWidgets.QWidget] = None  # Will be QuickPaintPalette after initialization
        self.outline_items: List = []
        self.is_active = False
    
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
        
        self.palette = QuickPaintPalette()
        self.is_active = True
        return self.palette
    
    def handle_mouse_press(self, event) -> bool:
        """
        Handle mouse press event.
        
        Uses RIGHT MOUSE BUTTON for painting (left is used by Reggie's selection).
        
        Args:
            event: Qt mouse event
        
        Returns:
            True if event was handled by QPT
        """
        print(f"[QPT Hook] handle_mouse_press called, palette={self.palette is not None}")
        
        if not self.palette:
            print("[QPT Hook] No palette, returning False")
            return False
        
        is_painting = self.palette.is_painting()
        print(f"[QPT Hook] is_painting={is_painting}")
        
        # Map Qt button to our button codes (1=left, 2=right, 3=middle)
        button_map = {
            QtCore.Qt.MouseButton.LeftButton: 1,
            QtCore.Qt.MouseButton.RightButton: 2,
            QtCore.Qt.MouseButton.MiddleButton: 3,
        }
        button = button_map.get(event.button(), 0)
        print(f"[QPT Hook] button={button}")
        
        # Only handle right mouse button for painting
        if button != 2:
            print(f"[QPT Hook] Not right button, returning False")
            return False
        
        if not is_painting:
            print(f"[QPT Hook] Right-click ignored - painting not active")
            return False
        
        # Convert screen coordinates to tile coordinates
        import globals_
        pos = globals_.mainWindow.view.mapToScene(event.pos().x(), event.pos().y())
        tile_x = int(pos.x() / 24)
        tile_y = int(pos.y() / 24)
        
        print(f"[QPT Hook] Mouse press at tile ({tile_x}, {tile_y}), button={button}")
        
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
        if not self.palette or not self.palette.is_painting():
            return False
        
        # Convert screen coordinates to tile coordinates
        import globals_
        pos = globals_.mainWindow.view.mapToScene(event.pos().x(), event.pos().y())
        tile_x = int(pos.x() / 24)
        tile_y = int(pos.y() / 24)
        
        result = self.palette.handle_mouse_event("move", (tile_x, tile_y))
        if result:
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
        
        if not self.palette.is_painting():
            return False
        
        # Convert screen coordinates to tile coordinates
        import globals_
        pos = globals_.mainWindow.view.mapToScene(event.pos().x(), event.pos().y())
        tile_x = int(pos.x() / 24)
        tile_y = int(pos.y() / 24)
        
        print(f"[QPT Hook] Mouse release at tile ({tile_x}, {tile_y}), button={button}")
        
        if self.palette.handle_mouse_event("release", (tile_x, tile_y), button):
            self.clear_outline()
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
        
        if not self.palette.is_painting():
            return False
        
        # Forward to the palette's key handler
        tab = self.palette.get_quick_paint_tab()
        if tab and tab.mouse_handler:
            if tab.mouse_handler.on_key_press(key):
                from PyQt6.QtCore import Qt
                if key == Qt.Key.Key_Escape:
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
            else:
                # Regular terrain tile - 1x1
                width_px = 24
                height_px = 24
                pen_color = QtCore.Qt.GlobalColor.green
            
            # Create a rectangle item
            rect_item = QtWidgets.QGraphicsRectItem(
                x * 24, y * 24, width_px, height_px
            )
            
            # Style the outline (PyQt6 enums)
            pen = QtGui.QPen(pen_color)
            pen.setWidth(2)
            pen.setStyle(QtCore.Qt.PenStyle.DashLine)
            rect_item.setPen(pen)
            rect_item.setBrush(QtGui.QBrush(QtCore.Qt.GlobalColor.transparent))
            
            # Add to scene and track
            globals_.mainWindow.scene.addItem(rect_item)
            self.outline_items.append(rect_item)
    
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
    
    def paint_at_position(self, x: int, y: int, tile_id: int, layer: int):
        """
        Paint an object at a specific position.
        
        Args:
            x, y: Tile coordinates
            tile_id: Tile object ID
            layer: Layer to paint on
        """
        try:
            # Get tileset and type from tile_id
            # This is a simplified version - actual implementation depends on
            # how tile_id maps to tileset/type in your system
            import globals_
            tileset = 0  # Default to first tileset
            obj_type = tile_id
            
            # Create the object
            obj = globals_.mainWindow.CreateObject(
                globals_.CurrentPaintType,  # Paint type (usually 0 for terrain)
                obj_type,
                layer,
                x, y
            )
            
            if obj:
                # Auto-tile the object
                from quickpaint_legacy import QuickPaintOperations
                QuickPaintOperations.autoTileObj(layer, obj)
        
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
