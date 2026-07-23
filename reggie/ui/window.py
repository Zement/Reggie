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
import struct

# PyQt6: import, and error msg if not installed
try:
    from PyQt6 import QtCore, QtGui, QtWidgets
except (ImportError, NameError):
    errormsg = 'PyQt6 is not installed for this Python installation. Go online and download it.'
    raise Exception(errormsg)
Qt = QtCore.Qt

from reggie.core.raw_data import RawData

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

# Local imports
from reggie.core import archive
import reggie.sprites as sprites
from reggie.core import spritelib as SLib
from reggie.core import common

from reggie.core import globals_

################################################################################
################################################################################
################################################################################

from libs import lh, lib_versions, lz77
# Defer ui imports to avoid QColor creation before QApplication
# from ui import GetIcon, SetAppStyle, ListWidgetWithToolTipSignal, LoadNumberFont, LoadTheme, IconsOnlyTabBar
from reggie.io.misc import LoadActionsLists, LoadSpriteData, LoadTilesetInfo, FilesAreMissing, module_path, IsNSMBLevel, ChooseLevelNameDialog, LoadLevelNames, PreferencesDialog, LoadSpriteCategories, ZoomWidget, ZoomStatusWidget, RecentFilesMenu, SetGamePaths, areValidGamePaths, LoadZoneThemes, validateFolderForPatch
from reggie.io.misc2 import LevelScene, LevelViewWidget
from reggie.core.dirty import setting, setSetting, SetDirty
# Defer gamedef import to avoid ui import before QApplication
# from gamedef import GameDefMenu, LoadGameDef
from reggie.core.levelitems import LocationItem, ZoneItem, ObjectItem, SpriteItem, EntranceItem, ListWidgetItem_SortsByOther, PathItem, CommentItem, PathEditorLineItem
from reggie.ui.dialogs import AutoSavedInfoDialog, DiagnosticToolDialog, ScreenCapChoiceDialog, AreaChoiceDialog, ObjectTypeSwapDialog, ObjectTilesetSwapDialog, ObjectShiftDialog, MetaInfoDialog, AboutDialog, CameraProfilesDialog
from reggie.ui.window_actions import WindowActions
from reggie.ui.zoom import ZoomController
from reggie.ui.stamps import StampController
from reggie.ui.clipboard import ClipboardController
from reggie.ui.menus import MenuBuilder
from reggie.ui.docks import DockBuilder
from reggie.ui.level_io import LevelIO
from reggie.ui import deferred
from reggie.ui import qpt_boot
# Defer imports that depend on ui to avoid Qt object creation before QApplication
# from patch_manager_dialog import PatchManagerDialog
# from background import BGDialog
# from zones import ZonesDialog
from reggie.core.tiles import UnloadTileset, LoadTileset, LoadOverrides
# from area import AreaOptionsDialog
from reggie.core.level import Level_NSMBW
# from sidelists import Stamp, StampChooserWidget, SpriteList, SpritePickerWidget, ObjectPickerWidget, LevelOverviewWidget
# from spriteeditor import SpriteEditorWidget
from reggie.ui.editors import LocationEditorWidget, PathNodeEditorWidget, EntranceEditorWidget
from reggie.core.undo import UndoStack
from reggie.io.translation import LoadTranslation

# Quick Paint Tool boot state now lives on reggie.ui.qpt_boot (imported below),
# not in this module. It's still loaded lazily in main() after the QApplication
# exists (importing quickpaint eagerly breaks the import chain).

################################################################################
################################################################################
################################################################################


# NOTE: ReggieWindow was split out of reggie/app.py into this module
# (Phase 2/3 refactor — see _docs/plan/REFACTORING_ANALYSIS.md). The import
# preamble is shared verbatim with app.py; app.py imports ReggieWindow from here.

class ReggieWindow(QtWidgets.QMainWindow):
    """
    Reggie main level editor window
    """

    def __init__(self):
        """
        Editor window constructor
        """
        globals_.Initializing = True

        # Reggie Version number goes below here. 64 char max (32 if non-ascii).
        self.ReggieInfo = globals_.ReggieID

        self.ZoomLevels = [7.5, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0, 75.0,
                           85.0, 90.0, 95.0, 100.0, 125.0, 150.0, 175.0, 200.0, 250.0, 300.0, 350.0, 400.0]

        # add the undo stack object
        self.undoStack = UndoStack()

        # required variables
        self.UpdateFlag = False
        self.SelectionUpdateFlag = False
        self.selObj = None
        self.CurrentSelection = []

        # set up the window
        QtWidgets.QMainWindow.__init__(self, None)
        # Don't include version here - Qt automatically appends application display name
        self.setWindowTitle('Reggie! Next Level Editor')
        # Use PNG for QIcon on all platforms - .icns files cause crashes in PyQt6 on macOS ARM64
        # The native dock icon is handled by the .icns in the app bundle
        self.setWindowIcon(QtGui.QIcon('reggiedata/icon.png'))
        self.setIconSize(QtCore.QSize(16, 16))
        self.setUnifiedTitleAndToolBarOnMac(True)

        # create the level view
        self.scene = LevelScene(0, 0, 1024 * 24, 512 * 24, self)
        self.scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)
        self.scene.selectionChanged.connect(self.ChangeSelectionHandler)

        self.view = LevelViewWidget(self.scene, self)
        self.view.centerOn(0, 0)  # this scrolls to the top left
        self.view.PositionHover.connect(self.PositionHovered)
        self.view.XScrollBar.valueChanged.connect(self.XScrollChange)
        self.view.YScrollBar.valueChanged.connect(self.YScrollChange)
        self.view.FrameSize.connect(self.HandleWindowSizeChange)

        # done creating the window!
        self.setCentralWidget(self.view)

        # Composed controllers extracted from this class (Phase 2 refactor).
        # Instantiated before the clipboard wiring below, because
        # TrackClipboardUpdates() is called (and connected) here and now
        # delegates into self._clipboard.
        self._windowActions = WindowActions(self)
        self._zoom = ZoomController(self)
        self._stamps = StampController(self)
        self._clipboard = ClipboardController(self)
        self._levelio = LevelIO(self)

        # set up the clipboard stuff
        self.clipboard = None
        self.systemClipboard = QtWidgets.QApplication.clipboard()
        self.systemClipboard.dataChanged.connect(self.TrackClipboardUpdates)

        # we might have something there already, activate Paste if so
        self.TrackClipboardUpdates()

    def __init2__(self):
        """
        Finishes initialization. (fixes bugs with some widgets calling globals_.mainWindow.something before it's init'ed)
        """

        print("[INIT2] Creating autosave timer...")
        self.AutosaveTimer = QtCore.QTimer()
        self.AutosaveTimer.timeout.connect(self.Autosave)
        self.AutosaveTimer.start(20000)
        print("[INIT2] ✓ Autosave timer created")

        # set up actions and menus
        print("[INIT2] Setting up actions and menus...")
        self.SetupActionsAndMenus()
        print("[INIT2] ✓ Actions and menus set up")

        # set up the status bar
        print("[INIT2] Creating status bar widgets...")
        self.posLabel = QtWidgets.QLabel()
        self.selectionLabel = QtWidgets.QLabel()
        self.hoverLabel = QtWidgets.QLabel()
        self.statusBar().addWidget(self.posLabel)
        self.statusBar().addWidget(self.selectionLabel)
        self.statusBar().addWidget(self.hoverLabel)
        print("[INIT2] ✓ Status bar widgets created")
        
        # Warning icons container
        self.warningIcons = []
        
        #self.diagnostic = DiagnosticWidget()
        print("[INIT2] Creating zoom widgets...")
        self.ZoomWidget = ZoomWidget()
        self.ZoomStatusWidget = ZoomStatusWidget()
        #self.statusBar().addPermanentWidget(self.diagnostic)
        self.statusBar().addPermanentWidget(self.ZoomWidget)
        self.statusBar().addPermanentWidget(self.ZoomStatusWidget)
        print("[INIT2] ✓ Zoom widgets created")

        # create the various panels
        print("[INIT2] Setting up docks and panels...")
        # Dock/panel construction extracted to reggie.ui.docks.DockBuilder
        # (Phase 2 — see _docs/plan/REFACTORING_ANALYSIS.md). Runs after
        # createMenubar() since it adds actions to self.vmenu.
        DockBuilder(self).SetupDocksAndPanels()
        print("[INIT2] ✓ Docks and panels set up")

        # Initialize Quick Paint Tool (after panels are created and QApplication exists).
        # QPT is a "code plugin" (reggie.plugins.loader.CodePlugin) whose boot
        # state lives on reggie.ui.qpt_boot.qpt, not in reggie.py module globals.
        print("[INIT2] Initializing Quick Paint Tool...")
        qpt = qpt_boot.qpt
        if qpt.available and not qpt.initialized and qpt.payload:
            try:
                print("[INIT2] Calling QPT initialize...")
                self.qpt_palette = qpt.payload['initialize'](self)
                print("[INIT2] ✓ QPT palette created")

                # Add to the palette tabs (creationTabs is the tab widget in the palette dock)
                print("[INIT2] Adding QPT tab to palette...")
                self.creationTabs.addTab(self.qpt_palette, deferred.GetIcon('palette'), '')
                self.creationTabs.setTabToolTip(self.creationTabs.count() - 1, 'Quick Paint')
                print("[INIT2] ✓ QPT tab added")

                qpt.initialized = True
                print("[INIT2] ✓ Quick Paint Tool initialized")
            except Exception as e:
                print(f"[INIT2] Warning: Could not initialize Quick Paint Tool: {str(e)}")
                import traceback
                traceback.print_exc()
                qpt.available = False
        else:
            print(f"[INIT2] QPT not available (available={qpt.available}, initialized={qpt.initialized}, payload={qpt.payload is not None})")

        # now get stuff ready
        loaded = False
        self.fileSavePath = None

        if len(sys.argv) > 1 and IsNSMBLevel(sys.argv[1]):
            loaded = self.LoadLevel(sys.argv[1], True, 1)
        else:
            lastlevel = globals_.gamedef.GetLastLevel()
            if lastlevel is not None:
                loaded = self.LoadLevel(lastlevel, True, 1)

        if not loaded:
            self.LoadLevel('01-01', False, 1)

        # call each toggle-button handler to set each feature correctly upon
        # startup
        toggleHandlers = {
            self.HandleSpritesVisibility: globals_.SpritesShown,
            self.HandleSpriteImages: globals_.SpriteImagesShown,
            self.HandleLocationsVisibility: globals_.LocationsShown,
            self.HandleCommentsVisibility: globals_.CommentsShown,
            self.HandlePathsVisibility: globals_.PathsShown,
        }
        for handler in toggleHandlers:
            handler(toggleHandlers[handler])

        # let's restore the state and geometry
        # geometry: determines the main window position
        # state: determines positions of docks
        if globals_.settings.contains('MainWindowGeometry'):
            self.restoreGeometry(setting('MainWindowGeometry'))
        if globals_.settings.contains('MainWindowState'):
            self.restoreState(setting('MainWindowState'), 0)

        # Aaaaaand... initializing is done!
        globals_.Initializing = False

    def SetupActionsAndMenus(self):
        """
        Sets up Reggie's actions, menus and toolbars
        """
        print("[INIT2] Creating RecentFilesMenu...")
        self.RecentMenu = RecentFilesMenu()
        print("[INIT2] ✓ RecentFilesMenu created")
        
        print("[INIT2] Creating GameDefMenu...")
        self.GameDefMenu = deferred.GameDefMenu()
        print("[INIT2] ✓ GameDefMenu created")

        print("[INIT2] Creating menubar...")
        # Menu/toolbar/action construction extracted to
        # reggie.ui.menus.MenuBuilder (Phase 2 — see
        # _docs/plan/REFACTORING_ANALYSIS.md). The builder operates on this
        # window (self.actions, self.<Handler> triggers, self.toolbar, ...).
        MenuBuilder(self).createMenubar()
        print("[INIT2] ✓ Menubar created")

    # Populated by MenuBuilder.CreateAction via self.win.actions. Kept as a
    # ReggieWindow class attribute so self.actions resolves everywhere it's read.
    actions = {}

    def HandleSwitchPatch(self, index):
        """
        Handle activated signals for patchComboBox
        """
        if index < 0:
            return
        
        # Get the selected item data
        patch_data = self.patchComboBox.itemData(index)
        
        if patch_data == 'patchmanager':
            # Open Patch Manager
            self.HandlePatchManager()
            # Reset to current patch
            self.updatePatchComboBox()
        elif patch_data is None:
            # Switch to base game
            from reggie.io.gamedef import loadNewGameDef
            success = loadNewGameDef(None)
            if success:
                # Update combo box to reflect the change
                self.updatePatchComboBox()
            else:
                # Reset to current patch on failure
                self.updatePatchComboBox()
        elif patch_data is not None:
            # Switch to selected patch
            from reggie.io.gamedef import loadNewGameDef
            success = loadNewGameDef(patch_data)
            if success:
                # Update combo box to reflect the change
                self.updatePatchComboBox()
            else:
                # Reset to current patch on failure
                self.updatePatchComboBox()

    def updatePatchComboBox(self):
        """
        Updates the patch combo box with current patches and selects the active one
        """
        # Check if patch combo box exists (might be disabled in preferences)
        if not hasattr(self, 'patchComboBox') or self.patchComboBox is None:
            return
        
        from reggie.io.gamedef import getAvailableGameDefs
        from reggie.core.dirty import setting
        
        # Store current selection
        current_patch = setting('LastGameDef')
        
        # Clear and repopulate
        self.patchComboBox.clear()
        
        # Get all patches
        patches = getAvailableGameDefs()
        
        # Find current patch index
        current_index = 0
        
        # Add base game if it exists
        if None in patches:
            patches.remove(None)
            self.patchComboBox.addItem('New Super Mario Bros. Wii', None)
            if current_patch is None:
                current_index = self.patchComboBox.count() - 1
        
        # Add custom patches
        for patch_folder in patches:
            if patch_folder is not None:
                try:
                    from reggie.io.gamedef import ReggieGameDefinition
                    # Check if it's a custom path
                    custom_path = setting('PatchPath_' + patch_folder)
                    if custom_path:
                        patch_def = ReggieGameDefinition(patch_folder, custom_path=custom_path)
                    else:
                        patch_def = ReggieGameDefinition(patch_folder)
                    
                    if patch_def.custom:
                        self.patchComboBox.addItem(patch_def.name, patch_folder)
                        if patch_folder == current_patch:
                            current_index = self.patchComboBox.count() - 1
                except:
                    # Skip invalid patches
                    continue
        
        # Add Patch Manager separator and option
        self.patchComboBox.insertSeparator(self.patchComboBox.count())
        self.patchComboBox.addItem('Patch Manager...', 'patchmanager')
        
        # Set current selection
        if current_index < self.patchComboBox.count():
            self.patchComboBox.setCurrentIndex(current_index)

    def DeselectPathSelection(self, checked):
        """
        Deselects selected path nodes in the list
        """
        for selecteditem in self.pathList.selectedItems():
            selecteditem.setSelected(False)

    def Autosave(self):
        """
        Auto saves the level
        """
        if not globals_.AutoSaveDirty: return

        data = globals_.Level.save()
        setSetting('AutoSaveFilePath', self.fileSavePath)
        setSetting('AutoSaveFileData', QtCore.QByteArray(data))
        globals_.AutoSaveDirty = False

    def TrackClipboardUpdates(self):
        return self._clipboard.TrackClipboardUpdates()

    def XScrollChange(self, pos):
        """
        Moves the Overview current position box based on X scroll bar value
        """
        self.levelOverview.Xposlocator = pos
        self.levelOverview.update()

    def YScrollChange(self, pos):
        """
        Moves the Overview current position box based on Y scroll bar value
        """
        self.levelOverview.Yposlocator = pos
        self.levelOverview.update()

    def HandleWindowSizeChange(self, w, h):
        self.levelOverview.Hlocator = h
        self.levelOverview.Wlocator = w
        self.levelOverview.update()

    def UpdateTitle(self):
        """
        Sets the window title accordingly
        """
        # ' - Reggie Next' is added automatically by Qt (see QApplication.setApplicationDisplayName()).
        self.setWindowTitle('%s%s' % (self.fileTitle, (' ' + globals_.trans.string('MainWindow', 0)) if globals_.Dirty else ''))

    def CheckDirty(self):
        """
        Checks if the level is unsaved and attempts to save it if so.
        Returns whether the level still contains unsaved changes.
        """
        if not globals_.Dirty:
            return False

        msg = QtWidgets.QMessageBox()
        msg.setText(globals_.trans.string('AutoSaveDlg', 2))
        msg.setInformativeText(globals_.trans.string('AutoSaveDlg', 3))
        msg.setStandardButtons(
            QtWidgets.QMessageBox.StandardButton.Save | QtWidgets.QMessageBox.StandardButton.Discard | QtWidgets.QMessageBox.StandardButton.Cancel)
        msg.setDefaultButton(QtWidgets.QMessageBox.StandardButton.Save)
        ret = msg.exec()

        if ret == QtWidgets.QMessageBox.StandardButton.Save:
            # If the save failed, the file is still dirty, so we need to negate
            # the return value.
            return not self.HandleSave()

        elif ret == QtWidgets.QMessageBox.StandardButton.Cancel:
            return True
        
        elif ret == QtWidgets.QMessageBox.StandardButton.Discard:
            # User chose to discard changes - reload the current area from disk
            # to discard all unsaved changes
            if globals_.Area is not None and hasattr(globals_.Area, 'areanum'):
                current_area_num = globals_.Area.areanum
                
                # Set a flag to indicate we just discarded changes
                # This will force a reload even if loading the "same" level
                self.justDiscardedChanges = True
                
                # Clear the dirty flag before reloading
                globals_.Dirty = False
                globals_.DirtyOverride += 1
                
                # Clear the scene and lists
                self.scene.clearSelection()
                self.CurrentSelection = []
                self.scene.clear()
                
                for thingList in (self.spriteList, self.entranceList, self.locationList, self.pathList, self.commentList):
                    thingList.clear()
                    thingList.selectionModel().setCurrentIndex(QtCore.QModelIndex(), QtCore.QItemSelectionModel.SelectionFlag.Clear)
                
                # Unload and reload the area to discard changes
                globals_.Area.unload()
                globals_.Area.load()
                
                # Reload the scene with the fresh data
                self.ResetPalette()
                
                # Refresh object layouts
                for layer in globals_.Area.layers:
                    for obj in layer:
                        obj.updateObjCache()
                
                for sprite in globals_.Area.sprites:
                    sprite.UpdateDynamicSizing()
                    sprite.ImageObj.positionChanged()
                
                # Update the scene and overview
                self.scene.update()
                self.levelOverview.Reset()
                self.levelOverview.update()
                
                globals_.DirtyOverride -= 1
            return False

        return False

    def LoadEventTabFromLevel(self):
        """
        Configures the Events tab from the data in globals_.Area.defEvents
        """
        defEvents = globals_.Area.defEvents
        checked = Qt.CheckState.Checked
        unchecked = Qt.CheckState.Unchecked

        data = globals_.Area.Metadata.binData('EventNotes_A%d' % globals_.Area.areanum)
        eventTexts = {}
        if data is not None:
            # Iterate through the data
            idx = 0

            while idx < len(data):
                event_id, str_len = struct.unpack_from(">2I", data, idx)
                eventTexts[event_id] = data[idx + 8:idx + 8 + str_len].decode('utf-8')

                idx += 8 + str_len

        for i, item in enumerate(self.eventChooserItems):
            item.setCheckState(0, checked if (defEvents & (1 << i)) != 0 else unchecked)
            item.setText(1, eventTexts.get(i, ""))
            item.setSelected(False)

        self.eventChooserItems[0].setSelected(True)
        self.eventNotesEditor.setText(eventTexts.get(0, ""))

    def handleEventTabItemClick(self, item):
        """
        Handles an item being clicked in the Events tab
        """
        # Write the current note to the event note editor
        noteText = item.text(1)
        self.eventNotesEditor.setText(noteText)

        selIdx = self.eventChooserItems.index(item)
        isOn = (globals_.Area.defEvents & 1 << selIdx) == 1 << selIdx
        if item.checkState(0) == Qt.CheckState.Checked and not isOn:
            # Turn a bit on
            globals_.Area.defEvents |= 1 << selIdx
            SetDirty()
        elif item.checkState(0) == Qt.CheckState.Unchecked and isOn:
            # Turn a bit off (mask out 1 bit)
            globals_.Area.defEvents &= ~(1 << selIdx)
            SetDirty()

    def handleEventNotesEdit(self):
        """
        Handles the text within self.eventNotesEditor changing
        """
        newText = self.eventNotesEditor.text()

        # Set the text to the event chooser
        currentItem = self.eventChooser.selectedItems()[0]
        currentItem.setText(1, newText)

        # Save all the events to the metadata
        data = b""
        for i in range(64):
            event_note = str(self.eventChooserItems[i].text(1))
            if not event_note: continue

            encoded = event_note.encode('utf-8')

            # Add the event id, note length and note to the data.
            data += struct.pack(">2I", i, len(encoded))
            data += encoded

        globals_.Area.Metadata.setBinData('EventNotes_A%d' % globals_.Area.areanum, data)
        SetDirty()

    # Stamp-palette handlers extracted to reggie.ui.stamps.StampController
    # (Phase 2 — see _docs/plan/REFACTORING_ANALYSIS.md). Thin delegators keep
    # the signal connections wired in SetupDocksAndPanels resolving unchanged.
    def handleStampsAdd(self):
        return self._stamps.handleStampsAdd()

    def handleStampsRemove(self):
        return self._stamps.handleStampsRemove()

    def handleStampsOpen(self):
        return self._stamps.handleStampsOpen()

    def handleStampsSave(self):
        return self._stamps.handleStampsSave()

    def handleStampSelectionChanged(self):
        return self._stamps.handleStampSelectionChanged()

    def handleStampNameEdited(self):
        return self._stamps.handleStampNameEdited()

    # AboutBox / HandleInfo / HelpBox / TipBox were extracted to
    # reggie.ui.window_actions.WindowActions (Phase 2, first extraction — see
    # _docs/plan/REFACTORING_ANALYSIS.md). These thin delegators keep the
    # existing QAction wiring (self.AboutBox, self.HelpBox, ...) working.
    def AboutBox(self):
        return self._windowActions.AboutBox()

    def HandleInfo(self):
        return self._windowActions.HandleInfo()

    def HelpBox(self):
        return self._windowActions.HelpBox()

    def TipBox(self):
        return self._windowActions.TipBox()

    def SelectAll(self):
        """
        Select all objects in the current area
        """
        paintRect = QtGui.QPainterPath()
        paintRect.addRect(0, 0, 1024 * 24, 512 * 24)
        self.scene.setSelectionArea(paintRect)

    def Deselect(self):
        """
        Deselect all currently selected items
        """
        items = self.scene.selectedItems()
        for obj in items:
            obj.setSelected(False)

    def Undo(self):
        """
        Undoes something
        """
        self.undoStack.undo()

    def Redo(self):
        """
        Redoes something previously undone
        """
        self.undoStack.redo()

    # Cut/Copy/Paste + ReggieClip encode/decode/place extracted to
    # reggie.ui.clipboard.ClipboardController (Phase 2 — see
    # _docs/plan/REFACTORING_ANALYSIS.md). Thin delegators keep the QAction
    # wiring AND the cross-module callers (globals_.mainWindow.placeEncodedObjects
    # in misc2.py, .getEncodedObjects in sidelists.py) working, so signatures
    # are preserved exactly.
    def Cut(self):
        return self._clipboard.Cut()

    def Copy(self):
        return self._clipboard.Copy()

    def Paste(self):
        return self._clipboard.Paste()

    def encodeObjects(self, clipboard_o, clipboard_s):
        return self._clipboard.encodeObjects(clipboard_o, clipboard_s)

    def placeEncodedObjects(self, encoded, select=True, xOverride=None, yOverride=None):
        return self._clipboard.placeEncodedObjects(encoded, select=select, xOverride=xOverride, yOverride=yOverride)

    def getEncodedObjects(self, encoded):
        return self._clipboard.getEncodedObjects(encoded)

    def ShiftItems(self):
        """
        Shifts the selected object(s)
        """
        items = self.scene.selectedItems()
        if not items: return

        dlg = ObjectShiftDialog()
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        xoffset = dlg.XOffset.value()
        yoffset = dlg.YOffset.value()
        if xoffset == 0 and yoffset == 0: return

        if ((xoffset % 16) != 0) or ((yoffset % 16) != 0):
            # warn if any objects exist
            objectsExist = False
            type_obj = ObjectItem

            for obj in items:
                if isinstance(obj, type_obj):
                    objectsExist = True
                    break

            if objectsExist:
                # Objects are selected and the offset is not a multiple of 16.
                # We should warn the user that we will round the offset to the
                # nearest multiple of 16, because objects can only be placed on
                # the grid.
                result = QtWidgets.QMessageBox.information(None, globals_.trans.string('ShftItmDlg', 5),
                                                            globals_.trans.string('ShftItmDlg', 6), QtWidgets.QMessageBox.StandardButton.Yes,
                                                            QtWidgets.QMessageBox.StandardButton.No)

                if result == QtWidgets.QMessageBox.StandardButton.No:
                    return

                # Round the offset to the nearest multiple of 16
                xoffset = 16 * round(xoffset / 16)
                yoffset = 16 * round(yoffset / 16)

        xpoffset = xoffset * 1.5
        ypoffset = yoffset * 1.5

        globals_.OverrideSnapping = True

        for obj in items:
            obj.setPos(obj.x() + xpoffset, obj.y() + ypoffset)

        globals_.OverrideSnapping = False

        SetDirty()

    def SwapObjectsTilesets(self):
        """
        Swaps objects' tilesets
        """
        dlg = ObjectTilesetSwapDialog()
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        from_tileset = dlg.FromTS.value() - 1
        to_tileset = dlg.ToTS.value() - 1
        do_exchange = dlg.DoExchange.isChecked()

        if from_tileset == to_tileset:
            return

        for layer in globals_.Area.layers:
            for nsmbobj in layer:
                if nsmbobj.tileset == from_tileset:
                    nsmbobj.SetType(to_tileset, nsmbobj.type)
                    SetDirty()
                elif do_exchange and nsmbobj.tileset == to_tileset:
                    nsmbobj.SetType(from_tileset, nsmbobj.type)
                    SetDirty()

    def SwapObjectsTypes(self):
        """
        Swaps objects' types
        """
        ObjectTypeSwapDialog().exec()

    def MergeLocations(self):
        """
        Merges selected sprite locations
        """
        items = self.scene.selectedItems()
        if not items: return

        new_rect = QtCore.QRectF()

        type_loc = LocationItem
        for obj in items:
            if not isinstance(obj, type_loc):
                continue

            new_rect |= obj.ZoneRect

            obj.delete()
            obj.setSelected(False)
            self.scene.removeItem(obj)
            self.levelOverview.update()
            SetDirty()

        if not new_rect.isValid():
            return

        loc = self.CreateLocation(*new_rect.getRect())
        loc.setSelected(True)

    ###########################################################################
    # Functions that create items
    ###########################################################################
    # Maybe move these as static methods to their respective classes
    def CreateLocation(self, x, y, width = 16, height = 16, id_ = None, add_to_scene = True):
        """
        Creates and returns a new location and makes sure it's added to the
        right lists, unless 'add_to_scene' is set to False. If 'id' is None, the
        smallest available id is used.
        This function returns None if there is no free location id available, and
        the created location otherwise.
        """
        if id_ is None:
            # This can be done more efficiently, but 255 is not that big, so it
            # does not really matter.
            all_ids = set(loc.id for loc in globals_.Area.locations)
            id_ = common.find_first_available_id(all_ids, 256, 1)

            if id_ is None:
                print("ReggieWindow#CreateLocation: No free location id")
                return None

        globals_.OverrideSnapping = True
        loc = LocationItem(x, y, width, height, id_)
        globals_.OverrideSnapping = False

        loc.positionChanged = self.HandleLocPosChange
        loc.sizeChanged = self.HandleLocSizeChange
        loc.listitem = ListWidgetItem_SortsByOther(loc)

        if add_to_scene:
            self.locationList.addItem(loc.listitem)
            self.scene.addItem(loc)
            globals_.Area.locations.append(loc)

            loc.UpdateListItem()

            # We've changed the level, so set the dirty flag
            SetDirty()

        return loc

    def CreateObject(self, tileset, object_num, layer, x, y, width = None, height = None, add_to_scene = True):
        """
        Creates and returns a new object and makes sure it's added to
        the right lists.
        """
        if width is None or height is None:
            if globals_.PlaceObjectsAtFullSize:
                try:
                    tile_def = globals_.ObjectDefinitions[tileset][object_num]
                    width = tile_def.width
                    height = tile_def.height
                except TypeError:  # Something was None
                    width = height = 1
            else:
                width = height = 1

        layer_list = globals_.Area.layers[layer]
        if not layer_list:
            z = (2 - layer) * 8192
        else:
            z = layer_list[-1].zValue() + 1

        obj = ObjectItem(tileset, object_num, layer, x, y, width, height, z)

        if add_to_scene:
            layer_list.append(obj)
            obj.positionChanged = self.HandleObjPosChange
            self.scene.addItem(obj)

            SetDirty()

        return obj

    def CreateEntrance(self, x, y, id_ = None, add_to_scene = True):
        """
        Creates and returns a new entrance and makes sure it's added to the
        right lists. This function returns None if this entrance could not be
        created.
        """
        all_ids = set(ent.entid for ent in globals_.Area.entrances)
        if id_ is None:
            id_ = common.find_first_available_id(all_ids, 256)

        if id_ is None:
            print("ReggieWindow#CreateEntrance: No free entrance id")
            return None
        elif id_ in all_ids and add_to_scene:
            print("ReggieWindow#CreateEntrance: Given entrance id (%d) already in use" % id_)
            return None

        ent = EntranceItem(x, y, id_, 0, 0, 0, 0, 0, 0, 0x80, 0, 0)
        ent.positionChanged = self.HandleEntPosChange
        ent.listitem = ListWidgetItem_SortsByOther(ent)

        if add_to_scene:
            # If it's the first available ID, all the other indices should match, so
            # we can just use the ID to insert.
            self.entranceList.insertItem(id_, ent.listitem)
            globals_.Area.entrances.insert(id_, ent)

            self.scene.addItem(ent)
            ent.UpdateListItem()

            SetDirty()

        return ent

    def CreateSprite(self, x, y, id_ = None, data = None, add_to_scene = True):
        """
        Creates and returns a new sprite and makes sure it's added to the right
        lists if 'add_to_scene' is set.
        If 'id_' is not set, the currently selected sprite id is used.
        If 'data' is not set, the current data of the default data editor is used.
        If 'data' is not set and the default data editor is configured for another
        sprite id than the id of the sprite that is created, a ValueError will
        be raised.
        """

        if id_ is None:
            id_ = globals_.CurrentSprite

        if data is None:
            if self.defaultDataEditor.spritetype != id_:
                raise ValueError("The default data editor was configured for sprite id %d while trying to use data for sprite id %d" % (self.defaultDataEditor.spritetype, id_))

            data = self.defaultDataEditor.data.copy()

        data.fix_size_if_needed(id_)

        spr = SpriteItem(id_, x, y, data)
        spr.positionChanged = self.HandleSprPosChange

        if add_to_scene:
            self.spriteList.addSprite(spr)
            globals_.Area.sprites.append(spr)

            # Add the ids for the idtype count
            decoder = deferred.SpriteEditorWidget.PropertyDecoder()
            sdef = globals_.Sprites[id_] if 0 <= id_ < globals_.NumSprites else None

            # Find what values are used by this sprite
            if sdef is not None:
                for field in sdef.fields:
                    if field[0] not in (1, 2):
                        # Only values and lists can be idtypes
                        continue

                    idtype = field[-2]
                    if idtype is None:
                        # Only look at settings with idtypes
                        continue

                    value = decoder.retrieve(data, field[2])

                    # 3. Add the value to self.sprite_idtypes
                    try:
                        counter = globals_.Area.sprite_idtypes[idtype]
                    except KeyError:
                        globals_.Area.sprite_idtypes[idtype] = {value: 1}
                        continue

                    counter[value] = counter.get(value, 0) + 1

            self.scene.addItem(spr)
            spr.UpdateListItem()

            SetDirty()

        return spr

    def CreateZone(self, x, y, width = 408, height = 224, id_ = None, add_to_scene = True):
        """
        Creates and returns a new zone and makes sure it's added to the right
        lists if 'add_to_scene' is set.
        If 'id_' is not set, the current number of zones in this Area is used as
        an id.
        """
        if id_ is None:
            id_ = len(globals_.Area.zones) + 1

        default_bounding = [[0, 0, 0, 0, 0, 15, 0, 0]]
        default_bga = [[0, 2, 2, 0, 0, 10, 10, 10, 1]]
        default_bgb = [[0, 1, 1, 0, 0, 10, 10, 10, 2]]

        zone = ZoneItem(x, y, width, height, 0, 0, id_ - 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, default_bounding, default_bga, default_bgb)

        if add_to_scene:
            globals_.Area.zones.append(zone)
            self.scene.addItem(zone)

            self.scene.update()
            self.levelOverview.update()

            SetDirty()

        return zone

    def HandleAddNewArea(self):
        """
        Adds a new area to the level
        """
        if len(globals_.Level.areas) >= 4:
            QtWidgets.QMessageBox.warning(self, 'Reggie', globals_.trans.string('AreaChoiceDlg', 2))
            return

        if self.CheckDirty():
            # Level is still dirty
            return

        newID = len(globals_.Level.areas) + 1
        globals_.Level.appendArea(None, None, None, None)

        if not self.HandleSave():
            globals_.Level.deleteArea(newID)
            return

        self.LoadLevel(self.fileSavePath, True, newID)

    def HandleImportArea(self):
        """
        Imports an area from another level
        """
        if len(globals_.Level.areas) >= 4:
            QtWidgets.QMessageBox.warning(self, 'Reggie', globals_.trans.string('AreaChoiceDlg', 2))
            return

        if self.CheckDirty():
            return

        filetypes = ''
        filetypes += globals_.trans.string('FileDlgs', 1) + ' (*' + '.arc' + ');;'  # *.arc
        filetypes += globals_.trans.string('FileDlgs', 5) + ' (*' + '.arc' + '.LH);;'  # *.arc.LH
        filetypes += globals_.trans.string('FileDlgs', 10) + ' (*' + '.arc' + '.LZ);;'  # *.arc.LZ
        filetypes += globals_.trans.string('FileDlgs', 2) + ' (*)'  # *
        fn = QtWidgets.QFileDialog.getOpenFileName(self, globals_.trans.string('FileDlgs', 0), '', filetypes)[0]
        if fn == '': return

        with open(str(fn), 'rb') as fileobj:
            arcdata = fileobj.read()

        if (arcdata[0] & 0xF0) == 0x40:  # If LH-compressed
            try:
                arcdata = lh.UncompressLH(arcdata)
            except IndexError:
                QtWidgets.QMessageBox.warning(None, globals_.trans.string('Err_Decompress', 0),
                                              globals_.trans.string('Err_Decompress', 1, '[file]', str(fn)))
                return

        arc = archive.U8.load(arcdata)

        # get the area count
        areacount = 0

        for item, val in arc.files:
            if val is not None:
                # it's a file
                fname = item[item.rfind('/') + 1:]
                if fname.startswith('course'):
                    maxarea = int(fname[6])
                    if maxarea > areacount: areacount = maxarea

        # choose one
        dlg = AreaChoiceDialog(areacount)
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Rejected:
            return

        area = dlg.areaCombo.currentIndex() + 1

        # get the required files
        reqcourse = 'course%d.bin' % area
        reqL0 = 'course%d_bgdatL0.bin' % area
        reqL1 = 'course%d_bgdatL1.bin' % area
        reqL2 = 'course%d_bgdatL2.bin' % area

        course = None
        L0 = None
        L1 = None
        L2 = None

        for item, val in arc.files:
            if val is not None:
                fname = item.split('/')[-1]
                if fname == reqcourse:
                    course = val
                elif fname == reqL0:
                    L0 = val
                elif fname == reqL1:
                    L1 = val
                elif fname == reqL2:
                    L2 = val

        # add them to our level
        globals_.Level.appendArea(course, L0, L1, L2)
        new_id = globals_.Level.areas[-1].areanum

        if not self.HandleSave():
            globals_.Level.deleteArea(new_id)
            return

        self.LoadLevel(self.fileSavePath, True, new_id)

    def HandleDeleteArea(self):
        """
        Deletes the current area
        """
        result = QtWidgets.QMessageBox.warning(self, 'Reggie', globals_.trans.string('DeleteArea', 0),
                                               QtWidgets.QMessageBox.StandardButton.Yes | QtWidgets.QMessageBox.StandardButton.No,
                                               QtWidgets.QMessageBox.StandardButton.No)
        if result == QtWidgets.QMessageBox.StandardButton.No: return

        # Save the current area in case something goes wrong.
        if not self.HandleSave(): return

        area_to_delete = globals_.Area.areanum
        new_area_one = 1 if area_to_delete != 1 else 2

        # Load the new area 1 before deleting the old area to avoid glitches
        # when the old area was area 1.
        self.LoadLevel(self.fileSavePath, True, new_area_one)

        # Actually delete the area
        globals_.Level.deleteArea(area_to_delete)

        self.actions['deletearea'].setEnabled(len(globals_.Level.areas) > 1)

        # Update the area selection combobox
        self.areaComboBox.clear()

        for area in globals_.Level.areas:
            self.areaComboBox.addItem(globals_.trans.string('AreaCombobox', 0, '[num]', area.areanum))

        self.areaComboBox.setCurrentIndex(0)

        # Save the level without the area as promised
        self.HandleSave()

    def HandleChangeGamePath(self, auto=False):
        """
        Change the game path used by the current game definition
        """
        if self.CheckDirty(): return

        # On macOS, use DontUseNativeDialog to show the title bar
        dialog_options = QtWidgets.QFileDialog.Option.ShowDirsOnly
        if sys.platform == 'darwin':
            dialog_options |= QtWidgets.QFileDialog.Option.DontUseNativeDialog

        while True:
            from reggie.io.misc import getExistingDirectoryWithSidebar
            stage_path = getExistingDirectoryWithSidebar(
                None,
                globals_.trans.string('ChangeGamePath', 0, '[game]', globals_.gamedef.name),
                '',
                dialog_options
            )

            if stage_path == '':
                return False

            stage_path = str(stage_path)
            
            # Validate folder type (just shows warning, doesn't change anything)
            # User can manually switch patches via the Patch Manager if needed
            validated_path, validated_patch_name = validateFolderForPatch(
                stage_path, True, globals_.gamedef.name, None
            )
            
            texture_path = os.path.join(stage_path, "Texture")

            while not os.path.isdir(texture_path):
                texture_path = QtWidgets.QFileDialog.getExistingDirectory(
                    None,
                    globals_.trans.string('ChangeGamePath', 4, '[game]', globals_.gamedef.name),
                    '',
                    dialog_options
                )

                if texture_path == "":
                    return False
                
                # Validate texture folder type as well
                validated_texture_path, validated_patch_name = validateFolderForPatch(
                    texture_path, False, globals_.gamedef.name, None
                )

            if (not areValidGamePaths(stage_path, texture_path)) and (not globals_.gamedef.custom):  # custom gamedefs can use incomplete folders
                QtWidgets.QMessageBox.information(
                    None, globals_.trans.string('ChangeGamePath', 1),
                    globals_.trans.string('ChangeGamePath', 2)
                )
            else:
                SetGamePaths(stage_path, texture_path)
                break

        if not auto:
            # Try loading 01-01. If that fails, load up an empty canvas.
            ok = self.LoadLevel('01-01', False, 1)
            if not ok:
                self.LoadLevel(None, False, 1)

        return True

    def HandlePatchManager(self):
        """
        Open the Patch Manager dialog
        """
        dlg = deferred.PatchManagerDialog()
        dlg.exec()

    def HandlePreferences(self):
        """
        Edit Reggie Next preferences
        """
        # Show the dialog
        dlg = PreferencesDialog()
        if dlg.exec() == QtWidgets.QDialog.DialogCode.Rejected:
            return

        # Get the translation
        name = str(dlg.generalTab.Trans.itemData(dlg.generalTab.Trans.currentIndex(), Qt.ItemDataRole.UserRole))
        setSetting('Translation', name)

        # Get the Zone Entrance Indicators setting
        globals_.DrawEntIndicators = dlg.generalTab.zEntIndicator.isChecked()
        setSetting('ZoneEntIndicators', globals_.DrawEntIndicators)

        # Get the Zone Bounds Indicators setting
        globals_.BoundsDrawn = dlg.generalTab.zBndIndicator.isChecked()
        setSetting('ZoneBoundIndicators', globals_.BoundsDrawn)

        # Get the reset data when hiding setting
        globals_.ResetDataWhenHiding = dlg.generalTab.rdhIndicator.isChecked()
        setSetting('ResetDataWhenHiding', globals_.ResetDataWhenHiding)

        # Get the reset data when hiding setting
        globals_.HideResetSpritedata = dlg.generalTab.erbIndicator.isChecked()
        setSetting('HideResetSpritedata', globals_.HideResetSpritedata)

        # Padding settings
        globals_.EnablePadding = dlg.generalTab.epbIndicator.isChecked()
        setSetting('EnablePadding', globals_.EnablePadding)

        globals_.PaddingLength = dlg.generalTab.psValue.value()
        setSetting('PaddingLength', globals_.PaddingLength)

        # Full object size settings
        globals_.PlaceObjectsAtFullSize = dlg.generalTab.fullObjSize.isChecked()
        setSetting('PlaceObjectsAtFullSize', globals_.PlaceObjectsAtFullSize)

        # Insert Path Node setting
        globals_.InsertPathNode = dlg.generalTab.insertPathNode.isChecked()
        setSetting('InsertPathNode', globals_.InsertPathNode)

        # Get the Toolbar tab settings
        boxes = (
            dlg.toolbarTab.FileBoxes, dlg.toolbarTab.EditBoxes, dlg.toolbarTab.ViewBoxes, dlg.toolbarTab.SettingsBoxes,
            dlg.toolbarTab.HelpBoxes
        )
        ToolbarSettings = {}
        for boxList in boxes:
            for box in boxList:
                ToolbarSettings[box.InternalName] = box.isChecked()
        setSetting('ToolbarActs', ToolbarSettings)

        # Get the Interface tab settings
        toolbar_separate = dlg.interfaceTab.toolbarSeparateRadio.isChecked()
        setSetting('ToolbarSeparate', toolbar_separate)
        
        # Get UI scaling settings
        ui_scale = dlg.interfaceTab.uiScaleSlider.value() / 100.0
        font_scale = dlg.interfaceTab.fontScaleSlider.value() / 100.0
        
        # Apply scaling if changed
        if (ui_scale != globals_.scalingManager.getUIScale() or 
            font_scale != globals_.scalingManager.getFontScale()):
            globals_.scalingManager.setUIScale(ui_scale)
            globals_.scalingManager.setFontScale(font_scale)
            globals_.scalingManager.saveSettings()
            globals_.scalingManager.applyScaling()

        # Get the theme settings
        setSetting('Theme', dlg.themesTab.themeBox.currentText())
        setSetting('uiStyle', dlg.themesTab.NonWinStyle.currentText())

        # Warn the user that they may need to restart
        QtWidgets.QMessageBox.warning(None, globals_.trans.string('PrefsDlg', 0), globals_.trans.string('PrefsDlg', 30))

    # File-I/O extracted to reggie.ui.level_io.LevelIO (Phase 2 — see
    # _docs/plan/REFACTORING_ANALYSIS.md). Delegators preserve signatures for
    # QAction targets and the cross-module globals_.mainWindow.LoadLevel caller.
    def HandleNewLevel(self):
        return self._levelio.HandleNewLevel()

    def HandleOpenFromName(self):
        return self._levelio.HandleOpenFromName()

    def HandleOpenFromFile(self):
        return self._levelio.HandleOpenFromFile()

    def HandleSave(self):
        return self._levelio.HandleSave()

    def HandleSaveAs(self, copy=False):
        return self._levelio.HandleSaveAs(copy)

    def HandleSaveCopyAs(self):
        return self._levelio.HandleSaveCopyAs()

    def LoadLevel(self, name, isFullPath, areaNum):
        return self._levelio.LoadLevel(name, isFullPath, areaNum)

    def newLevel(self):
        return self._levelio.newLevel()

    def LoadLevel_NSMBW(self, levelData, areaNum):
        return self._levelio.LoadLevel_NSMBW(levelData, areaNum)

    def HandleExit(self):
        """
        Exit the editor. Why would you want to do this anyway?
        """
        self.close()

    def HandleSwitchArea(self, idx):
        """
        Handle activated signals for areaComboBox
        """
        old_idx = globals_.Area.areanum - 1

        if idx == old_idx:
            return

        if self.CheckDirty():
            self.areaComboBox.setCurrentIndex(old_idx)
            return

        ok = self.LoadLevel(self.fileSavePath, True, idx + 1)

        if not ok:
            # loading the new area failed, so reset the combobox
            self.areaComboBox.setCurrentIndex(old_idx)

    def HandleUpdateLayer0(self, checked):
        """
        Handle toggling of layer 0 being shown
        """
        globals_.Layer0Shown = checked

        if globals_.Area is None:
            return

        for obj in globals_.Area.layers[0]:
            obj.setVisible(checked)

        self.scene.update()

    def HandleUpdateLayer1(self, checked):
        """
        Handle toggling of layer 1 being shown
        """
        globals_.Layer1Shown = checked

        if globals_.Area is None:
            return

        for obj in globals_.Area.layers[1]:
            obj.setVisible(checked)

        self.scene.update()

    def HandleUpdateLayer2(self, checked):
        """
        Handle toggling of layer 2 being shown
        """
        globals_.Layer2Shown = checked

        if globals_.Area is None:
            return

        for obj in globals_.Area.layers[2]:
            obj.setVisible(checked)

        self.scene.update()

    def HandleTilesetAnimToggle(self, checked):
        """
        Handle toggling of tileset animations
        """
        globals_.TilesetsAnimating = checked

        for tile in globals_.Tiles:
            if tile is not None: tile.resetAnimation()

        self.scene.update()

    def HandleCollisionsToggle(self, checked):
        """
        Handle toggling of tileset collisions viewing
        """
        globals_.CollisionsShown = checked

        setSetting('ShowCollisions', globals_.CollisionsShown)
        self.scene.update()

    def HandleRealViewToggle(self, checked):
        """
        Handle toggling of Real View
        """
        globals_.RealViewEnabled = checked
        SLib.RealViewEnabled = globals_.RealViewEnabled

        setSetting('RealViewEnabled', globals_.RealViewEnabled)
        self.scene.update()

    def HandleSpritesVisibility(self, checked):
        """
        Handle toggling of sprite visibility
        """
        globals_.SpritesShown = checked
        setSetting('ShowSprites', globals_.SpritesShown)

        if globals_.Area is None:
            return

        for spr in globals_.Area.sprites:
            spr.setVisible(checked)

    def HandleSpriteImages(self, checked):
        """
        Handle toggling of sprite images
        """
        globals_.SpriteImagesShown = checked

        setSetting('ShowSpriteImages', globals_.SpriteImagesShown)

        if globals_.Area is None:
            return

        globals_.DirtyOverride += 1
        for spr in globals_.Area.sprites:
            spr.UpdateRects()

            if globals_.Initializing:
                continue

            # Prevents snapping the sprite to the grid
            spr.ChangingPos = True

            if checked:
                spr.setPos(
                    (spr.objx + spr.ImageObj.xOffset) * 1.5,
                    (spr.objy + spr.ImageObj.yOffset) * 1.5,
                )
            else:
                spr.setPos(
                    spr.objx * 1.5,
                    spr.objy * 1.5,
                )

            spr.ChangingPos = False
            spr.update()

        globals_.DirtyOverride -= 1

        self.levelOverview.update()

    def HandleLocationsVisibility(self, checked):
        """
        Handle toggling of location visibility
        """
        globals_.LocationsShown = checked
        setSetting('ShowLocations', globals_.LocationsShown)

        if globals_.Area is None:
            return

        for loc in globals_.Area.locations:
            loc.setVisible(checked)

    def HandleCommentsVisibility(self, checked):
        """
        Handle toggling of comment visibility
        """
        globals_.CommentsShown = checked
        setSetting('ShowComments', globals_.CommentsShown)

        if globals_.Area is None:
            return

        for com in globals_.Area.comments:
            com.setVisible(checked)

    def HandlePathsVisibility(self, checked):
        """
        Handle toggling of path visibility
        """
        globals_.PathsShown = checked
        setSetting('ShowPaths', globals_.PathsShown)

        if globals_.Area is None:
            return

        for path in globals_.Area.paths:
            path.setVisible(checked)

    def HandleObjectsFreeze(self, checked):
        """
        Handle toggling of objects being frozen
        """
        globals_.ObjectsFrozen = checked
        setSetting('FreezeObjects', globals_.ObjectsFrozen)

        if globals_.Area is None:
            return

        flag1 = QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        flag2 = QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        unfrozen = not checked

        for layer in globals_.Area.layers:
            for obj in layer:
                obj.setFlag(flag1, unfrozen)
                obj.setFlag(flag2, unfrozen)

    def HandleSpritesFreeze(self, checked):
        """
        Handle toggling of sprites being frozen
        """
        globals_.SpritesFrozen = checked
        setSetting('FreezeSprites', globals_.SpritesFrozen)

        if globals_.Area is None:
            return

        flag1 = QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        flag2 = QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        unfrozen = not checked

        for spr in globals_.Area.sprites:
            spr.setFlag(flag1, unfrozen)
            spr.setFlag(flag2, unfrozen)

    def HandleEntrancesFreeze(self, checked):
        """
        Handle toggling of entrances being frozen
        """
        globals_.EntrancesFrozen = checked
        setSetting('FreezeEntrances', globals_.EntrancesFrozen)

        if globals_.Area is None:
            return

        flag1 = QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        flag2 = QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        unfrozen = not checked

        for ent in globals_.Area.entrances:
            ent.setFlag(flag1, unfrozen)
            ent.setFlag(flag2, unfrozen)

    def HandleLocationsFreeze(self, checked):
        """
        Handle toggling of locations being frozen
        """
        globals_.LocationsFrozen = checked
        setSetting('FreezeLocations', globals_.LocationsFrozen)

        if globals_.Area is None:
            return

        flag1 = QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        flag2 = QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        unfrozen = not checked

        for loc in globals_.Area.locations:
            loc.setFlag(flag1, unfrozen)
            loc.setFlag(flag2, unfrozen)

    def HandlePathsFreeze(self, checked):
        """
        Handle toggling of path nodes being frozen
        """
        globals_.PathsFrozen = checked
        setSetting('FreezePaths', globals_.PathsFrozen)

        if globals_.Area is None:
            return

        for path in globals_.Area.paths:
            path.set_freeze(checked)

    def HandleCommentsFreeze(self, checked):
        """
        Handle toggling of comments being frozen
        """
        globals_.CommentsFrozen = checked
        setSetting('FreezeComments', globals_.CommentsFrozen)

        if globals_.Area is None:
            return

        flag1 = QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
        flag2 = QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable
        unfrozen = not checked

        for com in globals_.Area.comments:
            com.setFlag(flag1, unfrozen)
            com.setFlag(flag2, unfrozen)

    def HandleSwitchGrid(self):
        """
        Handle switching of the grid view
        """
        if globals_.GridType is None:
            globals_.GridType = 'grid'
        elif globals_.GridType == 'grid':
            globals_.GridType = 'checker'
        else:
            globals_.GridType = None

        setSetting('GridType', globals_.GridType)
        self.scene.update()

    def HandleUIScaling(self):
        """
        Handle opening the UI Scaling dialog
        """
        from reggie.ui.ui_scaling import ScalingDialog
        
        dlg = ScalingDialog(self)
        dlg.exec()

    # Zoom controls extracted to reggie.ui.zoom.ZoomController (Phase 2 — see
    # _docs/plan/REFACTORING_ANALYSIS.md). Thin delegators keep the QAction
    # wiring (self.HandleZoomIn, ...) and external self.ZoomTo() calls working.
    # ZoomLevel / ZoomLevels stay window attributes (other code reads them).
    def HandleZoomIn(self, *, towardsCursor=False):
        return self._zoom.HandleZoomIn(towardsCursor=towardsCursor)

    def HandleZoomOut(self, *, towardsCursor=False):
        return self._zoom.HandleZoomOut(towardsCursor=towardsCursor)

    def HandleZoomActual(self):
        return self._zoom.HandleZoomActual()

    def HandleZoomMin(self):
        return self._zoom.HandleZoomMin()

    def HandleZoomMax(self):
        return self._zoom.HandleZoomMax()

    def ZoomTo(self, z, *, towardsCursor=False):
        return self._zoom.ZoomTo(z, towardsCursor=towardsCursor)

    def HandleOverviewClick(self, x, y):
        """
        Handle position changes from the level overview
        """
        self.view.centerOn(x, y)
        self.levelOverview.update()

    def SaveComments(self):
        """
        Saves the comments data back to self.Metadata
        """
        b = b""
        for com in globals_.Area.comments:
            text_data = com.text.encode("utf-8")
            # A previous version of this format used the third integer to store
            # the length (number of characters) of the comment string. This
            # makes reading comments back very hard, as a single character can
            # consist of multiple points.
            # So, to indicate we're using the new version, we set a length of
            # 2 ** 32 - 1, and we add an extra int to store the number of bytes
            # in the utf-8 encoding of the comment text.
            b += struct.pack(">4I", com.objx, com.objy, 0xFFFF_FFFF, len(text_data))
            b += text_data

        globals_.Area.Metadata.setBinData('InLevelComments_A%d' % globals_.Area.areanum, b)

    def closeEvent(self, event):
        """
        Handler for the main window close event
        """
        if self.CheckDirty():
            event.ignore()
            return

        # save our state
        self.spriteEditorDock.setVisible(False)
        self.entranceEditorDock.setVisible(False)
        self.pathEditorDock.setVisible(False)
        self.locationEditorDock.setVisible(False)
        self.defaultPropDock.setVisible(False)

        # state: determines positions of docks
        # geometry: determines the main window position
        setSetting('MainWindowState', self.saveState(0))
        setSetting('MainWindowGeometry', self.saveGeometry())

        if hasattr(self, 'HelpBoxInstance'):
            self.HelpBoxInstance.close()

        if hasattr(self, 'TipsBoxInstance'):
            self.TipsBoxInstance.close()

        globals_.gamedef.SetLastLevel(str(self.fileSavePath))

        setSetting('AutoSaveFilePath', None)
        setSetting('AutoSaveFileData', 'x')

        event.accept()

    def ResetPalette(self):
        """
        Resets the palette and initialises the scene from the currently loaded
        Area.
        """
        # Prepare the object picker
        self.objUseLayer1.setChecked(True)

        self.objPicker.LoadFromTilesets()

        self.objAllTab.setCurrentIndex(0)
        self.objAllTab.setTabEnabled(0, (globals_.Area.tileset0 != ''))
        self.objAllTab.setTabEnabled(1, (globals_.Area.tileset1 != ''))
        self.objAllTab.setTabEnabled(2, (globals_.Area.tileset2 != ''))
        self.objAllTab.setTabEnabled(3, (globals_.Area.tileset3 != ''))

        # Load events
        self.LoadEventTabFromLevel()

        # Add all things to the scene
        pcEvent = self.HandleObjPosChange
        for layer in reversed(globals_.Area.layers):
            for obj in layer:
                obj.positionChanged = pcEvent
                self.scene.addItem(obj)

        pcEvent = self.HandleSprPosChange

        self.spriteList.prepareBatchAdd()
        for spr in globals_.Area.sprites:
            spr.positionChanged = pcEvent
            self.spriteList.addSprite(spr)
            self.scene.addItem(spr)
            spr.UpdateListItem()

        self.spriteList.endBatchAdd()

        pcEvent = self.HandleEntPosChange
        for ent in globals_.Area.entrances:
            ent.positionChanged = pcEvent
            ent.listitem = ListWidgetItem_SortsByOther(ent)
            ent.listitem.entid = ent.entid
            self.entranceList.addItem(ent.listitem)
            self.scene.addItem(ent)
            ent.UpdateListItem()

        for zone in globals_.Area.zones:
            self.scene.addItem(zone)

        pcEvent = self.HandleLocPosChange
        scEvent = self.HandleLocSizeChange
        for location in globals_.Area.locations:
            location.positionChanged = pcEvent
            location.sizeChanged = scEvent
            location.listitem = ListWidgetItem_SortsByOther(location)
            self.locationList.addItem(location.listitem)
            self.scene.addItem(location)
            location.UpdateListItem()

        for path in globals_.Area.paths:
            path.add_to_scene()

        for com in globals_.Area.comments:
            com.positionChanged = self.HandleComPosChange
            com.textChanged = self.HandleComTxtChange
            com.listitem = QtWidgets.QListWidgetItem()
            self.commentList.addItem(com.listitem)
            self.scene.addItem(com)
            com.UpdateListItem()

    def ReloadTilesets(self, soft=False):
        """
        Reloads all the tilesets. If soft is True, they will not be reloaded if the filepaths have not changed.
        """
        LoadTilesetInfo(True)

        tilesets = [globals_.Area.tileset0, globals_.Area.tileset1, globals_.Area.tileset2, globals_.Area.tileset3]
        for idx, name in enumerate(tilesets):
            if (name is not None) and (name != ''):
                LoadTileset(idx, name, not soft)

        self.objPicker.LoadFromTilesets()

        for layer in globals_.Area.layers:
            for obj in layer:
                obj.updateObjCache()

        self.scene.update()

    def ReloadSpritedata(self):
        LoadSpriteData()

        # Adjust block counts for extended sprites
        for sprite in globals_.Area.sprites:
            sprite: SpriteItem # type hint
            block_count = globals_.Sprites[sprite.type].extendedSettings
            if block_count > 0:
                current_block_count = len(sprite.spritedata.blocks)
                if current_block_count > block_count:
                    sprite.spritedata.blocks = sprite.spritedata.blocks[:block_count]
                elif current_block_count < block_count:
                    sprite.spritedata.blocks = sprite.spritedata.blocks + [bytes(4)] * (block_count-current_block_count)

        # Reload spritedata editor
        cur_sel_sprite = self.spriteDataEditor.spritetype
        self.spriteDataEditor.setSprite(cur_sel_sprite, True)

        # Update list
        self.sprPicker.UpdateSpriteNames()

        # Redo the search if a search was made
        search = self.spriteSearchTerm.text()
        if search != "":
            self.sprPicker.SetSearchString(search)

    def ChangeSelectionHandler(self):
        """
        Update the visible panels whenever the selection changes
        """
        if self.SelectionUpdateFlag: return

        try:
            selitems = self.scene.selectedItems()
        except RuntimeError:
            # must catch this error: if you close the app while something is selected,
            # you get a RuntimeError about the 'underlying C++ object being deleted'
            return

        # do this to avoid flicker
        showSpritePanel = False
        showEntrancePanel = False
        showLocationPanel = False
        showPathPanel = False
        updateModeInfo = False

        # clear our variables
        self.selObj = None
        self.selObjs = None

        self.spriteList.clearSelection()
        self.entranceList.setCurrentItem(None)
        self.locationList.setCurrentItem(None)
        self.pathList.setCurrentItem(None)
        self.commentList.setCurrentItem(None)

        # possibly a small optimization
        func_ii = isinstance
        type_obj = ObjectItem
        type_spr = SpriteItem
        type_ent = EntranceItem
        type_loc = LocationItem
        type_path = PathItem
        type_com = CommentItem

        if not selitems:
            # nothing is selected
            self.actions['cut'].setEnabled(False)
            self.actions['copy'].setEnabled(False)
            self.actions['shiftitems'].setEnabled(False)
            self.actions['mergelocations'].setEnabled(False)

        elif len(selitems) == 1:
            # only one item, check the type
            self.actions['cut'].setEnabled(True)
            self.actions['copy'].setEnabled(True)
            self.actions['shiftitems'].setEnabled(True)
            self.actions['mergelocations'].setEnabled(False)

            item = selitems[0]
            self.selObj = item
            if func_ii(item, type_spr):
                showSpritePanel = True
                updateModeInfo = True
            elif func_ii(item, type_ent):
                self.creationTabs.setCurrentIndex(2)
                self.UpdateFlag = True
                self.entranceList.setCurrentItem(item.listitem)
                self.UpdateFlag = False
                showEntrancePanel = True
                updateModeInfo = True
            elif func_ii(item, type_loc):
                self.creationTabs.setCurrentIndex(3)
                self.UpdateFlag = True
                self.locationList.setCurrentItem(item.listitem)
                self.UpdateFlag = False
                showLocationPanel = True
                updateModeInfo = True
            elif func_ii(item, type_path):
                self.creationTabs.setCurrentIndex(4)
                self.UpdateFlag = True
                self.pathList.setCurrentItem(item.listitem)
                self.UpdateFlag = False
                showPathPanel = True
                updateModeInfo = True
            elif func_ii(item, type_com):
                self.creationTabs.setCurrentIndex(7)
                self.UpdateFlag = True
                self.commentList.setCurrentItem(item.listitem)
                self.UpdateFlag = False
                updateModeInfo = True

        else:
            updateModeInfo = True

            # more than one item
            self.actions['cut'].setEnabled(True)
            self.actions['copy'].setEnabled(True)
            self.actions['shiftitems'].setEnabled(True)

        # turn on the Stamp Add btn if applicable
        self.stampAddBtn.setEnabled(bool(selitems))

        # count the # of each type, for the statusbar label
        spr = 0
        ent = 0
        obj = 0
        loc = 0
        path = 0
        com = 0
        for item in selitems:
            if func_ii(item, type_spr): spr += 1
            if func_ii(item, type_ent): ent += 1
            if func_ii(item, type_obj): obj += 1
            if func_ii(item, type_loc): loc += 1
            if func_ii(item, type_path): path += 1
            if func_ii(item, type_com): com += 1

        self.actions['mergelocations'].setEnabled(loc >= 2)
        self.layerChangeButton.setEnabled(obj != 0)

        # write the statusbar label text
        text = ''
        if selitems:
            singleitem = len(selitems) == 1
            if singleitem:
                if obj:
                    text = globals_.trans.string('Statusbar', 0)  # 1 object selected
                elif spr:
                    text = globals_.trans.string('Statusbar', 1)  # 1 sprite selected
                elif ent:
                    text = globals_.trans.string('Statusbar', 2)  # 1 entrance selected
                elif loc:
                    text = globals_.trans.string('Statusbar', 3)  # 1 location selected
                elif path:
                    text = globals_.trans.string('Statusbar', 4)  # 1 path node selected
                else:
                    text = globals_.trans.string('Statusbar', 29)  # 1 comment selected
            else:  # multiple things selected; see if they're all the same type
                if not any((spr, ent, loc, path, com)):
                    text = globals_.trans.string('Statusbar', 5, '[x]', obj)  # x objects selected
                elif not any((obj, ent, loc, path, com)):
                    text = globals_.trans.string('Statusbar', 6, '[x]', spr)  # x sprites selected
                elif not any((obj, spr, loc, path, com)):
                    text = globals_.trans.string('Statusbar', 7, '[x]', ent)  # x entrances selected
                elif not any((obj, spr, ent, path, com)):
                    text = globals_.trans.string('Statusbar', 8, '[x]', loc)  # x locations selected
                elif not any((obj, spr, ent, loc, com)):
                    text = globals_.trans.string('Statusbar', 9, '[x]', path)  # x path nodes selected
                elif not any((obj, spr, ent, path, loc)):
                    text = globals_.trans.string('Statusbar', 30, '[x]', com)  # x comments selected
                else:  # different types
                    text = globals_.trans.string('Statusbar', 10, '[x]', len(selitems))  # x items selected
                    types = (
                        (obj, 12, 13),  # variable, translation string ID if var == 1, translation string ID if var > 1
                        (spr, 14, 15),
                        (ent, 16, 17),
                        (loc, 18, 19),
                        (path, 20, 21),
                        (com, 31, 32),
                    )
                    first = True
                    for var, singleCode, multiCode in types:
                        if var > 0:
                            if not first: text += globals_.trans.string('Statusbar', 11)
                            first = False
                            text += globals_.trans.string('Statusbar', (singleCode if var == 1 else multiCode), '[x]', var)
                            # above: '[x]', var) can't hurt if var == 1

                    text += globals_.trans.string('Statusbar', 22)  # ')'

        self.selectionLabel.setText(text)

        self.CurrentSelection = selitems

        for thing in selitems:
            # This helps sync non-objects with objects while dragging
            if not isinstance(thing, ObjectItem):
                thing.dragoffsetx = (((thing.objx // 16) * 16) - thing.objx) * 1.5
                thing.dragoffsety = (((thing.objy // 16) * 16) - thing.objy) * 1.5

        self.spriteEditorDock.setVisible(showSpritePanel)
        self.entranceEditorDock.setVisible(showEntrancePanel)
        self.locationEditorDock.setVisible(showLocationPanel)
        self.pathEditorDock.setVisible(showPathPanel)

        self.actions['deselect'].setEnabled(bool(selitems))

        if updateModeInfo:
            globals_.DirtyOverride += 1
            self.UpdateModeInfo()
            globals_.DirtyOverride -= 1

    def HandleObjPosChange(self, obj, oldx, oldy, x, y):
        """
        Handle the object being dragged
        """
        if obj == self.selObj:
            if oldx == x and oldy == y: return
            SetDirty()
        self.levelOverview.update()

    def CreationTabChanged(self, nt):
        """
        Handles the selected palette tab changing
        """
        CPT = -1

        if nt == 0:  # objects
            CPT = self.objAllTab.currentIndex()
        elif nt == 1:  # sprites
            # Ensure the user can't paint sprites
            # when the 'current sprites' tab is
            # opened.
            if self.sprAllTab.currentIndex() != 1:
                CPT = 4
        elif nt == 2:
            CPT = 5  # entrances
        elif nt == 3:
            CPT = 7  # locations
        elif nt == 4:
            CPT = 6  # paths
        elif nt == 6:
            CPT = 8  # stamp pad
        elif nt == 7:
            CPT = 9  # comment

        globals_.CurrentPaintType = CPT
        
        # Deactivate QPT tools when switching away from Quick Paint palette tab
        if hasattr(self, 'qpt_palette') and self.qpt_palette:
            # Find the Quick Paint tab index
            qpt_tab_index = -1
            for i in range(self.creationTabs.count()):
                if self.creationTabs.widget(i) == self.qpt_palette:
                    qpt_tab_index = i
                    break
            
            if qpt_tab_index != -1:
                if nt != qpt_tab_index:
                    # Switching away from Quick Paint tab - deactivate all tools
                    quick_paint_tab = self.qpt_palette.get_quick_paint_tab()
                    if quick_paint_tab and quick_paint_tab.is_painting():
                        quick_paint_tab.qpt_widget.on_stop_painting()
                        print("[Reggie] Stopped QPT painting - switched to different palette tab")
                    
                    from reggie.plugins.quickpaint.core.tool_manager import get_tool_manager
                    tool_manager = get_tool_manager()
                    tool_manager.deactivate_all()
                    # Reset cursor
                    if self.view:
                        self.view.setCursor(QtCore.Qt.CursorShape.ArrowCursor)
                    print("[Reggie] Deactivated QPT tools - switched to different palette tab")
                    # Hide hotkey overlay when switching away
                    qpt_funcs = getattr(globals_, 'qpt_functions', None)
                    if qpt_funcs and qpt_funcs.get('hide_overlay'):
                        qpt_funcs['hide_overlay']()
                else:
                    # Switching TO Quick Paint tab - activate QPT as default tool
                    from reggie.plugins.quickpaint.core.tool_manager import get_tool_manager, ToolType
                    tool_manager = get_tool_manager()
                    tool_manager.activate_tool(ToolType.QPT_SMART_PAINT)
                    print("[Reggie] Activated QPT tool - switched to Quick Paint palette tab")
                    # Show hotkey overlay when switching to QPT tab
                    qpt_funcs = getattr(globals_, 'qpt_functions', None)
                    if qpt_funcs and qpt_funcs.get('show_overlay'):
                        qpt_funcs['show_overlay']()

    def ObjTabChanged(self, nt):
        """
        Handles the selected slot tab in the object palette changing
        """
        if hasattr(self, 'objPicker'):
            if 0 <= nt <= 3:
                self.objPicker.ShowTileset(nt)
                eval('self.objTS%dTab' % nt).setLayout(self.createObjectLayout)
            self.defaultPropDock.setVisible(False)

        globals_.CurrentPaintType = nt

    def SprTabChanged(self, nt):
        """
        Handles the selected tab in the sprite palette changing
        """
        if nt == 0:
            cpt = 4
        else:
            cpt = -1

        globals_.CurrentPaintType = cpt

    def ChangeSelectionLayer(self, checked):
        """
        Changes the layer of the selection to the current layer.
        """
        self.ChangeSelectedObjectsLayer(globals_.CurrentLayer)

    def LayerChoiceChanged(self, nl):
        """
        Handles the selected layer changing
        """
        globals_.CurrentLayer = nl

        # Sync QPT layer radio buttons
        if hasattr(self, 'qpt_palette') and self.qpt_palette:
            qpt_tab = self.qpt_palette.get_quick_paint_tab()
            if qpt_tab and hasattr(qpt_tab, 'qpt_widget'):
                qpt_tab.qpt_widget.set_layer_silent(nl)
            fill_tab = self.qpt_palette.get_fill_paint_tab()
            if fill_tab:
                fill_tab.set_layer_silent(nl)

        # should we replace?
        if QtWidgets.QApplication.keyboardModifiers() == Qt.KeyboardModifier.AltModifier:
            self.ChangeSelectedObjectsLayer(nl)

    def ChangeSelectedObjectsLayer(self, new_layer_id):
        """
        Changes the layer of the selected objects to the new layer.
        """
        assert new_layer_id in (0, 1, 2)

        items = self.scene.selectedItems()
        type_obj = ObjectItem
        area = globals_.Area
        change = []

        for x in items:
            if isinstance(x, type_obj) and x.layer != new_layer_id:
                change.append(x)

        if not change:
            return

        change.sort(key=lambda x: x.zValue())
        newLayer = area.layers[new_layer_id]

        if not newLayer:
            z_value = (2 - new_layer_id) * 8192
        else:
            z_value = newLayer[-1].zValue() + 1

        if new_layer_id == 0:
            newVisibility = globals_.Layer0Shown
        elif new_layer_id == 1:
            newVisibility = globals_.Layer1Shown
        else:
            newVisibility = globals_.Layer2Shown

        for item in change:
            area.RemoveFromLayer(item)
            item.layer = new_layer_id
            newLayer.append(item)

            item.setZValue(z_value)
            item.setVisible(newVisibility)
            item.update()
            item.UpdateTooltip()

            z_value += 1

        self.scene.update()
        SetDirty()

    def ObjectChoiceChanged(self, type_):
        """
        Handles a new object being chosen
        """
        globals_.CurrentObject = type_

    def ObjectReplace(self, type):
        """
        Handles a new object being chosen to replace the selected objects
        """
        items = self.scene.selectedItems()
        type_obj = ObjectItem
        tileset = globals_.CurrentPaintType
        changed = False

        for x in items:
            if isinstance(x, type_obj) and (x.tileset != tileset or x.type != type):
                x.SetType(tileset, type)
                x.update()
                changed = True

        if changed:
            SetDirty()

    def SpriteChoiceChanged(self, type):
        """
        Handles a new sprite being chosen
        """
        globals_.CurrentSprite = type

        if type != 1000 and type >= 0:
            self.defaultDataEditor.setSprite(
                type,
                initial_data = RawData.from_sprite_id(type)
            )
            self.defaultPropButton.setEnabled(True)
        else:
            self.defaultPropButton.setEnabled(False)
            self.defaultPropDock.setVisible(False)
            self.defaultDataEditor.update()

    def _onSpriteImageLoadingProgress(self, current, total):
        """
        Updates the sprite image loading progress label.
        total == -1 signals that loading is complete.
        """
        if total == -1:
            self.spriteImagesLoadingLabel.hide()
        else:
            self.spriteImagesLoadingLabel.setText(
                globals_.trans.string('Sprites', 25, '[current]', current, '[total]', total)
            )
            self.spriteImagesLoadingLabel.show()

    def SpriteReplace(self, type):
        """
        Handles a new sprite type being chosen to replace the selected sprites
        """
        items = self.scene.selectedItems()
        type_spr = SpriteItem
        changed = False

        for x in items:
            if isinstance(x, type_spr):
                x.spritedata = self.defaultDataEditor.data  # change this first or else images get messed up
                x.SetType(type)
                x.update()
                changed = True

        if changed:
            SetDirty()

        self.ChangeSelectionHandler()

    def SelectNewSpriteView(self, type):
        """
        Handles a new sprite view being chosen
        """
        cat = globals_.SpriteCategories[type]
        self.sprPicker.SwitchView(cat)

        isSearch = (type == 0)
        layout = self.spriteSearchLayout
        layout.itemAt(0).widget().setVisible(isSearch)
        layout.itemAt(1).widget().setVisible(isSearch)

    def NewSearchTerm(self, text):
        """
        Handles a new sprite search term being entered
        """
        self.sprPicker.SetSearchString(text)

    def ShowDefaultProps(self):
        """
        Handles the Show Default Properties button being clicked
        """
        self.defaultPropDock.setVisible(True)

    def HandleSprPosChange(self, obj, oldx, oldy, x, y):
        """
        Handle the sprite being dragged
        """
        if obj == self.selObj:
            if oldx == x and oldy == y: return
            obj.UpdateListItem()
            SetDirty()

            # The sprite has changed position, so its LevelRect changed, so the
            # level overview needs to be redrawn.
            self.levelOverview.update()

    def SpriteDataUpdated(self, data):
        """
        Handle the current sprite's data being updated
        """
        if self.spriteEditorDock.isVisible():
            obj = self.selObj
            obj.spritedata = data
            obj.UpdateListItem()
            SetDirty()

            obj.UpdateDynamicSizing()
            self.spriteList.updateSprite(obj)

    def HandleEntPosChange(self, obj, oldx, oldy, x, y):
        """
        Handle the entrance being dragged
        """
        if oldx == x and oldy == y: return
        obj.UpdateListItem()
        if obj == self.selObj:
            SetDirty()

    def HandlePathPosChange(self, obj, oldx, oldy, x, y):
        """
        Handle the path being dragged
        """
        if oldx == x and oldy == y: return
        obj.path.node_moved(obj)
        obj.UpdateListItem()
        if obj == self.selObj:
            SetDirty()

    def HandleComPosChange(self, obj, oldx, oldy, x, y):
        """
        Handle the comment being dragged
        """
        if oldx == x and oldy == y: return
        obj.UpdateTooltip()
        obj.handlePosChange(oldx, oldy)
        obj.UpdateListItem()
        if obj == self.selObj:
            self.SaveComments()
            SetDirty()

    def HandleComTxtChange(self, obj):
        """
        Handle the comment's text being changed
        """
        obj.UpdateListItem()
        obj.UpdateTooltip()
        self.SaveComments()
        SetDirty()

    def HandleEntranceSelectByList(self, item):
        """
        Handle an entrance being selected from the list
        """
        if self.UpdateFlag: return

        ent = item.reference
        ent.ensureVisible(xMargin=192, yMargin=192)
        self.scene.clearSelection()
        ent.setSelected(True)

    def HandleEntranceToolTipAboutToShow(self, item):
        """
        Handle an entrance being hovered in the list
        """
        for ent in globals_.Area.entrances:
            if ent.listitem == item:
                ent.UpdateListItem(True)
                break

    def HandleLocationSelectByList(self, item):
        """
        Handle a location being selected from the list
        """
        if self.UpdateFlag: return

        loc = item.reference
        loc.ensureVisible(xMargin=192, yMargin=192)
        self.scene.clearSelection()
        loc.setSelected(True)

    def HandleLocationToolTipAboutToShow(self, item):
        """
        Handle a location being hovered in the list
        """
        item.reference.UpdateListItem(True)

    def HandlePathSelectByList(self, item):
        """
        Handle a path node being selected
        """
        path_item = item.reference

        path_item.ensureVisible(xMargin=192, yMargin=192)
        self.scene.clearSelection()
        path_item.setSelected(True)

    def HandlePathToolTipAboutToShow(self, item):
        """
        Handle a path node being hovered in the list
        """
        item.reference.UpdateListItem(True)

    def HandleCommentSelectByList(self, item):
        """
        Handle a comment being selected
        """
        for comment in globals_.Area.comments:
            if comment.listitem == item:
                comment.ensureVisible(xMargin=192, yMargin=192)
                self.scene.clearSelection()
                comment.setSelected(True)
                break

    def HandleCommentToolTipAboutToShow(self, item):
        """
        Handle a comment being hovered in the list
        """
        for comment in globals_.Area.comments:
            if comment.listitem == item:
                comment.UpdateListItem(True)
                break

    def HandleLocPosChange(self, loc, oldx, oldy, x, y):
        """
        Handle the location being dragged
        """
        if loc == self.selObj:
            if oldx == x and oldy == y: return
            self.locationEditor.setLocation(loc)
            SetDirty()

        loc.UpdateListItem()
        self.levelOverview.update()

    def HandleLocSizeChange(self, loc, width, height):
        """
        Handle the location being resized
        """
        if loc == self.selObj:
            self.locationEditor.setLocation(loc)
            SetDirty()

        loc.UpdateListItem()
        self.levelOverview.update()

    def UpdateModeInfo(self):
        """
        Change the info in the currently visible panel
        """
        self.UpdateFlag = True

        if self.spriteEditorDock.isVisible():
            obj = self.selObj
            self.spriteDataEditor.setSprite(obj.type, initial_data=obj.spritedata)
        elif self.entranceEditorDock.isVisible():
            self.entranceEditor.setEntrance(self.selObj)
        elif self.pathEditorDock.isVisible():
            self.pathEditor.setPath(self.selObj)
        elif self.locationEditorDock.isVisible():
            self.locationEditor.setLocation(self.selObj)

        self.UpdateFlag = False

    def PositionHovered(self, x, y):
        """
        Handle a position being hovered in the view
        """
        info = ''
        hovereditems = self.scene.items(QtCore.QPointF(x, y))
        hovered = None
        type_zone = ZoneItem
        type_peline = PathEditorLineItem
        for item in hovereditems:
            hover = item.hover if hasattr(item, 'hover') else True
            if (not isinstance(item, (type_zone, type_peline))) and hover:
                hovered = item
                break

        if hovered is not None:
            if isinstance(hovered, ObjectItem):  # Object
                info = globals_.trans.string('Statusbar', 23, '[width]', hovered.width, '[height]', hovered.height, '[xpos]',
                                    hovered.objx, '[ypos]', hovered.objy, '[layer]', hovered.layer, '[type]',
                                    hovered.type, '[tileset]', hovered.tileset + 1)
            elif isinstance(hovered, SpriteItem):  # Sprite
                info = globals_.trans.string('Statusbar', 24, '[name]', hovered.name, '[xpos]', hovered.objx, '[ypos]',
                                    hovered.objy)
            elif isinstance(hovered, SLib.AuxiliaryItem):  # Sprite (auxiliary thing) (treat it like the actual sprite)
                info = globals_.trans.string('Statusbar', 24, '[name]', hovered.parentItem().name, '[xpos]',
                                    hovered.parentItem().objx, '[ypos]', hovered.parentItem().objy)
            elif isinstance(hovered, EntranceItem):  # Entrance
                info = globals_.trans.string('Statusbar', 25, '[name]', hovered.name, '[xpos]', hovered.objx, '[ypos]',
                                    hovered.objy, '[dest]', hovered.destination)
            elif isinstance(hovered, LocationItem):  # Location
                info = globals_.trans.string('Statusbar', 26, '[id]', int(hovered.id), '[xpos]', int(hovered.objx), '[ypos]',
                                    int(hovered.objy), '[width]', int(hovered.width), '[height]', int(hovered.height))
            elif isinstance(hovered, PathItem):  # Path
                info = globals_.trans.string('Statusbar', 27, '[path]', hovered.pathid, '[node]', hovered.nodeid, '[xpos]',
                                    hovered.objx, '[ypos]', hovered.objy)
            elif isinstance(hovered, CommentItem):  # Comment
                info = globals_.trans.string('Statusbar', 33, '[xpos]', hovered.objx, '[ypos]', hovered.objy, '[text]',
                                    hovered.OneLineText())

        self.posLabel.setText(
            globals_.trans.string('Statusbar', 28, '[objx]', int(x / 24), '[objy]', int(y / 24), '[sprx]', int(x / 1.5),
                         '[spry]', int(y / 1.5)))
        self.hoverLabel.setText(info)

    def AddWarningIcon(self, message):
        """
        Adds a warning icon to the status bar with a tooltip
        """
        # Create warning label with icon
        warningLabel = QtWidgets.QLabel()
        warningLabel.setPixmap(self.style().standardIcon(QtWidgets.QStyle.StandardPixmap.SP_MessageBoxWarning).pixmap(16, 16))
        warningLabel.setToolTip(message)
        warningLabel.setStyleSheet("QLabel { margin: 2px; }")
        warningLabel.setCursor(QtCore.Qt.CursorShape.PointingHandCursor)
        
        # Make it clickable to dismiss
        warningLabel.mousePressEvent = lambda event: self.RemoveWarningIcon(warningLabel)
        
        # Add to status bar at the beginning
        self.statusBar().insertWidget(0, warningLabel)
        self.warningIcons.append(warningLabel)
        
        # Set up auto-dismiss timer (60 seconds)
        timer = QtCore.QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self.RemoveWarningIcon(warningLabel))
        timer.start(60000)
        warningLabel.dismissTimer = timer
        
    def RemoveWarningIcon(self, warningLabel):
        """
        Removes a warning icon from the status bar
        """
        if warningLabel in self.warningIcons:
            self.warningIcons.remove(warningLabel)
            self.statusBar().removeWidget(warningLabel)
            if hasattr(warningLabel, 'dismissTimer'):
                warningLabel.dismissTimer.stop()
            warningLabel.deleteLater()

    def keyPressEvent(self, event):
        """
        Handles key press events for the main window if needed
        """
        # QPT: Global P hotkey to switch to Quick Paint tab from any palette tab
        if event.key() == Qt.Key.Key_P.value:
            if hasattr(self, 'qpt_palette') and self.qpt_palette and hasattr(self, 'creationTabs'):
                # Find the Quick Paint tab index and switch to it
                for i in range(self.creationTabs.count()):
                    if self.creationTabs.widget(i) == self.qpt_palette:
                        if self.creationTabs.currentIndex() != i:
                            self.creationTabs.setCurrentIndex(i)
                            print("[Reggie] P hotkey: Switched to Quick Paint tab")
                        event.accept()
                        return
        
        # QPT: Handle ESC, Q, F, D, F1, F2 keys for painting tools
        # Only forward hotkeys when the Quick Paint palette tab is active
        # Use .value for comparison since event.key() returns int in PyQt6
        qpt_keys = (Qt.Key.Key_Escape.value, Qt.Key.Key_Q.value, Qt.Key.Key_S.value, Qt.Key.Key_C.value, Qt.Key.Key_E.value, Qt.Key.Key_F.value, Qt.Key.Key_D.value, Qt.Key.Key_F1.value, Qt.Key.Key_F2.value, Qt.Key.Key_F3.value)
        if event.key() in qpt_keys:
            # Check if Quick Paint palette is the active tab
            qpt_tab_active = False
            if hasattr(self, 'qpt_palette') and self.qpt_palette and hasattr(self, 'creationTabs'):
                for i in range(self.creationTabs.count()):
                    if self.creationTabs.widget(i) == self.qpt_palette:
                        qpt_tab_active = (self.creationTabs.currentIndex() == i)
                        break
            
            if qpt_tab_active:
                try:
                    qpt_funcs = getattr(globals_, 'qpt_functions', None)
                    if qpt_funcs and qpt_funcs.get('key_press'):
                        if qpt_funcs['key_press'](event.key()):
                            event.accept()
                            return
                except Exception as e:
                    print(f"[Reggie] Error forwarding key to QPT: {e}")
                    pass
        
        if event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
            sel = self.scene.selectedItems()

            if sel:

                self.SelectionUpdateFlag = True

                for obj in sel:
                    obj.delete()
                    obj.setSelected(False)
                    self.scene.removeItem(obj)

                SetDirty()
                event.accept()
                self.levelOverview.update()
                self.SelectionUpdateFlag = False
                self.ChangeSelectionHandler()
                return

        self.levelOverview.update()

        QtWidgets.QMainWindow.keyPressEvent(self, event)

    def HandleAreaOptions(self):
        """
        Pops up the options for Area Dialogue
        """
        dlg = deferred.AreaOptionsDialog()
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        SetDirty()

        # Sprites
        # Extracting the sprite id from the sprite name is hacky, but it works.
        globals_.Area.loaded_sprites = set(int(desc.split(']')[0][1:]) for desc in dlg.LoadedSpritesTab.auto_model.stringList())
        globals_.Area.force_loaded_sprites = set(int(desc.split(']')[0][1:]) for desc in dlg.LoadedSpritesTab.custom_model.stringList())

        # Settings
        globals_.Area.timeLimit = dlg.LoadingTab.timer.value() - 200
        globals_.Area.startEntrance = dlg.LoadingTab.entrance.value()
        globals_.Area.toadHouseType = dlg.LoadingTab.toadHouseType.currentIndex()
        globals_.Area.wrapFlag = dlg.LoadingTab.wrap.isChecked()
        globals_.Area.creditsFlag = dlg.LoadingTab.credits.isChecked()
        globals_.Area.ambushFlag = dlg.LoadingTab.ambush.isChecked()
        globals_.Area.unkFlag1 = dlg.LoadingTab.unk1.isChecked()
        globals_.Area.unkFlag2 = dlg.LoadingTab.unk2.isChecked()
        globals_.Area.unkVal1 = dlg.LoadingTab.unk3.value()
        globals_.Area.unkVal2 = dlg.LoadingTab.unk4.value()

        # Tilesets
        for idx, fname in enumerate(dlg.TilesetsTab.values()):

            if fname in ('', None):
                fname = ''
            elif fname.startswith(globals_.trans.string('AreaDlg', 16)):
                fname = fname[len(globals_.trans.string('AreaDlg', 17, '[name]', '')):]

            if idx == 0:
                globals_.Area.tileset0 = fname
            elif idx == 1:
                globals_.Area.tileset1 = fname
            elif idx == 2:
                globals_.Area.tileset2 = fname
            else:
                globals_.Area.tileset3 = fname

            if fname != '':
                LoadTileset(idx, fname)
            else:
                UnloadTileset(idx)

        self.objPicker.LoadFromTilesets()
        self.objAllTab.setCurrentIndex(0)
        self.objAllTab.setTabEnabled(0, (globals_.Area.tileset0 != ''))
        self.objAllTab.setTabEnabled(1, (globals_.Area.tileset1 != ''))
        self.objAllTab.setTabEnabled(2, (globals_.Area.tileset2 != ''))
        self.objAllTab.setTabEnabled(3, (globals_.Area.tileset3 != ''))

        for layer in globals_.Area.layers:
            for obj in layer:
                obj.updateObjCache()

        self.scene.update()

        # Reset Quick Paint Tool when area settings change (tilesets may have changed)
        if hasattr(self, 'qpt_palette') and self.qpt_palette is not None:
            try:
                self.qpt_palette.reset()
            except Exception as e:
                print(f"[QPT] Warning: Could not reset QPT: {e}")

    def HandleZones(self):
        """
        Pops up the options for Zone dialog
        """
        LoadZoneThemes()

        dlg = deferred.ZonesDialog()
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            self.levelOverview.update()
            return

        SetDirty()

        # resync the zones
        items = self.scene.items()
        func_ii = isinstance
        type_zone = ZoneItem

        for item in items:
            if func_ii(item, type_zone):
                self.scene.removeItem(item)

        globals_.Area.zones = []

        for i, tab in enumerate(dlg.zoneTabs):
            z = tab.zoneObj
            z.id = i
            z.UpdateTitle()
            globals_.Area.zones.append(z)
            self.scene.addItem(z)

            z.objx = common.clamp(16, 24560, tab.Zone_xpos.value())
            z.objy = common.clamp(16, 12272, tab.Zone_ypos.value())
            z.width = min(24560 - z.objx, tab.Zone_width.value())
            z.height = min(12272 - z.objy, tab.Zone_height.value())

            z.prepareGeometryChange()
            z.UpdateRects()
            z.setPos(z.objx * 1.5, z.objy * 1.5)

            z.modeldark = tab.Zone_modeldark.currentIndex()
            z.terraindark = tab.Zone_terraindark.currentIndex()
            z.cammode = tab.Zone_cammodezoom.modeButtonGroup.checkedId()
            z.camzoom = tab.Zone_cammodezoom.screenSizes.currentIndex()
            z.camtrack = tab.Zone_direction.currentIndex()

            if tab.Zone_yrestrict.isChecked():
                z.mpcamzoomadjust = tab.Zone_mpzoomadjust.value()
            else:
                z.mpcamzoomadjust = 15

            z.visibility = 0

            if tab.Zone_vspotlight.isChecked():
                z.visibility |= 1 << 4
            if tab.Zone_vfulldark.isChecked():
                z.visibility |= 1 << 5

            z.visibility |= tab.Zone_visibility.currentIndex()

            z.yupperbound = tab.Zone_yboundup.value()
            z.ylowerbound = tab.Zone_ybounddown.value()
            z.yupperbound2 = tab.Zone_yboundup2.value()
            z.ylowerbound2 = tab.Zone_ybounddown2.value()
            z.yupperbound3 = tab.Zone_yboundup3.value()
            z.ylowerbound3 = tab.Zone_ybounddown3.value()

            z.music = tab.Zone_musicid.value()
            z.sfxmod = tab.Zone_sfx.currentIndex() << 4
            if tab.Zone_boss.isChecked():
                z.sfxmod |= 1

        for spr in globals_.Area.sprites:
            spr.ImageObj.positionChanged()

        self.actions['backgrounds'].setEnabled(len(globals_.Area.zones) > 0)
        self.levelOverview.update()

    # Handles setting the backgrounds
    def HandleBG(self):
        """
        Pops up the Background settings Dialog
        """
        dlg = deferred.BGDialog()
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        SetDirty()
        for tab, z in zip(dlg.BGTabs, globals_.Area.zones):
            # first index: BGA/BGB
            # second index: X/Y
            z.XpositionA = tab.pos_boxes[0][0].value()
            z.YpositionA = -tab.pos_boxes[0][1].value()
            z.XpositionB = tab.pos_boxes[1][0].value()
            z.YpositionB = -tab.pos_boxes[1][1].value()

            z.XscrollA = tab.scroll_boxes[0][0].currentIndex()
            z.YscrollA = tab.scroll_boxes[0][1].currentIndex()
            z.XscrollB = tab.scroll_boxes[1][0].currentIndex()
            z.YscrollB = tab.scroll_boxes[1][1].currentIndex()

            z.ZoomA = tab.zoom_boxes[0].currentIndex()
            z.ZoomB = tab.zoom_boxes[1].currentIndex()

            z.bg1A = tab.hex_boxes[0][0].value()
            z.bg2A = tab.hex_boxes[0][1].value()
            z.bg3A = tab.hex_boxes[0][2].value()

            z.bg1B = tab.hex_boxes[1][0].value()
            z.bg2B = tab.hex_boxes[1][1].value()
            z.bg3B = tab.hex_boxes[1][2].value()

    def HandleScreenshot(self):
        """
        Takes a screenshot of the entire level and saves it
        """

        dlg = ScreenCapChoiceDialog()
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        screenshot_type = dlg.zoneCombo.currentIndex()
        hide_background = dlg.hide_background.isChecked()
        do_save = dlg.save_img.isChecked()

        if do_save:
            fn = QtWidgets.QFileDialog.getSaveFileName(self,
                globals_.trans.string('FileDlgs', 3), 'untitled.png',
                globals_.trans.string('FileDlgs', 4) + ' (*.png)')[0]

            if fn == '':
                return

        if screenshot_type == 0:  # Current view
            screenshot_rect = QtCore.QRect(QtCore.QPoint(), self.view.size())
            renderer = self.view
            ss_img = QtGui.QImage(screenshot_rect.size(), QtGui.QImage.Format.Format_ARGB32)

        else:
            if screenshot_type == 1:  # All zones together
                screenshot_rect = QtCore.QRectF()

                for z in globals_.Area.zones:
                    screenshot_rect |= z.ZoneRect

            else:  # One specific zone
                screenshot_rect = globals_.Area.zones[screenshot_type - 2].ZoneRect

            # Map the zone rects to the scene coordinate system
            screenshot_rect = (QtGui.QTransform() * 1.5).mapRect(screenshot_rect)
            # Add 40 pixels of padding on all sides
            screenshot_rect += QtCore.QMarginsF(40, 40, 40, 40)
            # Make sure the rectangle doesn't go out of bounds
            screenshot_rect &= QtCore.QRectF(0, 0, 1024 * 24, 512 * 24)

            renderer = self.scene
            ss_img = QtGui.QImage(screenshot_rect.size().toSize(), QtGui.QImage.Format.Format_ARGB32)

        ss_img.fill(Qt.GlobalColor.transparent)
        ss_painter = QtGui.QPainter(ss_img)

        if hide_background:
            # Remove the background
            brush = self.scene.backgroundBrush()
            style = brush.style()
            brush.setStyle(Qt.BrushStyle.NoBrush)
            self.scene.setBackgroundBrush(brush)

            # Render
            renderer.render(ss_painter, source=screenshot_rect)

            # Restore the background
            brush.setStyle(style)
            self.scene.setBackgroundBrush(brush)

        else:
            # Render with background
            renderer.render(ss_painter, source=screenshot_rect)

        ss_painter.end()

        if do_save:
            ss_img.save(fn, 'PNG', 50)
        else:
            globals_.app.clipboard().setImage(ss_img)

    @staticmethod
    def HandleDiagnostics():
        """
        Checks the level for any obvious problems and provides options to autofix them
        """
        DiagnosticToolDialog().exec()

    def HandleCameraProfiles(self):
        """Pops up the options for camera profiles"""
        dlg = CameraProfilesDialog()
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        camprofiles = []
        for row in range(dlg.list.count()):
            item = dlg.list.item(row)
            camprofiles.append(item.data(QtCore.Qt.ItemDataRole.UserRole))

        globals_.Area.camprofiles = camprofiles
        SetDirty()
