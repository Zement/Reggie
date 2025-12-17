"""
Level Integration - Connects the painting engine to Reggie's level system

This module provides the bridge between the QPT painting engine and Reggie's
level editing system, handling:
- Object creation via CreateObject()
- Object search database maintenance
- Undo/redo integration
- Level state synchronization
"""
from typing import List, Tuple, Dict, Optional, Set, TYPE_CHECKING
from dataclasses import dataclass

from .engine import PaintingEngine, ObjectPlacement, PaintingMode

# Import Reggie modules when available
try:
    import globals_
    from levelitems import ObjectItem
    REGGIE_AVAILABLE = True
except ImportError:
    REGGIE_AVAILABLE = False
    globals_ = None
    ObjectItem = None


class LevelIntegration:
    """
    Integrates the painting engine with Reggie's level system.
    
    Handles:
    - Creating objects in the level via CreateObject()
    - Maintaining the object search database for fast lookups
    - Synchronizing with Reggie's undo/redo system
    - Managing layer selection
    """
    
    def __init__(self, main_window=None):
        """
        Initialize the level integration.
        
        Args:
            main_window: Reference to Reggie's main window (ReggieWindow)
        """
        self.main_window = main_window
        self.engine = PaintingEngine()
        
        # Connect engine callbacks
        self.engine.on_place_object = self._on_place_object
        self.engine.on_outline_updated = self._on_outline_updated
        self.engine.on_painting_finished = self._on_painting_finished
        
        # Outline items for visual feedback
        self._outline_items: List = []
        
        # Track objects created in current session for undo
        self._session_objects: List = []
    
    def set_main_window(self, main_window):
        """Set the main window reference"""
        self.main_window = main_window
    
    def refresh_object_database(self):
        """
        Refresh the object search database from the current level.
        
        Scans all layers and builds a lookup table for fast tile queries.
        """
        if not REGGIE_AVAILABLE or not globals_.Area:
            return
        
        database = {}
        
        # Scan all layers
        for layer_idx, layer in enumerate(globals_.Area.layers):
            for obj in layer:
                if isinstance(obj, ObjectItem):
                    # Add all tiles covered by this object
                    for dy in range(obj.height):
                        for dx in range(obj.width):
                            x = obj.objx + dx
                            y = obj.objy + dy
                            database[(x, y, layer_idx)] = obj.type
        
        self.engine.update_object_database(database)
        print(f"[LevelIntegration] Refreshed object database: {len(database)} tiles")
    
    def _on_place_object(self, placement: ObjectPlacement):
        """
        Callback when the engine wants to place an object.
        
        Args:
            placement: ObjectPlacement describing the object to create
        """
        if not self.main_window or not REGGIE_AVAILABLE:
            print(f"[LevelIntegration] Would place: {placement}")
            return
        
        try:
            # Create the object using Reggie's CreateObject
            obj = self.main_window.CreateObject(
                tileset=placement.tileset,
                object_num=placement.object_id,
                layer=placement.layer,
                x=placement.x,
                y=placement.y,
                width=placement.width,
                height=placement.height
            )
            
            if obj:
                self._session_objects.append(obj)
                
                # Update the object database
                for dy in range(placement.height):
                    for dx in range(placement.width):
                        self.engine.add_to_object_database(
                            placement.x + dx,
                            placement.y + dy,
                            placement.layer,
                            placement.object_id
                        )
                
                print(f"[LevelIntegration] Created object: tileset={placement.tileset}, "
                      f"obj={placement.object_id}, pos=({placement.x}, {placement.y})")
        
        except Exception as e:
            print(f"[LevelIntegration] Error creating object: {e}")
    
    def _on_outline_updated(self, positions: List[Tuple[int, int]]):
        """
        Callback when the outline preview is updated.
        
        Args:
            positions: List of (x, y) positions in the outline
        """
        # Clear existing outline items
        self._clear_outline()
        
        if not positions:
            return
        
        # Create visual outline items
        # This would create semi-transparent preview objects
        # For now, just store the positions
        print(f"[LevelIntegration] Outline updated: {len(positions)} positions")
        
        # TODO: Create visual outline items in the scene
        # This requires creating temporary graphics items that show
        # where tiles will be placed
    
    def _on_painting_finished(self, placements: List[ObjectPlacement]):
        """
        Callback when painting is finished.
        
        Args:
            placements: List of ObjectPlacement objects that were placed
        """
        self._clear_outline()
        
        print(f"[LevelIntegration] Painting finished: {len(placements)} objects placed")
        
        # Reset session objects for next painting session
        self._session_objects = []
    
    def _clear_outline(self):
        """Clear the outline preview items"""
        # TODO: Remove outline items from scene
        self._outline_items = []
    
    # =========================================================================
    # PUBLIC API
    # =========================================================================
    
    def start_painting(self, x: int, y: int, immediate: bool = False) -> bool:
        """
        Start a painting operation.
        
        Args:
            x, y: Starting position in tile coordinates
            immediate: If True, paint immediately; if False, show outline
        
        Returns:
            True if painting started successfully
        """
        # Refresh the object database before starting
        self.refresh_object_database()
        
        # Set the mode
        self.engine.set_immediate_mode(immediate)
        
        # Start painting
        return self.engine.start_painting((x, y))
    
    def update_painting(self, x: int, y: int) -> bool:
        """
        Update the painting operation as the mouse moves.
        
        Args:
            x, y: Current position in tile coordinates
        
        Returns:
            True if update was processed
        """
        return self.engine.update_painting((x, y))
    
    def finish_painting(self, x: int, y: int) -> List[ObjectPlacement]:
        """
        Finish the painting operation.
        
        Args:
            x, y: Final position in tile coordinates
        
        Returns:
            List of ObjectPlacement objects that were placed
        """
        return self.engine.finish_painting((x, y))
    
    def cancel_painting(self):
        """Cancel the current painting operation"""
        self.engine.cancel_painting()
        self._clear_outline()
    
    def is_painting(self) -> bool:
        """Check if currently painting"""
        return self.engine.is_painting()
    
    def get_outline(self) -> List[Tuple[int, int]]:
        """Get the current outline positions"""
        return self.engine.get_outline()
    
    # =========================================================================
    # BRUSH AND LAYER MANAGEMENT
    # =========================================================================
    
    def set_brush(self, brush):
        """Set the current brush"""
        self.engine.set_brush(brush)
    
    def set_layer(self, layer: int):
        """Set the current layer"""
        self.engine.set_layer(layer)
    
    def get_current_layer(self) -> int:
        """Get the current layer"""
        return self.engine.layer


# Global instance for easy access
_level_integration: Optional[LevelIntegration] = None


def get_level_integration() -> LevelIntegration:
    """Get the global LevelIntegration instance"""
    global _level_integration
    if _level_integration is None:
        _level_integration = LevelIntegration()
    return _level_integration


def initialize_level_integration(main_window) -> LevelIntegration:
    """Initialize the level integration with the main window"""
    global _level_integration
    _level_integration = LevelIntegration(main_window)
    return _level_integration
