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
        self.qpt_widget.mode_changed.connect(self.on_mode_changed)
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
        layer = self.qpt_widget.get_current_layer()
        
        print(f"[QPT] on_painting_started: brush={brush is not None}, mode={mode}, layer={layer}")
        
        if brush:
            self.mouse_handler.set_brush(brush)
            self.mouse_handler.set_mode(mode)
            self.mouse_handler.set_layer(layer)
            print(f"[QPT] OK: Brush, mode, and layer set for painting")
        else:
            print("[QPT] WARNING: No brush available for painting!")
    
    def on_painting_stopped(self):
        """Handle painting stop"""
        self.mouse_handler.cancel_painting()
    
    def on_mode_changed(self, mode: str):
        """Handle painting mode change from the widget combobox"""
        from quickpaint.core.tool_manager import get_tool_manager, ToolType
        
        tool_manager = get_tool_manager()
        mode_to_tool = {
            "SmartPaint": ToolType.QPT_SMART_PAINT,
            "Single Tile": ToolType.QPT_SINGLE_TILE,
            "Shape Creator": ToolType.QPT_SHAPE_CREATOR,
            "Eraser": ToolType.QPT_ERASER
        }
        
        if mode in mode_to_tool:
            tool_manager.activate_tool(mode_to_tool[mode])
            print(f"[QPT] Mode changed to {mode}, tool activated: {mode_to_tool[mode].name}")
    
    def on_object_selected(self, tileset: int, obj_type: int, obj_id: int):
        """
        Handle object selection from tileset.
        
        Args:
            tileset: Tileset index
            obj_type: Object type
            obj_id: Object ID
        """
        print(f"[QPT] on_object_selected called: tileset={tileset}, obj_type={obj_type}, obj_id={obj_id}")
        
        # Update selected tile for Single Tile mode
        self.qpt_widget.set_selected_tile(obj_id)
        
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
                # Apply cross-stroke merge deletions FIRST (before creating new objects)
                # This prevents splitting of newly created merged objects
                engine = self.mouse_handler.engine
                merge_deletes = engine.get_pending_merge_deletes()
                for x, y, layer in merge_deletes:
                    self._delete_tile_at(x, y, layer)
                
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
                
                # Capture tile types NOW before session resets (session resets on next paint start)
                try:
                    engine = self.mouse_handler.engine
                    tile_types_snapshot = dict(engine.session.outline_tile_types) if engine.session else {}
                    print(f"[QPT] Auto-fill: Captured {len(tile_types_snapshot)} tile types, scheduling check...")
                    
                    # Schedule auto-fill check after terrain is fully placed (250ms)
                    QTimer.singleShot(250, lambda: self._try_auto_fill_closed_polygon(placements, tile_types_snapshot))
                except Exception as e2:
                    print(f"[QPT] Auto-fill snapshot error: {e2}")
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
    
    def _try_auto_fill_closed_polygon(self, placements, tile_types_snapshot):
        """
        Check if the newly painted terrain forms a closed polygon and auto-fill it.
        
        Only fills if the Fill Tool has a fill object set.
        Uses flood-fill from candidate interior points (tiles adjacent to terrain
        on the "inside" direction) to detect enclosed areas.
        
        Args:
            placements: List of ObjectPlacement objects from the paint operation
            tile_types_snapshot: Dict of (x,y) -> tile_type captured at paint time
        """
        try:
            import globals_
            from collections import deque
            from dirty import SetDirty
            
            if not globals_.Area or not globals_.mainWindow:
                return
            
            # Get the fill object from the FillPaintTab (via parent palette)
            palette = self.parent()
            while palette and not hasattr(palette, 'fill_paint_tab'):
                palette = palette.parent()
            
            if not palette or not hasattr(palette, 'fill_paint_tab'):
                return
            
            fill_tab = palette.fill_paint_tab
            fill_object_id = fill_tab._fill_object_id
            fill_tileset = fill_tab._tileset_idx
            
            if fill_object_id is None:
                return  # No fill object set
            
            # Get the layer from the Fill Paint tab's layer selector
            layer = fill_tab.get_current_layer()
            
            # Build set of all occupied positions on this layer
            # Use RenderObject to detect empty tiles in slope objects
            from tiles import RenderObject
            occupied = set()
            layer_obj = globals_.Area.layers[layer]
            for obj in layer_obj:
                tile_array = RenderObject(obj.tileset, obj.type, obj.width, obj.height)
                for dy in range(obj.height):
                    for dx in range(obj.width):
                        # Check if this tile is actually filled (not -1)
                        tile_value = tile_array[dy][dx] if dy < len(tile_array) and dx < len(tile_array[dy]) else -1
                        if tile_value != -1:
                            occupied.add((obj.objx + dx, obj.objy + dy))
            
            # Get zone bounds for the painted area
            if not placements:
                return
            
            # Find a representative position from the placements that's inside a zone
            # Try all placement positions to find one inside a zone (important for top/left edge polygons)
            fill_engine = fill_tab.fill_engine
            zone_bounds = None
            rep_x, rep_y = placements[0].x, placements[0].y
            
            if fill_engine._get_zone_bounds:
                for placement in placements:
                    for pdy in range(placement.height):
                        for pdx in range(placement.width):
                            test_x, test_y = placement.x + pdx, placement.y + pdy
                            bounds = fill_engine._get_zone_bounds(test_x, test_y)
                            if bounds is not None:
                                zone_bounds = bounds
                                rep_x, rep_y = test_x, test_y
                                break
                        if zone_bounds:
                            break
                    if zone_bounds:
                        break
            
            # If no zone bounds, use a large area centered on the placement
            if zone_bounds is None:
                # Use a large bounding area for outside-zone auto-fill
                zone_x = rep_x - 100
                zone_y = rep_y - 100
                zone_w = 200
                zone_h = 200
                has_zone = False
            else:
                zone_x, zone_y, zone_w, zone_h = zone_bounds
                has_zone = True
            
            zone_max_x = zone_x + zone_w
            zone_max_y = zone_y + zone_h
            
            # Collect candidate interior points from the newly placed terrain
            # For each placement, check the "inside" direction based on tile type
            inside_offsets = {
                'top': (0, 1),       # Inside is below
                'bottom': (0, -1),   # Inside is above
                'left': (1, 0),      # Inside is to the right
                'right': (-1, 0),    # Inside is to the left
                'top_left': (1, 1),
                'top_right': (-1, 1),
                'bottom_left': (1, -1),
                'bottom_right': (-1, -1),
                'inner_top_left': (-1, -1),
                'inner_top_right': (1, -1),
                'inner_bottom_left': (-1, 1),
                'inner_bottom_right': (1, 1),
            }
            
            # Get tile types from the snapshot (captured before session reset)
            # For merged placements (width>1 or height>1), check all covered positions
            candidates = set()
            
            print(f"[QPT] Auto-fill: {len(placements)} placements, {len(tile_types_snapshot)} tile types, zone=({zone_x},{zone_y})-({zone_max_x},{zone_max_y})")
            
            for placement in placements:
                for pdy in range(placement.height):
                    for pdx in range(placement.width):
                        px, py = placement.x + pdx, placement.y + pdy
                        pos = (px, py)
                        tile_type = tile_types_snapshot.get(pos)
                        if tile_type and tile_type in inside_offsets:
                            dx, dy = inside_offsets[tile_type]
                            interior_x = px + dx
                            interior_y = py + dy
                            if (interior_x, interior_y) not in occupied:
                                if zone_x <= interior_x < zone_max_x and zone_y <= interior_y < zone_max_y:
                                    candidates.add((interior_x, interior_y))
            
            if not candidates:
                print(f"[QPT] Auto-fill: No interior candidates found")
                return
            
            print(f"[QPT] Auto-fill: {len(candidates)} interior candidates")
            
            # Try flood-fill from each candidate to find enclosed areas
            # An area is "enclosed" if bounded by terrain OR zone edges
            MAX_AUTO_FILL = 5000  # Safety limit
            
            already_filled = set()
            
            for start_x, start_y in candidates:
                if (start_x, start_y) in already_filled:
                    continue
                if (start_x, start_y) in occupied:
                    continue
                
                # BFS flood fill - zone edges act as boundaries (not as "unbounded")
                # But ONLY if terrain also touches those zone edges (closing the polygon)
                filled = set()
                queue = deque([(start_x, start_y)])
                visited = {(start_x, start_y)}
                # Track which specific zone edges the fill touches
                fill_touches_left = False
                fill_touches_right = False
                fill_touches_top = False
                fill_touches_bottom = False
                too_large = False
                
                while queue:
                    if len(filled) > MAX_AUTO_FILL:
                        too_large = True  # Too large, abort
                        break
                    
                    cx, cy = queue.popleft()
                    
                    # Check if outside zone bounds - track which edge and treat as boundary
                    if cx < zone_x:
                        fill_touches_left = True
                        continue
                    if cx >= zone_max_x:
                        fill_touches_right = True
                        continue
                    if cy < zone_y:
                        fill_touches_top = True
                        continue
                    if cy >= zone_max_y:
                        fill_touches_bottom = True
                        continue
                    
                    # Check if occupied (this is the terrain boundary)
                    if (cx, cy) in occupied:
                        continue
                    
                    filled.add((cx, cy))
                    
                    # Check 4-connected neighbors
                    for ndx, ndy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        nx, ny = cx + ndx, cy + ndy
                        if (nx, ny) not in visited:
                            visited.add((nx, ny))
                            queue.append((nx, ny))
                
                if too_large or not filled:
                    print(f"[QPT] Auto-fill: Candidate ({start_x},{start_y}) not enclosed (too_large={too_large}, filled={len(filled)})")
                    continue  # Not enclosed or too large, skip
                
                touches_zone_edge = fill_touches_left or fill_touches_right or fill_touches_top or fill_touches_bottom
                
                # CRITICAL: If fill touches zone edges, verify terrain also touches those edges
                # This ensures open polygons only fill if zone edge "closes" them
                if touches_zone_edge and has_zone:
                    # Check if terrain touches the same zone edges that the fill touched
                    terrain_touches_left = any(x == zone_x for x, y in occupied)
                    terrain_touches_right = any(x == zone_max_x - 1 for x, y in occupied)
                    terrain_touches_top = any(y == zone_y for x, y in occupied)
                    terrain_touches_bottom = any(y == zone_max_y - 1 for x, y in occupied)
                    
                    # For each zone edge the fill touched, terrain must also touch it
                    # This ensures the polygon is "closed" by terrain connecting to zone edge
                    invalid_fill = False
                    if fill_touches_left and not terrain_touches_left:
                        invalid_fill = True
                    if fill_touches_right and not terrain_touches_right:
                        invalid_fill = True
                    if fill_touches_top and not terrain_touches_top:
                        invalid_fill = True
                    if fill_touches_bottom and not terrain_touches_bottom:
                        invalid_fill = True
                    
                    if invalid_fill:
                        print(f"[QPT] Auto-fill: Candidate ({start_x},{start_y}) rejected - fill touches zone edge but terrain doesn't connect to it")
                        print(f"[QPT]   Fill touches: L={fill_touches_left}, R={fill_touches_right}, T={fill_touches_top}, B={fill_touches_bottom}")
                        print(f"[QPT]   Terrain touches: L={terrain_touches_left}, R={terrain_touches_right}, T={terrain_touches_top}, B={terrain_touches_bottom}")
                        continue
                
                print(f"[QPT] Auto-fill: Found enclosed area with {len(filled)} tiles (zone_edge={touches_zone_edge})")
                
                # Apply overpaint if the fill touches the zone edge (and we have a zone)
                if touches_zone_edge and has_zone:
                    filled = fill_engine._add_overpaint(filled, zone_x, zone_y, zone_w, zone_h)
                    print(f"[QPT] Auto-fill: Applied overpaint, now {len(filled)} tiles")
                
                # This is an enclosed area! Auto-fill it with vertical slice merging
                already_filled.update(filled)
                
                # Step 1: Group positions by column for vertical slice merging
                columns = {}
                for fx, fy in filled:
                    if fx not in columns:
                        columns[fx] = []
                    columns[fx].append(fy)
                
                # Step 2: Create vertical slices (1-wide columns)
                vertical_slices = []
                for col_x, y_values in columns.items():
                    y_values.sort()
                    if not y_values:
                        continue
                    
                    run_start = y_values[0]
                    run_end = y_values[0]
                    
                    for i in range(1, len(y_values)):
                        if y_values[i] == run_end + 1:
                            run_end = y_values[i]
                        else:
                            vertical_slices.append({
                                'x': col_x, 'y': run_start,
                                'height': run_end - run_start + 1
                            })
                            run_start = y_values[i]
                            run_end = y_values[i]
                    
                    vertical_slices.append({
                        'x': col_x, 'y': run_start,
                        'height': run_end - run_start + 1
                    })
                
                # Step 3: Merge horizontally adjacent slices with same y and height
                slice_groups = {}
                for s in vertical_slices:
                    key = (s['y'], s['height'])
                    if key not in slice_groups:
                        slice_groups[key] = []
                    slice_groups[key].append(s)
                
                placements = []
                for (y, height), slices in slice_groups.items():
                    slices.sort(key=lambda s: s['x'])
                    run_start_x = slices[0]['x']
                    run_end_x = slices[0]['x']
                    
                    for i in range(1, len(slices)):
                        if slices[i]['x'] == run_end_x + 1:
                            run_end_x = slices[i]['x']
                        else:
                            placements.append({
                                'x': run_start_x, 'y': y,
                                'width': run_end_x - run_start_x + 1, 'height': height
                            })
                            run_start_x = slices[i]['x']
                            run_end_x = slices[i]['x']
                    
                    placements.append({
                        'x': run_start_x, 'y': y,
                        'width': run_end_x - run_start_x + 1, 'height': height
                    })
                
                # Step 4: Create merged objects
                placed_count = 0
                for p in placements:
                    try:
                        globals_.mainWindow.CreateObject(
                            fill_tileset,
                            fill_object_id,
                            layer,
                            p['x'], p['y'],
                            p['width'], p['height']
                        )
                        placed_count += 1
                    except Exception as e:
                        print(f"[QPT] Auto-fill error at ({p['x']}, {p['y']}): {e}")
                
                if placed_count > 0:
                    SetDirty()
                    print(f"[QPT] Auto-fill: Placed {placed_count} merged vertical slices (from {len(filled)} tiles)")
            
            if already_filled:
                globals_.mainWindow.scene.update()
                
                # Auto-apply deco objects if checkbox is enabled in Fill Paint tab
                try:
                    fill_tab = globals_.mainWindow.qpt_palette.get_fill_paint_tab()
                    if fill_tab and fill_tab.auto_deco_checkbox.isChecked():
                        # Convert already_filled set to list for _auto_apply_deco_fills
                        fill_tab._auto_apply_deco_fills(list(already_filled))
                        print(f"[QPT] Auto-fill: Applied auto-deco to {len(already_filled)} positions")
                except Exception as deco_e:
                    print(f"[QPT] Auto-fill deco error: {deco_e}")
                
        except Exception as e:
            print(f"[QPT] Auto-fill check error: {e}")
            import traceback
            traceback.print_exc()
    
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
        
        Uses RenderObject to detect empty tiles within slope objects.
        Positions with tile value -1 are empty and NOT added to database.
        Empty slope regions are tracked separately to prevent ghost tiles.
        """
        try:
            import globals_
            from tiles import RenderObject
            if not globals_.Area:
                return
            
            database = {}
            empty_slope_regions = set()  # Track empty tiles within slope bounds
            
            # Scan all layers for existing objects
            for layer_idx, layer in enumerate(globals_.Area.layers):
                for obj in layer:
                    # Use RenderObject to get the actual tile layout
                    # This returns a 2D array where -1 = empty tile
                    tile_array = RenderObject(obj.tileset, obj.type, obj.width, obj.height)
                    
                    # Add only non-empty tiles to the database
                    # Track empty tiles within slope bounds separately
                    for dy in range(obj.height):
                        for dx in range(obj.width):
                            tile_value = tile_array[dy][dx] if dy < len(tile_array) and dx < len(tile_array[dy]) else -1
                            
                            x = obj.objx + dx
                            y = obj.objy + dy
                            
                            if tile_value != -1:
                                # This is an actual tile, add to database
                                database[(x, y, layer_idx)] = obj.type
                            else:
                                # This is an empty tile within slope bounds
                                # QPT should NOT place tiles here
                                empty_slope_regions.add((x, y, layer_idx))
            
            # Update the engine's object database and empty slope regions
            self.mouse_handler.update_object_database(database, empty_slope_regions)
            print(f"[QPT] Refreshed object database: {len(database)} tiles ({len(empty_slope_regions)} empty tiles in slopes skipped)")
        except Exception as e:
            print(f"[QPT] Error refreshing object database: {e}")
            import traceback
            traceback.print_exc()
    
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
        current_mode = self.qpt_widget.get_current_mode()
        
        # Single Tile and Eraser modes don't require "Start Painting"
        # They are always active when their mode is selected
        if current_mode in ("Single Tile", "Eraser"):
            return self._handle_simple_brush_event(event_type, pos, button, current_mode)
        
        # SmartPaint mode requires explicit Start Painting
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
    
    def _handle_simple_brush_event(self, event_type: str, pos: tuple, button: int, mode: str) -> bool:
        """
        Handle mouse events for Single Tile and Eraser modes.
        These modes paint/erase directly without needing Start/Stop.
        
        Args:
            event_type: "press", "move", or "release"
            pos: Mouse position (x, y) in tile coordinates
            button: Mouse button (1=left, 2=right, 3=middle)
            mode: Current mode ("Single Tile" or "Eraser")
        
        Returns:
            True if event was handled
        """
        import globals_
        
        if event_type == "press":
            # Only handle right-click for starting paint/erase
            if button != 2:
                return False
            # Start simple brush stroke
            self._simple_brush_active = True
            self._simple_brush_last_pos = pos
            self._apply_simple_brush(pos, mode)
            return True
        elif event_type == "move":
            if getattr(self, '_simple_brush_active', False):
                # Interpolate between last position and current position
                last_pos = getattr(self, '_simple_brush_last_pos', pos)
                positions = self._interpolate_positions(last_pos, pos)
                for p in positions:
                    self._apply_simple_brush(p, mode)
                self._simple_brush_last_pos = pos
                return True
        elif event_type == "release":
            self._simple_brush_active = False
            self._simple_brush_last_pos = None
            return True
        
        return False
    
    def _interpolate_positions(self, start: tuple, end: tuple) -> list:
        """Interpolate positions between start and end using Bresenham's algorithm"""
        x0, y0 = int(start[0]), int(start[1])
        x1, y1 = int(end[0]), int(end[1])
        
        positions = []
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy
        
        while True:
            positions.append((x0, y0))
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                x0 += sx
            if e2 < dx:
                err += dx
                y0 += sy
        
        return positions
    
    def _apply_simple_brush(self, pos: tuple, mode: str):
        """Apply the simple brush (single tile or eraser) at the given position"""
        import globals_
        from levelitems import ObjectItem
        from tiles import CreateTilesets
        
        x, y = int(pos[0]), int(pos[1])
        layer = self.qpt_widget.get_current_layer() if self.qpt_widget else globals_.CurrentLayer
        
        if mode == "Single Tile":
            # Get the selected tile from the tileset selector
            selected_obj_id = self.tileset_selector.selected_object_id
            if selected_obj_id is None:
                return
            
            # Get the tileset slot
            tileset_slot = self.tileset_selector.tileset_combo.currentIndex()
            
            # Check if there's already an object at this position
            existing = self._get_object_at(x, y, layer)
            if existing:
                # Remove existing object
                self._remove_object(existing)
            
            # Create new object (1x1 size)
            self._place_object(tileset_slot, selected_obj_id, x, y, 1, 1, layer)
            
        elif mode == "Eraser":
            # Find and remove any object at this position
            existing = self._get_object_at(x, y, layer)
            if existing:
                self._remove_object(existing)
    
    def _get_object_at(self, x: int, y: int, layer: int):
        """Get the object at the given tile position"""
        import globals_
        
        if not hasattr(globals_.Area, 'layers') or layer >= len(globals_.Area.layers):
            return None
        
        for obj in globals_.Area.layers[layer]:
            if (obj.objx <= x < obj.objx + obj.width and
                obj.objy <= y < obj.objy + obj.height):
                return obj
        
        return None
    
    def _remove_object(self, obj):
        """Remove an object from the scene and layer"""
        import globals_
        from dirty import SetDirty
        
        try:
            layer_idx = obj.layer
            if layer_idx < len(globals_.Area.layers):
                globals_.Area.layers[layer_idx].remove(obj)
            globals_.mainWindow.scene.removeItem(obj)
            SetDirty()
        except Exception as e:
            print(f"[QPT] Error removing object: {e}")
    
    def _place_object(self, tileset: int, obj_type: int, x: int, y: int, width: int, height: int, layer: int):
        """Place a new object at the given position"""
        import globals_
        from levelitems import ObjectItem
        from dirty import SetDirty
        
        try:
            # Create the object
            obj = ObjectItem(tileset, obj_type, layer, x, y, width, height, 1)
            
            # Add to layer
            if layer < len(globals_.Area.layers):
                globals_.Area.layers[layer].append(obj)
            
            # Add to scene
            globals_.mainWindow.scene.addItem(obj)
            
            SetDirty()
        except Exception as e:
            print(f"[QPT] Error placing object: {e}")
    
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
    
    def handle_key_event(self, key: int) -> bool:
        """
        Handle key event.
        
        Args:
            key: Qt key code
            
        Returns:
            True if event was handled
        """
        if key == QtCore.Qt.Key.Key_Escape:
            if self.mouse_handler:
                return self.mouse_handler.on_key_press(key)
        return False
    
    def activate(self):
        """Activate the QPT tool by setting combobox to SmartPaint"""
        self.qpt_widget.set_mode("SmartPaint")
    
    def deactivate(self):
        """Deactivate the QPT tool - clear combobox selection visually"""
        # We don't actually deselect the combobox, just let the tool manager handle state
        pass
    
    def is_qpt_mode_active(self) -> bool:
        """Check if any QPT mode is currently selected"""
        mode = self.qpt_widget.get_current_mode()
        return mode in ("SmartPaint", "Single Tile", "Eraser", "Shape Creator")
    
    def reset(self):
        """
        Reset QPT to default state.
        Call this when level changes, area changes, or area settings are modified.
        """
        print("[QPT] QuickPaintTab.reset() called")
        
        # Reset tileset selector to Pa0 and reload objects
        # Use a timer to defer reload - ObjectDefinitions may not be ready yet
        if hasattr(self, 'tileset_selector'):
            self.tileset_selector.current_tileset = 0
            self.tileset_selector.tileset_combo.blockSignals(True)
            self.tileset_selector.tileset_combo.setCurrentIndex(0)
            self.tileset_selector.tileset_combo.blockSignals(False)
            self.tileset_selector.objects_loaded = False
            self.tileset_selector.tileset_objects.clear()
            self.tileset_selector.update_object_list()  # Clear immediately
            QtCore.QTimer.singleShot(200, self.tileset_selector.initialize_objects)
        
        self.qpt_widget.reset_to_default()


class DecoContainer(QtWidgets.QFrame):
    """
    Container widget for a single deco object configuration.
    
    Contains:
    - Radio button to select this container
    - Object display showing selected deco object
    - Probability slider (0-100%)
    - Start/Stop buttons for deco fill
    """
    
    # Signals
    selected = QtCore.pyqtSignal(object)  # Emitted when this container is selected
    object_changed = QtCore.pyqtSignal(int, int, int)  # tileset, obj_type, obj_id
    fill_requested = QtCore.pyqtSignal(object, float)  # container, probability
    
    _container_count = 0  # Class counter for unique IDs
    
    def __init__(self, parent=None):
        super().__init__(parent)
        DecoContainer._container_count += 1
        self.container_id = DecoContainer._container_count
        
        self._tileset_idx: int = 0
        self._object_id: Optional[int] = None
        self._object_width: int = 1
        self._object_height: int = 1
        self._is_active: bool = False
        
        self.setFrameStyle(QtWidgets.QFrame.Shape.StyledPanel)
        self.setLineWidth(1)
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        
        # Header row with radio button and remove button
        header_layout = QtWidgets.QHBoxLayout()
        
        self.radio = QtWidgets.QRadioButton(f"Deco #{self.container_id}")
        self.radio.setToolTip("Select this deco object for filling")
        self.radio.toggled.connect(self._on_radio_toggled)
        header_layout.addWidget(self.radio)
        
        header_layout.addStretch()
        
        self.remove_btn = QtWidgets.QPushButton("×")
        self.remove_btn.setFixedSize(20, 20)
        self.remove_btn.setToolTip("Remove this deco container")
        self.remove_btn.clicked.connect(self._on_remove_clicked)
        header_layout.addWidget(self.remove_btn)
        
        layout.addLayout(header_layout)
        
        # Object display
        obj_layout = QtWidgets.QHBoxLayout()
        obj_layout.addWidget(QtWidgets.QLabel("Object:"))
        self.object_label = QtWidgets.QLabel("(click tileset)")
        self.object_label.setStyleSheet("font-weight: bold;")
        obj_layout.addWidget(self.object_label)
        obj_layout.addStretch()
        layout.addLayout(obj_layout)
        
        # Probability slider
        prob_layout = QtWidgets.QHBoxLayout()
        prob_layout.addWidget(QtWidgets.QLabel("Probability:"))
        
        self.prob_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.prob_slider.setMinimum(1)
        self.prob_slider.setMaximum(100)
        self.prob_slider.setValue(5)  # Default 5%
        self.prob_slider.setTickInterval(10)
        self.prob_slider.valueChanged.connect(self._on_prob_changed)
        prob_layout.addWidget(self.prob_slider)
        
        self.prob_label = QtWidgets.QLabel("5%")
        self.prob_label.setFixedWidth(35)
        prob_layout.addWidget(self.prob_label)
        
        layout.addLayout(prob_layout)
        
        # Start button
        self.start_btn = QtWidgets.QPushButton("Fill Deco")
        self.start_btn.setToolTip("Fill the current fill area with this deco object")
        self.start_btn.clicked.connect(self._on_start_clicked)
        self.start_btn.setEnabled(False)  # Disabled until object selected
        layout.addWidget(self.start_btn)
    
    def _on_radio_toggled(self, checked: bool):
        """Handle radio button toggle"""
        if checked:
            self._is_active = True
            # Use border highlight instead of background to work with all themes
            self.setStyleSheet("DecoContainer { border: 2px solid #4a90d9; }")
            self.selected.emit(self)
        else:
            self._is_active = False
            self.setStyleSheet("DecoContainer { border: 1px solid #555; }")
    
    def _on_prob_changed(self, value: int):
        """Handle probability slider change"""
        self.prob_label.setText(f"{value}%")
    
    def _on_start_clicked(self):
        """Handle start fill button"""
        if self._object_id is not None:
            probability = self.prob_slider.value() / 100.0
            self.fill_requested.emit(self, probability)
    
    def _on_remove_clicked(self):
        """Handle remove button - will be handled by parent"""
        self.deleteLater()
    
    def set_object(self, tileset: int, object_id: int, width: int = 1, height: int = 1):
        """Set the deco object for this container"""
        self._tileset_idx = tileset
        self._object_id = object_id
        self._object_width = width
        self._object_height = height
        
        size_str = f" ({width}x{height})" if width > 1 or height > 1 else ""
        self.object_label.setText(f"#{object_id}{size_str}")
        self.start_btn.setEnabled(True)
        self.object_changed.emit(tileset, 0, object_id)
    
    def get_object_info(self) -> tuple:
        """Get the object info (tileset, object_id, width, height)"""
        return (self._tileset_idx, self._object_id, self._object_width, self._object_height)
    
    def is_selected(self) -> bool:
        """Check if this container is selected"""
        return self.radio.isChecked()
    
    def select(self):
        """Select this container"""
        self.radio.setChecked(True)
    
    def deselect(self):
        """Deselect this container"""
        self.radio.setChecked(False)


class FillPaintTab(QtWidgets.QWidget):
    """
    Fill Paint Tab - Flood fill painting tool.
    
    Provides:
    - Flood fill painting with zone boundaries
    - Fill preview before confirmation
    - Deco object filling with probability
    """
    
    # Signals
    fill_started = QtCore.pyqtSignal()
    fill_cancelled = QtCore.pyqtSignal()
    fill_confirmed = QtCore.pyqtSignal(list)  # List of positions
    
    def __init__(self, parent=None, button_group=None):
        """
        Initialize the Fill Paint tab.
        
        Args:
            parent: Parent widget
            button_group: QButtonGroup for radio button synchronization across tabs
        """
        super().__init__(parent)
        
        from quickpaint.core.fill_engine import get_fill_engine, FillState
        from quickpaint.core.tool_manager import get_tool_manager, ToolType
        
        self.fill_engine = get_fill_engine()
        self.tool_manager = get_tool_manager()
        self.button_group = button_group
        
        # Connect fill engine signals
        self.fill_engine.fill_preview_updated.connect(self._on_fill_preview)
        self.fill_engine.fill_confirmed.connect(self._on_fill_confirmed)
        self.fill_engine.fill_cancelled.connect(self._on_fill_cancelled)
        self.fill_engine.fill_warning.connect(self._on_fill_warning)
        
        self._fill_object_id: Optional[int] = 1  # Default fill object
        self._tileset_idx: int = 0
        
        # Deco containers list
        self._deco_containers: List[DecoContainer] = []
        self._active_deco_container: Optional[DecoContainer] = None
        
        self.init_ui()
    
    def init_ui(self):
        """Initialize the UI"""
        from quickpaint.ui.tileset_selector import TilesetSelector
        
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # ===== SCROLL AREA FOR CONTENT =====
        scroll_area = QtWidgets.QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("QScrollArea { border: none; }")
        
        # Container widget for scroll area
        container = QtWidgets.QWidget()
        container_layout = QtWidgets.QVBoxLayout(container)
        container_layout.setContentsMargins(4, 4, 4, 4)
        container_layout.setSpacing(4)
        
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
        self.layer_button_group.idClicked.connect(self._on_layer_changed)
        
        layer_layout.addWidget(self.layer_radio_0)
        layer_layout.addWidget(self.layer_radio_1)
        layer_layout.addWidget(self.layer_radio_2)
        layer_layout.addStretch(1)
        container_layout.addLayout(layer_layout)
        self._current_layer = 1
        
        # ===== TILESET SELECTOR =====
        self.tileset_selector = TilesetSelector()
        self.tileset_selector.object_selected.connect(self._on_fill_object_selected)
        container_layout.addWidget(self.tileset_selector)
        
        # Initialize tileset objects after a short delay
        QtCore.QTimer.singleShot(100, self.tileset_selector.initialize_objects)
        
        # ===== STATUS LABEL (shared between Fill and Deco tools) =====
        self.status_label = QtWidgets.QLabel("Idle")
        self.status_label.setStyleSheet(
            "color: white; font-weight: bold; padding: 3px 6px; "
            "background-color: #444; font-size: 10pt;"
        )
        self.status_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        container_layout.addWidget(self.status_label)
        
        # ===== FILL TOOL SECTION =====
        fill_group = QtWidgets.QGroupBox("Fill Tool")
        fill_layout = QtWidgets.QVBoxLayout(fill_group)
        
        # Radio button for Fill Tool
        self.fill_radio = QtWidgets.QRadioButton("Fill Tool (F)")
        self.fill_radio.setToolTip("Click to activate Fill Tool. Hotkey: F")
        self.fill_radio.toggled.connect(self._on_fill_radio_toggled)
        fill_layout.addWidget(self.fill_radio)
        
        # Instructions
        instructions = QtWidgets.QLabel(
            "1. Select fill object above\n"
            "2. Right-click to preview fill area\n"
            "3. Right-click again to confirm\n"
            "4. ESC=cancel, F2=clear area"
        )
        instructions.setStyleSheet("color: gray; font-size: 10px;")
        fill_layout.addWidget(instructions)
        
        # Fill object display
        obj_layout = QtWidgets.QHBoxLayout()
        obj_layout.addWidget(QtWidgets.QLabel("Fill Object:"))
        self.fill_object_label = QtWidgets.QLabel("(select above)")
        self.fill_object_label.setStyleSheet("font-weight: bold;")
        obj_layout.addWidget(self.fill_object_label)
        obj_layout.addStretch()
        fill_layout.addLayout(obj_layout)
        
        # Clear Area button
        self.clear_area_btn = QtWidgets.QPushButton("Clear Area (F2)")
        self.clear_area_btn.setToolTip("Delete all tiles in the current fill preview area")
        self.clear_area_btn.setEnabled(False)  # Enabled when preview is active
        self.clear_area_btn.clicked.connect(self._on_clear_area_clicked)
        fill_layout.addWidget(self.clear_area_btn)
        
        container_layout.addWidget(fill_group)
        
        # ===== DECO FILL SECTION =====
        deco_group = QtWidgets.QGroupBox("Deco Fill (D)")
        deco_layout = QtWidgets.QVBoxLayout(deco_group)
        
        # Deco instructions
        deco_instructions = QtWidgets.QLabel(
            "Add deco containers, select object from tileset,\n"
            "right-click to fill area, then 'Fill Deco' to place."
        )
        deco_instructions.setStyleSheet("color: gray; font-size: 10px;")
        deco_layout.addWidget(deco_instructions)
        
        # Deco containers will be added here dynamically
        self.deco_container_layout = QtWidgets.QVBoxLayout()
        deco_layout.addLayout(self.deco_container_layout)
        
        # Add deco container button
        add_deco_btn = QtWidgets.QPushButton("+ Add Deco Object")
        add_deco_btn.clicked.connect(self._add_deco_container)
        deco_layout.addWidget(add_deco_btn)
        
        container_layout.addWidget(deco_group)
        
        # Auto-apply deco checkbox (below deco section)
        self.auto_deco_checkbox = QtWidgets.QCheckBox("Auto-apply deco objects after fill")
        self.auto_deco_checkbox.setToolTip(
            "When enabled, all deco containers with assigned objects\n"
            "will automatically fill after a regular fill operation."
        )
        container_layout.addWidget(self.auto_deco_checkbox)
        
        container_layout.addStretch()
        
        # Add container to scroll area
        scroll_area.setWidget(container)
        layout.addWidget(scroll_area)
    
    def _on_layer_changed(self, layer_id: int):
        """Handle layer selection change from radio buttons"""
        if self._current_layer == layer_id:
            return
        self._current_layer = layer_id
        self.fill_engine.set_layer(layer_id)
        print(f"[FillPaintTab] Layer changed to {layer_id}")
        
        # Sync globals_.CurrentLayer and Objects palette radio buttons
        import globals_
        globals_.CurrentLayer = layer_id
        if hasattr(globals_, 'mainWindow') and globals_.mainWindow:
            mw = globals_.mainWindow
            if hasattr(mw, 'LayerButtonGroup'):
                btn = mw.LayerButtonGroup.button(layer_id)
                if btn and not btn.isChecked():
                    btn.setChecked(True)
            # Sync QPT tab
            if hasattr(mw, 'qpt_palette') and mw.qpt_palette:
                qpt_tab = mw.qpt_palette.get_quick_paint_tab()
                if qpt_tab and hasattr(qpt_tab, 'qpt_widget'):
                    qpt_tab.qpt_widget.set_layer_silent(layer_id)
    
    def set_layer_silent(self, layer_id: int):
        """Set the layer without triggering sync (called from external sync)"""
        self._current_layer = layer_id
        self.fill_engine.set_layer(layer_id)
        btn = self.layer_button_group.button(layer_id)
        if btn and not btn.isChecked():
            self.layer_button_group.blockSignals(True)
            btn.setChecked(True)
            self.layer_button_group.blockSignals(False)
    
    def get_current_layer(self) -> int:
        """Get the currently selected layer"""
        return self._current_layer
    
    def _on_fill_radio_toggled(self, checked: bool):
        """Handle fill radio button toggle"""
        from quickpaint.core.tool_manager import ToolType
        import globals_
        
        if checked:
            # Deselect all deco container radios when fill is selected
            self._deselect_all_deco_containers()
            
            self.tool_manager.activate_tool(ToolType.FILL_PAINT)
            # Show preview count if fill area already exists
            from quickpaint.core.fill_engine import FillState
            if self.fill_engine.state == FillState.PREVIEW:
                count = len(self.fill_engine.fill_positions)
                self.status_label.setText(f"Fill: Preview - {count} tiles (right-click to confirm)")
            else:
                self.status_label.setText("Fill: Ready - Right-click to create fill area")
            # Set cursor based on whether fill object is selected
            self._update_fill_cursor()
        else:
            self.status_label.setText("Idle")
    
    def _deselect_all_deco_containers(self):
        """Deselect all deco container radio buttons"""
        for container in self._deco_containers:
            if container.is_selected():
                container.radio.blockSignals(True)
                container.deselect()
                container.radio.blockSignals(False)
        self._active_deco_container = None
    
    def _on_fill_preview(self, positions: list):
        """Handle fill preview update"""
        count = len(positions)
        if count > 0:
            self.status_label.setText(f"Fill: Preview - {count} tiles (right-click to confirm)")
            self.clear_area_btn.setEnabled(True)
        else:
            self.status_label.setText("Fill: Ready - Right-click to create fill area")
            self.clear_area_btn.setEnabled(False)
    
    def _on_fill_confirmed(self, positions: list):
        """Handle fill confirmation"""
        count = len(positions)
        self.status_label.setText(f"Fill: Placed {count} tiles")
        self.clear_area_btn.setEnabled(False)
        self.fill_confirmed.emit(positions)
        
        # Auto-apply deco objects if checkbox is enabled
        if self.auto_deco_checkbox.isChecked():
            self._auto_apply_deco_fills(positions)
    
    def _auto_apply_deco_fills(self, positions: list):
        """
        Automatically apply deco fills from all containers with assigned objects.
        Called after fill confirmation when auto-apply checkbox is enabled.
        
        Args:
            positions: List of (x, y) positions that were filled
        """
        if not self._deco_containers:
            return
        
        if not positions:
            return
        
        # Convert to set for efficient lookup
        fill_positions_set = set(positions) if isinstance(positions[0], tuple) else set((p[0], p[1]) for p in positions)
        
        # Shared set to track all occupied positions across all deco fill operations
        # This ensures consecutive deco fills don't overlap with each other
        shared_occupied = set()
        
        applied_count = 0
        for container in self._deco_containers:
            # Check if container has a deco object set
            tileset, object_id, obj_width, obj_height = container.get_object_info()
            if object_id is None:
                continue  # Skip containers without objects
            
            # Get probability from the container's slider
            probability = container.prob_slider.value() / 100.0
            if probability <= 0:
                continue  # Skip if probability is 0
            
            # Apply deco fill for this container, passing fill positions and shared occupied
            print(f"[FillPaintTab] Auto-applying deco: container #{container.container_id}, prob={probability:.0%}")
            self._apply_deco_fill(container, probability, shared_occupied, fill_positions_set)
            applied_count += 1
        
        if applied_count > 0:
            self.status_label.setText(f"Fill: Placed tiles + {applied_count} deco layer(s)")
    
    def _on_fill_cancelled(self):
        """Handle fill cancellation"""
        self.status_label.setText("Cancelled")
        self.clear_area_btn.setEnabled(False)
        self.fill_cancelled.emit()
    
    def _on_fill_warning(self, count: int):
        """Handle fill area warning - ask user if they want to continue"""
        from quickpaint.core.fill_engine import MAX_FILL_AREA
        
        self.status_label.setText(f"Fill: Large area ({count}+ tiles) - confirm to continue")
        
        reply = QtWidgets.QMessageBox.question(
            self,
            "Large Fill Area",
            f"The fill area exceeds {MAX_FILL_AREA} tiles.\n\n"
            "Calculating the full area may take a while.\n\n"
            "Do you want to continue?",
            QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
            QtWidgets.QMessageBox.StandardButton.No
        )
        
        if reply == QtWidgets.QMessageBox.StandardButton.Yes:
            # User wants to continue - calculate full fill area
            result = self.fill_engine.continue_fill()
            self.status_label.setText(f"Fill: Preview - {result.count} tiles (right-click to confirm)")
        else:
            # User cancelled - reset to idle
            self.fill_engine.cancel_fill()
            self.status_label.setText("Cancelled - area too large")
    
    def _on_fill_object_selected(self, tileset: int, obj_type: int, obj_id: int):
        """Handle fill object selection from tileset selector"""
        print(f"[FillPaintTab] Object selected: tileset={tileset}, obj_id={obj_id}")
        
        # If a deco container is active, set deco object on it
        if self._active_deco_container and self._active_deco_container.is_selected():
            # Get object dimensions from ObjectDefinitions
            import globals_
            width, height = 1, 1
            try:
                if hasattr(globals_, 'ObjectDefinitions') and globals_.ObjectDefinitions:
                    obj_def = globals_.ObjectDefinitions[tileset][obj_id]
                    if obj_def:
                        width = obj_def.width
                        height = obj_def.height
            except (IndexError, TypeError, AttributeError):
                pass
            
            self._active_deco_container.set_object(tileset, obj_id, width, height)
            print(f"[FillPaintTab] Set deco object #{obj_id} ({width}x{height}) on container #{self._active_deco_container.container_id}")
        else:
            # Set fill object
            self.set_fill_object(tileset, obj_id)
    
    def _add_deco_container(self):
        """Add a new deco object container"""
        container = DecoContainer()
        container.selected.connect(self._on_deco_container_selected)
        container.fill_requested.connect(self._on_deco_fill_requested)
        container.destroyed.connect(lambda: self._on_deco_container_removed(container))
        
        self._deco_containers.append(container)
        self.deco_container_layout.addWidget(container)
        
        # Add container radio to button group
        if self.button_group:
            self.button_group.addButton(container.radio)
        
        # Auto-select the new container
        container.select()
        
        print(f"[FillPaintTab] Added deco container #{container.container_id}")
    
    def _on_deco_container_selected(self, container: DecoContainer):
        """Handle deco container selection"""
        from quickpaint.core.tool_manager import ToolType
        import globals_
        
        self._active_deco_container = container
        
        # Deselect other containers
        for c in self._deco_containers:
            if c != container and c.is_selected():
                c.radio.blockSignals(True)
                c.deselect()
                c.radio.blockSignals(False)
        
        # Deselect fill radio
        self.fill_radio.blockSignals(True)
        self.fill_radio.setChecked(False)
        self.fill_radio.blockSignals(False)
        
        # Activate deco fill tool
        self.tool_manager.activate_tool(ToolType.DECO_FILL)
        # Show preview count if fill area already exists
        from quickpaint.core.fill_engine import FillState
        if self.fill_engine.state == FillState.PREVIEW:
            count = len(self.fill_engine.fill_positions)
            self.status_label.setText(f"Deco: Preview - {count} tiles (right-click to confirm)")
        else:
            self.status_label.setText("Deco: Ready - Right-click to create fill area")
        
        # Set crosshair cursor
        if hasattr(globals_, 'mainWindow') and globals_.mainWindow and globals_.mainWindow.view:
            globals_.mainWindow.view.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        
        print(f"[FillPaintTab] Deco container #{container.container_id} selected")
    
    def _on_deco_container_removed(self, container: DecoContainer):
        """Handle deco container removal"""
        if container in self._deco_containers:
            self._deco_containers.remove(container)
        if self._active_deco_container == container:
            self._active_deco_container = None
        print(f"[FillPaintTab] Deco container removed")
    
    def _on_deco_fill_requested(self, container: DecoContainer, probability: float):
        """Handle deco fill request from a container"""
        print(f"[FillPaintTab] Deco fill requested: container #{container.container_id}, probability={probability}")
        self._apply_deco_fill(container, probability)
    
    def _apply_deco_fill(self, container: DecoContainer, probability: float, shared_occupied: set = None, fill_positions: set = None):
        """
        Apply deco fill to the current fill area.
        
        Args:
            container: The deco container with object info
            probability: Fill probability (0.0 to 1.0)
            shared_occupied: Optional set of already occupied positions from previous
                           deco fill operations (used by auto-apply)
            fill_positions: Optional set of fill positions to use (for auto-fill).
                          If None, uses fill_engine.fill_positions.
        """
        import random
        import globals_
        from dirty import SetDirty
        
        # Get fill positions - use provided positions or fall back to fill engine
        if fill_positions is None:
            fill_positions = self.fill_engine.fill_positions
        if not fill_positions:
            QtWidgets.QMessageBox.warning(
                self, "No Fill Area",
                "Please create a fill area first by right-clicking inside a zone."
            )
            return
        
        tileset, object_id, obj_width, obj_height = container.get_object_info()
        if object_id is None:
            QtWidgets.QMessageBox.warning(
                self, "No Deco Object",
                "Please select a deco object from the tileset first."
            )
            return
        
        # Get current layer from Fill Paint tab's layer selector
        current_layer = self._current_layer
        
        # Get tile type checker from reggie_hook
        get_tile_type = None
        if hasattr(globals_, 'qpt_functions') and 'get_tile_type' in globals_.qpt_functions:
            get_tile_type = globals_.qpt_functions['get_tile_type']
        
        # Use shared occupied set if provided (for auto-apply), otherwise create new
        if shared_occupied is None:
            shared_occupied = set()
        
        # Filter positions: only allow empty or fill tiles (not deco or foreign)
        # Also check if multi-tile object fits within the fill area
        # And check against shared_occupied for positions from previous deco fills
        valid_positions = []
        for x, y in fill_positions:
            # Check if object fits at this position (all tiles in fill area)
            fits = True
            can_place = True
            
            for dx in range(obj_width):
                for dy in range(obj_height):
                    check_x, check_y = x + dx, y + dy
                    
                    # Must be within fill area
                    if (check_x, check_y) not in fill_positions:
                        fits = False
                        break
                    
                    # Check against shared occupied positions (from previous deco fills)
                    if (check_x, check_y) in shared_occupied:
                        can_place = False
                        break
                    
                    # Check tile type - only allow empty or fill tiles
                    if get_tile_type:
                        tile_type = get_tile_type(check_x, check_y, current_layer)
                        if tile_type in ('deco', 'foreign'):
                            can_place = False
                            break
                
                if not fits or not can_place:
                    break
            
            if fits and can_place:
                valid_positions.append((x, y))
        
        if not valid_positions:
            QtWidgets.QMessageBox.information(
                self, "No Space",
                "No valid positions available for this deco object size."
            )
            return
        
        # Calculate number of objects to place based on probability
        # For multi-tile objects, adjust probability by dividing by object area
        # E.g., 2x2 object (area=4) at 20% probability becomes 5% effective probability
        object_area = obj_width * obj_height
        adjusted_probability = probability / object_area
        
        num_to_place = int(len(valid_positions) * adjusted_probability)
        if num_to_place == 0 and probability > 0:
            num_to_place = 1  # At least try to place one
        
        # Randomly shuffle positions
        random.shuffle(valid_positions)
        
        # Place deco objects, tracking occupied positions to prevent overlap
        # Use shared_occupied to track positions across multiple deco fill operations
        placed_count = 0
        
        for x, y in valid_positions:
            if placed_count >= num_to_place:
                break
            
            # Check if this position overlaps with already placed deco objects (within this operation)
            overlaps = False
            for dx in range(obj_width):
                for dy in range(obj_height):
                    if (x + dx, y + dy) in shared_occupied:
                        overlaps = True
                        break
                if overlaps:
                    break
            
            if overlaps:
                continue
            
            try:
                obj = globals_.mainWindow.CreateObject(
                    tileset,
                    object_id,
                    current_layer,
                    x, y,
                    obj_width, obj_height
                )
                if obj:
                    placed_count += 1
                    # Mark all positions covered by this object as occupied
                    for dx in range(obj_width):
                        for dy in range(obj_height):
                            shared_occupied.add((x + dx, y + dy))
            except Exception as e:
                print(f"Error placing deco at ({x}, {y}): {e}")
        
        if placed_count > 0:
            SetDirty()
            globals_.mainWindow.scene.update()
        
        print(f"[FillPaintTab] Placed {placed_count} deco objects")
        self.status_label.setText(f"Deco: Placed {placed_count} objects")
    
    def set_fill_object(self, tileset: int, object_id: int):
        """Set the fill object"""
        self._tileset_idx = tileset
        self._fill_object_id = object_id
        self.fill_object_label.setText(f"Object #{object_id}")
        self.fill_engine.set_fill_object(tileset, object_id, self._current_layer)
        # Update cursor now that we have a fill object
        self._update_fill_cursor()
    
    def _update_fill_cursor(self):
        """Update cursor based on fill tool state"""
        import globals_
        from quickpaint.core.tool_manager import ToolType
        
        if not hasattr(globals_, 'mainWindow') or not globals_.mainWindow or not globals_.mainWindow.view:
            return
        
        # Only update if Fill Paint is active
        if not self.tool_manager.is_active(ToolType.FILL_PAINT):
            return
        
        # Show "forbidden" cursor if no fill object selected, crosshair otherwise
        if self._fill_object_id is None:
            globals_.mainWindow.view.setCursor(QtCore.Qt.CursorShape.ForbiddenCursor)
        else:
            globals_.mainWindow.view.setCursor(QtCore.Qt.CursorShape.CrossCursor)
    
    def activate(self):
        """Activate the fill tool"""
        from quickpaint.core.tool_manager import ToolType
        from quickpaint.core.fill_engine import FillState
        self.fill_radio.setChecked(True)
        # Ensure tool manager is activated even if radio was already checked
        self.tool_manager.activate_tool(ToolType.FILL_PAINT)
        # Show preview count if fill area already exists
        if self.fill_engine.state == FillState.PREVIEW:
            count = len(self.fill_engine.fill_positions)
            self.status_label.setText(f"Fill: Preview - {count} tiles (right-click to confirm)")
        else:
            self.status_label.setText("Fill: Ready - Right-click to create fill area")
        self._update_fill_cursor()
    
    def deactivate(self):
        """Deactivate the fill tool"""
        self.fill_radio.setChecked(False)
        self.fill_engine.cancel_fill()
    
    def reset(self):
        """
        Reset Fill Paint tab to default state.
        Called when level changes or area changes.
        """
        print("[FillPaintTab] reset() called")
        
        # Reset tileset selector to Pa0 and reload objects
        # Use a timer to defer reload - ObjectDefinitions may not be ready yet
        if hasattr(self, 'tileset_selector'):
            self.tileset_selector.current_tileset = 0
            self.tileset_selector.tileset_combo.blockSignals(True)
            self.tileset_selector.tileset_combo.setCurrentIndex(0)
            self.tileset_selector.tileset_combo.blockSignals(False)
            self.tileset_selector.objects_loaded = False
            self.tileset_selector.tileset_objects.clear()
            self.tileset_selector.update_object_list()  # Clear immediately
            QtCore.QTimer.singleShot(200, self.tileset_selector.initialize_objects)
        
        # Reset layer to 1
        self._current_layer = 1
        self.layer_radio_1.setChecked(True)
        self.fill_engine.set_layer(1)
        
        # Clear fill object selection
        self._fill_object_id = None
        self.fill_object_label.setText("No object selected")
        
        # Remove all deco containers
        for container in self._deco_containers[:]:  # Copy list to avoid modification during iteration
            container.deleteLater()
        self._deco_containers.clear()
        self._active_deco_container = None
        
        # Cancel any active fill preview
        self.fill_engine.cancel_fill()
        
        # Reset status
        self.status_label.setText("Idle")
        
        print("[FillPaintTab] Reset complete")
    
    def handle_mouse_event(self, event_type: str, pos: tuple, button: int) -> bool:
        """
        Handle mouse event for fill tool.
        
        Args:
            event_type: "press", "move", or "release"
            pos: (x, y) tile position
            button: Mouse button (1=left, 2=right)
            
        Returns:
            True if event was handled
        """
        from quickpaint.core.tool_manager import ToolType
        from quickpaint.core.fill_engine import FillState
        
        print(f"[FillPaintTab] handle_mouse_event: type={event_type}, pos={pos}, button={button}")
        
        # Check if either Fill or Deco tool is active
        is_fill_active = self.tool_manager.is_active(ToolType.FILL_PAINT)
        is_deco_active = self.tool_manager.is_active(ToolType.DECO_FILL)
        print(f"[FillPaintTab] Fill active: {is_fill_active}, Deco active: {is_deco_active}")
        
        if not is_fill_active and not is_deco_active:
            return False
        
        if event_type == "press" and button == 2:  # Right-click
            x, y = pos
            
            print(f"[FillPaintTab] Fill state: {self.fill_engine.state}, fill_object_id: {self._fill_object_id}")
            
            # For Fill tool, require fill object to be selected
            # For Deco tool, we can create fill area without fill object
            if is_fill_active and self._fill_object_id is None:
                self.status_label.setText("Fill: Select a fill object first")
                print("[FillPaintTab] No fill object selected")
                return True
            
            if self.fill_engine.state == FillState.IDLE:
                # Start fill preview
                # Check if Shift is held to allow fill outside zones
                modifiers = QtWidgets.QApplication.keyboardModifiers()
                allow_outside = bool(modifiers & QtCore.Qt.KeyboardModifier.ShiftModifier)
                
                print(f"[FillPaintTab] Starting fill at ({x}, {y}), allow_outside={allow_outside}")
                result = self.fill_engine.start_fill(x, y, allow_outside_zone=allow_outside)
                print(f"[FillPaintTab] Fill result: positions={len(result.positions)}, outside_zone={result.outside_zone}, interrupted={result.interrupted}")
                
                if result.interrupted and result.exceeded_limit:
                    # Outside zone fill was auto-cancelled at threshold
                    self.status_label.setText("Cancelled - area too large (outside zone)")
                elif result.outside_zone:
                    self.status_label.setText("Click inside a zone (or hold Shift)")
                elif len(result.positions) == 0:
                    self.status_label.setText("Cannot fill here (occupied or invalid)")
                else:
                    # Update status for deco tool
                    if is_deco_active:
                        self.status_label.setText(f"Deco: Preview - {len(result.positions)} tiles (right-click to confirm)")
                return True
                
            elif self.fill_engine.state == FillState.PREVIEW:
                if is_fill_active:
                    # Confirm fill and apply
                    # Note: fill_engine.confirm_fill() emits fill_confirmed signal
                    # which is connected to _on_fill_confirmed, so don't emit again here
                    print("[FillPaintTab] Confirming fill")
                    self.fill_engine.confirm_fill()
                elif is_deco_active:
                    # For deco tool, right-click in preview commits the deco fill
                    print("[FillPaintTab] Deco: Committing deco fill via right-click")
                    if self._active_deco_container:
                        probability = self._active_deco_container.prob_slider.value() / 100.0
                        self._apply_deco_fill(self._active_deco_container, probability)
                    else:
                        self.status_label.setText("Deco: No container selected")
                return True
        
        return False
    
    def handle_key_event(self, key: int) -> bool:
        """
        Handle key event.
        
        Args:
            key: Qt key code
            
        Returns:
            True if event was handled
        """
        from quickpaint.core.tool_manager import ToolType
        from quickpaint.core.fill_engine import FillState
        
        if key == QtCore.Qt.Key.Key_Escape.value:
            if self.fill_engine.state == FillState.PREVIEW:
                self.fill_engine.cancel_fill()
                if self.tool_manager.is_active(ToolType.DECO_FILL):
                    self.status_label.setText("Deco: Ready - Right-click to create fill area")
                else:
                    self.status_label.setText("Fill: Ready - Right-click to create fill area")
                return True
        
        if key == QtCore.Qt.Key.Key_F2.value:
            if self.fill_engine.state == FillState.PREVIEW:
                self._clear_fill_area()
                return True
        
        return False
    
    def _on_clear_area_clicked(self):
        """Handle Clear Area button click"""
        self._clear_fill_area()
    
    def _clear_fill_area(self):
        """
        Clear/delete all tiles within the current fill preview area.
        Deletes both fill tiles and deco tiles.
        """
        from quickpaint.core.fill_engine import FillState
        
        if self.fill_engine.state != FillState.PREVIEW:
            return
        
        positions = list(self.fill_engine.fill_positions)
        if not positions:
            return
        
        import globals_
        from dirty import SetDirty
        
        current_layer = self._current_layer
        deleted_count = 0
        
        # Get all objects in the current layer
        if not hasattr(globals_, 'Area') or globals_.Area is None:
            return
        
        layer = globals_.Area.layers[current_layer]
        
        # Find and delete objects that overlap with fill positions
        positions_set = set(positions)
        objects_to_delete = []
        
        # Debug: show sample positions and objects
        sample_pos = list(positions_set)[:3]
        print(f"[FillPaintTab] Clear area: layer={current_layer}, {len(layer)} objects, {len(positions_set)} positions")
        print(f"[FillPaintTab] Sample fill positions (tiles): {sample_pos}")
        
        # Debug: show first few objects and their positions
        # Note: obj.objx/objy are already in tile units, not pixels
        for i, obj in enumerate(layer[:3]):
            print(f"[FillPaintTab] Object {i}: pos=({obj.objx},{obj.objy}), size={obj.width}x{obj.height}")
        
        # Import RenderObject to check for empty tiles in slope objects
        from tiles import RenderObject
        
        for obj in layer:
            # obj.objx/objy are already in tile coordinates
            obj_x = obj.objx
            obj_y = obj.objy
            obj_w = obj.width
            obj_h = obj.height
            
            # Get tile array for this object to check for empty tiles (-1)
            tile_array = RenderObject(obj.tileset, obj.type, obj_w, obj_h)
            
            # Check if any FILLED tile of this object is in the fill area
            # Skip empty tiles (-1) which are part of slope objects
            found = False
            for dx in range(obj_w):
                for dy in range(obj_h):
                    if (obj_x + dx, obj_y + dy) in positions_set:
                        # Check if this tile is actually filled (not -1)
                        tile_value = tile_array[dy][dx] if dy < len(tile_array) and dx < len(tile_array[dy]) else -1
                        if tile_value != -1:
                            objects_to_delete.append(obj)
                            found = True
                            break
                if found:
                    break
        
        print(f"[FillPaintTab] Found {len(objects_to_delete)} objects to delete")
        
        # Delete the objects
        for obj in objects_to_delete:
            obj.delete()
            obj.setSelected(False)
            globals_.mainWindow.scene.removeItem(obj)
            deleted_count += 1
        
        # Cancel the fill preview
        self.fill_engine.cancel_fill()
        
        # Mark level as dirty
        if deleted_count > 0:
            SetDirty()
            globals_.mainWindow.scene.update()
        
        self.status_label.setText(f"Cleared: {deleted_count} objects deleted")
        print(f"[FillPaintTab] Cleared fill area: {deleted_count} objects deleted from {len(positions)} tile positions")
    
    def get_fill_preview(self) -> List[tuple]:
        """Get current fill preview positions"""
        return list(self.fill_engine.fill_positions)
    
    def cycle_deco_container(self):
        """Cycle through deco containers (D hotkey)"""
        if not self._deco_containers:
            # No containers - do nothing
            print("[FillPaintTab] D pressed but no deco containers exist")
            return
        
        # Find currently selected container index
        current_idx = -1
        for i, container in enumerate(self._deco_containers):
            if container.is_selected():
                current_idx = i
                break
        
        # Cycle to next container
        next_idx = (current_idx + 1) % len(self._deco_containers)
        self._deco_containers[next_idx].select()
        # The select() call will trigger _on_deco_container_selected which handles tool activation


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
    Manages tool activation, hotkeys, and active tool display.
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
        
        # Import tool manager
        from quickpaint.core.tool_manager import get_tool_manager, ToolType
        self.tool_manager = get_tool_manager()
        self.tool_manager.tool_changed.connect(self._on_tool_changed)
        
        # Create button group for radio buttons across tabs
        self.tool_button_group = QtWidgets.QButtonGroup(self)
        self.tool_button_group.setExclusive(True)
        
        self.init_ui()
        print("[QPT] OK: QuickPaintPalette initialized")
    
    def init_ui(self):
        """Initialize the UI"""
        print("[QPT] QuickPaintPalette.init_ui starting...")
        
        print("[QPT] Creating layout...")
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        print("[QPT] OK: Layout created")
        
        # Tab widget
        print("[QPT] Creating QTabWidget...")
        self.tabs = QtWidgets.QTabWidget()
        print("[QPT] OK: QTabWidget created")
        
        # QPT tab
        print("[QPT] Creating QuickPaintTab...")
        self.quick_paint_tab = QuickPaintTab()
        print("[QPT] OK: QuickPaintTab created")
        self.tabs.addTab(self.quick_paint_tab, "QPT")
        
        # Fill Paint tab
        print("[QPT] Creating FillPaintTab...")
        self.fill_paint_tab = FillPaintTab(button_group=self.tool_button_group)
        print("[QPT] OK: FillPaintTab created")
        self.tabs.addTab(self.fill_paint_tab, "Fill Paint")
        
        # Outline Overlay tab (stub)
        print("[QPT] Creating OutlineOverlayTab...")
        self.outline_overlay_tab = OutlineOverlayTab()
        print("[QPT] OK: OutlineOverlayTab created")
        self.tabs.addTab(self.outline_overlay_tab, "Tileset Overlay")
        
        # Add Fill radio button to button group
        # QPT modes are handled via combobox, which deselects radio buttons when changed
        print("[QPT] Adding radio buttons to button group...")
        self.tool_button_group.addButton(self.fill_paint_tab.fill_radio)
        # Note: Deco containers are added dynamically when created
        print("[QPT] OK: Radio buttons added to button group")
        
        # Connect QPT mode combobox changes to deselect Fill/Deco radio buttons
        self.quick_paint_tab.qpt_widget.mode_changed.connect(self._on_qpt_mode_selected)
        
        # Active tool display label (compact, below tabs)
        self.active_tool_label = QtWidgets.QLabel("Active: Quick Paint")
        self.active_tool_label.setStyleSheet(
            "background-color: #2d5a2d; color: white; padding: 2px 6px; "
            "font-weight: bold; font-size: 9pt;"
        )
        self.active_tool_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.active_tool_label.setFixedHeight(18)
        
        # Add tool label first, then tabs below
        layout.addWidget(self.active_tool_label)
        layout.addWidget(self.tabs, 1)
        
        # Track current tab to avoid redundant activations
        self._current_tab_index = 0
        
        # Connect tab change signal AFTER all UI is created
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
        # Initialize with QPT active on first tab (use timer to ensure Reggie is ready)
        QtCore.QTimer.singleShot(50, self._initialize_default_tool)
        
        # Install event filter on all child widgets to forward QPT hotkeys
        self._install_event_filter_recursive(self)
        
        print("[QPT] OK: QuickPaintPalette.init_ui completed")
    
    def keyPressEvent(self, event):
        """
        Forward QPT-related keys to main window so hotkeys work when sidebar has focus.
        """
        if self._forward_qpt_key(event):
            return
        super().keyPressEvent(event)
    
    def eventFilter(self, obj, event):
        """
        Event filter to capture key events from child widgets and forward QPT hotkeys.
        """
        if event.type() == QtCore.QEvent.Type.KeyPress:
            if self._forward_qpt_key(event):
                return True  # Event handled
        return super().eventFilter(obj, event)
    
    def _forward_qpt_key(self, event) -> bool:
        """
        Check if key is a QPT hotkey and forward to main window.
        Returns True if key was forwarded.
        """
        # QPT hotkeys that should be forwarded
        qpt_keys = (
            QtCore.Qt.Key.Key_Q.value,
            QtCore.Qt.Key.Key_S.value,
            QtCore.Qt.Key.Key_C.value,
            QtCore.Qt.Key.Key_E.value,
            QtCore.Qt.Key.Key_F.value,
            QtCore.Qt.Key.Key_D.value,
            QtCore.Qt.Key.Key_Escape.value,
            QtCore.Qt.Key.Key_F1.value
        )
        
        if event.key() in qpt_keys:
            # Forward to main window's keyPressEvent
            import globals_
            if hasattr(globals_, 'mainWindow') and globals_.mainWindow:
                globals_.mainWindow.keyPressEvent(event)
                return True
        return False
    
    def _install_event_filter_recursive(self, widget):
        """Install event filter on widget and all its children."""
        widget.installEventFilter(self)
        for child in widget.findChildren(QtWidgets.QWidget):
            child.installEventFilter(self)
    
    def _initialize_default_tool(self):
        """Initialize with QPT as the default active tool"""
        from quickpaint.core.tool_manager import ToolType
        self.tool_manager.activate_tool(ToolType.QPT_SMART_PAINT)
        # Deselect any Fill/Deco radio buttons
        self.tool_button_group.setExclusive(False)
        for btn in self.tool_button_group.buttons():
            btn.setChecked(False)
        self.tool_button_group.setExclusive(True)
        self._update_tool_label("Active: Quick Paint", "#2d5a2d")
    
    def _on_qpt_mode_selected(self, mode: str):
        """Handle QPT mode selection from combobox - deselect Fill/Deco radio buttons"""
        # Deselect all radio buttons in the button group
        self.tool_button_group.setExclusive(False)
        for btn in self.tool_button_group.buttons():
            btn.setChecked(False)
        self.tool_button_group.setExclusive(True)
    
    def _on_tab_changed(self, index: int):
        """Handle tab change - activate appropriate tool for new tab"""
        from quickpaint.core.tool_manager import ToolType
        
        # Skip if same tab (avoid redundant deactivation/activation)
        if index == self._current_tab_index:
            return
        
        old_index = self._current_tab_index
        self._current_tab_index = index
        
        # Stop QPT painting when leaving the QPT tab
        if old_index == 0 and self.quick_paint_tab.is_painting():
            self.quick_paint_tab.qpt_widget.on_stop_painting()
            print("[QPT] Stopped painting due to tab change")
        
        # Don't deactivate tools or change active tool when switching within Quick Paint tabs
        # Tools should only change via radio buttons or hotkeys
        # Just update the cursor to ensure it's correct for the active tool
        import globals_
        if hasattr(globals_, 'mainWindow') and globals_.mainWindow and globals_.mainWindow.view:
            # Update cursor based on active tool
            if self.tool_manager.is_any_fill_active():
                globals_.mainWindow.view.setCursor(QtCore.Qt.CursorShape.CrossCursor)
            else:
                globals_.mainWindow.view.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
    
    def _update_tool_label(self, text: str, bg_color: str):
        """Update the active tool label"""
        self.active_tool_label.setText(text)
        self.active_tool_label.setStyleSheet(
            f"background-color: {bg_color}; color: white; padding: 2px 6px; "
            "font-weight: bold; font-size: 9pt;"
        )
    
    def _on_tool_changed(self, new_tool, old_tool):
        """Handle tool change from tool manager"""
        from quickpaint.core.tool_manager import ToolType
        
        display_name = self.tool_manager.get_tool_display_name()
        
        # Cancel fill area when switching away from fill/deco tools
        if new_tool not in (ToolType.FILL_PAINT, ToolType.DECO_FILL):
            if old_tool in (ToolType.FILL_PAINT, ToolType.DECO_FILL):
                self.fill_paint_tab.fill_engine.cancel_fill()
                self.fill_paint_tab.status_label.setText("Idle")
        
        # Update label with appropriate color
        if new_tool in (ToolType.QPT_SMART_PAINT, ToolType.QPT_SINGLE_TILE, 
                        ToolType.QPT_ERASER, ToolType.QPT_SHAPE_CREATOR):
            self._update_tool_label(f"Active: {display_name}", "#2d5a2d")
            # Deselect Fill/Deco radio buttons when a QPT mode is active
            self.tool_button_group.setExclusive(False)
            for btn in self.tool_button_group.buttons():
                btn.setChecked(False)
            self.tool_button_group.setExclusive(True)
        elif new_tool == ToolType.FILL_PAINT:
            self._update_tool_label(f"Active: {display_name}", "#3d6a9f")
            # Fill radio button is already checked via button group
        elif new_tool == ToolType.DECO_FILL:
            self._update_tool_label(f"Active: {display_name}", "#5a3d7a")
            # Deco radio button is already checked via button group
        elif new_tool == ToolType.TILESET_OVERLAY:
            self._update_tool_label(f"Active: {display_name}", "#7a5a3d")
        else:
            self._update_tool_label("No Tool", "#555555")
        
        # Update cursor on the MAIN WINDOW's graphics view, not the sidebar
        self._update_canvas_cursor(new_tool)
    
    def _update_canvas_cursor(self, tool):
        """Update cursor on the main canvas based on active tool"""
        from quickpaint.core.tool_manager import ToolType
        import globals_
        
        if not hasattr(globals_, 'mainWindow') or globals_.mainWindow is None:
            return
        
        # Get the graphics view (canvas)
        view = globals_.mainWindow.view
        if view is None:
            return
        
        if tool == ToolType.FILL_PAINT or tool == ToolType.DECO_FILL:
            view.setCursor(QtCore.Qt.CursorShape.CrossCursor)
        else:
            view.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
    
    def handle_hotkey(self, key: int) -> bool:
        """
        Handle hotkey press.
        
        Args:
            key: Qt key code
            
        Returns:
            True if hotkey was handled
        """
        from quickpaint.core.tool_manager import ToolType
        
        # Use .value for enum comparison since key is an int from event.key()
        if key == QtCore.Qt.Key.Key_Q.value:
            # If QPT tab is already active and tool is SmartPaint, toggle Start/Stop painting
            if (self.tabs.currentIndex() == 0 and 
                self.tool_manager.active_tool == ToolType.QPT_SMART_PAINT):
                # Toggle painting
                if self.quick_paint_tab.is_painting():
                    self.quick_paint_tab.qpt_widget.on_stop_painting()
                    print("[QPT] Q hotkey: Stopped painting")
                else:
                    self.quick_paint_tab.qpt_widget.on_start_painting()
                    print("[QPT] Q hotkey: Started painting")
                return True
            else:
                # Switch to QPT and activate SmartPaint
                self.tabs.setCurrentIndex(0)
                self.quick_paint_tab.qpt_widget.set_mode("SmartPaint")
                self.tool_manager.activate_tool(ToolType.QPT_SMART_PAINT)
                print("[QPT] Q hotkey: Activated QPT SmartPaint")
                return True
            
        elif key == QtCore.Qt.Key.Key_S.value:
            # Switch to QPT tab and activate Single Tile mode
            self.tabs.setCurrentIndex(0)
            self.quick_paint_tab.qpt_widget.set_mode("Single Tile")
            self.tool_manager.activate_tool(ToolType.QPT_SINGLE_TILE)
            print("[QPT] S hotkey: Activated Single Tile mode")
            return True
            
        elif key == QtCore.Qt.Key.Key_C.value:
            # Switch to QPT tab and activate Shape Creator mode
            self.tabs.setCurrentIndex(0)
            self.quick_paint_tab.qpt_widget.set_mode("Shape Creator")
            self.tool_manager.activate_tool(ToolType.QPT_SHAPE_CREATOR)
            print("[QPT] C hotkey: Activated Shape Creator mode")
            return True
            
        elif key == QtCore.Qt.Key.Key_E.value:
            # Switch to QPT tab and activate Eraser mode
            self.tabs.setCurrentIndex(0)
            self.quick_paint_tab.qpt_widget.set_mode("Eraser")
            self.tool_manager.activate_tool(ToolType.QPT_ERASER)
            print("[QPT] E hotkey: Activated Eraser mode")
            return True
            
        elif key == QtCore.Qt.Key.Key_F.value:
            # Switch to Fill tab and activate Fill Tool
            self.tabs.setCurrentIndex(1)
            self.fill_paint_tab.activate()
            return True
            
        elif key == QtCore.Qt.Key.Key_D.value:
            # Switch to Fill tab and cycle through deco containers
            self.tabs.setCurrentIndex(1)
            self.fill_paint_tab.cycle_deco_container()
            return True
            
        elif key == QtCore.Qt.Key.Key_Escape.value:
            # Cancel current operation
            if self.tabs.currentIndex() == 0:
                return self.quick_paint_tab.handle_key_event(key)
            elif self.tabs.currentIndex() == 1:
                return self.fill_paint_tab.handle_key_event(key)
            return False
        
        return False
    
    def get_quick_paint_tab(self):
        """Get the Quick Paint tab"""
        return self.quick_paint_tab
    
    def get_fill_paint_tab(self):
        """Get the Fill Paint tab"""
        return self.fill_paint_tab
    
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
        # Check which tab is active and route accordingly
        current_tab = self.tabs.currentIndex()
        
        if current_tab == 0:  # Quick Paint
            return self.quick_paint_tab.handle_mouse_event(event_type, pos, button)
        elif current_tab == 1:  # Fill Paint
            return self.fill_paint_tab.handle_mouse_event(event_type, pos, button)
        
        return False
    
    def get_outline(self) -> List[tuple]:
        """Get the current painting outline"""
        return self.quick_paint_tab.get_outline()
    
    def get_outline_with_types(self) -> List[tuple]:
        """Get the current painting outline with tile types"""
        return self.quick_paint_tab.get_outline_with_types()
    
    def get_fill_preview(self) -> List[tuple]:
        """Get the current fill preview positions"""
        return self.fill_paint_tab.get_fill_preview()
    
    def is_painting(self) -> bool:
        """Check if currently painting"""
        return self.quick_paint_tab.is_painting()
    
    def is_fill_active(self) -> bool:
        """Check if fill or deco tool is active"""
        from quickpaint.core.tool_manager import ToolType
        return (self.tool_manager.is_active(ToolType.FILL_PAINT) or 
                self.tool_manager.is_active(ToolType.DECO_FILL))
    
    def reset(self):
        """
        Reset QPT to default state.
        Call this when level changes, area changes, or area settings are modified.
        """
        from quickpaint.core.tool_manager import ToolType
        
        # Reset both tabs
        self.quick_paint_tab.reset()
        self.fill_paint_tab.reset()
        
        # Switch to QPT tab and activate QPT tool
        self.tabs.setCurrentIndex(0)
        self.quick_paint_tab.qpt_widget.set_mode("SmartPaint")
        self.tool_manager.activate_tool(ToolType.QPT_SMART_PAINT)
        # Deselect Fill/Deco radio buttons
        self.tool_button_group.setExclusive(False)
        for btn in self.tool_button_group.buttons():
            btn.setChecked(False)
        self.tool_button_group.setExclusive(True)
        
        print("[QuickPaintPalette] Reset complete - QPT activated")
