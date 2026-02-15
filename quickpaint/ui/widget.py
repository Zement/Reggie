"""
Quick Paint Widget - Main UI for the Quick Paint Tool
"""
from typing import Optional, Dict
from PyQt6 import QtWidgets, QtCore, QtGui

from quickpaint.core.brush import SmartBrush
from quickpaint.core.presets import PresetManager
from quickpaint.core.modes import SmartPaintMode, SingleTileMode, ShapeCreator, PaintingDirection


class SavePresetDialog(QtWidgets.QDialog):
    """Dialog for saving a preset with tileset names and priority."""
    
    def __init__(self, parent, default_tileset: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Preset Settings")
        self.setMinimumWidth(350)
        
        layout = QtWidgets.QVBoxLayout(self)
        
        # Tileset names
        layout.addWidget(QtWidgets.QLabel("Tileset names (one per line, supports regex):"))
        self.tileset_edit = QtWidgets.QPlainTextEdit()
        self.tileset_edit.setPlainText(default_tileset)
        self.tileset_edit.setMinimumHeight(80)
        layout.addWidget(self.tileset_edit)
        
        # Priority slider
        priority_layout = QtWidgets.QHBoxLayout()
        priority_layout.addWidget(QtWidgets.QLabel("Priority:"))
        
        self.priority_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.priority_slider.setRange(0, 9)
        self.priority_slider.setValue(5)
        self.priority_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.priority_slider.setTickInterval(1)
        priority_layout.addWidget(self.priority_slider)
        
        self.priority_label = QtWidgets.QLabel("5")
        self.priority_label.setMinimumWidth(20)
        self.priority_slider.valueChanged.connect(lambda v: self.priority_label.setText(str(v)))
        priority_layout.addWidget(self.priority_label)
        
        layout.addLayout(priority_layout)
        
        # Buttons
        button_box = QtWidgets.QDialogButtonBox(
            QtWidgets.QDialogButtonBox.StandardButton.Ok | 
            QtWidgets.QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def get_tileset_names(self) -> list:
        text = self.tileset_edit.toPlainText()
        return [t.strip() for t in text.split('\n') if t.strip()]
    
    def get_priority(self) -> int:
        return self.priority_slider.value()


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
    layer_changed = QtCore.pyqtSignal(int)
    
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
        print("[QPT] OK: QWidget parent initialized")
        
        print("[QPT] Setting preset manager...")
        self.preset_manager = preset_manager or PresetManager()
        print("[QPT] OK: Preset manager set")
        
        print("[QPT] Initializing attributes...")
        self.current_brush: Optional[SmartBrush] = None
        self.painting_active = False
        self.current_mode = "SmartPaint"
        self.tileset_selector = tileset_selector
        print("[QPT] OK: Attributes initialized")
        
        print("[QPT] Calling init_ui...")
        self.init_ui()
        print("[QPT] OK: init_ui completed")
        
        print("[QPT] Loading presets...")
        self.load_presets()
        print("[QPT] OK: QuickPaintWidget initialized")
    
    def init_ui(self):
        """Initialize the UI"""
        print("[QPT] QuickPaintWidget.init_ui starting...")
        
        print("[QPT] Creating layout...")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(5)
        print("[QPT] OK: Layout created")
        
        # ===== PAINTING MODE (moved to top) =====
        print("[QPT] Creating painting mode section...")
        mode_label = QtWidgets.QLabel("Painting Mode:")
        layout.addWidget(mode_label)
        
        mode_layout = QtWidgets.QHBoxLayout()
        self.mode_combo = QtWidgets.QComboBox()
        self.mode_combo.addItems(["SmartPaint (Q)", "Single Tile (S)", "Shape Creator (C)", "Eraser (E)"])
        self.mode_combo.currentTextChanged.connect(self.on_mode_changed)
        mode_layout.addWidget(self.mode_combo)
        layout.addLayout(mode_layout)
        
        # Mode description label
        self.mode_description = QtWidgets.QLabel("")
        self.mode_description.setWordWrap(True)
        self.mode_description.setStyleSheet("color: gray; font-size: 10px;")
        layout.addWidget(self.mode_description)
        self._update_mode_description("SmartPaint (Q)")
        print("[QPT] OK: Painting mode section created")
        
        # ===== LAYER SELECTOR =====
        import globals_ as globals_module
        layer_layout = QtWidgets.QHBoxLayout()
        layer_layout.addWidget(QtWidgets.QLabel(globals_module.trans.string('Palette', 0)))
        
        self.layer_button_group = QtWidgets.QButtonGroup(self)
        self.layer_radio_0 = QtWidgets.QRadioButton("0")
        self.layer_radio_1 = QtWidgets.QRadioButton("1")
        self.layer_radio_2 = QtWidgets.QRadioButton("2")
        self.layer_radio_1.setChecked(True)  # Default to layer 1
        
        self.layer_button_group.addButton(self.layer_radio_0, 0)
        self.layer_button_group.addButton(self.layer_radio_1, 1)
        self.layer_button_group.addButton(self.layer_radio_2, 2)
        self.layer_button_group.idClicked.connect(self.on_layer_changed)
        
        layer_layout.addWidget(self.layer_radio_0)
        layer_layout.addWidget(self.layer_radio_1)
        layer_layout.addWidget(self.layer_radio_2)
        layer_layout.addStretch(1)
        layout.addLayout(layer_layout)
        self.current_layer = 1
        print("[QPT] OK: Layer selector created")
        
        # ===== SMARTPAINT-ONLY WIDGETS CONTAINER =====
        # These widgets are only visible when SmartPaint mode is selected
        self.smartpaint_container = QtWidgets.QWidget()
        smartpaint_layout = QtWidgets.QVBoxLayout(self.smartpaint_container)
        smartpaint_layout.setContentsMargins(0, 0, 0, 0)
        smartpaint_layout.setSpacing(5)
        
        # ===== SLOPE FLAGS =====
        print("[QPT] Creating slope flags section...")
        flags_label = QtWidgets.QLabel("Slope Objects (enable/disable):")
        smartpaint_layout.addWidget(flags_label)
        
        # Create slope flag checkboxes
        self.slope_flags = {}
        # Internal slope names (used as keys) and display labels
        slope_data = [
            ('slope_top_1x1_left', '1x1 Ground L'),
            ('slope_top_1x1_right', '1x1 Ground R'),
            ('slope_top_2x1_left', '2x1 Ground L'),
            ('slope_top_2x1_right', '2x1 Ground R'),
            ('slope_top_4x1_left', '4x1 Ground L'),
            ('slope_top_4x1_right', '4x1 Ground R'),
            ('slope_bottom_1x1_left', '1x1 Ceiling L'),
            ('slope_bottom_1x1_right', '1x1 Ceiling R'),
            ('slope_bottom_2x1_left', '2x1 Ceiling L'),
            ('slope_bottom_2x1_right', '2x1 Ceiling R'),
            ('slope_bottom_4x1_left', '4x1 Ceiling L'),
            ('slope_bottom_4x1_right', '4x1 Ceiling R'),
        ]
        
        # Create flags in a grid layout (4 columns)
        flags_grid = QtWidgets.QGridLayout()
        for idx, (slope_name, label) in enumerate(slope_data):
            checkbox = QtWidgets.QCheckBox(label)
            checkbox.setChecked(True)  # All enabled by default
            checkbox.stateChanged.connect(self.on_slope_flag_changed)
            self.slope_flags[slope_name] = checkbox  # Use internal name as key
            row = idx // 4
            col = idx % 4
            flags_grid.addWidget(checkbox, row, col)
        
        smartpaint_layout.addLayout(flags_grid)
        print("[QPT] OK: Slope flags section created")
        
        # ===== TILE PICKER =====
        print("[QPT] Creating tile picker section...")
        picker_label = QtWidgets.QLabel("Tile Picker (click to assign):")
        smartpaint_layout.addWidget(picker_label)
        
        # Canvas-based tile picker
        print("[QPT] Creating canvas tile picker...")
        from quickpaint.ui.tile_picker_canvas import TilePickerCanvas
        self.tile_picker_canvas = TilePickerCanvas(self.current_brush)
        self.tile_picker_canvas.tile_selected.connect(self.on_tile_selected_from_canvas)
        print("[QPT] OK: Canvas tile picker created")
        smartpaint_layout.addWidget(self.tile_picker_canvas)
        print("[QPT] OK: Tile picker section created")
        
        # Connect tileset selector changes to tile picker updates
        if self.tileset_selector:
            self.tileset_selector.tileset_combo.currentIndexChanged.connect(self.on_tileset_slot_changed)
            print("[QPT] OK: Tileset selector connected")
        
        # ===== PRESET LIST (moved below Tile Picker) =====
        print("[QPT] Creating preset label...")
        preset_label = QtWidgets.QLabel("Presets:")
        smartpaint_layout.addWidget(preset_label)
        print("[QPT] OK: Preset label created")
        
        print("[QPT] Creating preset list...")
        self.preset_list = QtWidgets.QTableWidget()
        print("[QPT] OK: QTableWidget created")
        
        print("[QPT] Configuring preset list...")
        self.preset_list.setColumnCount(2)
        self.preset_list.setHorizontalHeaderLabels(["Name", "Tilesets"])
        self.preset_list.horizontalHeader().setStretchLastSection(True)
        self.preset_list.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        self.preset_list.setSelectionMode(QtWidgets.QAbstractItemView.SelectionMode.SingleSelection)
        self.preset_list.itemSelectionChanged.connect(self.on_preset_selected)
        self.preset_list.cellDoubleClicked.connect(self.on_preset_double_clicked)
        smartpaint_layout.addWidget(self.preset_list)
        print("[QPT] OK: Preset list configured")
        
        # Preset management buttons (right below preset list)
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
        
        smartpaint_layout.addLayout(preset_btn_layout)
        print("[QPT] OK: Preset buttons created")
        
        # Dampening factor slider
        dampening_layout = QtWidgets.QHBoxLayout()
        dampening_layout.addWidget(QtWidgets.QLabel("Dampening:"))
        
        self.dampening_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.dampening_slider.setRange(0, 10)
        self.dampening_slider.setValue(2)  # Default value
        self.dampening_slider.setTickPosition(QtWidgets.QSlider.TickPosition.TicksBelow)
        self.dampening_slider.setTickInterval(1)
        self.dampening_slider.valueChanged.connect(self.on_dampening_changed)
        dampening_layout.addWidget(self.dampening_slider)
        
        self.dampening_label = QtWidgets.QLabel("2")
        self.dampening_label.setMinimumWidth(20)
        dampening_layout.addWidget(self.dampening_label)
        
        smartpaint_layout.addLayout(dampening_layout)
        print("[QPT] OK: Dampening slider created")
        
        # ===== CONTROL BUTTONS =====
        button_layout = QtWidgets.QVBoxLayout()
        
        # Start/Stop Painting
        painting_layout = QtWidgets.QHBoxLayout()
        self.start_painting_btn = QtWidgets.QPushButton("Start Painting (Q)")
        self.start_painting_btn.clicked.connect(self.on_start_painting)
        painting_layout.addWidget(self.start_painting_btn)
        
        self.stop_painting_btn = QtWidgets.QPushButton("Stop Painting (Q)")
        self.stop_painting_btn.clicked.connect(self.on_stop_painting)
        self.stop_painting_btn.setEnabled(False)
        painting_layout.addWidget(self.stop_painting_btn)
        button_layout.addLayout(painting_layout)
        
        smartpaint_layout.addLayout(button_layout)
        
        # Add smartpaint container to main layout
        layout.addWidget(self.smartpaint_container)
        
        # ===== SINGLE TILE PICKER (for Single Tile mode) =====
        self.single_tile_container = QtWidgets.QWidget()
        single_tile_layout = QtWidgets.QVBoxLayout(self.single_tile_container)
        single_tile_layout.setContentsMargins(0, 0, 0, 0)
        single_tile_layout.setSpacing(5)
        
        single_tile_label = QtWidgets.QLabel("Select a tile from the tileset above, then right-click on canvas to paint.")
        single_tile_label.setWordWrap(True)
        single_tile_label.setStyleSheet("color: gray; font-size: 10px;")
        single_tile_layout.addWidget(single_tile_label)
        
        # Selected tile display
        self.selected_tile_label = QtWidgets.QLabel("Selected tile: None")
        single_tile_layout.addWidget(self.selected_tile_label)
        
        single_tile_layout.addStretch()
        layout.addWidget(self.single_tile_container)
        self.single_tile_container.hide()  # Hidden by default
        
        # ===== ERASER INFO (for Eraser mode) =====
        self.eraser_container = QtWidgets.QWidget()
        eraser_layout = QtWidgets.QVBoxLayout(self.eraser_container)
        eraser_layout.setContentsMargins(0, 0, 0, 0)
        eraser_layout.setSpacing(5)
        
        eraser_label = QtWidgets.QLabel("Right-click and drag on canvas to erase tiles.")
        eraser_label.setWordWrap(True)
        eraser_label.setStyleSheet("color: gray; font-size: 10px;")
        eraser_layout.addWidget(eraser_label)
        
        eraser_layout.addStretch()
        layout.addWidget(self.eraser_container)
        self.eraser_container.hide()  # Hidden by default
        
        # ===== SHAPE CREATOR INFO (stub) =====
        self.shape_creator_container = QtWidgets.QWidget()
        shape_layout = QtWidgets.QVBoxLayout(self.shape_creator_container)
        shape_layout.setContentsMargins(0, 0, 0, 0)
        shape_layout.setSpacing(5)
        
        shape_label = QtWidgets.QLabel("Shape Creator - Coming Soon")
        shape_label.setWordWrap(True)
        shape_label.setStyleSheet("color: gray; font-size: 10px;")
        shape_layout.addWidget(shape_label)
        
        shape_layout.addStretch()
        layout.addWidget(self.shape_creator_container)
        self.shape_creator_container.hide()  # Hidden by default
        
        layout.addStretch()
    
    def load_presets(self):
        """Load presets from preset manager, filtered by current slot and tileset"""
        self.preset_list.setRowCount(0)
        
        # Get current slot and tileset name for filtering
        current_slot = f"Pa{self.tile_picker_canvas.tileset_idx}"
        current_tileset_name = self._get_current_tileset_name()
        
        # Get all presets
        presets = self.preset_manager.get_all_presets()
        
        # Filter presets that match current slot and tileset
        matching_presets = []
        for preset_name, preset in presets.items():
            if preset and preset.slot == current_slot:
                # Check if tileset name matches (using regex)
                if current_tileset_name and preset.matches_tileset(current_tileset_name):
                    matching_presets.append(preset)
                elif not current_tileset_name:
                    # No tileset loaded, show all presets for this slot
                    matching_presets.append(preset)
        
        # Sort by priority (user presets first, then non-regex, then regex)
        matching_presets = self._sort_presets_by_priority(matching_presets)
        
        for i, preset in enumerate(matching_presets):
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
    
    def _get_current_tileset_name(self) -> str:
        """Get the current tileset name from Reggie's globals"""
        try:
            import globals_
            tileset_idx = self.tile_picker_canvas.tileset_idx
            if globals_.Area and hasattr(globals_.Area, 'tileset' + str(tileset_idx)):
                return getattr(globals_.Area, 'tileset' + str(tileset_idx), '')
        except Exception:
            pass
        return ''
    
    def _sort_presets_by_priority(self, presets: list) -> list:
        """
        Sort presets by priority (0-9, higher = first).
        """
        # Sort by priority descending (9 first, 0 last)
        return sorted(presets, key=lambda p: p.priority, reverse=True)
    
    def on_preset_selected(self):
        """Handle preset selection (single click) - just highlight, don't load"""
        selected_rows = self.preset_list.selectedIndexes()
        if selected_rows:
            row = selected_rows[0].row()
            preset_name = self.preset_list.item(row, 0).text()
            
            # Enable delete button only for custom presets
            builtin_presets = self.preset_manager.load_builtin_presets()
            is_builtin = preset_name in builtin_presets
            self.delete_preset_btn.setEnabled(not is_builtin)
    
    def on_preset_double_clicked(self, row: int, col: int):
        """Handle preset double-click - load the preset into UI"""
        preset_name = self.preset_list.item(row, 0).text()
        preset = self.preset_manager.get_preset(preset_name)
        if preset:
            self.load_preset_into_ui(preset)
    
    def load_preset_into_ui(self, preset: SmartBrush, preserve_mode: bool = False):
        """
        Load a preset into the UI, updating all parameters.
        
        Order of operations:
        1. Change tileset slot (this clears the Tile Picker Grid)
        2. Change painting mode (unless preserve_mode is True)
        3. Update slope flags
        4. Update terrain and slopes in the Tile Picker Grid (delayed for tileset sync)
        
        Args:
            preset: SmartBrush preset to load
            preserve_mode: If True, keep the current painting mode instead of switching
                          to the preset's mode. Used during auto-load on tileset change.
        """
        print(f"[QPT] Loading preset '{preset.name}' into UI... (preserve_mode={preserve_mode})")
        
        # Create a copy of the preset to avoid modifying the original in the preset manager
        preset_copy = preset.copy()
        
        # 1. Change tileset slot (this triggers on_tileset_slot_changed which clears the grid)
        slot_index = {"Pa0": 0, "Pa1": 1, "Pa2": 2, "Pa3": 3}.get(preset_copy.slot, 0)
        if self.tileset_selector:
            # Block signals to prevent double-clearing
            self.tileset_selector.tileset_combo.blockSignals(True)
            self.tileset_selector.tileset_combo.setCurrentIndex(slot_index)
            self.tileset_selector.tileset_combo.blockSignals(False)
            # Manually update the tileset
            self.tile_picker_canvas.tileset_idx = slot_index
        print(f"[QPT]   Slot set to {preset_copy.slot}")
        
        # 2. Change painting mode (skip if preserving current mode during auto-load)
        if not preserve_mode:
            mode_index = {"SmartPaint": 0, "SingleTile": 1, "ShapeCreator": 2}.get(preset_copy.painting_mode, 0)
            self.mode_combo.setCurrentIndex(mode_index)
            self.current_mode = preset_copy.painting_mode
            print(f"[QPT]   Painting mode set to {preset_copy.painting_mode}")
        else:
            print(f"[QPT]   Painting mode preserved as {self.current_mode}")
        
        # 3. Set the brush (using the copy, not the original)
        self.current_brush = preset_copy
        self.tile_picker_canvas.set_brush(preset_copy)
        
        # 4. Update slope flags (sync checkboxes with preset's enabled_slopes)
        self.sync_slope_checkboxes_with_brush()
        print(f"[QPT]   Slope flags synced ({len(preset_copy.enabled_slopes)} enabled)")
        
        # 5. Delay canvas redraw to ensure tileset objects are ready
        # This handles cases where the slot was just changed
        QtCore.QTimer.singleShot(50, lambda: self._finish_preset_load(preset_copy))
    
    def _finish_preset_load(self, preset: SmartBrush):
        """Complete preset loading after tileset is ready"""
        # Force a full redraw: first draw empty grid, then update with assigned tiles
        self.tile_picker_canvas.draw_empty_grid()
        self.tile_picker_canvas.update_canvas_display()
        self.tile_picker_canvas.update_status_indicator()
        
        # Emit signals
        self.preset_changed.emit(preset)
        
        print(f"[QPT] OK: Preset '{preset.name}' loaded successfully")
    
    def on_mode_changed(self, mode: str):
        """Handle painting mode change"""
        # Extract base mode name (remove hotkey suffix)
        base_mode = mode.split(" (")[0]
        self.current_mode = base_mode
        self._update_mode_description(mode)
        self._update_mode_visibility(base_mode)
        self.mode_changed.emit(base_mode)
    
    def on_layer_changed(self, layer_id: int):
        """Handle layer selection change from radio buttons"""
        if self.current_layer == layer_id:
            return
        self.current_layer = layer_id
        print(f"[QPT] Layer changed to {layer_id}")
        
        # Sync globals_.CurrentLayer and Objects palette radio buttons
        import globals_
        globals_.CurrentLayer = layer_id
        if hasattr(globals_, 'mainWindow') and globals_.mainWindow:
            mw = globals_.mainWindow
            if hasattr(mw, 'LayerButtonGroup'):
                btn = mw.LayerButtonGroup.button(layer_id)
                if btn and not btn.isChecked():
                    btn.setChecked(True)
        
        # Update the painting engine's layer
        try:
            if hasattr(globals_, 'qpt_functions') and globals_.qpt_functions:
                get_hook = globals_.qpt_functions.get('get_hook')
                if get_hook:
                    hook = get_hook()
                    if hook and hook.palette:
                        tab = hook.palette.get_quick_paint_tab()
                        if tab and hasattr(tab, 'mouse_handler'):
                            tab.mouse_handler.engine.set_layer(layer_id)
                        # Sync Fill Paint tab
                        fill_tab = hook.palette.get_fill_paint_tab()
                        if fill_tab:
                            fill_tab.set_layer_silent(layer_id)
        except Exception as e:
            print(f"[QPT] Could not set engine layer: {e}")
        
        # Emit signal for other consumers
        self.layer_changed.emit(layer_id)
    
    def set_layer_silent(self, layer_id: int):
        """Set the layer without triggering sync (called from external sync)"""
        self.current_layer = layer_id
        self.layer_button_group.blockSignals(True)
        btn = self.layer_button_group.button(layer_id)
        if btn and not btn.isChecked():
            btn.setChecked(True)
        self.layer_button_group.blockSignals(False)
        
        # Also update the engine
        try:
            import globals_
            if hasattr(globals_, 'qpt_functions') and globals_.qpt_functions:
                get_hook = globals_.qpt_functions.get('get_hook')
                if get_hook:
                    hook = get_hook()
                    if hook and hook.palette:
                        tab = hook.palette.get_quick_paint_tab()
                        if tab and hasattr(tab, 'mouse_handler'):
                            tab.mouse_handler.engine.set_layer(layer_id)
        except Exception:
            pass
    
    def get_current_layer(self) -> int:
        """Get the currently selected layer"""
        return self.current_layer
    
    def _update_mode_visibility(self, mode: str):
        """Show/hide containers based on selected mode"""
        # Hide all mode-specific containers first
        self.smartpaint_container.hide()
        self.single_tile_container.hide()
        self.eraser_container.hide()
        self.shape_creator_container.hide()
        
        # Show the appropriate container
        if mode == "SmartPaint":
            self.smartpaint_container.show()
        elif mode == "Single Tile":
            self.single_tile_container.show()
        elif mode == "Eraser":
            self.eraser_container.show()
        elif mode == "Shape Creator":
            self.shape_creator_container.show()
    
    def on_dampening_changed(self, value: int):
        """Handle dampening factor change"""
        self.dampening_label.setText(str(value))
        # Update the painting engine's dampening factor
        # The engine is accessed via: hook.palette.quick_paint_tab.mouse_handler.engine
        try:
            import globals_
            if hasattr(globals_, 'qpt_functions') and globals_.qpt_functions:
                get_hook = globals_.qpt_functions.get('get_hook')
                if get_hook:
                    hook = get_hook()
                    if hook and hook.palette:
                        tab = hook.palette.get_quick_paint_tab()
                        if tab and hasattr(tab, 'mouse_handler'):
                            tab.mouse_handler.engine.dampening_factor = value
                            print(f"[QPT] Dampening factor set to {value}")
        except Exception as e:
            print(f"[QPT] Could not set dampening factor: {e}")
    
    def _update_mode_description(self, mode: str):
        """Update the mode description label based on selected mode"""
        descriptions = {
            "SmartPaint (Q)": "Direction-aware auto-tiling. First stroke direction determines wall type.",
            "Single Tile (S)": "Paint with a single tile. Select from tileset above.",
            "Shape Creator (C)": "Coming soon. Will create rectangles/ellipses.",
            "Eraser (E)": "Right-click and drag to erase tiles from the canvas.",
        }
        self.mode_description.setText(descriptions.get(mode, ""))
    
    def on_slope_flag_changed(self):
        """Handle slope flag changes"""
        if not self.current_brush:
            return
        
        # Get enabled slope flags
        enabled_slopes = set(name for name, checkbox in self.slope_flags.items() if checkbox.isChecked())
        
        # Find slopes that were disabled (unchecked)
        disabled_slopes = self.current_brush.enabled_slopes - enabled_slopes
        
        # Clear assignments for disabled slopes
        for slope_name in disabled_slopes:
            if slope_name in self.current_brush.slopes_assigned:
                self.current_brush.slopes_assigned.discard(slope_name)
                self.current_brush.slopes[slope_name] = 0
                print(f"[QPT] Cleared assignment for disabled slope: {slope_name}")
        
        # Store enabled slopes in brush
        self.current_brush.enabled_slopes = enabled_slopes
        
        print(f"[QPT] Slope flags changed: {len(enabled_slopes)} slopes enabled")
        
        # Update status indicator to reflect new slope requirements
        self.tile_picker_canvas.update_status_indicator()
        
        # Redraw tile picker to show/hide slopes based on flags
        # Use update_canvas_display to preserve assigned tiles visibility
        self.tile_picker_canvas.update_canvas_display()
    
    def sync_slope_checkboxes_with_brush(self):
        """Sync slope checkboxes with the current brush's enabled_slopes"""
        if not self.current_brush:
            return
        
        # Block signals to prevent triggering on_slope_flag_changed during sync
        for slope_name, checkbox in self.slope_flags.items():
            checkbox.blockSignals(True)
            checkbox.setChecked(slope_name in self.current_brush.enabled_slopes)
            checkbox.blockSignals(False)
        
        # Update status indicator after sync
        self.tile_picker_canvas.update_status_indicator()
    
    def on_start_painting(self):
        """Handle start painting button"""
        print(f"[QPT] on_start_painting called, current_brush={self.current_brush is not None}")
        
        if not self.current_brush:
            QtWidgets.QMessageBox.warning(self, "No Preset", "Please select a preset first.")
            return
        
        self.painting_active = True
        self.start_painting_btn.setEnabled(False)
        self.stop_painting_btn.setEnabled(True)
        print(f"[QPT] OK: Painting started, painting_active={self.painting_active}")
        
        # Set alternate select cursor on main canvas when painting
        import globals_
        if hasattr(globals_, 'mainWindow') and globals_.mainWindow and globals_.mainWindow.view:
            from PyQt6.QtCore import Qt
            globals_.mainWindow.view.setCursor(Qt.CursorShape.CrossCursor)
        
        self.painting_started.emit()
    
    def on_stop_painting(self):
        """Handle stop painting button"""
        self.painting_active = False
        self.start_painting_btn.setEnabled(True)
        self.stop_painting_btn.setEnabled(False)
        
        # Reset cursor on main canvas when painting stops
        import globals_
        if hasattr(globals_, 'mainWindow') and globals_.mainWindow and globals_.mainWindow.view:
            from PyQt6.QtCore import Qt
            globals_.mainWindow.view.setCursor(Qt.CursorShape.ArrowCursor)
        
        self.painting_stopped.emit()
    
    def on_save_preset(self):
        """Handle save preset button"""
        # Get current tileset name to pre-fill dialogs
        current_tileset = self._get_current_tileset_name()
        
        # Get preset name (pre-filled with current tileset)
        name, ok = QtWidgets.QInputDialog.getText(
            self, "Save Preset", "Preset name:",
            QtWidgets.QLineEdit.EchoMode.Normal,
            current_tileset
        )
        if not ok or not name:
            return
        
        # Show custom dialog for tileset names and priority
        dialog = SavePresetDialog(self, current_tileset)
        if dialog.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return
        
        tilesets = dialog.get_tileset_names()
        priority = dialog.get_priority()
        
        if not tilesets:
            QtWidgets.QMessageBox.warning(self, "No Tilesets", "Please enter at least one tileset name.")
            return
        
        # Create and save preset
        if self.current_brush:
            self.current_brush.name = name
            self.current_brush.tileset_names = tilesets
            self.current_brush.priority = priority
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
                    self.tile_picker_canvas.set_brush(preset)
                    self.tile_picker_canvas.update_canvas_display()
                    self.sync_slope_checkboxes_with_brush()
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
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No
        )
        
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
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
    
    def on_tile_selected_from_canvas(self, tile_id_or_position: int | str, position_type: str = None):
        """
        Handle tile position selection from the canvas picker.
        Assigns the currently selected object to the clicked position.
        
        Args:
            tile_id_or_position: Either tile ID (from signal) or position_type (from direct call)
            position_type: The position type to assign the object to (when called via signal)
        """
        # Handle both signal connection (int, str) and direct call (str)
        if position_type is None:
            # Direct call with just position_type
            position_type = tile_id_or_position
        if not self.current_brush:
            QtWidgets.QMessageBox.warning(self, "No Brush", "Please select a brush first.")
            return
        
        # Get the currently selected object from the tileset selector
        selected_obj_id = self.tileset_selector.selected_object_id
        if selected_obj_id is None:
            QtWidgets.QMessageBox.warning(self, "No Object Selected", "Please select an object first.")
            return
        
        # Assign the object to the position
        if position_type in ['center', 'top', 'bottom', 'left', 'right', 'top_left', 'top_right', 'bottom_left', 'bottom_right', 'inner_top_left', 'inner_top_right', 'inner_bottom_left', 'inner_bottom_right']:
            self.current_brush.set_terrain_tile(position_type, selected_obj_id)
            print(f"[QPT] Assigned object {selected_obj_id} to terrain position {position_type}")
        else:
            # It's a slope type
            self.current_brush.set_slope_tile(position_type, selected_obj_id)
            print(f"[QPT] Assigned object {selected_obj_id} to slope position {position_type}")
        
        # Update the canvas display to show the newly assigned object
        self.tile_picker_canvas.update_canvas_display()
        # Update status indicator (for both terrain and slopes)
        self.tile_picker_canvas.update_status_indicator()
    
    def on_tileset_slot_changed(self, tileset_idx: int):
        """
        Handle tileset slot changes (Pa0, Pa1, etc.).
        Clear the tile picker when switching tileset slots and try to auto-load a matching preset.
        
        Args:
            tileset_idx: The new tileset index (0-3 for Pa0-Pa3)
        """
        print(f"[QPT] Tileset slot changed to Pa{tileset_idx}")
        
        # Update the tile picker canvas tileset
        self.tile_picker_canvas.tileset_idx = tileset_idx
        
        # Reload the preset list (filtered by new slot and tileset)
        self.load_presets()
        
        # Create a fresh empty brush for this slot (don't modify existing presets)
        # This replaces the old clear_all_tiles() which was modifying preset objects
        # Preserve the current painting mode when switching tilesets
        self.current_brush = SmartBrush(f"Pa{tileset_idx}_custom", [], f"Pa{tileset_idx}", self.current_mode)
        
        # Reset Single Tile selected object (tileset objects changed)
        self.selected_tile_label.setText("Selected tile: None")
        if self.tileset_selector:
            self.tileset_selector.selected_object_id = None
        self.tile_picker_canvas.set_brush(self.current_brush)
        self.tile_picker_canvas.draw_empty_grid()
        self.tile_picker_canvas.update_status_indicator()
        
        # Delay preset loading to ensure TilesetSelector has updated its object list first
        # This is needed because both handlers are connected to the same signal
        QtCore.QTimer.singleShot(50, lambda: self._delayed_preset_load(tileset_idx))
        
        print(f"[QPT] OK: Tileset slot changed to Pa{tileset_idx}")
    
    def _delayed_preset_load(self, tileset_idx: int):
        """Load preset after tileset selector has updated its objects"""
        print(f"[QPT] Delayed preset load for Pa{tileset_idx}")
        self.try_auto_load_preset(tileset_idx)
    
    def try_auto_load_preset(self, tileset_idx: int):
        """
        Try to auto-load a preset that matches the currently loaded tileset.
        
        Args:
            tileset_idx: The tileset index (0-3 for Pa0-Pa3)
        """
        # Get the actual tileset name from Reggie's globals
        try:
            import globals_
            if globals_.Area and hasattr(globals_.Area, 'tileset' + str(tileset_idx)):
                tileset_name = getattr(globals_.Area, 'tileset' + str(tileset_idx), '')
                if tileset_name:
                    print(f"[QPT] Looking for preset matching tileset: {tileset_name}")
                    matching_preset = self.find_matching_preset(tileset_name)
                    if matching_preset:
                        print(f"[QPT] Auto-loading preset: {matching_preset.name}")
                        self.load_preset_into_ui(matching_preset, preserve_mode=True)
                        return
        except Exception as e:
            print(f"[QPT] Error getting tileset name: {e}")
        
        print(f"[QPT] No matching preset found for tileset slot Pa{tileset_idx}")
    
    def find_matching_preset(self, tileset_name: str) -> Optional[SmartBrush]:
        """
        Find the highest priority preset that matches the given tileset name.
        
        Priority (highest to lowest):
        1. User preset without regex
        2. User preset with regex
        3. Builtin preset without regex
        4. Builtin preset with regex
        
        Args:
            tileset_name: The tileset name to match (e.g., "Pa1_nohara")
        
        Returns:
            Highest priority matching SmartBrush preset, or None if no match found
        """
        current_slot = f"Pa{self.tile_picker_canvas.tileset_idx}"
        presets = self.preset_manager.get_all_presets()
        
        # Find all matching presets
        matching = []
        for preset_name, preset in presets.items():
            if preset and preset.slot == current_slot and preset.matches_tileset(tileset_name):
                matching.append(preset)
        
        if not matching:
            return None
        
        # Sort by priority and return the highest
        sorted_presets = self._sort_presets_by_priority(matching)
        return sorted_presets[0] if sorted_presets else None
    
    def initialize_with_current_tileset(self):
        """
        Initialize the QPT with the current tileset.
        Called when the QPT is first opened to try auto-loading a preset.
        """
        if self.tileset_selector:
            tileset_idx = self.tileset_selector.tileset_combo.currentIndex()
            self.tile_picker_canvas.tileset_idx = tileset_idx
            # Reload preset list filtered by current slot/tileset
            self.load_presets()
            # Try to auto-load a matching preset
            self.try_auto_load_preset(tileset_idx)
    
    def on_game_patch_changed(self):
        """
        Handle game patch or tileset changes.
        Clear the tile picker and update the brush.
        """
        print("[QPT] Game patch or tileset changed")
        
        # Clear the tile picker
        if self.current_brush:
            self.tile_picker_canvas.clear_all_tiles()
        
        print("[QPT] OK: Tile picker cleared due to patch/tileset change")
    
    def reset_to_default(self):
        """
        Reset QPT to default state. Called when level/area changes or area settings are modified.
        - Resets tileset slot to Pa0
        - Clears the tile picker
        - Reloads presets for the new context
        """
        print("[QPT] Resetting to default state...")
        
        # Stop painting if active
        if self.painting_active:
            self.on_stop_painting()
        
        # Reset tileset slot to Pa0
        if self.tileset_selector:
            self.tileset_selector.tileset_combo.blockSignals(True)
            self.tileset_selector.tileset_combo.setCurrentIndex(0)
            self.tileset_selector.tileset_combo.blockSignals(False)
            # Refresh the tileset selector's object list
            self.tileset_selector.on_tileset_changed(0)
        
        # Reset canvas tileset index
        self.tile_picker_canvas.tileset_idx = 0
        
        # Create a fresh empty brush (preserve current painting mode)
        self.current_brush = SmartBrush("Pa0_custom", [], "Pa0", self.current_mode)
        self.tile_picker_canvas.set_brush(self.current_brush)
        self.tile_picker_canvas.draw_empty_grid()
        self.tile_picker_canvas.update_status_indicator()
        
        # Reset Single Tile selected object (tileset objects changed)
        self.selected_tile_label.setText("Selected tile: None")
        if self.tileset_selector:
            self.tileset_selector.selected_object_id = None
        
        # Reset layer to 1
        self.current_layer = 1
        self.layer_radio_1.setChecked(True)
        
        # Reload presets for the new context
        self.load_presets()
        
        # Try to auto-load a matching preset after a delay
        QtCore.QTimer.singleShot(100, lambda: self.try_auto_load_preset(0))
        
        print("[QPT] OK: Reset to default state complete")
    
    def get_current_brush(self) -> Optional[SmartBrush]:
        """Get the currently selected brush"""
        return self.current_brush
    
    def is_painting(self) -> bool:
        """Check if painting is active"""
        return self.painting_active
    
    def get_current_mode(self) -> str:
        """Get the currently selected painting mode"""
        return self.current_mode
    
    def set_mode(self, mode: str):
        """
        Set the painting mode programmatically (for hotkey activation).
        
        Args:
            mode: Mode name ("SmartPaint", "Single Tile", "Shape Creator", "Eraser")
        """
        mode_map = {
            "SmartPaint": 0,
            "Single Tile": 1,
            "Shape Creator": 2,
            "Eraser": 3
        }
        if mode in mode_map:
            self.mode_combo.setCurrentIndex(mode_map[mode])
    
    def set_selected_tile(self, tile_id: int):
        """Set the selected tile for Single Tile mode"""
        self.selected_tile_id = tile_id
        self.selected_tile_label.setText(f"Selected tile: {tile_id}")
    
    def get_selected_tile(self) -> int:
        """Get the selected tile ID for Single Tile mode"""
        return getattr(self, 'selected_tile_id', None)
