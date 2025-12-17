"""
Tileset Selector and Object List - Allows selection of tileset and objects for tile picker
"""
from typing import Optional, List, Dict
from PyQt6 import QtWidgets, QtCore, QtGui

from quickpaint.core.brush import SmartBrush


class FlowLayout(QtWidgets.QLayout):
    """
    A flow layout that arranges widgets in a horizontal flow, wrapping to the next line
    when there's not enough horizontal space. Similar to CSS flexbox with wrap.
    """
    
    def __init__(self, parent=None, margin=0, spacing=-1):
        super().__init__(parent)
        self.setContentsMargins(margin, margin, margin, margin)
        self._spacing = spacing
        self._items = []
    
    def addItem(self, item):
        self._items.append(item)
    
    def count(self):
        return len(self._items)
    
    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None
    
    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None
    
    def expandingDirections(self):
        return QtCore.Qt.Orientation(0)
    
    def hasHeightForWidth(self):
        return True
    
    def heightForWidth(self, width):
        return self._do_layout(QtCore.QRect(0, 0, width, 0), test_only=True)
    
    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)
    
    def sizeHint(self):
        return self.minimumSize()
    
    def minimumSize(self):
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QtCore.QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size
    
    def _do_layout(self, rect, test_only):
        """Perform the layout, optionally just calculating height"""
        margins = self.contentsMargins()
        effective_rect = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x = effective_rect.x()
        y = effective_rect.y()
        line_height = 0
        spacing = self._spacing if self._spacing >= 0 else self.spacing()
        
        for item in self._items:
            widget = item.widget()
            if widget is None:
                continue
                
            item_size = item.sizeHint()
            next_x = x + item_size.width() + spacing
            
            # Wrap to next line if needed
            if next_x - spacing > effective_rect.right() and line_height > 0:
                x = effective_rect.x()
                y = y + line_height + spacing
                next_x = x + item_size.width() + spacing
                line_height = 0
            
            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), item_size))
            
            x = next_x
            line_height = max(line_height, item_size.height())
        
        return y + line_height - rect.y() + margins.bottom()


class TilesetSelector(QtWidgets.QWidget):
    """
    Tileset selector with object list.
    
    Allows user to:
    1. Select a tileset (Pa0, Pa1, Pa2, Pa3)
    2. View and select objects from that tileset
    3. Place selected objects into tile picker positions
    """
    
    # Signal emitted when an object is selected
    object_selected = QtCore.pyqtSignal(int, int, int)  # tileset, type, object_id
    
    def __init__(self, parent=None):
        """
        Initialize the tileset selector.
        
        Args:
            parent: Parent widget
        """
        super().__init__(parent)
        self.current_tileset = 0
        self.available_tilesets = ["Pa0", "Pa1", "Pa2", "Pa3"]
        self.tileset_objects: Dict[int, List[Dict]] = {}
        self.objects_loaded = False
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        
        # ===== TILESET SELECTOR =====
        selector_label = QtWidgets.QLabel("Tileset:")
        layout.addWidget(selector_label)
        
        selector_layout = QtWidgets.QHBoxLayout()
        self.tileset_combo = QtWidgets.QComboBox()
        self.tileset_combo.addItems(self.available_tilesets)
        self.tileset_combo.currentIndexChanged.connect(self.on_tileset_changed)
        selector_layout.addWidget(self.tileset_combo)
        layout.addLayout(selector_layout)
        
        # ===== OBJECT LIST =====
        objects_label = QtWidgets.QLabel("Objects:")
        layout.addWidget(objects_label)
        
        # Create a scroll area for the object list
        self.object_scroll_area = QtWidgets.QScrollArea()
        self.object_scroll_area.setWidgetResizable(True)  # Allow content to resize with scroll area width
        self.object_scroll_area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)  # No horizontal scroll
        self.object_scroll_area.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.object_scroll_area.setMinimumHeight(200)
        
        # Object list widget with flow layout - wraps items based on available width
        self.object_list_widget = QtWidgets.QWidget()
        self.object_list_layout = FlowLayout(self.object_list_widget, margin=2, spacing=2)
        
        self.object_scroll_area.setWidget(self.object_list_widget)
        layout.addWidget(self.object_scroll_area)
        
        # Store buttons for easy access
        self.object_buttons: Dict[int, QtWidgets.QPushButton] = {}
        self.selected_object_id: Optional[int] = None
    
    def on_tileset_changed(self, index: int):
        """
        Handle tileset change.
        
        Args:
            index: Index of selected tileset
        """
        print(f"[QPT] on_tileset_changed called: index={index}")
        self.current_tileset = index
        
        # Load objects from Reggie's ObjectDefinitions if not already loaded
        if not self.objects_loaded:
            print("[QPT] Loading objects from Reggie...")
            self.load_objects_from_reggie()
            self.objects_loaded = True
            print("[QPT] OK: Objects loaded")
        
        print(f"[QPT] Updating object list for tileset {index}")
        self.update_object_list()
        print(f"[QPT] OK: Object list updated")
    
    def update_object_list(self):
        """Update the object list display for current tileset"""
        # Clear existing buttons
        for button in self.object_buttons.values():
            button.deleteLater()
        self.object_buttons.clear()
        
        # Clear layout
        while self.object_list_layout.count():
            item = self.object_list_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Get objects for current tileset
        if self.current_tileset in self.tileset_objects:
            objects = self.tileset_objects[self.current_tileset]
            
            for obj_data in objects:
                obj_id = obj_data.get('id', 0)
                obj_type = obj_data.get('type', 0)
                
                # Create button with object preview image
                button = QtWidgets.QPushButton()
                
                # Get the preview pixmap from Reggie
                pixmap = self.get_object_preview(self.current_tileset, obj_id)
                
                if pixmap:
                    # Set button size based on object dimensions
                    button.setFixedSize(pixmap.width() + 4, pixmap.height() + 4)
                    button.setIcon(QtGui.QIcon(pixmap))
                    button.setIconSize(pixmap.size())
                    button.setToolTip(f"Object {obj_id}")
                    
                    # Make button transparent with no background
                    button.setStyleSheet(
                        "QPushButton { "
                        "background-color: transparent; "
                        "border: none; "
                        "padding: 0px; "
                        "} "
                        "QPushButton:hover { "
                        "background-color: rgba(255, 255, 255, 50); "
                        "border: 1px solid rgba(255, 255, 255, 100); "
                        "} "
                        "QPushButton:pressed { "
                        "background-color: rgba(100, 150, 255, 100); "
                        "border: 1px solid rgba(100, 150, 255, 200); "
                        "}"
                    )
                else:
                    # Fallback if preview fails
                    button.setFixedSize(40, 40)
                    button.setText(f"Obj {obj_id}")
                
                # Create a proper closure to avoid lambda issues
                def make_callback(tileset, obj_type, obj_id):
                    def callback():
                        print(f"[QPT] Button clicked: tileset={tileset}, obj_type={obj_type}, obj_id={obj_id}")
                        self.on_object_selected(tileset, obj_type, obj_id)
                    return callback
                
                button.clicked.connect(make_callback(self.current_tileset, obj_type, obj_id))
                button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)  # Prevent focus-triggered clicks
                
                self.object_buttons[obj_id] = button
                self.object_list_layout.addWidget(button)  # FlowLayout handles positioning
    
    def on_object_selected(self, tileset: int, obj_type: int, obj_id: int):
        """
        Handle object selection.
        
        Args:
            tileset: Tileset index
            obj_type: Object type
            obj_id: Object ID
        """
        # Update visual selection
        if self.selected_object_id is not None and self.selected_object_id in self.object_buttons:
            # Remove highlight from previously selected button
            btn = self.object_buttons[self.selected_object_id]
            btn.setStyleSheet(
                "QPushButton { "
                "background-color: transparent; "
                "border: none; "
                "padding: 0px; "
                "} "
                "QPushButton:hover { "
                "background-color: rgba(255, 255, 255, 50); "
                "border: 1px solid rgba(255, 255, 255, 100); "
                "} "
                "QPushButton:pressed { "
                "background-color: rgba(100, 150, 255, 100); "
                "border: 1px solid rgba(100, 150, 255, 200); "
                "}"
            )
        
        # Highlight the newly selected button
        if obj_id in self.object_buttons:
            btn = self.object_buttons[obj_id]
            btn.setStyleSheet(
                "QPushButton { "
                "background-color: rgba(100, 150, 255, 150); "
                "border: 2px solid rgba(100, 150, 255, 255); "
                "padding: 0px; "
                "} "
                "QPushButton:hover { "
                "background-color: rgba(150, 180, 255, 150); "
                "border: 2px solid rgba(150, 180, 255, 255); "
                "} "
                "QPushButton:pressed { "
                "background-color: rgba(100, 150, 255, 200); "
                "border: 2px solid rgba(100, 150, 255, 255); "
                "}"
            )
        
        self.selected_object_id = obj_id
        self.object_selected.emit(tileset, obj_type, obj_id)
    
    def set_tileset_objects(self, tileset_objects: Dict[int, List[Dict]]):
        """
        Set the available objects for each tileset.
        
        Args:
            tileset_objects: Dictionary mapping tileset index to list of objects
        """
        self.tileset_objects = tileset_objects
        self.update_object_list()
    
    def get_current_tileset(self) -> int:
        """Get the currently selected tileset index"""
        return self.current_tileset
    
    def get_current_tileset_name(self) -> str:
        """Get the currently selected tileset name"""
        return self.available_tilesets[self.current_tileset]
    
    def initialize_objects(self):
        """Initialize objects for the current tileset (called after Reggie is fully loaded)"""
        if not self.objects_loaded:
            self.load_objects_from_reggie()
            self.objects_loaded = True
            self.update_object_list()
    
    def load_objects_from_reggie(self):
        """Load tileset objects from Reggie's ObjectDefinitions"""
        try:
            import globals_
            
            # Build tileset_objects dictionary from Reggie's ObjectDefinitions
            tileset_objects = {}
            
            if globals_.ObjectDefinitions:
                for tileset_idx, obj_defs in enumerate(globals_.ObjectDefinitions):
                    if obj_defs is None:
                        continue
                    
                    objects = []
                    for obj_id, obj_def in enumerate(obj_defs):
                        if obj_def is not None:
                            objects.append({
                                'id': obj_id,
                                'type': 0,  # Default type
                                'name': f'Object {obj_id}'
                            })
                    
                    if objects:
                        tileset_objects[tileset_idx] = objects
            
            if tileset_objects:
                self.set_tileset_objects(tileset_objects)
        except Exception as e:
            print(f"Error loading objects from Reggie: {e}")
    
    def get_object_preview(self, tileset_idx: int, obj_id: int) -> QtGui.QPixmap:
        """
        Render an object preview pixmap, similar to how Reggie does it.
        
        Args:
            tileset_idx: Tileset index (0-3)
            obj_id: Object ID
        
        Returns:
            QPixmap with the rendered object, or None if rendering fails
        """
        try:
            import globals_
            from tiles import RenderObject
            
            if not globals_.ObjectDefinitions or not globals_.Tiles:
                return None
            
            obj_defs = globals_.ObjectDefinitions[tileset_idx]
            if not obj_defs or obj_id >= len(obj_defs) or obj_defs[obj_id] is None:
                return None
            
            obj_def = obj_defs[obj_id]
            
            # Render the object using Reggie's RenderObject function
            obj_render = RenderObject(tileset_idx, obj_id, obj_def.width, obj_def.height, True)
            
            # Create pixmap
            pm = QtGui.QPixmap(obj_def.width * 24, obj_def.height * 24)
            pm.fill(QtCore.Qt.GlobalColor.transparent)
            
            # Paint the object
            painter = QtGui.QPainter()
            painter.begin(pm)
            
            y = 0
            for row in obj_render:
                x = 0
                for tile_num in row:
                    if tile_num > 0:
                        tile = globals_.Tiles[tile_num]
                        if tile is None:
                            # Use override for unknown tiles
                            if hasattr(globals_, 'Overrides') and hasattr(globals_, 'OVERRIDE_UNKNOWN'):
                                painter.drawPixmap(x, y, globals_.Overrides[globals_.OVERRIDE_UNKNOWN].getCurrentTile())
                        elif isinstance(tile.main, QtGui.QImage):
                            painter.drawImage(x, y, tile.main)
                        else:
                            painter.drawPixmap(x, y, tile.main)
                    x += 24
                y += 24
            
            painter.end()
            return pm
            
        except Exception as e:
            print(f"Error rendering object preview for tileset {tileset_idx}, object {obj_id}: {e}")
            return None
