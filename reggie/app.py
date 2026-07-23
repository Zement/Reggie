#!/usr/bin/python
# -*- coding: latin-1 -*-

# Reggie Next - New Super Mario Bros. Wii Level Editor
# Milestone 4
# Copyright (C) 2009-2020 Treeki, Tempus, angelsl, JasonP27, Kamek64,
# MalStar1000, RoadrunnerWMC, AboodXD, John10v10, TheGrop, CLF78,
# Zementblock, Danster64

# This file is part of Reggie Next.

# Reggie Next is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# Reggie Next is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with Reggie Next.  If not, see <http://www.gnu.org/licenses/>.


# reggie.py
# This is the main executable for Reggie Next.


################################################################
################################################################

# Python version: sanity check
minimum = (3, 5)
import sys

if sys.version_info < minimum:
    errormsg = 'Please update your copy of Python to ' + '.'.join(map(str, minimum)) + \
               ' or greater. Currently running on: ' + sys.version[:5]

    raise Exception(errormsg)

# Stdlib imports
import os.path
import time
import traceback

# PyQt6: import, and error msg if not installed
try:
    from PyQt6 import QtCore, QtGui, QtWidgets
except (ImportError, NameError):
    errormsg = 'PyQt6 is not installed for this Python installation. Go online and download it.'
    raise Exception(errormsg)
Qt = QtCore.Qt

version = map(int, QtCore.QT_VERSION_STR.split('.'))
min_version = "6.9"
pqt_min = map(int, min_version.split('.'))
for v, c in zip(version, pqt_min):
    if c > v:
        # lower version
        errormsg = 'Please update your copy of PyQt to ' + min_version \
                 + ' or greater. Currently running on: ' + QtCore.QT_VERSION_STR

        raise Exception(errormsg) from None
    elif c < v:
        # higher version
        break

################################################################################
################################################################################
################################################################################

# Local imports.
#
# This module only holds main() + _excepthook, so it imports just what THOSE need
# (ReggieWindow lives in reggie/ui/window.py and carries its own imports). The
# full editor-wide import list was trimmed here after the ReggieWindow split; see
# _docs/plan/REFACTORING_ANALYSIS.md.
import reggie.sprites as sprites
from reggie.core import globals_
from reggie.core import spritelib as SLib
from reggie.core.dirty import setting, setSetting
from reggie.core.tiles import LoadOverrides
from reggie.io.misc import (
    LoadActionsLists, FilesAreMissing, module_path,
    SetGamePaths, areValidGamePaths, validateFolderForPatch,
)
from reggie.io.translation import LoadTranslation
from reggie.ui.dialogs import AutoSavedInfoDialog
from reggie.ui.window import ReggieWindow
from reggie.ui import deferred
from reggie.ui import qpt_boot

# Quick Paint Tool boot state lives on reggie.ui.qpt_boot; it's loaded lazily in
# main() after the QApplication exists (importing quickpaint eagerly breaks the
# import chain). ui/gamedef/patch-dialog imports are likewise deferred into main().

################################################################################
################################################################################
################################################################################


# NOTE: ReggieWindow now lives in reggie/ui/window.py; this module keeps the
# application entry point (main) and the excepthook. See
# _docs/plan/REFACTORING_ANALYSIS.md.

def _excepthook(*exc_info):
    """
    Custom unhandled exceptions handler
    """
    separator = '-' * 80
    logFile = "log.txt"
    notice = globals_.trans.string('ErrorDlg', 0, '[log]', logFile)

    timeString = time.strftime("%Y-%m-%d, %H:%M:%S")

    e = "".join(traceback.format_exception(*exc_info))
    short_string = str(exc_info[1])

    if len(short_string) > 200:
        short_string = short_string[:200] + f'... (see details for more)'

    sections = [separator, timeString, separator, short_string]
    msg = '\n'.join(sections)

    globals_.ErrMsg += '\n'.join([separator, timeString, separator, e])

    try:
        with open(logFile, "w", encoding="utf-8") as f:
            f.write(globals_.ErrMsg)

    except IOError:
        pass

    errorbox = QtWidgets.QMessageBox()
    errorbox.setIcon(QtWidgets.QMessageBox.Icon.Critical)
    errorbox.setWindowTitle("Reggie! Next - Unhandled Exception")
    errorbox.setDetailedText(e)

    errorbox.setText(notice + msg)
    errorbox.exec()

    globals_.DirtyOverride = 0

sys.excepthook = _excepthook


def main():
    """
    Main startup function for Reggie
    """

    # set High-DPI-Displays-related attributes before creating an application
    # QtGui.QGuiApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    if hasattr(QtGui.QGuiApplication, 'setHighDpiScaleFactorRoundingPolicy'):
        QtGui.QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.Round)

    # Create an application
    globals_.app = QtWidgets.QApplication(sys.argv)
    
    # Import all deferred modules now that QApplication exists. These used to be
    # injected into this module's globals via `global` decls; they now live on
    # reggie.ui.deferred so code outside reggie.py can reach them too (this
    # unblocks moving main()/ReggieWindow later). See reggie/ui/deferred.py.
    print("[BOOT] Importing deferred modules...")
    try:
        deferred.load()
        print("[BOOT] ✓ All deferred imports completed")
    except Exception as e:
        print(f"[BOOT] ✗ Error importing deferred modules: {e}")
        raise
    
    # Import QPT functions now that QApplication exists. State lives on
    # reggie.ui.qpt_boot (see that module) instead of reggie.py module globals.
    print("[BOOT] Importing QPT functions...")
    qpt_boot.load()

    # Go to the script path
    print("[BOOT] Setting up script path...")
    path = module_path()
    if path is not None:
        os.chdir(path)
    print("[BOOT] ✓ Script path set")

    # Create backup of settings
    print("[BOOT] Creating settings backup...")
    if os.path.isfile('settings.ini'):
        from shutil import copy2
        copy2('settings.ini', 'settings.ini.bak')
        del copy2
    print("[BOOT] ✓ Settings backup created")

    # Skip git version checking - it can cause Qt issues with subprocess
    # The fallback version in globals_.ReggieVersionShort is used instead
    
    # Load the settings
    print("[BOOT] Loading settings...")
    globals_.settings = QtCore.QSettings('settings.ini', QtCore.QSettings.Format.IniFormat)
    print("[BOOT] ✓ Settings loaded")
    
    # Migrate old settings format (remove typeof entries)
    print("[BOOT] Migrating settings...")
    try:
        def migrate_settings():
            """Remove old typeof entries from settings"""
            all_keys = globals_.settings.allKeys()
            typeof_keys = [key for key in all_keys if key.startswith('typeof(')]
            for key in typeof_keys:
                globals_.settings.remove(key)
        
        # Check if we need to migrate (if any typeof entries exist)
        if any(key.startswith('typeof(') for key in globals_.settings.allKeys()):
            migrate_settings()
            globals_.settings.sync()
        print("[BOOT] ✓ Settings migrated")
    except Exception as e:
        print(f"[BOOT] Warning: Could not migrate settings: {e}")
    
    # Reorganize settings into groups if they're still flat
    print("[BOOT] Reorganizing settings...")
    from reggie.core.dirty import reorganizeSettings, ensureSettingsVisible
    reorganizeSettings()
    print("[BOOT] ✓ Settings reorganized")

    # Check the version and set the UI style to Fusion by default
    print("[BOOT] Checking version...")
    if setting("ReggieVersion") is None:
        setSetting("ReggieVersion", globals_.ReggieVersionFloat)
        setSetting('uiStyle', "Fusion")
    print("[BOOT] ✓ Version checked")
    
    # Ensure all important settings are visible in the file
    print("[BOOT] Ensuring settings visible...")
    ensureSettingsVisible()
    globals_.settings.sync()
    print("[BOOT] ✓ Settings visible")
    
    # Clean up orphaned patch paths (patches deleted outside Reggie)
    print("[BOOT] Cleaning up orphaned paths...")
    from reggie.io.gamedef import cleanupOrphanedPatchPaths
    cleanupOrphanedPatchPaths()
    print("[BOOT] ✓ Orphaned paths cleaned")

    # 4.0 -> oldest version with settings.ini compatible with the current version
    print("[BOOT] Checking version compatibility...")
    if setting("ReggieVersion") < 4.0 or setting("ReggieVersion") > globals_.ReggieVersionFloat:
        warningBox = QtWidgets.QMessageBox(QtWidgets.QMessageBox.Icon.NoIcon, 'Unsupported settings file', 'Your settings.ini file is unsupported. Please remove it and run Reggie again.')
        warningBox.exec()
        sys.exit(1)
    print("[BOOT] ✓ Version compatible")

    # Load the translation (needs to happen first)
    print("[BOOT] Loading translation...")
    LoadTranslation()
    print("[BOOT] ✓ Translation loaded")

    # Check if required files are missing
    print("[BOOT] Checking for missing files...")
    if FilesAreMissing():
        sys.exit(1)
    print("[BOOT] ✓ All files present")

    # Load some requirements for spritelib
    print("[BOOT] Loading theme...")
    deferred.LoadTheme()
    print("[BOOT] ✓ Theme loaded")
    
    print("[BOOT] Loading overrides...")
    LoadOverrides()
    print("[BOOT] ✓ Overrides loaded")

    # Initialize UI scaling manager
    print("[BOOT] Initializing UI scaling...")
    from reggie.ui.ui_scaling import ScalingManager
    globals_.scalingManager = ScalingManager()
    globals_.scalingManager.loadSettings()
    print("[BOOT] ✓ UI scaling manager initialized")

    # Initialise spritelib
    print("[BOOT] Initializing spritelib...")
    SLib.OutlineColor = globals_.theme.color('smi')
    SLib.main()
    sprites.LoadBasics()
    print("[BOOT] ✓ Spritelib initialized")

    # Load the gamedef (including sprite image path, for which we need spritelib)
    print("[BOOT] Loading gamedef...")
    deferred.LoadGameDef(setting('LastGameDef'))
    print("[BOOT] ✓ Gamedef loaded")

    # Load remaining requirements
    print("[BOOT] Loading actions lists...")
    LoadActionsLists()
    print("[BOOT] ✓ Actions lists loaded")
    
    print("[BOOT] Loading number font...")
    deferred.LoadNumberFont()
    print("[BOOT] ✓ Number font loaded")
    
    print("[BOOT] Setting app style...")
    deferred.SetAppStyle()
    print("[BOOT] ✓ App style set")
    
    # Apply UI scaling after app style is set
    print("[BOOT] Applying UI scaling...")
    globals_.scalingManager.applyScaling()
    print("[BOOT] ✓ UI scaling applied")

    # Set the default window icon (used for random popups and stuff)
    print("[BOOT] Setting window icon...")
    globals_.app.setWindowIcon(deferred.GetIcon('reggie'))
    globals_.app.setApplicationDisplayName('Reggie! Next %s' % globals_.ReggieVersionShort)
    print("[BOOT] ✓ Window icon set")

    print("[BOOT] Loading global settings...")
    gt = setting('GridType')

    if gt not in ('checker', 'grid'):
        globals_.GridType = None
    else:
        globals_.GridType = gt

    globals_.CollisionsShown = setting('ShowCollisions', False)
    globals_.RealViewEnabled = setting('RealViewEnabled', True)
    globals_.ObjectsFrozen = setting('FreezeObjects', False)
    globals_.SpritesFrozen = setting('FreezeSprites', False)
    globals_.EntrancesFrozen  = setting('FreezeEntrances', False)
    globals_.LocationsFrozen = setting('FreezeLocations', False)
    globals_.PathsFrozen = setting('FreezePaths', False)
    globals_.CommentsFrozen = setting('FreezeComments', False)
    globals_.SpritesShown = setting('ShowSprites', True)
    globals_.SpriteImagesShown = setting('ShowSpriteImages', True)
    globals_.LocationsShown = setting('ShowLocations', True)
    globals_.CommentsShown = setting('ShowComments', True)
    globals_.PathsShown = setting('ShowPaths', True)
    globals_.DrawEntIndicators = setting('ZoneEntIndicators', False)
    globals_.BoundsDrawn = setting('ZoneBoundIndicators', False)
    globals_.ResetDataWhenHiding = setting('ResetDataWhenHiding', False)
    globals_.HideResetSpritedata = setting('HideResetSpritedata', False)
    globals_.EnablePadding = setting('EnablePadding', False)
    globals_.PaddingLength = int(setting('PaddingLength', 0))
    globals_.PlaceObjectsAtFullSize = setting('PlaceObjectsAtFullSize', True)
    globals_.InsertPathNode = setting('InsertPathNode', False)
    SLib.RealViewEnabled = globals_.RealViewEnabled
    print("[BOOT] ✓ Global settings loaded")

    # Choose a folder for the game
    print("[BOOT] Setting up game path dialog...")
    # Let the user pick a folder without restarting the editor if they fail
    # On macOS, use DontUseNativeDialog to show the title bar
    # Note: We defer accessing QFileDialog options to avoid Qt widget creation
    try:
        dialog_options = QtWidgets.QFileDialog.Option.ShowDirsOnly
        if sys.platform == 'darwin':
            dialog_options |= QtWidgets.QFileDialog.Option.DontUseNativeDialog
    except:
        # Fallback if accessing the enum fails
        dialog_options = 0x00000004  # ShowDirsOnly value
        if sys.platform == 'darwin':
            dialog_options |= 0x00000100  # DontUseNativeDialog value
    print("[BOOT] ✓ Game path dialog configured")
    
    # Track if we did initial setup
    did_initial_setup = False
    
    while not areValidGamePaths():
        did_initial_setup = True
        from reggie.io.misc import getExistingDirectoryWithSidebar
        stage_path = getExistingDirectoryWithSidebar(
            None,
            globals_.trans.string('ChangeGamePath', 0, '[game]', globals_.gamedef.name),
            '',
            dialog_options
        )

        if stage_path == '':
            sys.exit(0)

        stage_path = str(stage_path)
        
        # Validate folder type (just shows warning, doesn't change anything)
        # User can manually switch patches via the Patch Manager if needed
        validated_path, validated_patch_name = validateFolderForPatch(
            stage_path, True, globals_.gamedef.name, None
        )
        
        texture_path = os.path.join(stage_path, "Texture")

        while not os.path.isdir(texture_path):
            texture_path = getExistingDirectoryWithSidebar(
                None,
                globals_.trans.string('ChangeGamePath', 4, '[game]', globals_.gamedef.name),
                '',
                dialog_options
            )

            if texture_path == "":
                sys.exit(0)
            
            # Validate texture folder type as well
            validated_texture_path, validated_patch_name = validateFolderForPatch(
                texture_path, False, globals_.gamedef.name, None
            )

        SetGamePaths(stage_path, texture_path)
        if areValidGamePaths():
            break

        QtWidgets.QMessageBox.information(
            None, globals_.trans.string('ChangeGamePath', 1),
            globals_.trans.string('ChangeGamePath', 3)
        )
    
    # Open Patch Manager only if we just did initial setup
    print("[BOOT] Checking if patch manager needed...")
    if did_initial_setup:
        print("[BOOT] Opening patch manager...")
        from reggie.patches.patch_manager_dialog import PatchManagerDialog
        patch_dialog = deferred.PatchManagerDialog()
        patch_dialog.exec()
        print("[BOOT] ✓ Patch manager closed")
    print("[BOOT] ✓ Patch manager check complete")

    # Check to see if we have anything saved
    print("[BOOT] Checking for autosave...")
    autofile = setting('AutoSaveFilePath')
    autofiledata = setting('AutoSaveFileData', 'x')
    if autofile is not None and autofiledata != 'x':
        print("[BOOT] Autosave found, showing dialog...")
        result = AutoSavedInfoDialog(autofile).exec()
        if result == QtWidgets.QDialog.DialogCode.Accepted:
            globals_.RestoredFromAutoSave = True
            globals_.AutoSavePath = autofile
            globals_.AutoSaveData = bytes(autofiledata)
        else:
            setSetting('AutoSaveFilePath', None)
            setSetting('AutoSaveFileData', 'x')
        print("[BOOT] ✓ Autosave dialog handled")
    print("[BOOT] ✓ Autosave check complete")

    # Create and show the main window
    print("[BOOT] Creating main window...")
    globals_.mainWindow = ReggieWindow()
    print("[BOOT] ✓ Main window created")
    
    print("[BOOT] Initializing main window...")
    globals_.mainWindow.__init2__()  # fixes bugs
    print("[BOOT] ✓ Main window initialized")
    
    print("[BOOT] Showing main window...")
    globals_.mainWindow.show()
    print("[BOOT] ✓ Main window shown")

    if '-generatestringsxml' in sys.argv:
        globals_.trans.generateXML()

    print("[BOOT] ✓ Reggie boot complete! Starting event loop...")
    exitcodesys = globals_.app.exec()
    globals_.app.deleteLater()
    sys.exit(exitcodesys)


if __name__ == '__main__': main()
