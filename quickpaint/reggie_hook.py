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
        
        # Map Qt button to our button codes (1=left, 2=right, 3=middle)
        button_map = {
            QtCore.Qt.MouseButton.LeftButton: 1,
            QtCore.Qt.MouseButton.RightButton: 2,
            QtCore.Qt.MouseButton.MiddleButton: 3,
        }
        button = button_map.get(event.button(), 0)
        
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
        
        if self.palette.handle_mouse_event("move", (tile_x, tile_y)):
            self.update_outline()
            return True
        
        return False
    
    def handle_mouse_release(self, event) -> bool:
        """
        Handle mouse release event.
        
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
        
        # Map Qt button to our button codes
        button_map = {
            QtCore.Qt.MouseButton.LeftButton: 1,
            QtCore.Qt.MouseButton.RightButton: 2,
            QtCore.Qt.MouseButton.MiddleButton: 3,
        }
        button = button_map.get(event.button(), 0)
        
        if self.palette.handle_mouse_event("release", (tile_x, tile_y), button):
            self.clear_outline()
            self.apply_operations()
            return True
        
        return False
    
    def update_outline(self):
        """Update the outline visualization"""
        self.clear_outline()
        
        outline = self.palette.get_outline()
        if not outline:
            return
        
        # Create visual outline items
        for x, y in outline:
            # Create a rectangle item for each outline position
            rect_item = QtWidgets.QGraphicsRectItem(
                x * 24, y * 24, 24, 24
            )
            
            # Style the outline
            pen = QtGui.QPen(QtCore.Qt.green)
            pen.setWidth(2)
            pen.setStyle(QtCore.Qt.DashLine)
            rect_item.setPen(pen)
            rect_item.setBrush(QtGui.QBrush(QtCore.Qt.transparent))
            
            # Add to scene and track
            import globals_
            globals_.mainWindow.scene.addItem(rect_item)
            self.outline_items.append(rect_item)
    
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
        Erase objects at a specific position.
        
        Args:
            x, y: Tile coordinates
            layer: Layer to erase from
        """
        try:
            # Find and remove objects at this position
            import globals_
            layer_obj = globals_.Area.layers[layer]
            
            # Find objects at this tile position
            to_remove = []
            for obj in layer_obj:
                if obj.objx == x and obj.objy == y:
                    to_remove.append(obj)
            
            # Remove found objects
            for obj in to_remove:
                layer_obj.remove(obj)
                globals_.mainWindow.scene.removeItem(obj)
        
        except Exception as e:
            print(f"Error erasing at ({x}, {y}): {str(e)}")
    
    def is_painting(self) -> bool:
        """Check if QPT is currently painting"""
        return self.palette and self.palette.is_painting()


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
