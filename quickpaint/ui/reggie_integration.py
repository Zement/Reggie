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
        print("[QPT] ✓ QWidget parent initialized")
        
        # Import here to avoid QWidget creation before QApplication is ready
        print("[QPT] Importing PresetManager...")
        from quickpaint.core.presets import PresetManager
        print("[QPT] ✓ PresetManager imported")
        
        print("[QPT] Importing MouseEventHandler...")
        from quickpaint.ui.events import MouseEventHandler
        print("[QPT] ✓ MouseEventHandler imported")
        
        print("[QPT] Creating preset manager...")
        # PresetManager requires builtin and user directories
        import os
        builtin_dir = os.path.join('assets', 'qpt', 'builtin')
        user_dir = os.path.join('assets', 'qpt', 'presets')
        self.preset_manager = PresetManager(builtin_dir, user_dir)
        print("[QPT] ✓ Preset manager created")
        
        print("[QPT] Creating mouse handler...")
        self.mouse_handler = MouseEventHandler()
        print("[QPT] ✓ Mouse handler created")
        
        print("[QPT] Initializing UI...")
        self.init_ui()
        print("[QPT] ✓ QuickPaintTab initialized")
    
    def init_ui(self):
        """Initialize the UI"""
        print("[QPT] init_ui starting...")
        
        # Import here to avoid QWidget creation before QApplication is ready
        print("[QPT] Importing TilesetSelector...")
        from quickpaint.ui.tileset_selector import TilesetSelector
        print("[QPT] ✓ TilesetSelector imported")
        
        print("[QPT] Importing QuickPaintWidget...")
        from quickpaint.ui.widget import QuickPaintWidget
        print("[QPT] ✓ QuickPaintWidget imported")
        
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
        
        # Initialize tileset objects after a short delay to ensure Reggie is fully loaded
        QtCore.QTimer.singleShot(100, self.tileset_selector.initialize_objects)
    
    def on_painting_started(self):
        """Handle painting start"""
        brush = self.qpt_widget.get_current_brush()
        mode = self.qpt_widget.get_current_mode()
        
        if brush:
            self.mouse_handler.set_brush(brush)
            self.mouse_handler.set_mode(mode)
    
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
            from quickpaint.core.brush import SmartBrush, TilesetCategory
            tileset_name = self.tileset_selector.get_current_tileset_name()
            self.qpt_widget.current_brush = SmartBrush(
                f"Object_{tileset}",
                [tileset_name],
                TilesetCategory.CAT1
            )
            print(f"[QPT] Created new brush for tileset {tileset}")
            
            # Set the tileset for the canvas (but don't draw yet)
            self.qpt_widget.tile_picker_canvas.set_tileset(tileset)
            self.qpt_widget.tile_picker_canvas.set_brush(self.qpt_widget.current_brush)
            print(f"[QPT] Tile picker canvas initialized for tileset {tileset}")
            print(f"[QPT] Canvas will update when you select a position type")
        else:
            print(f"[QPT] Brush already exists, not reinitializing canvas")
    
    def on_painting_ended(self, operations: List):
        """
        Handle painting end.
        
        Args:
            operations: List of PaintOperation objects
        """
        # Apply operations to the level
        # This would integrate with Reggie's level editing
        pass
    
    def handle_mouse_event(self, event_type: str, pos: tuple, button: int = 1) -> bool:
        """
        Handle mouse event from Reggie.
        
        Args:
            event_type: "press", "move", or "release"
            pos: Mouse position (x, y) in tile coordinates
            button: Mouse button (1=left, 2=right, 3=middle)
        
        Returns:
            True if event was handled, False otherwise
        """
        if not self.qpt_widget.is_painting():
            return False
        
        if event_type == "press":
            return self.mouse_handler.on_mouse_press(pos, button)
        elif event_type == "move":
            return self.mouse_handler.on_mouse_move(pos)
        elif event_type == "release":
            return self.mouse_handler.on_mouse_release(pos, button)
        
        return False
    
    def get_outline(self) -> List[tuple]:
        """Get the current painting outline"""
        return self.mouse_handler.get_outline()
    
    def is_painting(self) -> bool:
        """Check if currently painting"""
        return self.mouse_handler.is_painting()


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
        print("[QPT] ✓ QWidget parent initialized")
        self.init_ui()
        print("[QPT] ✓ QuickPaintPalette initialized")
    
    def init_ui(self):
        """Initialize the UI"""
        print("[QPT] QuickPaintPalette.init_ui starting...")
        
        print("[QPT] Creating layout...")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        print("[QPT] ✓ Layout created")
        
        # ===== TAB WIDGET =====
        print("[QPT] Creating QTabWidget...")
        self.tabs = QtWidgets.QTabWidget()
        print("[QPT] ✓ QTabWidget created")
        
        # Quick Paint tab (main)
        print("[QPT] Creating QuickPaintTab...")
        self.quick_paint_tab = QuickPaintTab()
        print("[QPT] ✓ QuickPaintTab created")
        self.tabs.addTab(self.quick_paint_tab, "Quick Paint")
        
        # Fill Paint tab (stub)
        print("[QPT] Creating FillPaintTab...")
        self.fill_paint_tab = FillPaintTab()
        print("[QPT] ✓ FillPaintTab created")
        self.tabs.addTab(self.fill_paint_tab, "Fill Paint")
        
        # Outline Overlay tab (stub)
        print("[QPT] Creating OutlineOverlayTab...")
        self.outline_overlay_tab = OutlineOverlayTab()
        print("[QPT] ✓ OutlineOverlayTab created")
        self.tabs.addTab(self.outline_overlay_tab, "Outline Overlay")
        
        print("[QPT] Adding tabs to layout...")
        layout.addWidget(self.tabs)
        print("[QPT] ✓ QuickPaintPalette.init_ui completed")
    
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
    
    def is_painting(self) -> bool:
        """Check if currently painting"""
        return self.quick_paint_tab.is_painting()
