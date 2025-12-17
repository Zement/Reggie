"""
Reggie Integration - Integrates QPT into Reggie's UI and event system
"""
from typing import Optional, Dict, List
from PyQt6 import QtWidgets, QtCore, QtGui

# Defer imports to avoid QWidget creation before QApplication is ready
# from quickpaint.ui.widget import QuickPaintWidget
# from quickpaint.ui.tileset_selector import TilesetSelector
# from quickpaint.ui.events import MouseEventHandler
# from quickpaint.core.presets import PresetManager


class QuickPaintTab(QtWidgets.QWidget):
    """
    Quick Paint Tab for Reggie sidebar.
    
    Contains:
    - Tileset selector with object list
    - Tile picker
    - Painting controls
    """
    
    def __init__(self, parent=None):
        """
        Initialize the Quick Paint tab.
        
        Args:
            parent: Parent widget
        """
        print("[QPT] QuickPaintTab.__init__ starting...")
        super().__init__(parent)
        print("[QPT] OK: QWidget parent initialized")
        
        # Initialize file logging
        from quickpaint.core.logging import init_logging
        init_logging()
        
        # Import here to avoid QWidget creation before QApplication is ready
        print("[QPT] Importing PresetManager...")
        from quickpaint.core.presets import PresetManager
        print("[QPT] OK: PresetManager imported")
        
        print("[QPT] Importing MouseEventHandler...")
        from quickpaint.ui.events import MouseEventHandler
        print("[QPT] OK: MouseEventHandler imported")
        
        print("[QPT] Creating preset manager...")
        # PresetManager requires builtin and user directories
        import os
        builtin_dir = os.path.join('assets', 'qpt', 'builtin')
        user_dir = os.path.join('assets', 'qpt', 'presets')
        self.preset_manager = PresetManager(builtin_dir, user_dir)
        print("[QPT] OK: Preset manager created")
        
        print("[QPT] Creating mouse handler...")
        self.mouse_handler = MouseEventHandler()
        print("[QPT] OK: Mouse handler created")
        
        print("[QPT] Initializing UI...")
        self.init_ui()
        print("[QPT] OK: QuickPaintTab initialized")
    
    def init_ui(self):
        """Initialize the UI"""
        print("[QPT] init_ui starting...")
        
        # Import here to avoid QWidget creation before QApplication is ready
        print("[QPT] Importing TilesetSelector...")
        from quickpaint.ui.tileset_selector import TilesetSelector
        print("[QPT] OK: TilesetSelector imported")
        
        print("[QPT] Importing QuickPaintWidget...")
        from quickpaint.ui.widget import QuickPaintWidget
        print("[QPT] OK: QuickPaintWidget imported")
        
        print("[QPT] Creating layout...")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        print("[QPT] Layout created")
        
        # ===== SCROLL AREA FOR CONTENT =====
        print("[QPT] Creating scroll area...")
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        
        # Container widget for scroll area
        container = QtWidgets.QWidget()
        container_layout = QtWidgets.QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        
        # ===== TILESET SELECTOR =====
        print("[QPT] Creating TilesetSelector...")
        self.tileset_selector = TilesetSelector()
        container_layout.addWidget(self.tileset_selector)
        print("[QPT] TilesetSelector created")
        
        # ===== SEPARATOR =====
        print("[QPT] Creating separator...")
        separator = QtWidgets.QFrame()
        separator.setFrameShape(QtWidgets.QFrame.Shape.HLine)
        separator.setFrameShadow(QtWidgets.QFrame.Shadow.Sunken)
        container_layout.addWidget(separator)
        print("[QPT] Separator created")
        
        # ===== QUICK PAINT WIDGET =====
        print("[QPT] Creating QuickPaintWidget...")
        self.qpt_widget = QuickPaintWidget(self.preset_manager, tileset_selector=self.tileset_selector)
        print("[QPT] QuickPaintWidget created")
        container_layout.addWidget(self.qpt_widget)
        
        # Add container to scroll area
        scroll_area.setWidget(container)
        layout.addWidget(scroll_area)
        print("[QPT] Scroll area created")
        
        # ===== CONNECT SIGNALS =====
        self.qpt_widget.painting_started.connect(self.on_painting_started)
        self.qpt_widget.painting_stopped.connect(self.on_painting_stopped)
        self.tileset_selector.object_selected.connect(self.on_object_selected)
        self.mouse_handler.painting_ended.connect(self.on_painting_ended)
        self.mouse_handler.object_placed.connect(self.on_object_placed)
        self.mouse_handler.outline_updated.connect(self.on_outline_updated)
        
        # Initialize tileset objects after a short delay to ensure Reggie is fully loaded
        QtCore.QTimer.singleShot(100, self.tileset_selector.initialize_objects)
        
        # Try to auto-load a preset for the current tileset after initialization
        QtCore.QTimer.singleShot(200, self.qpt_widget.initialize_with_current_tileset)
    
    def on_painting_started(self):
        """Handle painting start"""
        brush = self.qpt_widget.get_current_brush()
        mode = self.qpt_widget.get_current_mode()
        
        print(f"[QPT] on_painting_started: brush={brush is not None}, mode={mode}")
        
        if brush:
            self.mouse_handler.set_brush(brush)
            self.mouse_handler.set_mode(mode)
            print(f"[QPT] OK: Brush and mode set for painting")
        else:
            print("[QPT] WARNING: No brush available for painting!")
    
    def on_painting_stopped(self):
        """Handle painting stop"""
        self.mouse_handler.cancel_painting()
    
    def on_object_selected(self, tileset: int, obj_type: int, obj_id: int):
        """
        Handle object selection from tileset.
        
        Args:
            tileset: Tileset index
            obj_type: Object type
            obj_id: Object ID
        """
        print(f"[QPT] on_object_selected called: tileset={tileset}, obj_type={obj_type}, obj_id={obj_id}")
        
        # Create or update a brush for this object if not already created
        if not self.qpt_widget.current_brush:
            from quickpaint.core.brush import SmartBrush
            tileset_name = self.tileset_selector.get_current_tileset_name()
            slot = f"Pa{tileset}"
            self.qpt_widget.current_brush = SmartBrush(
                f"Object_{tileset}",
                [tileset_name],
                slot
            )
            print(f"[QPT] Created new brush for tileset {tileset}")
            
            # Set the tileset for the canvas (but don't draw yet)
            self.qpt_widget.tile_picker_canvas.set_tileset(tileset)
            self.qpt_widget.tile_picker_canvas.set_brush(self.qpt_widget.current_brush)
            print(f"[QPT] Tile picker canvas initialized for tileset {tileset}")
            print(f"[QPT] Canvas will update when you select a position type")
        else:
            print(f"[QPT] Brush already exists, not reinitializing canvas")
    
    def on_painting_ended(self, placements: List):
        """
        Handle painting end - place objects in the level.
        
        Args:
            placements: List of ObjectPlacement objects
        """
        print(f"[QPT] on_painting_ended: {len(placements)} placements")
        
        # Get reference to Reggie's main window
        try:
            import globals_
            main_window = globals_.mainWindow
            
            if main_window and placements:
                for placement in placements:
                    # For terrain-aware replacements, delete existing tile first
                    # This handles the case where we're replacing a border with center
                    self._delete_tile_at(placement.x, placement.y, placement.layer)
                    
                    # Create the object in the level
                    main_window.CreateObject(
                        tileset=placement.tileset,
                        object_num=placement.object_id,
                        layer=placement.layer,
                        x=placement.x,
                        y=placement.y,
                        width=placement.width,
                        height=placement.height
                    )
                print(f"[QPT] OK: Created {len(placements)} objects in level")
                
                # Schedule terrain-aware deletions after 100ms delay
                from PyQt6.QtCore import QTimer
                QTimer.singleShot(100, self._apply_terrain_aware_deletes)
        except Exception as e:
            print(f"[QPT] Error placing objects: {e}")
    
    def on_object_placed(self, placement):
        """
        Handle single object placement (immediate mode).
        
        Args:
            placement: ObjectPlacement object
        """
        try:
            import globals_
            main_window = globals_.mainWindow
            
            if main_window and placement:
                main_window.CreateObject(
                    tileset=placement.tileset,
                    object_num=placement.object_id,
                    layer=placement.layer,
                    x=placement.x,
                    y=placement.y,
                    width=placement.width,
                    height=placement.height
                )
                print(f"[QPT] OK: Placed object at ({placement.x}, {placement.y})")
        except Exception as e:
            print(f"[QPT] Error placing object: {e}")
    
    def _apply_terrain_aware_deletes(self):
        """
        Apply pending terrain-aware deletions.
        Called after a 100ms delay for visual distinction.
        """
        try:
            import globals_
            from quickpaint.reggie_hook import apply_terrain_aware_deletes
            apply_terrain_aware_deletes()
        except Exception as e:
            print(f"[QPT] Error applying terrain-aware deletes: {e}")
    
    def _delete_tile_at(self, x: int, y: int, layer: int):
        """
        Delete any existing tile at the specified position.
        Handles large objects by splitting them.
        
        Args:
            x, y: Tile coordinates
            layer: Layer to delete from
        """
        try:
            import globals_
            if not globals_.Area:
                return
            
            layer_obj = globals_.Area.layers[layer]
            
            # Find objects that cover this position
            to_process = []
            for obj in layer_obj:
                if (obj.objx <= x < obj.objx + obj.width and
                    obj.objy <= y < obj.objy + obj.height):
                    to_process.append(obj)
            
            # Process each object
            for obj in to_process:
                obj_x, obj_y = obj.objx, obj.objy
                obj_w, obj_h = obj.width, obj.height
                obj_type = obj.type
                obj_tileset = obj.tileset
                
                # Remove the original object
                layer_obj.remove(obj)
                globals_.mainWindow.scene.removeItem(obj)
                
                # If 1x1, we're done
                if obj_w == 1 and obj_h == 1:
                    continue
                
                # Recreate parts that should remain (all except target position)
                for dy in range(obj_h):
                    for dx in range(obj_w):
                        tile_x = obj_x + dx
                        tile_y = obj_y + dy
                        
                        if tile_x == x and tile_y == y:
                            continue
                        
                        globals_.mainWindow.CreateObject(
                            tileset=obj_tileset,
                            object_num=obj_type,
                            layer=layer,
                            x=tile_x,
                            y=tile_y,
                            width=1,
                            height=1
                        )
        except Exception as e:
            print(f"[QPT] Error deleting tile at ({x}, {y}): {e}")
    
    def _refresh_object_database(self):
        """
        Refresh the object database from the current level.
        This allows terrain-aware checks to see existing tiles.
        """
        try:
            import globals_
            if not globals_.Area:
                return
            
            database = {}
            
            # Scan all layers for existing objects
            for layer_idx, layer in enumerate(globals_.Area.layers):
                for obj in layer:
                    # Add all tiles covered by this object
                    for dy in range(obj.height):
                        for dx in range(obj.width):
                            x = obj.objx + dx
                            y = obj.objy + dy
                            database[(x, y, layer_idx)] = obj.type
            
            # Update the engine's object database
            self.mouse_handler.update_object_database(database)
            print(f"[QPT] Refreshed object database: {len(database)} tiles")
        except Exception as e:
            print(f"[QPT] Error refreshing object database: {e}")
    
    def on_outline_updated(self, positions: List = None):
        """
        Handle outline update - show preview of where tiles will be placed.
        
        Args:
            positions: List of (x, y) positions (optional, can be None)
        """
        # Call the reggie_hook to update the visual outline
        import globals_
        qpt_funcs = getattr(globals_, 'qpt_functions', None)
        if qpt_funcs and qpt_funcs.get('update_outline'):
            qpt_funcs['update_outline']()
    
    def handle_mouse_event(self, event_type: str, pos: tuple, button: int = 2) -> bool:
        """
        Handle mouse event from Reggie.
        
        Args:
            event_type: "press", "move", or "release"
            pos: Mouse position (x, y) in tile coordinates
            button: Mouse button (1=left, 2=right, 3=middle)
        
        Returns:
            True if event was handled, False otherwise
        """
        is_painting = self.qpt_widget.is_painting()
        # Reduce log spam for move events
        if event_type != "move":
            print(f"[QPT] handle_mouse_event: type={event_type}, pos={pos}, button={button}, is_painting={is_painting}")
        
        if not is_painting:
            return False
        
        if event_type == "press":
            # Refresh object database before starting to paint
            self._refresh_object_database()
            return self.mouse_handler.on_mouse_press(pos, button)
        elif event_type == "move":
            return self.mouse_handler.on_mouse_move(pos)
        elif event_type == "release":
            return self.mouse_handler.on_mouse_release(pos, button)
        
        return False
    
    def get_outline(self) -> List[tuple]:
        """Get the current painting outline"""
        return self.mouse_handler.get_outline()
    
    def get_outline_with_types(self) -> List[tuple]:
        """Get the current painting outline with tile types"""
        return self.mouse_handler.get_outline_with_types()
    
    def is_painting(self) -> bool:
        """Check if currently painting"""
        # Check the widget's painting_active flag, not the mouse handler
        return self.qpt_widget.is_painting()
    
    def reset(self):
        """
        Reset QPT to default state.
        Call this when level changes, area changes, or area settings are modified.
        """
        print("[QPT] QuickPaintTab.reset() called")
        self.qpt_widget.reset_to_default()


class FillPaintTab(QtWidgets.QWidget):
    """
    Fill Paint Tab - Stub for future implementation.
    
    Will provide:
    - Flood fill painting
    - Area selection
    - Fill options
    """
    
    def __init__(self, parent=None):
        """
        Initialize the Fill Paint tab.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QtWidgets.QVBoxLayout(self)
        
        label = QtWidgets.QLabel("Fill Paint - Coming Soon")
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        
        layout.addStretch()


class OutlineOverlayTab(QtWidgets.QWidget):
    """
    Outline Overlay Tab - Stub for future implementation.
    
    Will provide:
    - Outline visualization
    - Outline editing
    - Outline export
    """
    
    def __init__(self, parent=None):
        """
        Initialize the Outline Overlay tab.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QtWidgets.QVBoxLayout(self)
        
        label = QtWidgets.QLabel("Outline Overlay - Coming Soon")
        label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)
        
        layout.addStretch()


class QuickPaintPalette(QtWidgets.QWidget):
    """
    Quick Paint Palette - Main container for all QPT tabs.
    
    Integrates into Reggie's sidebar as a new palette section.
    """
    
    def __init__(self, parent=None):
        """
        Initialize the Quick Paint Palette.
        
        Args:
            parent: Parent widget
        """
        print("[QPT] QuickPaintPalette.__init__ starting...")
        super().__init__(parent)
        print("[QPT] OK: QWidget parent initialized")
        self.init_ui()
        print("[QPT] OK: QuickPaintPalette initialized")
    
    def init_ui(self):
        """Initialize the UI"""
        print("[QPT] QuickPaintPalette.init_ui starting...")
        
        print("[QPT] Creating layout...")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        print("[QPT] OK: Layout created")
        
        # ===== TAB WIDGET =====
        print("[QPT] Creating QTabWidget...")
        self.tabs = QtWidgets.QTabWidget()
        print("[QPT] OK: QTabWidget created")
        
        # Quick Paint tab (main)
        print("[QPT] Creating QuickPaintTab...")
        self.quick_paint_tab = QuickPaintTab()
        print("[QPT] OK: QuickPaintTab created")
        self.tabs.addTab(self.quick_paint_tab, "Quick Paint")
        
        # Fill Paint tab (stub)
        print("[QPT] Creating FillPaintTab...")
        self.fill_paint_tab = FillPaintTab()
        print("[QPT] OK: FillPaintTab created")
        self.tabs.addTab(self.fill_paint_tab, "Fill Paint")
        
        # Outline Overlay tab (stub)
        print("[QPT] Creating OutlineOverlayTab...")
        self.outline_overlay_tab = OutlineOverlayTab()
        print("[QPT] OK: OutlineOverlayTab created")
        self.tabs.addTab(self.outline_overlay_tab, "Outline Overlay")
        
        print("[QPT] Adding tabs to layout...")
        layout.addWidget(self.tabs)
        print("[QPT] OK: QuickPaintPalette.init_ui completed")
    
    def get_quick_paint_tab(self):
        """Get the Quick Paint tab"""
        return self.quick_paint_tab
    
    def handle_mouse_event(self, event_type: str, pos: tuple, button: int = 1) -> bool:
        """
        Handle mouse event from Reggie.
        
        Args:
            event_type: "press", "move", or "release"
            pos: Mouse position (x, y) in tile coordinates
            button: Mouse button
        
        Returns:
            True if event was handled, False otherwise
        """
        return self.quick_paint_tab.handle_mouse_event(event_type, pos, button)
    
    def get_outline(self) -> List[tuple]:
        """Get the current painting outline"""
        return self.quick_paint_tab.get_outline()
    
    def get_outline_with_types(self) -> List[tuple]:
        """Get the current painting outline with tile types"""
        return self.quick_paint_tab.get_outline_with_types()
    
    def is_painting(self) -> bool:
        """Check if currently painting"""
        return self.quick_paint_tab.is_painting()
    
    def reset(self):
        """
        Reset QPT to default state.
        Call this when level changes, area changes, or area settings are modified.
        """
        self.quick_paint_tab.reset()
