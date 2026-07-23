"""
Hotkey Overlay - Displays QPT hotkeys over the canvas

Shows two containers:
- Container 1 (left): Main tab hotkeys (P, Q, F, D)
- Container 2 (right): Active tool hotkeys
"""
from typing import Optional
from PyQt6 import QtWidgets, QtCore, QtGui


class HotkeyContainer(QtWidgets.QFrame):
    """
    Container for hotkey display.
    
    Shows a title and list of hotkeys. Extendable for future additions.
    """
    
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.title = title
        self._hotkeys = []
        
        # More transparent background
        self.setStyleSheet("""
            HotkeyContainer {
                background-color: rgba(20, 20, 20, 120);
                border: 1px solid rgba(80, 80, 80, 150);
                border-radius: 4px;
            }
        """)
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(3)
        
        # Title label (no toggle button)
        self.title_label = QtWidgets.QLabel(self.title)
        self.title_label.setStyleSheet("""
            color: rgba(230, 230, 230, 240);
            font-weight: bold;
            font-size: 9pt;
        """)
        layout.addWidget(self.title_label)
        
        # Content area for hotkeys
        self.content_widget = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 2, 0, 0)
        self.content_layout.setSpacing(2)
        
        layout.addWidget(self.content_widget)
    
    def set_hotkeys(self, hotkeys: list):
        """
        Set the hotkeys to display.
        
        Args:
            hotkeys: List of (key, description) tuples
        """
        self._hotkeys = hotkeys
        
        # Clear existing
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add new hotkey labels
        for key, desc in hotkeys:
            label = QtWidgets.QLabel(f"<b>{key}</b>: {desc}")
            label.setStyleSheet("""
                color: rgba(220, 220, 220, 230);
                font-size: 9pt;
                padding: 1px 0px;
            """)
            self.content_layout.addWidget(label)
    
    def set_title(self, title: str):
        """Set the container title"""
        self.title = title
        self.title_label.setText(title)


class HotkeyOverlay(QtWidgets.QWidget):
    """
    Overlay widget showing QPT hotkeys over the canvas.
    
    Positioned 1 tile (24px) from top and left edges.
    Contains two containers for hotkey display.
    Only visible when Quick Paint tab is active.
    """
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        self._current_tool = None
        
        # Make widget transparent to mouse events except for the containers
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setStyleSheet("background: transparent;")
        
        self.init_ui()
        self.hide()  # Hidden by default
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignTop)
        
        # Container 1: Main hotkeys (left)
        self.main_container = HotkeyContainer("Tools (F3)")
        self.main_container.set_hotkeys([
            ("P", "Quick Paint Tab"),
            ("Q", "Smart Paint"),
            ("S", "Single Tile"),
            ("C", "Shape Creator"),
            ("E", "Eraser"),
            ("F", "Fill Tool"),
            ("D", "Deco Fill"),
        ])
        layout.addWidget(self.main_container)
        
        # Container 2: Tool-specific hotkeys (right)
        self.tool_container = HotkeyContainer("Smart Paint")
        self._update_tool_hotkeys("qpt")
        layout.addWidget(self.tool_container)
        
        layout.addStretch()
        
        # Set fixed size based on content
        self.adjustSize()
    
    def _update_tool_hotkeys(self, tool_type: str):
        """Update tool-specific hotkeys based on active tool"""
        self._current_tool = tool_type
        
        if tool_type == "qpt":
            self.tool_container.set_title("Smart Paint")
            self.tool_container.set_hotkeys([
                ("Q", "Start/Stop"),
                ("RClick", "Draw stroke"),
                ("RClick", "Confirm"),
                ("F1", "Slope Mode"),
                ("ESC", "Cancel"),
                ("", ""),
                ("", ""),
            ])
        elif tool_type == "fill":
            self.tool_container.set_title("Fill Tool")
            self.tool_container.set_hotkeys([
                ("RClick", "Create area"),
                ("RClick", "Confirm fill"),
                ("Shift", "Outside zones"),
                ("F2", "Clear area"),
                ("ESC", "Cancel"),
                ("", ""),
                ("", ""),
            ])
        elif tool_type == "deco":
            self.tool_container.set_title("Deco Fill")
            self.tool_container.set_hotkeys([
                ("RClick", "Create area"),
                ("RClick", "Confirm fill"),
                ("Shift", "Outside zones"),
                ("F2", "Clear area"),
                ("ESC", "Cancel"),
                ("", ""),
                ("", ""),
            ])
        elif tool_type == "single_tile":
            self.tool_container.set_title("Single Tile")
            self.tool_container.set_hotkeys([
                ("RClick", "Paint tile"),
                ("Drag", "Paint stroke"),
                ("", ""),
                ("", ""),
                ("", ""),
                ("", ""),
                ("", ""),
            ])
        elif tool_type == "eraser":
            self.tool_container.set_title("Eraser")
            self.tool_container.set_hotkeys([
                ("RClick", "Erase tile"),
                ("Drag", "Erase stroke"),
                ("", ""),
                ("", ""),
                ("", ""),
                ("", ""),
                ("", ""),
            ])
        elif tool_type == "shape_creator":
            self.tool_container.set_title("Shape Creator")
            self.tool_container.set_hotkeys([
                ("", "Coming Soon"),
                ("", ""),
                ("", ""),
                ("", ""),
                ("", ""),
                ("", ""),
                ("", ""),
            ])
        else:
            self.tool_container.set_title("No Tool")
            self.tool_container.set_hotkeys([])
        
        self.adjustSize()
    
    def set_active_tool(self, tool_type: str):
        """
        Set the currently active tool to display appropriate hotkeys.
        
        Args:
            tool_type: One of "qpt", "fill", "deco", or None
        """
        if tool_type != self._current_tool:
            self._update_tool_hotkeys(tool_type or "qpt")
    
    def position_overlay(self, view_geometry: QtCore.QRect):
        """
        Position the overlay relative to the graphics view.
        
        Args:
            view_geometry: The geometry of the graphics view in parent coordinates
        """
        # Position exactly 1 tile (24px) from top and left of the view
        x = view_geometry.x() + 24
        y = view_geometry.y()  # No extra offset - view.y() already accounts for toolbar
        self.move(x, y)
    
    def show_overlay(self):
        """Show the overlay"""
        self.show()
        self.raise_()  # Ensure it's on top
    
    def hide_overlay(self):
        """Hide the overlay"""
        self.hide()


def create_hotkey_overlay(main_window) -> Optional[HotkeyOverlay]:
    """
    Create and attach the hotkey overlay to the main window.
    
    Args:
        main_window: Reggie's main window
        
    Returns:
        HotkeyOverlay widget or None if creation failed
    """
    try:
        # Create overlay as child of central widget to overlay the view
        overlay = HotkeyOverlay(main_window.centralWidget())
        
        # Position it (will be updated when view geometry changes)
        if hasattr(main_window, 'view') and main_window.view:
            view_geo = main_window.view.geometry()
            overlay.position_overlay(view_geo)
        
        return overlay
    except Exception as e:
        print(f"[QPT] Error creating hotkey overlay: {e}")
        return None
