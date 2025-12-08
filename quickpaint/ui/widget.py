"""
Quick Paint Widget - Main UI for the Quick Paint Tool
"""
from typing import Optional, Dict
from PyQt6 import QtWidgets, QtCore, QtGui

from quickpaint.core.brush import SmartBrush, TilesetCategory
from quickpaint.core.presets import PresetManager
from quickpaint.core.modes import SmartPaintMode, SingleTileMode, ShapeCreator, PaintingDirection


class QuickPaintWidget(QtWidgets.QWidget):
    """
    Main Quick Paint Tool Widget.
    
    Contains:
    - Preset list (two-column: name, tilesets)
    - Painting mode selector
    - Category selector
    - Tile picker
    - Control buttons (Start/Stop Painting, Save/Load/Delete Preset)
    """
    
    # Signals
    painting_started = QtCore.pyqtSignal()
    painting_stopped = QtCore.pyqtSignal()
    preset_changed = QtCore.pyqtSignal(SmartBrush)
    mode_changed = QtCore.pyqtSignal(str)
    
    def __init__(self, preset_manager: PresetManager = None, tileset_selector=None, parent=None):
        """
        Initialize the Quick Paint Widget.
        
        Args:
            preset_manager: PresetManager instance
            tileset_selector: TilesetSelector instance
            parent: Parent widget
        """
        print("[QPT] QuickPaintWidget.__init__ starting...")
        super().__init__(parent)
        print("[QPT] ✓ QWidget parent initialized")
        
        print("[QPT] Setting preset manager...")
        self.preset_manager = preset_manager or PresetManager()
        print("[QPT] ✓ Preset manager set")
        
        print("[QPT] Initializing attributes...")
        self.current_brush: Optional[SmartBrush] = None
        self.painting_active = False
        self.current_mode = "SmartPaint"
        self.tileset_selector = tileset_selector
        print("[QPT] ✓ Attributes initialized")
        
        print("[QPT] Calling init_ui...")
        self.init_ui()
        print("[QPT] ✓ init_ui completed")
        
        print("[QPT] Loading presets...")
        self.load_presets()
        print("[QPT] ✓ QuickPaintWidget initialized")
    
    def init_ui(self):
        """Initialize the UI"""
        print("[QPT] QuickPaintWidget.init_ui starting...")
        
        print("[QPT] Creating layout...")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        print("[QPT] ✓ Layout created")
        
        # ===== PRESET LIST =====
        print("[QPT] Creating preset label...")
        preset_label = QtWidgets.QLabel("Presets:")
        layout.addWidget(preset_label)
        print("[QPT] ✓ Preset label created")
        
        print("[QPT] Creating preset list...")
        self.preset_list = QtWidgets.QTableWidget()
        print("[QPT] ✓ QTableWidget created")
        
        print("[QPT] Configuring preset list...")
        self.preset_list.setColumnCount(2)
        self.preset_list.setHorizontalHeaderLabels(["Name", "Tilesets"])
        self.preset_list.horizontalHeader().setStretchLastSection(True)
        # PyQt6: SelectionBehavior enum values are SelectRows, SelectColumns
        self.preset_list.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.preset_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.preset_list.itemSelectionChanged.connect(self.on_preset_selected)
        layout.addWidget(self.preset_list)
        print("[QPT] ✓ Preset list configured")
        
        # ===== CATEGORY =====
        print("[QPT] Creating category section...")
        category_label = QtWidgets.QLabel("Tileset Categories:")
        layout.addWidget(category_label)
        
        category_layout = QtWidgets.QHBoxLayout()
        self.category_combo = QtWidgets.QComboBox()
        self.category_combo.addItems(["CAT1 (No Slopes)", "CAT2 (4x1 Slopes)", "CAT3 (All Slopes)"])
        self.category_combo.currentIndexChanged.connect(self.on_category_changed)
        category_layout.addWidget(self.category_combo)
        layout.addLayout(category_layout)
        print("[QPT] ✓ Category section created")
        
        # ===== TILE PICKER =====
        print("[QPT] Creating tile picker section...")
        picker_label = QtWidgets.QLabel("Tile Picker:")
        layout.addWidget(picker_label)
        
        # Position selector buttons
        print("[QPT] Creating position selector...")
        position_label = QtWidgets.QLabel("Select Position Type:")
        layout.addWidget(position_label)
        
        position_layout = QtWidgets.QGridLayout()
        self.position_buttons: Dict[str, QtWidgets.QPushButton] = {}
        
        # Terrain positions with capitalized labels
        terrain_positions = [
            ('top', 'Top\n(Ground)'),
            ('center', 'Center\n(Fill)'),
            ('bottom', 'Bottom\n(Ceiling)'),
            ('left', 'Left\n(L Wall)'),
            ('right', 'Right\n(R Wall)'),
            ('top_left', 'Top Left\n(L Edge)'),
            ('top_right', 'Top Right\n(R Edge)'),
            ('bottom_left', 'Bottom Left\n(L Ceiling Edge)'),
            ('bottom_right', 'Bottom Right\n(R Ceiling Edge)'),
            ('inner_top_left', 'Inner\nTop Left'),
            ('inner_top_right', 'Inner\nTop Right'),
            ('inner_bottom_left', 'Inner\nBottom Left'),
            ('inner_bottom_right', 'Inner\nBottom Right'),
        ]
        
        for i, (pos_key, pos_label) in enumerate(terrain_positions):
            btn = QtWidgets.QPushButton(pos_label)
            btn.setMaximumWidth(80)
            btn.setMinimumHeight(32)
            btn.setStyleSheet("font-size: 10px;")
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked, p=pos_key: self.on_position_selected(p))
            self.position_buttons[pos_key] = btn
            position_layout.addWidget(btn, i // 7, i % 7)
        
        layout.addLayout(position_layout)
        print("[QPT] ✓ Position selector created")
        
        # Canvas-based tile picker
        print("[QPT] Creating canvas tile picker...")
        from quickpaint.ui.tile_picker_canvas import TilePickerCanvas
        self.tile_picker_canvas = TilePickerCanvas(self.current_brush)
        self.tile_picker_canvas.tile_selected.connect(self.on_tile_selected_from_canvas)
        print("[QPT] ✓ Canvas tile picker created")
        layout.addWidget(self.tile_picker_canvas)
        print("[QPT] ✓ Tile picker section created")
        
        # ===== PAINTING MODE =====
        print("[QPT] Creating painting mode section...")
        mode_label = QtWidgets.QLabel("Painting Mode:")
        layout.addWidget(mode_label)
        
        mode_layout = QtWidgets.QHBoxLayout()
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["SmartPaint", "SingleTile", "ShapeCreator"])
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        layout.addLayout(mode_layout)
        print("[QPT] ✓ Painting mode section created")
        
        # ===== CONTROL BUTTONS =====
        button_layout = QtWidgets.QVBoxLayout()
        
        # Start/Stop Painting
        painting_layout = QtWidgets.QHBoxLayout()
        self.start_painting_btn = QtWidgets.QPushButton("Start Painting")
        self.start_painting_btn.clicked.connect(self.on_start_painting)
        painting_layout.addWidget(self.start_painting_btn)
        
        self.stop_painting_btn = QtWidgets.QPushButton("Stop Painting")
        self.stop_painting_btn.clicked.connect(self.on_stop_painting)
        self.stop_painting_btn.setEnabled(False)
        painting_layout.addWidget(self.stop_painting_btn)
        button_layout.addLayout(painting_layout)
        
        # Preset management buttons
        preset_btn_layout = QtWidgets.QHBoxLayout()
        
        self.save_preset_btn = QtWidgets.QPushButton("Save Preset")
        self.save_preset_btn.clicked.connect(self.on_save_preset)
        preset_btn_layout.addWidget(self.save_preset_btn)
        
        self.load_preset_btn = QtWidgets.QPushButton("Load Preset")
        self.load_preset_btn.clicked.connect(self.on_load_preset)
        preset_btn_layout.addWidget(self.load_preset_btn)
        
        self.delete_preset_btn = QtWidgets.QPushButton("Delete Preset")
        self.delete_preset_btn.clicked.connect(self.on_delete_preset)
        self.delete_preset_btn.setEnabled(False)
        preset_btn_layout.addWidget(self.delete_preset_btn)
        
        button_layout.addLayout(preset_btn_layout)
        layout.addLayout(button_layout)
        
        layout.addStretch()
    
    def load_presets(self):
        """Load presets from preset manager"""
        self.preset_list.setRowCount(0)
        
        # Get all presets
        presets = self.preset_manager.get_all_presets()
        
        for i, (preset_name, preset) in enumerate(presets.items()):
            if preset:
                self.preset_list.insertRow(i)
                
                # Name column
                name_item = QtWidgets.QTableWidgetItem(preset.name)
                name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.preset_list.setItem(i, 0, name_item)
                
                # Tilesets column
                tilesets_str = ", ".join(preset.tileset_names)
                tilesets_item = QtWidgets.QTableWidgetItem(tilesets_str)
                tilesets_item.setFlags(tilesets_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
                self.preset_list.setItem(i, 1, tilesets_item)
    
    def on_preset_selected(self):
        """Handle preset selection"""
        selected_rows = self.preset_list.selectedIndexes()
        if selected_rows:
            row = selected_rows[0].row()
            preset_name = self.preset_list.item(row, 0).text()
            
            preset = self.preset_manager.get_preset(preset_name)
            if preset:
                self.current_brush = preset
                self.tile_picker_canvas.set_brush(preset)
                self.category_combo.setCurrentIndex(
                    ['cat1', 'cat2', 'cat3'].index(preset.category.value)
                )
                self.preset_changed.emit(preset)
                
                # Enable delete button only for custom presets
                builtin_presets = self.preset_manager.load_builtin_presets()
                is_builtin = preset_name in builtin_presets
                self.delete_preset_btn.setEnabled(not is_builtin)
    
    def on_mode_changed(self, mode: str):
        """Handle painting mode change"""
        self.current_mode = mode
        self.mode_changed.emit(mode)
    
    def on_category_changed(self, index: int):
        """Handle category change"""
        categories = [TilesetCategory.CAT1, TilesetCategory.CAT2, TilesetCategory.CAT3]
        if self.current_brush:
            self.current_brush.category = categories[index]
    
    def on_start_painting(self):
        """Handle start painting button"""
        if not self.current_brush:
            QtWidgets.QMessageBox.warning(self, "No Preset", "Please select a preset first.")
            return
        
        self.painting_active = True
        self.start_painting_btn.setEnabled(False)
        self.stop_painting_btn.setEnabled(True)
        self.painting_started.emit()
    
    def on_stop_painting(self):
        """Handle stop painting button"""
        self.painting_active = False
        self.start_painting_btn.setEnabled(True)
        self.stop_painting_btn.setEnabled(False)
        self.painting_stopped.emit()
    
    def on_save_preset(self):
        """Handle save preset button"""
        # Get preset name
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Save Preset", "Preset name:"
        )
        if not ok or not name:
            return
        
        # Get tileset names
        tilesets_text, ok = QtWidgets.QInputDialog.getMultiLineText(
            self, "Tileset Names",
            "Enter tileset names (one per line, supports regex):"
        )
        if not ok:
            return
        
        tilesets = [t.strip() for t in tilesets_text.split('\n') if t.strip()]
        
        if not tilesets:
            QtWidgets.QMessageBox.warning(self, "No Tilesets", "Please enter at least one tileset name.")
            return
        
        # Create and save preset
        if self.current_brush:
            self.current_brush.name = name
            self.current_brush.tileset_names = tilesets
            self.preset_manager.save_preset(self.current_brush)
            self.load_presets()
            QtWidgets.QMessageBox.information(self, "Success", f"Preset '{name}' saved.")
    
    def on_load_preset(self):
        """Handle load preset button"""
        file_dialog = QtWidgets.QFileDialog()
        file_path, _ = file_dialog.getOpenFileName(
            self, "Load Preset", "", "JSON Files (*.json)"
        )
        if file_path:
            try:
                with open(file_path, 'r') as f:
                    import json
                    data = json.load(f)
                    preset = SmartBrush.from_json(data)
                    self.current_brush = preset
                    self.tile_picker.set_brush(preset)
                    self.preset_changed.emit(preset)
                    QtWidgets.QMessageBox.information(self, "Success", f"Preset loaded: {preset.name}")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Error", f"Failed to load preset: {str(e)}")
    
    def on_delete_preset(self):
        """Handle delete preset button"""
        selected_rows = self.preset_list.selectedIndexes()
        if not selected_rows:
            QtWidgets.QMessageBox.warning(self, "No Selection", "Please select a preset to delete.")
            return
        
        row = selected_rows[0].row()
        preset_name = self.preset_list.item(row, 0).text()
        
        # Check if it's a builtin preset
        is_builtin = preset_name in self.preset_manager.list_builtin_presets()
        if is_builtin:
            QtWidgets.QMessageBox.warning(self, "Cannot Delete", "Cannot delete builtin presets.")
            return
        
        # Confirm deletion
        reply = QtWidgets.QMessageBox.question(
            self, "Confirm Delete",
            f"Delete preset '{preset_name}'?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
        )
        
        if reply == QtWidgets.QMessageBox.Yes:
            self.preset_manager.delete_preset(preset_name)
            self.load_presets()
            QtWidgets.QMessageBox.information(self, "Success", f"Preset '{preset_name}' deleted.")
    
    def on_position_selected(self, position_type: str):
        """
        Handle position type selection.
        
        Args:
            position_type: The selected position type (e.g., 'center', 'top', 'floor_up_1x1')
        """
        if not self.current_brush:
            QtWidgets.QMessageBox.warning(self, "No Object Selected", "Please select an object first.")
            return
        
        # Get the currently selected object from the tileset selector
        selected_obj_id = self.tileset_selector.selected_object_id
        if selected_obj_id is None:
            QtWidgets.QMessageBox.warning(self, "No Object Selected", "Please select an object first.")
            return
        
        # Assign the selected object to this position
        self.current_brush.set_terrain_tile(position_type, selected_obj_id)
        print(f"[QPT] Assigned object {selected_obj_id} to position {position_type}")
        
        # Update the canvas display
        self.tile_picker_canvas.update_canvas_display()
        
        print(f"[QPT] Position selected: {position_type}")
    
    def on_tile_selected_from_canvas(self, obj_id: int, position_type: str):
        """
        Handle object selection from the canvas picker.
        
        Args:
            obj_id: The selected object ID
            position_type: The position type to assign the object to
        """
        if not self.current_brush:
            QtWidgets.QMessageBox.warning(self, "No Brush", "Please select an object first.")
            return
        
        # Assign the object to the position
        if position_type in ['center', 'top', 'bottom', 'left', 'right', 'top_left', 'top_right', 'bottom_left', 'bottom_right', 'inner_top_left', 'inner_top_right', 'inner_bottom_left', 'inner_bottom_right']:
            self.current_brush.set_terrain_tile(position_type, obj_id)
            print(f"[QPT] Assigned object {obj_id} to terrain position {position_type}")
        else:
            # It's a slope type
            self.current_brush.set_slope_tile(position_type, obj_id)
            print(f"[QPT] Assigned object {obj_id} to slope position {position_type}")
        
        # Update the canvas display to show the newly assigned object
        self.tile_picker_canvas.update_canvas_display()
    
    def get_current_brush(self) -> Optional[SmartBrush]:
        """Get the currently selected brush"""
        return self.current_brush
    
    def is_painting(self) -> bool:
        """Check if painting is active"""
        return self.painting_active
    
    def get_current_mode(self) -> str:
        """Get the currently selected painting mode"""
        return self.current_mode
