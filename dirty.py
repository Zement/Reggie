from PyQt6 import QtCore

import globals_

def SetDirty(noautosave = False):
    if globals_.DirtyOverride > 0: return

    if not noautosave: globals_.AutoSaveDirty = True
    if globals_.Dirty: return

    globals_.Dirty = True
    try:
        globals_.mainWindow.UpdateTitle()
    except Exception:
        pass


# Define which group each setting belongs to
# Note: Using 'Main' instead of 'General' to avoid QSettings URL encoding to %General
SETTING_GROUPS = {
    'View': ['ShowSprites', 'ShowSpriteImages', 'ShowLocations', 'ShowComments', 
             'ShowPaths', 'ShowCollisions', 'RealViewEnabled', 'GridType'],
    'Freeze': ['FreezeObjects', 'FreezeSprites', 'FreezeEntrances', 
               'FreezeLocations', 'FreezePaths', 'FreezeComments'],
    'Preferences': ['Translation', 'ZoneEntIndicators', 'ZoneBoundIndicators',
                    'ResetDataWhenHiding', 'HideResetSpritedata', 'EnablePadding',
                    'PaddingLength', 'PlaceObjectsAtFullSize', 'InsertPathNode', 'Theme'],
    # Geometry settings are NOT in a group - they stay at root level for Qt
}

def _get_group_for_setting(name):
    """Determine which group a setting belongs to"""
    if name in ['MainWindowState', 'MainWindowGeometry', 'ToolbarActs', 'AutoSaveFilePath', 'AutoSaveFileData']:
        return None
    
    # Check predefined groups
    for group, settings in SETTING_GROUPS.items():
        if name in settings:
            return group
    
    # Check for dynamic patterns
    if name.startswith(('StageGamePath_', 'TextureGamePath_', 'LastLevel_', 'PatchPath_')):
        return 'GamePaths'
    
    # Default to Main (not General to avoid %General encoding)
    return 'Main'

def setting(name, default=None):
    """
    Thin wrapper around QSettings that properly handles type conversion
    """
    # Try to find the setting in its group first
    group = _get_group_for_setting(name)
    
    # Check both with and without group for backwards compatibility
    if group is None:
        # Geometry settings are at root level
        if globals_.settings.contains(name):
            value = globals_.settings.value(name)
        else:
            return default
    else:
        full_key = f"{group}/{name}"
        
        if globals_.settings.contains(full_key):
            value = globals_.settings.value(full_key)
        elif globals_.settings.contains(name):
            # Fallback to old location (no group)
            value = globals_.settings.value(name)
        else:
            return default
    
    # Handle None/null values
    if value is None or value == 'None' or value == '@Invalid()':
        return None
    
    # If we have a default, try to convert to its type
    if default is not None:
        target_type = type(default)
        
        # Handle bool specially (QSettings returns strings 'true'/'false')
        if target_type is bool:
            if isinstance(value, bool):
                return value
            return value in ('true', 'True', '1', 1, True)
        
        # Handle other types
        try:
            if target_type in (int, float, str):
                return target_type(value)
            elif target_type is dict:
                return value if isinstance(value, dict) else default
            elif target_type is QtCore.QByteArray:
                return value if isinstance(value, QtCore.QByteArray) else default
        except (ValueError, TypeError):
            return default
    
    # No default provided - try to intelligently convert the value
    if isinstance(value, str):
        if value.lower() in ('true', 'false'):
            return value.lower() == 'true'
        try:
            if '.' not in value:
                return int(value)
            return float(value)
        except ValueError:
            return value
    
    return value


def _normalize_path_for_settings(path):
    """
    Normalize a file path for storage in settings.ini
    Format: C:/folder\\subfolder\\file (forward slash after drive, single backslash for separators)
    Note: QSettings will automatically escape backslashes when writing to INI file
    """
    if not path or not isinstance(path, str):
        return path
    
    import os
    # Normalize to Windows format first
    path = os.path.normpath(path)
    
    # Check if it's a Windows path with drive letter
    if len(path) >= 2 and path[1] == ':':
        # Windows path: C:\folder\subfolder
        # Convert to: C:/folder\subfolder (single backslashes - QSettings will escape them)
        drive = path[0:2]  # e.g., "C:"
        rest = path[3:] if len(path) > 3 else ""  # Skip "C:\" to get "folder\subfolder"
        # Use single backslashes - QSettings will double them when writing to INI
        return drive + '/' + rest if rest else drive + '/'
    else:
        # UNC or relative path - keep as-is, QSettings will handle escaping
        return path

def setSetting(name, value):
    """
    Thin wrapper around QSettings that properly stores values in groups
    """
    assert isinstance(name, str)
    
    # Normalize paths before saving
    if isinstance(value, str) and ('Path' in name or 'Level' in name) and ('\\' in value or '/' in value):
        value = _normalize_path_for_settings(value)
    
    # Determine the group for this setting
    group = _get_group_for_setting(name)
    
    # Write using full key path to avoid URL encoding of group names
    # If group is None (Geometry settings), write to root level
    if group is None:
        globals_.settings.setValue(name, value)
    else:
        full_key = f"{group}/{name}"
        globals_.settings.setValue(full_key, value)


def ensureSettingsVisible():
    """
    Ensures all important settings are written to the settings file,
    even if they have default values. This makes the settings file
    more user-friendly and editable.
    """
    import globals_
    
    # List of settings that should always be visible in the file
    always_visible = [
        ('ShowSprites', True), ('ShowSpriteImages', True), ('ShowLocations', True),
        ('ShowComments', True), ('ShowPaths', True), ('ShowCollisions', False),
        ('RealViewEnabled', True), ('FreezeObjects', False), ('FreezeSprites', False),
        ('FreezeEntrances', False), ('FreezeLocations', False), ('FreezePaths', False),
        ('FreezeComments', False), ('ZoneEntIndicators', False), ('ZoneBoundIndicators', False),
        ('ResetDataWhenHiding', False), ('HideResetSpritedata', False), ('EnablePadding', False),
        ('PaddingLength', 0), ('PlaceObjectsAtFullSize', True), ('InsertPathNode', False),
    ]
    
    # Write each setting if it doesn't exist
    for name, default in always_visible:
        group = _get_group_for_setting(name)
        if not globals_.settings.contains(f"{group}/{name}") and not globals_.settings.contains(name):
            setSetting(name, default)

def reorganizeSettings():
    """
    Reorganizes existing settings from flat structure into groups.
    This is a one-time migration for existing settings files.
    Also normalizes all file paths to consistent format.
    """
    import globals_
    
    # Get all keys at root level (not in groups)
    all_keys = [k for k in globals_.settings.allKeys() if '/' not in k]
    
    if not all_keys:
        # Already organized, but normalize all existing paths
        normalizeAllPaths()
        return
    
    # Read all values
    values = {}
    for key in all_keys:
        value = globals_.settings.value(key)
        # Normalize paths during migration
        if isinstance(value, str) and ('Path' in key or 'Level' in key) and ('\\' in value or '/' in value):
            value = _normalize_path_for_settings(value)
        values[key] = value
    
    # Remove old keys
    for key in all_keys:
        globals_.settings.remove(key)
    
    # Write back with groups in specific order
    # Order: Main, View, Freeze, Preferences, GamePaths, then Geometry at root level
    group_order = ['Main', 'View', 'Freeze', 'Preferences', 'GamePaths', None]
    
    for group_name in group_order:
        for key, value in values.items():
            group = _get_group_for_setting(key)
            if group == group_name:
                # Write using full key path to avoid URL encoding
                if group is None:
                    # Geometry settings stay at root level
                    globals_.settings.setValue(key, value)
                else:
                    full_key = f"{group}/{key}"
                    globals_.settings.setValue(full_key, value)
    
    globals_.settings.sync()

def normalizeAllPaths():
    """
    Normalizes all file paths in settings to consistent format.
    Called when reading or writing any path to ensure all paths are normalized.
    """
    import globals_
    
    # Get all keys (including grouped ones)
    all_keys = globals_.settings.allKeys()
    
    # Find and normalize all path-related settings
    for key in all_keys:
        key_name = key.split('/')[-1] if '/' in key else key
        if ('Path' in key_name or 'Level' in key_name):
            value = globals_.settings.value(key)
            if isinstance(value, str) and ('\\' in value or '/' in value):
                normalized = _normalize_path_for_settings(value)
                if normalized != value:
                    globals_.settings.setValue(key, normalized)
    
    globals_.settings.sync()

