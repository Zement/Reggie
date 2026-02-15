"""
Tool Manager - Tracks and manages the active painting tool.

Provides centralized tool state management for QPT, Fill Tool, and Deco Fill tools.
"""
from enum import Enum, auto
from typing import Optional, Callable, List
from PyQt6 import QtCore


class ToolType(Enum):
    """Available tool types"""
    NONE = auto()
    # Quick Paint modes
    QPT_SMART_PAINT = auto()
    QPT_SINGLE_TILE = auto()
    QPT_ERASER = auto()
    QPT_SHAPE_CREATOR = auto()
    # Fill tools
    FILL_PAINT = auto()
    DECO_FILL = auto()
    # Other
    TILESET_OVERLAY = auto()


class ToolManager(QtCore.QObject):
    """
    Manager for tracking the active painting tool.
    
    Use get_tool_manager() to get the singleton instance.
    
    Signals:
        tool_changed: Emitted when the active tool changes (new_tool, old_tool)
        tool_deactivated: Emitted when the active tool is deactivated
    """
    
    # Signals
    tool_changed = QtCore.pyqtSignal(object, object)  # new_tool, old_tool
    tool_deactivated = QtCore.pyqtSignal()
    
    def __init__(self):
        super().__init__()
        
        self._active_tool: ToolType = ToolType.NONE
        self._deco_containers: List[int] = []  # IDs of deco containers for cycling
        self._current_deco_index: int = 0
        
        # Callbacks for tool activation/deactivation
        self._on_activate_callbacks: dict = {}
        self._on_deactivate_callbacks: dict = {}
    
    @property
    def active_tool(self) -> ToolType:
        """Get the currently active tool"""
        return self._active_tool
    
    def is_active(self, tool_type: ToolType) -> bool:
        """Check if a specific tool is active"""
        return self._active_tool == tool_type
    
    def is_any_qpt_active(self) -> bool:
        """Check if any QPT mode is active"""
        return self._active_tool in [
            ToolType.QPT_SMART_PAINT,
            ToolType.QPT_SINGLE_TILE,
            ToolType.QPT_ERASER,
            ToolType.QPT_SHAPE_CREATOR
        ]
    
    def is_any_fill_active(self) -> bool:
        """Check if any fill tool is active"""
        return self._active_tool in [
            ToolType.FILL_PAINT,
            ToolType.DECO_FILL
        ]
    
    def is_any_tool_active(self) -> bool:
        """Check if any tool is active (not NONE)"""
        return self._active_tool != ToolType.NONE
    
    def activate_tool(self, tool_type: ToolType) -> bool:
        """
        Activate a tool, deactivating the previous one.
        
        Args:
            tool_type: The tool to activate
            
        Returns:
            True if activation succeeded
        """
        if tool_type == self._active_tool:
            return True  # Already active
        
        old_tool = self._active_tool
        
        # Deactivate current tool
        if old_tool != ToolType.NONE:
            self._call_deactivate_callback(old_tool)
        
        # Activate new tool
        self._active_tool = tool_type
        
        if tool_type != ToolType.NONE:
            self._call_activate_callback(tool_type)
        
        # Emit signal
        self.tool_changed.emit(tool_type, old_tool)
        
        print(f"[ToolManager] Tool changed: {old_tool.name} -> {tool_type.name}")
        return True
    
    def deactivate_tool(self):
        """Deactivate the current tool"""
        if self._active_tool != ToolType.NONE:
            old_tool = self._active_tool
            self._call_deactivate_callback(old_tool)
            self._active_tool = ToolType.NONE
            self.tool_changed.emit(ToolType.NONE, old_tool)
            self.tool_deactivated.emit()
            print(f"[ToolManager] Tool deactivated: {old_tool.name}")
    
    def deactivate_all(self):
        """Deactivate all tools - call when leaving the QPT main tab"""
        self.deactivate_tool()
    
    def register_activate_callback(self, tool_type: ToolType, callback: Callable):
        """Register a callback for when a tool is activated"""
        self._on_activate_callbacks[tool_type] = callback
    
    def register_deactivate_callback(self, tool_type: ToolType, callback: Callable):
        """Register a callback for when a tool is deactivated"""
        self._on_deactivate_callbacks[tool_type] = callback
    
    def _call_activate_callback(self, tool_type: ToolType):
        """Call the activation callback for a tool"""
        if tool_type in self._on_activate_callbacks:
            try:
                self._on_activate_callbacks[tool_type]()
            except Exception as e:
                print(f"[ToolManager] Error in activate callback for {tool_type.name}: {e}")
    
    def _call_deactivate_callback(self, tool_type: ToolType):
        """Call the deactivation callback for a tool"""
        if tool_type in self._on_deactivate_callbacks:
            try:
                self._on_deactivate_callbacks[tool_type]()
            except Exception as e:
                print(f"[ToolManager] Error in deactivate callback for {tool_type.name}: {e}")
    
    # =========================================================================
    # DECO CONTAINER MANAGEMENT
    # =========================================================================
    
    def register_deco_container(self, container_id: int):
        """Register a deco container for cycling with D key"""
        if container_id not in self._deco_containers:
            self._deco_containers.append(container_id)
    
    def unregister_deco_container(self, container_id: int):
        """Unregister a deco container"""
        if container_id in self._deco_containers:
            self._deco_containers.remove(container_id)
            if self._current_deco_index >= len(self._deco_containers):
                self._current_deco_index = 0
    
    def cycle_deco_container(self) -> Optional[int]:
        """
        Cycle to the next deco container.
        
        Returns:
            The ID of the next deco container, or None if no containers
        """
        if not self._deco_containers:
            return None
        
        self._current_deco_index = (self._current_deco_index + 1) % len(self._deco_containers)
        return self._deco_containers[self._current_deco_index]
    
    def get_current_deco_container(self) -> Optional[int]:
        """Get the current deco container ID"""
        if not self._deco_containers:
            return None
        return self._deco_containers[self._current_deco_index]
    
    # =========================================================================
    # DISPLAY NAME
    # =========================================================================
    
    def get_tool_display_name(self) -> str:
        """Get a human-readable name for the current tool"""
        names = {
            ToolType.NONE: "No Tool",
            ToolType.QPT_SMART_PAINT: "Quick Paint: SmartPaint",
            ToolType.QPT_SINGLE_TILE: "Quick Paint: SingleTile",
            ToolType.QPT_ERASER: "Quick Paint: Eraser",
            ToolType.QPT_SHAPE_CREATOR: "Quick Paint: ShapeCreator",
            ToolType.FILL_PAINT: "Fill Paint",
            ToolType.DECO_FILL: "Deco Fill Paint",
            ToolType.TILESET_OVERLAY: "Tileset Overlay",
        }
        return names.get(self._active_tool, "Unknown")


# Global instance (lazy initialization)
_tool_manager_instance: Optional[ToolManager] = None


def get_tool_manager() -> ToolManager:
    """Get the global ToolManager instance"""
    global _tool_manager_instance
    if _tool_manager_instance is None:
        _tool_manager_instance = ToolManager()
    return _tool_manager_instance
