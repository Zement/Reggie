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

# The version check lives in app.py, which is the entry point: nothing can
# reach this module without having passed it. A second copy here claimed 3.5,
# which was both stale and unreachable - and a wrong number in the tree is
# worse than no number, because it is the one people read.
import sys

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
from reggie.ui.tabs import MasterTabWidget
from reggie.ui.sidebar import Percent
from reggie.ui.unsavedlist import dirty_entries, dirty_paths

#: The undo history section's starting and maximum heights, as percentages of
#: the sidebar (Zement, 2026-08-30). Relative rather than absolute because 400px
#: was chosen on one machine and came out at 40% of a shorter sidebar - the same
#: reasoning that put the level overview's size behind a percentage in D-c.4.
#: Over 100 is allowed and means "taller than the sidebar", which scrolls.
UNDO_SECTION_DEFAULT_HEIGHT = Percent(15)
UNDO_SECTION_MAX_HEIGHT = Percent(75)

from reggie.ui import tooltabs
from reggie.ui import focusgroups
from reggie.ui.tooltabs import ToolTabManager

#: Version marker for saveState/restoreState (Block D-c).
#
# Bump this whenever the set of docks changes. Qt ignores a state whose version
# does not match, so a bump discards a layout describing a window that no longer
# exists and applies the new default instead - no migration code, no prompt, and
# no partly-applied layout. 0 was the pre-D-c editor; 1 is D-c.3, where the
# palette and the four property editors stopped being docks.
LAYOUT_VERSION = 1
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
from reggie.core import undo
from reggie.core.undo import UndoStack
from reggie.io.translation import LoadTranslation

# Quick Paint Tool boot state now lives on reggie.ui.qpt_boot (imported below),
# not in this module. It's still loaded lazily in main() after the QApplication
# exists (importing quickpaint eagerly breaks the import chain).

################################################################################
################################################################################
################################################################################


def _list_row_is_live(item):
    """Whether an item's side-list row still exists on the C++ side.

    QListWidget.clear() *destroys* the QListWidgetItems it holds, and every
    level item keeps a reference to its own row in `self.listitem`. So a row can
    be present as a Python object and already freed underneath - and touching a
    freed one is a hard crash inside Qt rather than an exception Python can
    catch. text() is the cheapest probe that forces the round trip.
    """
    listitem = getattr(item, 'listitem', None)
    if listitem is None:
        return False

    try:
        listitem.text()
    except RuntimeError:
        return False

    return True


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

        # Version/credit string goes below here. 64 char max (32 if non-ascii).
        # The attribute keeps its Reggie-era name: LoadReggieInfo/
        # DecodeOldReggieInfo in core/level.py are the *level metadata* path and
        # are a different thing that happens to share the word.
        self.ReggieInfo = globals_.ReginaldID

        self.ZoomLevels = [7.5, 10.0, 15.0, 20.0, 25.0, 30.0, 35.0, 40.0, 45.0, 50.0, 55.0, 60.0, 65.0, 70.0, 75.0,
                           85.0, 90.0, 95.0, 100.0, 125.0, 150.0, 175.0, 200.0, 250.0, 300.0, 350.0, 400.0]

        # The undo stack lives on the editor session, not here - two open areas
        # must not share a history. `self.undoStack` is a property below that
        # forwards to the active session, so the ~40 call sites that push onto
        # `mainWindow.undoStack` keep working untouched.
        #
        # This one is the fallback for when no session exists yet: the window is
        # constructed before the first level is opened, and its signals are
        # wired to it during __init2__.
        self._fallbackUndoStack = UndoStack()

        # required variables
        self.UpdateFlag = False
        self.SelectionUpdateFlag = False

        # selObj / CurrentSelection / ZoomLevel are properties below, forwarding
        # to the active session (D-c.4). These are the fallbacks they use before
        # a session exists - the window is built before the first level opens.
        self._fallbackSelObj = None
        self._fallbackSelection = []
        self._fallbackZoomLevel = 100.0

        # set up the window
        QtWidgets.QMainWindow.__init__(self, None)
        # Don't include version here - Qt automatically appends application display name
        self.setWindowTitle('Reggie! Next Level Editor')
        # Use PNG for QIcon on all platforms - .icns files cause crashes in PyQt6 on macOS ARM64
        # The native dock icon is handled by the .icns in the app bundle
        self.setWindowIcon(QtGui.QIcon('reggiedata/icon.png'))
        self.setIconSize(QtCore.QSize(16, 16))
        self.setUnifiedTitleAndToolBarOnMac(True)

        # The canvas belongs to the active session from D-c.1 on; self.scene and
        # self.view are properties reading it. This pair is the fallback, used
        # before the first level is opened - the window exists and is shown well
        # before any session does, and ~87 call sites read mainWindow.scene /
        # .view without checking.
        # The same idea for the open file's path, and for the same reason it is
        # needed early: `fileSavePath` is a property since D-d.3b, and it is
        # read before any session exists.
        self._fileSavePath = None

        self._fallbackScene = LevelScene(0, 0, 1024 * 24, 512 * 24, self)
        self._fallbackScene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.NoIndex)
        self._fallbackScene.selectionChanged.connect(self.ChangeSelectionHandler)

        self._fallbackView = LevelViewWidget(self._fallbackScene, self)
        self._fallbackView.centerOn(0, 0)  # this scrolls to the top left
        self._fallbackView.PositionHover.connect(self.PositionHovered)
        self._fallbackView.XScrollBar.valueChanged.connect(self.XScrollChange)
        self._fallbackView.YScrollBar.valueChanged.connect(self.YScrollChange)
        self._fallbackView.FrameSize.connect(self.HandleWindowSizeChange)

        # The master container (D-c.2): one tab per open session. Since D-c.3 it
        # is no longer the central widget itself - it shares a splitter with the
        # sidebar, and that splitter is the centre. The fallback view is what
        # the container shows while no session exists: during this constructor,
        # and in the headless suites that never open one.
        self.tabs = MasterTabWidget(self)
        self.sidebar = None

        # The tool tabs (D-c.5) - Preferences, the Patch Manager, the undo
        # history and the collaboration window, as pages rather than windows.
        # Built here, before anything can open one, and beside the session
        # manager rather than inside it: sessions are levels, and none of these
        # four is a level.
        self.toolTabs = ToolTabManager(self)

        self.centralSplitter = QtWidgets.QSplitter(
            QtCore.Qt.Orientation.Horizontal, self)
        self.centralSplitter.setChildrenCollapsible(False)
        self.centralSplitter.addWidget(self.tabs)
        self.setCentralWidget(self.centralSplitter)

        self.ShowSessionCanvas(None)

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

        # Undo/redo menu items follow the QUndoStack state (Block C - A1)
        self._undoBaseText = self.actions['undo'].text()
        self._redoBaseText = self.actions['redo'].text()
        self.BindUndoStack(self.undoStack)

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

        # Keyboard focus groups (D-c.6). Installed here because it registers the
        # sidebar and the toolbar, so both have to exist first.
        print("[INIT2] Installing focus groups...")
        focusgroups.install(self)
        print("[INIT2] ✓ Focus groups installed")

        # The directory listing (D-d.2), up by default: it is the block's main
        # feature and the thing the sidebar exists for. Before the level load
        # below, so the tree is there to mark it as loaded.
        print("[INIT2] Opening directory listing...")
        self.ShowDirectoryListing()
        print("[INIT2] ✓ Directory listing opened")

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
            self.LoadLevel(globals_.FirstStageFilename, True, 1)

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
            # Version 1 since D-c.3. The palette and the four property editors
            # stopped being docks in that phase, so a saved version-0 state
            # describes a window that no longer exists. Qt returns False and
            # ignores a state whose version does not match, which is exactly the
            # migration wanted here: the new default layout applies, and the
            # next save writes a version-1 state. Measured in §2.4 of the plan -
            # a stale state is inert rather than dangerous, so this is about
            # giving a sensible default, not about avoiding breakage.
            self.restoreState(setting('MainWindowState'), LAYOUT_VERSION)

        # Aaaaaand... initializing is done!
        globals_.Initializing = False

    def SetupActionsAndMenus(self):
        """
        Sets up Reggie's actions, menus and toolbars
        """
        print("[INIT2] Creating RecentFilesMenu...")
        self.RecentMenu = RecentFilesMenu()
        print("[INIT2] ✓ RecentFilesMenu created")
        
        # No GameDefMenu since D-d.1b: File -> Change Game is gone, and the menu
        # was only ever reachable through it. Its one irreplaceable part - the
        # patch info panel - lives in the Patch Manager now (PatchInfoPanel).

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

    @property
    def scene(self):
        """The active session's canvas scene.

        A property rather than an attribute so the ~87 sites that read
        ``mainWindow.scene`` / ``.view`` reach whichever tab is in front without
        any of them changing - the same trick ``undoStack`` uses, and the same
        reason: many readers, and none of them holds the value across a switch.

        Falls back to a window-owned scene before the first session exists; the
        window is built and shown before a level is opened.
        """
        session = self._activeSession()
        return self._fallbackScene if session is None else session.scene

    @property
    def view(self):
        """The active session's canvas view. See :attr:`scene`."""
        session = self._activeSession()
        return self._fallbackView if session is None else session.view

    def _activeSession(self):
        """The active session, or None before one exists."""
        manager = globals_.get_session_manager()
        return manager.active if manager is not None else None

    @property
    def fileSavePath(self):
        """The path of the file in front (D-d.3b).

        A plain attribute until several files could be open at once, at which
        point it stopped being merely a duplicate of the handle's path and
        started being *wrong*: it named one file while the editor held several.
        All ~50 read sites mean "the file in front", which is what this returns.

        The duplication was already dangerous with one file. In D-d.3 a rename
        applied to the manager but not to this attribute made the two disagree,
        and re-opening the file then found no handle, loaded it again, and built
        fresh scene items over a level whose old ones were still live - "wrapped
        C/C++ object of type ObjectItem has been deleted". Resolving through the
        session removes the second copy rather than keeping them in step.

        Falls back to the window-owned value when there is no session: a new
        unsaved level, boot before the first load, and the headless suites.
        """
        session = self._activeSession()
        if session is None:
            return self._fileSavePath
        return session.file_path

    @fileSavePath.setter
    def fileSavePath(self, value):
        # Only the fallback. Deliberately **not** a rename of the active
        # session's handle, tempting as that is: assigning this does not always
        # mean "the open file moved". `LoadLevel` assigns it while naming a file
        # it is *about* to open, before that file's session exists - so a
        # setter that renamed would re-key the previous file's handle to the
        # incoming path and lose both.
        #
        # Save As is the one case that does mean a rename, and it says so, by
        # calling `_RebindSessionsTo` explicitly after the write.
        self._fileSavePath = value

    @property
    def ZoomLevel(self):
        """The active session's zoom, as a percentage.

        Per session since D-c.4. The *view* has held its own transform since
        D-c.1, so the canvas already zoomed correctly per area; this number did
        not, and the status bar therefore reported whichever area was zoomed
        last. Writable, because ZoomTo assigns it.

        A session that has never been shown has no zoom yet and takes the
        window's default - it cannot pick one at construction, since the list of
        levels lives here.
        """
        session = self._activeSession()
        if session is None:
            return self._fallbackZoomLevel
        if session.zoom_level is None:
            session.zoom_level = self._fallbackZoomLevel
        return session.zoom_level

    @ZoomLevel.setter
    def ZoomLevel(self, value):
        session = self._activeSession()
        if session is None:
            self._fallbackZoomLevel = value
        else:
            session.zoom_level = value

    @property
    def selObj(self):
        """The item whose property panel is open, per session (D-c.4).

        Window-owned until the tab bar made it visibly wrong: a sprite selected
        in one area kept its panel up over a tab where nothing was selected, and
        UpdateModeInfo would then fill that panel from the other area's item.
        """
        session = self._activeSession()
        return self._fallbackSelObj if session is None else session.sel_obj

    @selObj.setter
    def selObj(self, value):
        session = self._activeSession()
        if session is None:
            self._fallbackSelObj = value
        else:
            session.sel_obj = value

    @property
    def CurrentSelection(self):
        """The active session's selected items. See :attr:`selObj`."""
        session = self._activeSession()
        return self._fallbackSelection if session is None else session.current_selection

    @CurrentSelection.setter
    def CurrentSelection(self, value):
        session = self._activeSession()
        if session is None:
            self._fallbackSelection = value
        else:
            session.current_selection = value

    def ShowSessionCanvas(self, session):
        """Bring a session's canvas to the front of the master container.

        Since D-c.2 the central widget is the tab container and every session's
        view is a page in it, so this selects a tab rather than swapping the
        window's centre. Deliberately *not* reparenting anything: the outgoing
        view keeps its scene and its items, which is the whole point of a canvas
        per session.

        Called from ``SessionManager.activate()``, so it runs for every path
        that makes a session active - including the ones that never reach
        ``ActivateSession``. Opening a file goes open_level -> open() ->
        activate(), and when this only ran from the window's method the boot
        canvas was left showing the empty fallback: the level was loaded, in a
        view nobody had put on screen.
        """
        tabs = getattr(self, 'tabs', None)
        if tabs is None:
            return False

        if session is None:
            tabs.showPlaceholder(self._fallbackView)
            return True

        tabs.sync()
        return tabs.showSession(session)

    @property
    def undoStack(self):
        """The active session's undo history.

        A property rather than an attribute so the ~40 sites that push onto
        ``mainWindow.undoStack`` reach whichever area is in front, without any
        of them changing. Falls back to a window-owned stack before the first
        session exists - the window is built before a level is opened.
        """
        session = self._activeSession()
        return self._fallbackUndoStack if session is None else session.undo_stack

    def BindUndoStack(self, stack):
        """Point the undo/redo menu items at ``stack``.

        Called once at startup and again whenever the active session changes,
        since each session owns its own stack and the menu state - enabled, and
        the "Undo <action>" label - belongs to whichever one is in front.
        """
        previous = getattr(self, '_boundUndoStack', None)
        if previous is stack:
            return

        if previous is not None:
            # Qt keeps every connection, so without this the menu items would
            # follow all stacks at once and the last signal to arrive would win.
            for signal, slot in (
                (previous.canUndoChanged, self.actions['undo'].setEnabled),
                (previous.canRedoChanged, self.actions['redo'].setEnabled),
                (previous.undoTextChanged, self.HandleUndoTextChanged),
                (previous.redoTextChanged, self.HandleRedoTextChanged),
            ):
                try:
                    signal.disconnect(slot)
                except (TypeError, RuntimeError):
                    # Already gone, or the stack was destroyed with its session.
                    pass

        stack.canUndoChanged.connect(self.actions['undo'].setEnabled)
        stack.canRedoChanged.connect(self.actions['redo'].setEnabled)
        stack.undoTextChanged.connect(self.HandleUndoTextChanged)
        stack.redoTextChanged.connect(self.HandleRedoTextChanged)

        self._boundUndoStack = stack

        # Bring the menu items in line with the stack we just bound: the
        # signals above only fire on *changes*, so switching to a session whose
        # stack is already non-empty would otherwise leave Undo greyed out.
        self.actions['undo'].setEnabled(stack.canUndo())
        self.actions['redo'].setEnabled(stack.canRedo())
        self.HandleUndoTextChanged(stack.undoText())
        self.HandleRedoTextChanged(stack.redoText())

        # The undo history section, if it is open, shows the same stack the menu
        # items do - so it moves here rather than being wired once at creation.
        # A QUndoView bound to a dead session's stack is both wrong and a crash
        # waiting to happen, since the stack goes when the session does.
        #
        # getattr throughout: the manager can call this during the window's
        # constructor, before the sidebar or these attributes exist.
        view = getattr(self, 'undoHistoryView', None)
        if view is not None:
            view.setStack(stack)

            # And retitle it, so the header names the area whose history this
            # now is. Without it the section would quietly show a different
            # level's steps under the old name.
            section = getattr(self, 'undoHistorySection', None)
            if section is not None:
                section.setTitle(self.UndoHistoryTitle())

    def ActivateSession(self, session):
        """Show an already-open session's area, without touching the disk.

        The editor-facing half of an area switch (Block D-b.4). The session
        manager moves the state bindings - globals_.Area, spritelib, the undo
        stack; this moves what the user sees.

        **Since D-c.1 each session owns its scene**, so activation shows a
        different canvas rather than emptying and refilling a shared one. That
        deletes the most dangerous code in D-b: the old path detached every item
        from one scene and rebuilt it from the incoming area, and getting that
        subtly wrong destroyed the outgoing area's items twice over (the
        ZoneItem crash, then the path-node crash). Nothing is detached here at
        all - the outgoing scene simply stops being on screen.

        The side lists are still window-owned, so they are still rebuilt.
        """
        manager = globals_.get_session_manager()
        if manager is None or session is None:
            return False

        for thingList in (self.spriteList, self.entranceList, self.locationList,
                          self.pathList, self.commentList):
            thingList.clear()
            thingList.selectionModel().setCurrentIndex(
                QtCore.QModelIndex(),
                QtCore.QItemSelectionModel.SelectionFlag.Clear)

        # Note: CurrentSelection is NOT cleared here. It was, before D-c.4 made
        # it per session - at which point clearing it before activate() would
        # wipe the *outgoing* area's selection, so leaving that area would lose
        # what was picked in it. The incoming session brings its own.

        # Moves globals_.Area, spritelib's own bindings, this session's tilesets
        # and the undo stack together. Everything below reads through them -
        # including self.scene and self.view, which resolve to this session's.
        # activate() also brings this session's tab to the front, so by the time
        # it returns the property and the widget on screen already agree.
        manager.activate(session)

        # ResetPalette adds each item to the scene and fires positionChanged
        # handlers, which call SetDirty. Nothing here is a user edit. It is
        # still called on every activation because the *side lists* were just
        # cleared; the scene work inside it is a no-op the second time, since
        # QGraphicsScene ignores an item it already holds.
        globals_.DirtyOverride += 1
        try:
            self.ResetPalette()
        finally:
            globals_.DirtyOverride -= 1

        self._RefillAreaComboBox()
        self._SyncAreaComboBox()
        self.UpdateTitle()

        # Bold-for-loaded in the directory listing (D-d.2). Here rather than in
        # LoadLevel because this is the one point every route passes through -
        # opening a level, switching area, and closing a session, which
        # activates a survivor on its way out.
        self.RefreshDirectoryListing()

        # Bring the toolbar, the zoom controls and the property panels in line
        # with this session (D-c.4). All three read state that now belongs to
        # the session, and none is driven by a signal a tab switch fires - so
        # without this the status bar keeps the previous area's zoom % and a
        # property panel stays open over an area where nothing is selected.
        self.SyncToolbarContext()

        self.scene.update()
        self.levelOverview.Reset()
        self.levelOverview.update()

        return True

    def SetMenuEnabled(self, name, enabled):
        """Enable or disable a whole menu by name (Block D-c).

        Names are 'file', 'edit', 'view', 'level', 'help' - untranslated, since
        the menu *titles* change with the language and keying on them would make
        every caller depend on the translation.

        Disabling the menu greys the top-level entry, so the menu cannot be
        opened at all; the actions inside keep their own enabled state, which is
        what makes this composable with SyncToolbarContext rather than fighting
        it. Returns False for an unknown name rather than raising - a caller
        naming a menu that does not exist should not take the editor down.
        """
        menu = getattr(self, 'menus', {}).get(name)
        if menu is None:
            return False

        action = menu.menuAction()

        # A hidden menu is not the user's to reach, so there is nothing to
        # enable or disable (D-d.2c). Help is one: it is still built, because
        # its actions keep their shortcuts and the sidebar's Help section
        # renders this very menu - but it is not in the menu bar any more.
        #
        # Reported as False rather than silently "done", because Qt treats a
        # hidden action as disabled: claiming success would mean SetMenusEnabled
        # returning a name whose menu it did not actually enable.
        if not action.isVisible():
            return False

        action.setEnabled(bool(enabled))
        return True

    def SetMenusEnabled(self, enabled, names=None):
        """Enable or disable several menus at once.

        Defaults to every menu the user can reach - which is not necessarily
        every menu in the registry, since a hidden one is skipped. The return
        value is the menus actually changed, so a caller can tell.
        """
        menus = getattr(self, 'menus', {})
        wanted = list(menus) if names is None else list(names)
        return [name for name in wanted if self.SetMenuEnabled(name, enabled)]

    def SetToolbarEnabled(self, enabled):
        """Enable or disable every toolbar button at once (Block D-c).

        The toolbar itself, not the actions on it: an action is usually shared
        with a menu entry, so disabling the actions would grey the menus too.
        Disabling the widget leaves each action's own state untouched, so
        turning the toolbar back on restores exactly what was enabled before
        rather than enabling everything.
        """
        bars = [getattr(self, 'toolbar', None), getattr(self, 'patchToolbar', None)]
        touched = 0

        for bar in bars:
            if bar is not None:
                bar.setEnabled(bool(enabled))
                touched += 1

        return touched

    def SyncToolbarContext(self):
        """Enable only what the thing in front can actually do (D-c.4).

        "Context-sensitive" here means the *enabled state* follows what is in
        front, not that the buttons rearrange themselves. Which buttons the
        toolbar holds is the user's choice, made in Preferences, and a toolbar
        that reshuffles under the pointer would be worse than one with a few
        greyed items.

        Two thirds of it already worked and are not repeated here: the
        selection-dependent actions (cut, copy, shift, merge, deselect) are set
        by ChangeSelectionHandler, and the zoom actions by SyncZoomToSession -
        both of which an area switch now calls. What was missing is the case
        with no canvas at all, where every level action was still enabled and
        would act on nothing.
        """
        session = self._activeSession()
        has_canvas = session is not None and session.area is not None

        # Everything that edits or reports on a level. Deliberately a list of
        # names rather than "all actions": File > Open and Preferences must
        # stay reachable with no level open, which is how the user gets one.
        level_actions = (
            'save', 'saveas', 'savecopyas', 'screenshot',
            'selectall', 'deselect', 'shiftitems', 'mergelocations',
            'zoommax', 'zoomin', 'zoomactual', 'zoomout', 'zoommin',
            'areaoptions', 'zones', 'backgrounds', 'camprofiles',
            'addarea', 'importarea', 'deletearea', 'reloadgfx',
            'swapobjectstypes', 'swapobjectstilesets', 'diagnostic',
        )

        # Names are checked rather than assumed: they are registered across
        # menus.py and docks.py, and a typo here would silently leave an action
        # enabled forever rather than raising.
        for name in level_actions:
            act = self.actions.get(name)
            if act is not None:
                act.setEnabled(has_canvas)

        if has_canvas:
            # Hand the finer-grained state back to the handlers that own it,
            # rather than leaving everything blanket-enabled by the loop above.
            self.ChangeSelectionHandler()
            self.SyncZoomToSession()

    def SyncZoomToSession(self):
        """Point the zoom controls at the active session's zoom.

        The view already carries its own transform - it has been per session
        since D-c.1 - so this is about the *reporting*: the status-bar widget,
        the slider, and which of the five zoom actions are enabled. Applying the
        transform again here would be redundant but harmless; not doing it keeps
        this a read of state rather than a second writer of it.
        """
        z = self.ZoomLevel

        try:
            zi = self.ZoomLevels.index(z)
        except ValueError:
            # A zoom that is not one of the steps - reachable by fitting the
            # window to a zone. The buttons stay usable; only the exact index
            # is unavailable, so bracket it.
            zi = min(range(len(self.ZoomLevels)),
                     key=lambda i: abs(self.ZoomLevels[i] - z))

        self.actions['zoommax'].setEnabled(zi < len(self.ZoomLevels) - 1)
        self.actions['zoomin'].setEnabled(zi < len(self.ZoomLevels) - 1)
        self.actions['zoomactual'].setEnabled(z != 100.0)
        self.actions['zoomout'].setEnabled(zi > 0)
        self.actions['zoommin'].setEnabled(zi > 0)

        self.ZoomWidget.setZoomLevel(z)
        self.ZoomStatusWidget.setZoomLevel(z)

        self.levelOverview.mainWindowScale = z / 100.0

    def PlaceSidebar(self):
        """Put the sidebar on its configured side of the master container.

        A QSplitter is ordered by insertion, so moving the sidebar from one side
        to the other is re-inserting it - insertWidget(0) or addWidget - not a
        rebuild. Called when the sidebar is created and again whenever the side
        setting changes.
        """
        from reggie.ui.sidebar import SIDE_LEFT, configured_side

        if self.sidebar is None:
            return False

        side = configured_side()
        wanted = 0 if side == SIDE_LEFT else 1

        # Once, on the first placement: a drag of this divider is the user
        # setting the sidebar width themselves, which clears any clamp the
        # restore recorded (D-d.1b). Connected here because it is the one place
        # that knows both the splitter and the sidebar exist.
        if not getattr(self, '_sidebarDragConnected', False):
            self.centralSplitter.splitterMoved.connect(
                self.sidebar._handleSidebarResized)
            self._sidebarDragConnected = True

        if self.centralSplitter.indexOf(self.sidebar) == wanted:
            return False

        self.centralSplitter.insertWidget(wanted, self.sidebar)

        # The canvas takes the slack; the sidebar keeps the width the user gave
        # it. Set by position rather than remembered, so it stays right after a
        # flip.
        self.centralSplitter.setStretchFactor(wanted, 0)
        self.centralSplitter.setStretchFactor(1 - wanted, 1)

        self.sidebar.applySide(side)
        return True

    def CloseSession(self, session):
        """Close one open area, keeping the rest of the level open.

        The tab bar's close button, and the only place a single session is torn
        down at the user's request. Refuses the last canvas tab: Zement's rule is
        that one area stays loaded at all times, so there is no editor state with
        no level in it.

        No dirty prompt. A session's edits live in the shared level object, not
        in the session, so closing a tab does not discard them - saving the file
        afterwards still writes that area, exactly as saving from another tab
        always did. The prompt stays where work genuinely can be lost: quitting,
        changing patch, opening another file.
        """
        manager = globals_.get_session_manager()
        if manager is None or session is None:
            return False

        if len(manager) <= 1:
            return False

        manager.close(session)
        self.tabs.sync()

        # close() activated a survivor, but only moved the state bindings and
        # the tab - the side lists, the title and the overview still describe
        # the session that just went away.
        if manager.active is not None:
            self.ActivateSession(manager.active)
        else:
            # No survivor to activate, so nothing else will repaint the tree's
            # bold marks - and the level that just closed is still shown as
            # loaded (D-d.2).
            self.RefreshDirectoryListing()

        return True

    def _RefillAreaComboBox(self):
        """Rebuild the area selector from the level actually open.

        _SyncAreaComboBox only moves the selection, and silently does nothing
        when the wanted index does not exist yet. An area added since the box
        was last filled - by Add Area, or by a peer's snapshot - would leave the
        box a row short, and selecting that area would then be a no-op.
        """
        level = globals_.Level
        if level is None:
            return

        areas = getattr(level, 'areas', None) or []
        if self.areaComboBox.count() == len(areas):
            return

        blocked = self.areaComboBox.blockSignals(True)
        try:
            self.areaComboBox.clear()
            for area in areas:
                self.areaComboBox.addItem(
                    globals_.trans.string('AreaCombobox', 0, '[num]', area.areanum))
        finally:
            self.areaComboBox.blockSignals(blocked)

    def SwitchPatch(self, folder):
        """Load a different game patch. ``folder is None`` means retail.

        The single entry point since D-d.1b. It was `HandleSwitchPatch(index)`,
        which took a combo-box row and read the folder back out of it - so a
        caller without a combo box had to fake one. The combo box is gone (the
        sidebar's Game Patches page replaced it), and this takes the patch id
        directly.

        Returns True if the patch actually changed.
        """
        # Unsaved work is settled *before* the patch changes (Block C - B3,
        # round 2, R5). Asking afterwards would offer to save the old patch's
        # level through the new patch's paths, and Cancel would have nothing to
        # cancel - the switch would already have happened.
        #
        # Cancel is right here, unlike the join dialog: the user started this
        # and may reasonably change their mind.
        from reggie.io.gamedef import loadNewGameDef, RefreshPatchSelector

        if self.CheckDirty():
            RefreshPatchSelector()
            return False

        # folder is None for the base game, which loadNewGameDef takes as-is.
        success = loadNewGameDef(folder)

        # Either way every patch control is put back in step: on the new patch
        # after a success, on the restored one after a failure.
        RefreshPatchSelector()

        if success:
            # Open the new patch's own first level, rather than keeping one
            # whose tilesets belong to the patch that was just unloaded.
            self.LoadFirstLevelOfPatch()

        return success

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

        # The tab labels carry the same dirty marker, per tab rather than for
        # the window as a whole. Hooked here because UpdateTitle is what the
        # editor already calls whenever the dirty state may have moved.
        tabs = getattr(self, 'tabs', None)
        if tabs is not None:
            tabs.refreshTitles()

        # And the unsaved-levels section (D-d.3c), which lists the same dirty
        # state the tab markers show. Hooked here for the same reason: this is
        # the one place the editor already calls whenever that state may have
        # moved, so the section cannot drift out of step with the tabs beside
        # it. Guarded because UpdateTitle runs long before the sidebar exists.
        try:
            self.RefreshUnsavedLevels()
        except Exception:
            # A stale list is worth living with; a title that cannot be set is
            # not, and neither is a failed save whose UpdateTitle threw.
            pass

    def CheckDirty(self):
        """
        Checks if the level is unsaved and attempts to save it if so.
        Returns whether the level still contains unsaved changes.
        """
        if not globals_.Dirty:
            return False

        # In a session, only the save authority is asked about unsaved work
        # (Block C - B3). Everyone else is looking at changes the *session*
        # authored - a snapshot replaced their area, or a peer's edit arrived -
        # so prompting them to save is asking them to write work they did not
        # author over a file that may not even be the session's level.
        #
        # This is the root of known-open 10.1b: after a patch transfer the
        # client was asked to save its own untouched level every time the
        # session moved, and dismissing the dialog re-ran the load and re-fired
        # the "tileset not found" warnings.
        #
        # Answering False means "no unsaved changes stand in the way", which is
        # the truthful answer here: the changes exist, but they are the host's
        # to keep, and it has them.
        if not self._maySaveInSession():
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
        Select all objects in the current area, or all text in the focused widget
        """
        if globals_.app.activeWindow() is not globals_.mainWindow:
            focus = globals_.app.focusWidget()
            if focus is not None:
                if isinstance(focus, (QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QLineEdit)):
                    focus.selectAll()
            return

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

    def HandleUndoTextChanged(self, text):
        """
        Shows the next undo step's description in the Edit menu
        """
        if text:
            self.actions['undo'].setText('%s: %s' % (self._undoBaseText, text))
        else:
            self.actions['undo'].setText(self._undoBaseText)

    def HandleRedoTextChanged(self, text):
        """
        Shows the next redo step's description in the Edit menu
        """
        if text:
            self.actions['redo'].setText('%s: %s' % (self._redoBaseText, text))
        else:
            self.actions['redo'].setText(self._redoBaseText)

    def ShowDirectoryListing(self):
        """Put the directory listing into sidebar slice 2 (Block D-d, phase 2).

        Idempotent: if the section is already up it is brought to the front
        rather than added twice. The rail entry calls this, and so will the
        menu entry when there is one.

        Unlike the undo history this is not a toggle - a rail category that
        hid its own content when picked would be surprising - so closing it is
        the section header's X, which the sidebar handles.
        """
        if self.sidebar is None:
            return None

        existing = self.sidebar.sectionFor(
            getattr(self, 'levelTreeWidget', None))
        if existing is not None:
            self.sidebar.showSections()
            return existing

        from reggie.ui.leveltree import LevelTreeWidget

        self.levelTreeWidget = LevelTreeWidget(self)
        self.levelTreeWidget.activated.connect(self.HandleTreeActivated)

        # Put back what the last one had open. A context section is destroyed
        # when the user switches to another, so without this the tree comes
        # back collapsed and scrolled to the top every time - which is exactly
        # what it did (Zement, 2026-09-01).
        state = getattr(self, '_levelTreeState', None)
        if state:
            self.levelTreeWidget.applyState(state)

        self.levelTreeSection = self.sidebar.addSection(
            globals_.trans.string('MenuItems', 143),
            self.levelTreeWidget,
            # stretch=1: a tree is a scrolling list, so more height is directly
            # more of what the user came for - the same reasoning that gives the
            # palette its stretch in slice 3.
            stretch=1,
            on_close=self._closeDirectoryListing,
            context=True)

        return self.levelTreeSection

    def HandleTreeActivated(self, index):
        """Open what was activated in the directory listing (Block D-d.3).

        The tree's five node kinds divide into three answers:

        - **area** - open or raise that area of that file.
        - **level** - the same for area 1, which is what the old level picker
          did and what activating a level has always meant.
        - **patch, category, tileset** - nothing. A category is a heading, and
          a tileset slot names a file this editor does not edit (that is Block
          G's Puzzle Next). Expanding them is what they are for, and the view
          already does that on its own.
        """
        if index is None or not index.isValid():
            return False

        from reggie.ui.leveltree import AREA, LEVEL

        node = index.internalPointer()
        if node is None or node.kind not in (LEVEL, AREA):
            return False

        area_num = node.area_num if node.kind == AREA else 1
        return self.OpenLevelFromTree(node.file_path, node.file_name, area_num)

    def OpenLevelFromTree(self, file_path, file_name, area_num=1):
        """Open a file and area, reusing whatever is already open.

        Split out from ``HandleTreeActivated`` so the work can be driven
        without a QModelIndex - by a test, and by D-d.4's dialogs.

        Three cases, cheapest first, matching plan §3.3:

        1. that area is already open        -> activate its session
        2. the file is open at another area -> ``SwitchToArea``, which adds a
           session on the same ``LevelHandle``
        3. the file is not open             -> ``LoadLevel``

        **The collab hook is asked first, in every case that changes what this
        editor shows.** A client proposes and the host's broadcast performs the
        load; outside a session the hook returns True immediately. This is the
        one guard that keeps a client from desynchronising, and a second load
        path that skipped it would reintroduce the bug C-B3 phase 3d fixed -
        which is exactly the risk a *new* way to open levels creates.
        """
        if not file_path:
            return False

        manager = globals_.get_session_manager()

        # Case 1: already open at that area. Raising an existing tab shows the
        # user's own unsaved work; re-loading would discard it, and there is
        # nothing to propose because nothing about the session changes except
        # which tab is in front.
        if manager is not None:
            existing = manager.find(file_path, area_num)
            if existing is not None:
                return bool(self.ActivateSession(existing))

        # The wire carries level *names*, never paths - peers resolve them
        # against their own stage folder - so the proposal is named from the
        # node rather than from the path that follows it.
        level_name = file_name or ''

        if not self._levelio._ProposeCollabSwitch(level_name, area_num):
            # A client whose host has not agreed. The host's broadcast will
            # perform the load if it does agree, so there is nothing to do here
            # but stop.
            return False

        # Case 2: this file is open, another area of it. Adding a session on
        # the shared handle rather than re-reading the archive is what keeps
        # the other areas' unsaved edits alive (phase D-4).
        open_sessions = manager.sessions_for(file_path) if manager else []

        if open_sessions:
            if self.fileSavePath == file_path:
                return bool(self.SwitchToArea(area_num))

            # Open, but not as the file in front - so `SwitchToArea`, which
            # works on whatever is active, would open an area of the wrong
            # level. Activate one of this file's own sessions first; that puts
            # its path in front, and the area switch is then a switch within
            # the right file.
            #
            # Reloading instead is what the first version did, and it is not
            # merely wasteful: the reload builds a second set of scene items
            # over a level whose sessions are still live, and the editor dies
            # with "wrapped C/C++ object of type ObjectItem has been deleted".
            self.ActivateSession(open_sessions[0])
            if self.fileSavePath == file_path:
                return bool(self.SwitchToArea(area_num))

        # Case 3: not open at all - so open it *alongside* what is already
        # there (D-d.3b). This is what the tree is for: "opening areas from
        # different levels simultaneously is of course one of the main features
        # we wanted to implement with the tree view" (Zement, 2026-09-01).
        #
        # No CheckDirty here, and that is the point rather than an omission.
        # It asks "does unsaved work stand in the way of *replacing* what is
        # open" - and nothing is being replaced. The other file stays open,
        # with its edits, in its own tab.
        return bool(self.LoadLevel(file_path, True, area_num, add=True))

    def ShowGamePatches(self):
        """Put the installed-patch list into sidebar slice 2 (D-d.2c).

        A context-sensitive section like the directory listing. It was a rail
        *page* until Zement's 2026-09-01 report: "Game Patches panel/tree does
        not have a collapsible header element and close button. All panels
        should have the same header." It had none because a page is not a
        section - see `Sidebar.addSection`.
        """
        if self.sidebar is None:
            return None

        existing = self.sidebar.sectionFor(
            getattr(self, 'patchListWidget', None))
        if existing is not None:
            self.sidebar.showSections()
            return existing

        from reggie.ui.patchlist import PatchListWidget

        self.patchListWidget = PatchListWidget(self)
        self.patchListSection = self.sidebar.addSection(
            globals_.trans.string('MenuItems', 142),
            self.patchListWidget,
            stretch=1,
            on_close=self._closeGamePatches,
            context=True)

        # The list is built fresh each time this section is opened, so a
        # collaboration restriction applied to the previous one went with it. A
        # client that closed and re-opened the section would otherwise get a
        # patch list it could use - and switching patch as a client pulls the
        # tilesets out from under the session.
        collab = getattr(self, '_collab', None)
        if collab is not None:
            try:
                collab.applyEditingPermissions()
            except Exception:
                pass

        return self.patchListSection

    def _closeGamePatches(self):
        """Take the patch list out of slice 2 and forget it."""
        if self.sidebar is None:
            return

        existing = self.sidebar.sectionFor(
            getattr(self, 'patchListWidget', None))
        if existing is not None:
            self.sidebar.removeSection(existing)

        self.patchListWidget = None
        self.patchListSection = None

    def ShowHelpSection(self):
        """Put the Help entries into sidebar slice 2 as a tree (D-d.2c).

        Zement, 2026-09-01: "*Help* by the way should simply show the current
        Help file menu contents as a tree in slice 2." It reads the existing
        Help menu rather than listing the entries again, so an entry added to
        the menu appears here with no second place to remember.
        """
        if self.sidebar is None:
            return None

        existing = self.sidebar.sectionFor(
            getattr(self, 'helpTreeWidget', None))
        if existing is not None:
            self.sidebar.showSections()
            return existing

        from reggie.ui.helptree import HelpTreeWidget

        self.helpTreeWidget = HelpTreeWidget(self)
        self.helpTreeSection = self.sidebar.addSection(
            globals_.trans.string('MenuItems', 88),
            self.helpTreeWidget,
            stretch=1,
            on_close=self._closeHelpSection,
            context=True)

        return self.helpTreeSection

    def _closeHelpSection(self):
        """Take the Help tree out of slice 2 and forget it."""
        if self.sidebar is None:
            return

        existing = self.sidebar.sectionFor(
            getattr(self, 'helpTreeWidget', None))
        if existing is not None:
            self.sidebar.removeSection(existing)

        self.helpTreeWidget = None
        self.helpTreeSection = None

    def _closeDirectoryListing(self):
        """Take the directory listing out of slice 2 and forget it.

        The widget really is dropped here, unlike the collab window: the tree
        belongs to the sidebar rather than to a controller that outlives it, and
        rebuilding it is one folder listing.
        """
        if self.sidebar is None:
            return

        widget = getattr(self, 'levelTreeWidget', None)

        # Saved before the widget goes, so re-opening restores what was open
        # rather than starting from a collapsed tree. Kept on the window rather
        # than in settings: it describes this session's browsing, and a tree
        # restored across a restart would be re-expanding levels the user may
        # not want to wait for.
        if widget is not None:
            try:
                self._levelTreeState = widget.captureState()
            except Exception:
                # A state that cannot be captured is worth losing; a section
                # that cannot be closed is not.
                self._levelTreeState = None

        existing = self.sidebar.sectionFor(widget)
        if existing is not None:
            self.sidebar.removeSection(existing)

        self.levelTreeWidget = None
        self.levelTreeSection = None

    def RefreshDirectoryListing(self, rebuild=False):
        """Keep the tree in step with the sessions, or with the patch.

        ``rebuild`` re-reads the Stage folder, which is what a patch switch
        needs; without it only the bold-for-loaded marks are repainted, which is
        what opening or closing an area needs. Guarded, because the tree is a
        section the user may have closed.
        """
        widget = getattr(self, 'levelTreeWidget', None)
        if widget is None:
            return

        try:
            if rebuild:
                widget.refresh()
            else:
                widget.refreshLoadedMarks()
        except Exception:
            # A stale tree is worse than none, but neither is worth failing a
            # patch switch or a level load over.
            pass

    # -- the unsaved-levels section (Block D-d, phase D-d.3c) ------------

    def RefreshUnsavedLevels(self):
        """Show, hide or refill the unsaved-levels section.

        Driven from ``UpdateTitle``, which is already "what the editor calls
        whenever the dirty state may have moved" - the same hook the tab labels'
        dirty markers use, and for the same reason. So this runs constantly,
        including on paths with no sidebar, no manager and no session: every
        step below is guarded, and the whole thing is a no-op when there is
        nothing to describe.

        "Hidden entirely when nothing is unsaved" (§6.5) is implemented as
        *absent*, not hidden: an empty section still costs a header and a
        divider in a column the user is short of, and the section is cheap to
        rebuild.
        """
        sidebar = getattr(self, 'sidebar', None)
        if sidebar is None:
            return None

        widget = getattr(self, 'unsavedLevelsWidget', None)

        # §6.5's rule 4. A client that may not save must not be shown a list of
        # things it cannot do - the same answer CheckDirty gives when it
        # declines to prompt a client about work that is the host's to keep.
        # Note what this does NOT do: it does not show the *host's* list on the
        # client. Nothing on the wire carries the host's dirty state, and
        # inventing a message for it belongs with the end-of-D-d collab work.
        wanted = self._maySaveInSession() and bool(dirty_paths())

        if not wanted:
            if widget is not None:
                self._closeUnsavedLevels()
            return None

        if widget is None:
            from reggie.ui.unsavedlist import UnsavedLevelsWidget

            self.unsavedLevelsWidget = UnsavedLevelsWidget(self)
            self.unsavedLevelsSection = sidebar.addSection(
                globals_.trans.string('MenuItems', 154),
                self.unsavedLevelsWidget,
                # A short list that should not eat the directory listing's
                # height: it claims no share of the leftover space, and asks
                # for enough room to read a few rows.
                stretch=0,
                default_height=120,
                # No X. Every other section is something the user opened, so
                # closing it is undoing that; this one is not - it is the
                # editor reporting a state, and it goes on its own the moment
                # that state does.
                #
                # It was closable at first, and the suite caught what that
                # meant: `SetDirty` returns early when the level is *already*
                # dirty, so after closing it by hand the section would not come
                # back until the set of dirty files changed - which may be
                # after the next save, or never. A button whose effect the
                # editor silently undoes at an unpredictable later moment is
                # worse than no button.
                closable=False,
                pinned=True)
        else:
            widget.refresh()

        return self.unsavedLevelsSection

    def _closeUnsavedLevels(self):
        """Take the unsaved-levels section out of slice 2 and forget it.

        Reached from ``RefreshUnsavedLevels`` alone - when the last file is
        saved, or when a collab session takes the save authority away. The
        section has no X of its own (see there), so there is no by-hand route.

        Nothing is captured on the way out, unlike the directory listing: this
        widget's contents are derived wholly from the manager and rebuild
        identically next time, so there is no browsing state to lose.
        """
        sidebar = getattr(self, 'sidebar', None)
        if sidebar is None:
            return

        existing = sidebar.sectionFor(getattr(self, 'unsavedLevelsWidget', None))
        if existing is not None:
            sidebar.removeSection(existing)

        self.unsavedLevelsWidget = None
        self.unsavedLevelsSection = None

    def SaveLevelFile(self, file_path, session=None):
        """Save one open file, whichever tab is in front.

        **Activate, then save.** ``HandleSave`` reads ``globals_.Level`` and
        ``self.fileSavePath``, and since D-d.3b both resolve through the *active
        session* - so calling it without activating first would save whatever
        tab happens to be current, under the name of the one that was asked for.

        Parameterising ``HandleSave`` with a path was the alternative and was
        rejected: the compression, padding, autosave, undo-clear and collab
        steps all read the active session too, so it would not be one parameter
        but a second save path over a second source of truth - and a second save
        path is how areas got dropped before D-b.

        The visible cost is that saving an entry brings its tab to the front.
        That is left visible on purpose: it is the honest reflection of an
        editor whose save acts on the level in front, and it is what the user
        would do by hand. Restoring the previous tab afterwards would make Save
        All flicker through every dirty file and would hide which file was
        actually written.

        ``session`` names *which* level when the path cannot. A level that has
        never been saved has no path, so two new levels both answer ``None``
        and ``sessions_for(None)`` finds neither - unsaved handles are not in
        `_handles`, which is keyed by path (D-d.3b). Without it a New Level
        listed correctly and then could not be saved from the list at all, and
        Save All gave up on it without touching the other files (measured
        2026-09-01). For a file that *has* a path the session is redundant, and
        the path still wins - a row may have been saved under a new name since
        it was built.

        Saving a pathless level lands in ``HandleSave``, which delegates to
        Save As for exactly this case. So the user gets the file dialog, which
        is the only possible answer to "save a level with no name".
        """
        manager = globals_.get_session_manager()
        if manager is None:
            return False

        if file_path:
            sessions = manager.sessions_for(file_path)
        elif session is not None and session in manager.sessions:
            sessions = [session]
        else:
            # No path and no session: nothing to identify a level by.
            return False

        if not sessions:
            # Closed, or saved, between the list being built and the row being
            # double-clicked. Nothing to save, and nothing to report.
            return False

        # Already in front? For a named file any session on it will do, since
        # they share the level a save writes. For a pathless one, only the
        # session itself identifies it - `file_path == file_path` would be
        # `None == None`, which is true of every unsaved level.
        active = manager.active
        if file_path:
            in_front = active is not None and active.file_path == file_path
        else:
            in_front = active in sessions

        if not in_front and not self.ActivateSession(sessions[0]):
            return False

        return bool(self._levelio.HandleSave())

    def SaveAllDirtyLevels(self):
        """Save every open file with unsaved work. Returns whether all of them
        were written.

        **The active file is saved last** when it is among the dirty ones, so
        the user ends on the tab they started on. Saving in ``dirty_files()``
        order would leave them on whichever file sorted last, which is an
        arbitrary place to be put by a button that says "Save All".

        Stops at the first failure rather than pressing on: a save that fails
        has already shown the user a dialog, and continuing would stack more of
        them on top of a question they have not answered.

        **Levels that have never been saved are skipped** (Zement, 2026-09-01:
        "those *have to go through* the Save dialog path once, so that a file
        name and file path is chosen. If this hasn't happened yet, then we can't
        bulk-save this level, and should simply skip it"). Right: a bulk action
        that stops to ask a question per level is not a bulk action, and one
        cancelled dialog would abandon the files after it. They stay reachable
        by double-clicking the row, which opens the Save dialog as it should,
        and the list marks them so it is visible why they were left.

        Skipping them does **not** make this return False. Nothing failed -
        there was simply nothing this action could do for them, which is what
        "skip" means.

        Works on ``(path, session)`` pairs rather than paths for the reason
        ``SaveLevelFile`` takes a session - an unsaved level has no path to
        name it by.
        """
        entries = [e for e in dirty_entries() if e[0]]
        if not entries:
            return True

        manager = globals_.get_session_manager()
        active = manager.active if manager is not None else None

        if active is not None:
            handle = getattr(active, 'handle', None)
            # By handle rather than by path, so an unsaved level in front is
            # recognised as the active one too.
            rest = [e for e in entries
                    if getattr(e[1], 'handle', None) is not handle]
            mine = [e for e in entries
                    if getattr(e[1], 'handle', None) is handle]
            entries = rest + mine

        for path, session in entries:
            if not self.SaveLevelFile(path, session):
                return False

        return True

    def HandleShowUndoHistory(self, checked=None):
        """
        Toggles the undo history section in sidebar slice 2 (D-c.6)

        Was a tool tab in D-c.5, and briefly a modal dialog before that. It is
        better beside the canvas than covering it: undoing is something you do
        *while* looking at what you are undoing, and a full-width tab made you
        leave the level to reach it (Zement, 2026-08-30).

        A toggle rather than an open, because a section in the sidebar has no
        close button of its own - the menu entry is how it comes and goes.

        ``checked`` arrives from the checkable QAction. Ignored in favour of
        what is actually on screen: the two agree in normal use, and when they
        disagree - the section removed by something other than the menu - the
        sidebar is right and the action is stale.
        """
        if self.sidebar is None:
            return None

        existing = self.sidebar.sectionFor(getattr(self, 'undoHistoryView', None))
        if existing is not None:
            self.sidebar.removeSection(existing)
            self.undoHistoryView = None
            self.undoHistorySection = None
            self._SyncUndoHistoryAction(False)
            return None

        view = QtWidgets.QUndoView()
        view.setEmptyLabel(globals_.trans.string('Undo', 3))

        # Bound to the *stack*, which since D-b belongs to a session - so this
        # follows BindUndoStack rather than being wired once here. Without that
        # it would show whichever level was open when it was opened, and go
        # quiet after the first area switch.
        view.setStack(self.undoStack)

        self.undoHistoryView = view
        self.undoHistorySection = self.sidebar.addSection(
            self.UndoHistoryTitle(), view,
            # Its own handler rather than the sidebar's default removal: closing
            # from the header has to leave the menu tick and this window's
            # references in the same state the menu entry would, or the two
            # disagree about whether the section is up.
            on_close=self.HandleShowUndoHistory,
            # Zement's numbers (2026-08-30). The default is a starting height
            # the user can drag away from, not a rule; the maximum stops a long
            # history from taking the whole sidebar.
            default_height=UNDO_SECTION_DEFAULT_HEIGHT,
            max_height=UNDO_SECTION_MAX_HEIGHT)

        self._SyncUndoHistoryAction(True)

        return self.undoHistorySection

    def _SyncUndoHistoryAction(self, shown):
        """Keep the menu's tick in step with whether the section is up."""
        act = self.actions.get('undohistory')
        if act is None or not act.isCheckable():
            return

        # Blocked, or setChecked would re-fire triggered() on some styles and
        # toggle the section straight back off.
        blocked = act.blockSignals(True)
        try:
            act.setChecked(bool(shown))
        finally:
            act.blockSignals(blocked)

    def UndoHistoryTitle(self):
        """The undo section's header: which level and area it is following.

        Asked for by name (Zement, 2026-08-30). A history that silently follows
        the active area needs to say which one it is showing, or a step list
        that changed under you looks like a bug rather than a context switch.
        """
        base = globals_.trans.string('Undo', 2)

        session = self._activeSession()
        if session is None:
            return base

        name = os.path.splitext(os.path.basename(session.file_path or ''))[0]
        if not name:
            name = globals_.trans.string('WindowTitle', 0)

        return '%s - %s, Area %d' % (base, name, session.area_num)

    def _maySaveInSession(self):
        """
        Whether this editor may write the level it has open (Block C - B3).

        True whenever no session is running, so the ordinary single-user editor
        is untouched. In a session it is the host's answer alone: Save is the
        host's, whatever a client's role (Zement, 2026-08-09).

        Guarded rather than assumed: the controller is created lazily by
        HandleCollaborate, so it is absent for anyone who has never opened the
        collaboration dialog, and a fault in it must never stop someone saving
        their own work.
        """
        controller = getattr(self, '_collab', None)
        if controller is None:
            return True

        try:
            return bool(controller.isSaveAuthority())
        except Exception:
            return True

    def _CollabLevelName(self):
        """
        The level this editor has open, as the session names it (Block C - B3).

        An area switch stays within the same level, but the proposal that
        carries it still has to name that level: the wire carries names, never
        paths, so the other peers resolve it against their own stage folder.
        Asking the controller keeps the one definition of "the level's name" in
        one place rather than re-deriving it from fileSavePath here.
        """
        controller = getattr(self, '_collab', None)
        if controller is None:
            return ''

        try:
            return str(controller.sessionLevelName() or '')
        except Exception:
            return ''

    def HandleCollaborate(self):
        """
        Opens the collaboration setup dialog, or the status window if a session
        is already running (Block C - B1).

        The controller is created lazily: it pulls in the whole collab package,
        and a user who never collaborates should not pay for that at startup.
        """
        if getattr(self, '_collab', None) is None:
            from reggie.ui.collab_controller import CollabController
            self._collab = CollabController(self)

        self._collab.showSetupDialog()

    # Cut/Copy/Paste + ReggieClip encode/decode/place extracted to
    # reggie.ui.clipboard.ClipboardController (Phase 2 — see
    # _docs/plan/REFACTORING_ANALYSIS.md). Thin delegators keep the QAction
    # wiring AND the cross-module callers (globals_.mainWindow.placeEncodedObjects
    # in misc2.py, .getEncodedObjects in sidelists.py) working, so signatures
    # are preserved exactly.
    def Cut(self):
        return self._clipboard.Cut()

    def Copy(self):
        # If a separate window (e.g. the sprite-data editor) is focused, copy the
        # selected text from it instead of the selected scene items.
        if globals_.app.activeWindow() is not globals_.mainWindow:
            focus = globals_.app.focusWidget()
            if focus is not None:
                if isinstance(focus, (QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit)):
                    text = focus.textCursor().selectedText()
                elif isinstance(focus, QtWidgets.QLineEdit):
                    text = focus.selectedText()
                else:
                    return

                self.systemClipboard.setText(text)
            return

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

        old_positions = [(obj, (obj.objx, obj.objy)) for obj in items]

        globals_.OverrideSnapping = True

        for obj in items:
            obj.setPos(obj.x() + xpoffset, obj.y() + ypoffset)

        globals_.OverrideSnapping = False

        entries = [(obj, old, (obj.objx, obj.objy))
                   for obj, old in old_positions if (obj.objx, obj.objy) != old]
        if entries:
            self.undoStack.push(undo.MoveItemsCommand(
                entries, already_applied=True, text=globals_.trans.string('Undo', 28)))

        SetDirty()

    def SwapObjectsTilesets(self):
        """
        Swaps objects' tilesets
        """
        dlg = ObjectTilesetSwapDialog()
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        from_tileset = dlg.FromTS.currentIndex()
        to_tileset = dlg.ToTS.currentIndex()
        do_exchange = dlg.DoExchange.isChecked()

        if from_tileset == to_tileset:
            return

        to_change = []
        for layer in globals_.Area.layers:
            for nsmbobj in layer:
                if nsmbobj.tileset == from_tileset:
                    to_change.append((nsmbobj, to_tileset))
                elif do_exchange and nsmbobj.tileset == to_tileset:
                    to_change.append((nsmbobj, from_tileset))

        if not to_change:
            return

        self.undoStack.beginMacro(globals_.trans.string(
            'Undo', 30, '[from]', from_tileset + 1, '[to]', to_tileset + 1))
        try:
            for nsmbobj, new_tileset in to_change:
                with undo.record_property_edit(nsmbobj):
                    nsmbobj.SetType(new_tileset, nsmbobj.type)
                SetDirty()
        finally:
            self.undoStack.endMacro()

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
        locations = [obj for obj in items if isinstance(obj, type_loc)]
        for obj in locations:
            new_rect |= obj.ZoneRect

        if not new_rect.isValid():
            return

        self.undoStack.beginMacro(globals_.trans.string('Undo', 29))
        try:
            self.undoStack.push(undo.RemoveItemsCommand(locations))
            self.levelOverview.update()

            loc = self.CreateLocation(*new_rect.getRect())
            if loc is not None:
                self.undoStack.push(undo.AddItemsCommand([loc], already_applied=True))
        finally:
            self.undoStack.endMacro()

        if loc is not None:
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

            # Recorded only while a bulk edit session (QPT) is open
            undo.notify_item_created(obj)

            SetDirty()

        return obj

    def CreateEntrance(self, x, y, id_ = None, add_to_scene = True, allow_dupe_id = False):
        """
        Creates and returns a new entrance and makes sure it's added to the
        right lists. This function returns None if this entrance could not be
        created.
        """
        all_ids = set(ent.entid for ent in globals_.Area.entrances)
        if id_ is None:
            id_ = common.find_first_available_id(all_ids, 256)

        if id_ is None:
            QtWidgets.QMessageBox.warning(self, globals_.trans.string('MainWindow', 2), globals_.trans.string('MainWindow', 3),
                                          QtWidgets.QMessageBox.StandardButton.Ok)
            return None
        elif id_ in all_ids and add_to_scene and not allow_dupe_id:
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

        # Via set_action_allowed so a session's restriction survives; see its
        # docstring.
        from reggie.ui.collab_controller import set_action_allowed
        set_action_allowed('deletearea', len(globals_.Level.areas) > 1)

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
            # Try loading the first detected file in our Stage folder. If that fails, load up an empty canvas.
            ok = self.LoadLevel(globals_.FirstStageFilename, True, 1)
            if not ok:
                self.LoadLevel(None, False, 1)

        return True

    def HandlePatchManager(self):
        """
        Open the Patch Manager as a tool tab (D-c.5)
        """
        self.toolTabs.openTool(tooltabs.PATCH_MANAGER,
                               deferred.PatchManagerDialog,
                               'Patch Manager')

    def HandlePreferences(self):
        """
        Open the preferences as a tool tab (D-c.5)

        Was a modal ``exec()`` whose caller read a hundred widget values on the
        line after it returned. As a tab there is no line after, so the reading
        moved into ApplyPreferences and the tab manager calls it when the user
        presses OK - which is the same moment, reached differently.
        """
        self.toolTabs.openTool(tooltabs.PREFERENCES,
                               PreferencesDialog,
                               globals_.trans.string('PrefsDlg', 0))

    def ApplyPreferences(self, dlg):
        """
        Write back everything the preferences page holds.

        Called by ToolTabManager when the page is confirmed, with the page still
        whole. Every line below is what used to follow ``dlg.exec()``.
        """
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

        # Display full filepath setting
        globals_.UseFullFilepath = dlg.generalTab.fullFileTitle.isChecked()
        setSetting('UseFullFilepath', globals_.UseFullFilepath)

        # Draggable area tabs (Block D-c). Applied immediately rather than at
        # the next restart: turning dragging off also drops any manual order the
        # user had arranged, which they should see happen while the reason for
        # it is still on screen.
        # The shell settings live on the Interface tab, which is where new,
        # not-yet-sorted preferences go. All applied at once rather than at the
        # next restart: the point of each is seeing the layout it produces.
        shell = dlg.interfaceTab

        setSetting('TabsDraggable', shell.tabsDraggable.isChecked())
        self.tabs.applySettings()

        # Read fresh on every paste, so there is nothing to apply beyond the
        # write itself.
        setSetting('IncrementPastedIDs', shell.incrementPastedIDs.isChecked())

        setSetting('SidebarSide', shell.sidebarSide.currentData())
        self.PlaceSidebar()

        setSetting('RailWidth', shell.railWidth.currentData())
        if self.sidebar is not None:
            self.sidebar.applyRailWidth()

        setSetting('OverviewCorner', shell.overviewCorner.currentData())
        setSetting('OverviewHeightPct', shell.overviewHeight.value())
        setSetting('OverviewTranslucent', shell.overviewTranslucent.isChecked())
        setSetting('OverviewOpacityPct', shell.overviewOpacity.value())
        self.tabs.applyOverlaySettings()

        # Undo history limit setting. Qt only allows changing the limit of an
        # empty stack, so a non-empty stack picks the new value up on its next
        # clear() (level load / area switch / save).
        globals_.UndoLimit = dlg.undoTab.historyLimit.value()
        setSetting('UndoLimit', globals_.UndoLimit)
        if self.undoStack.count() == 0:
            self.undoStack.setUndoLimit(globals_.UndoLimit)

        # Collaboration settings (Block C - B1). The tab persists its own values,
        # since they are read straight from QSettings by the collab layer rather
        # than mirrored into globals_.
        dlg.collabTab.apply()

        # Update window title
        if self.fileSavePath:
            if globals_.UseFullFilepath:
                self.fileTitle = self.fileSavePath
            else:
                self.fileTitle = os.path.basename(self.fileSavePath)
            self.UpdateTitle()

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

        # Get keybinds and save them
        from reggie.io.misc import SetKeybind
        for tab in dlg.keybindsTab.tabs:
            for keyEdit in tab.keyEdits:
                SetKeybind(keyEdit.name, keyEdit.keySequence())

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
        setSetting('Theme', dlg.appearanceTab.themeBox.currentText())
        setSetting('uiStyle', dlg.appearanceTab.windowStyle.currentText())

        globals_.UseRoundedRectangles = dlg.appearanceTab.roundedRects.isChecked()
        globals_.DarkMode = dlg.appearanceTab.darkMode.isChecked()

        setSetting('UseRoundedRectangles', globals_.UseRoundedRectangles)
        setSetting('DarkMode', globals_.DarkMode)

        # Update mode
        deferred.SetColorScheme()

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

    def LoadLevel(self, name, isFullPath, areaNum, add=False):
        return self._levelio.LoadLevel(name, isFullPath, areaNum, add=add)

    def newLevel(self, add=False):
        return self._levelio.newLevel(add=add)

    def LoadLevel_NSMBW(self, levelData, areaNum, add=False, file_path=None):
        return self._levelio.LoadLevel_NSMBW(levelData, areaNum, add=add,
                                             file_path=file_path)

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

        # No dirty check here any more (Block D, phase D-4). It used to be
        # required: switching ran Level.changeArea(), which unloads the outgoing
        # area, and Area.unload() drops the parsed data without serialising it -
        # so an edited area that was switched away from lost its edits, and a
        # later save wrote its pre-edit archive bytes. The prompt was the guard
        # against that.
        #
        # Areas now stay live in their own sessions, so there is nothing to lose
        # and nothing to ask about. The check stays everywhere work genuinely
        # can be lost: closing the editor, changing patch, opening another file.

        # In a session, a client asks the host before moving everyone, and the
        # host's broadcast is what loads it (Block C - B3, phase 3d).
        #
        # The combo box is put back to the area actually loaded, not to old_idx.
        # Proposing keeps the event loop running, so the host's answer - and the
        # level load that follows it - can complete *before* this returns.
        # Stamping old_idx over that would leave the box showing an area the
        # editor is not on: Zement's client sat on "Area 2" while both peers had
        # correctly loaded Area 1 (2026-08-11). The scene was right; only the
        # dropdown lied.
        #
        # globals_.Area is re-read rather than reusing old_idx precisely because
        # it may have changed while we waited.
        if not self._levelio._ProposeCollabSwitch(self._CollabLevelName(),
                                                  idx + 1):
            self._SyncAreaComboBox()
            return

        ok = self.SwitchToArea(idx + 1)

        if not ok:
            # switching to the new area failed, so reset the combobox
            self.areaComboBox.setCurrentIndex(old_idx)

    def SwitchToArea(self, area_num):
        """Show another area of the open level, keeping this one live.

        Block D, phase D-4. This used to be LoadLevel(path, True, n), which
        re-read the file from disk and handed off to Level.changeArea() -
        destroying the outgoing area's parsed state in the process.

        Now each area is its own session on the shared LevelHandle: the first
        visit loads it, every later visit is an activation. Falls back to the
        old path when there is no session manager, so nothing depends on one
        existing.
        """
        from reggie.core import session as session_module

        manager = globals_.get_session_manager()
        if manager is None:
            return bool(self.LoadLevel(self.fileSavePath, True, area_num))

        session = session_module.open_area(area_num)
        if session is None:
            return bool(self.LoadLevel(self.fileSavePath, True, area_num))

        # open_area activated the session to load into it; ActivateSession is
        # what moves the *view*. Activating twice is harmless - the manager
        # short-circuits on the session already being active - and keeping them
        # separate is what lets the load happen against correct globals.
        return self.ActivateSession(session)

    def LoadFirstLevelOfPatch(self):
        """
        Opens the current patch's first level after a patch switch.

        Block C - B3, round 2, R5. Switching patch used to keep the previous
        patch's level open, whose tilesets belong to a game that is no longer
        loaded - so the scene filled with pink placeholder tiles and a row of
        "tileset not found" warnings. Correct behaviour given the old design,
        and a bad experience; it is also, as Zement put it, one of the biggest
        sources of confusion when a session and a patch switch coincide.

        Applies even when no level is open. "Switching patch puts you on that
        patch's first level" is one rule with no exception to remember, which is
        Zement's call and the right one.

        Returns True if a level was loaded.

        The caller must have handled unsaved changes already: this is reached
        only after a *successful* switch, and prompting here would put the
        dialog after the patch had changed, when saving would write the old
        level through the new patch's paths.
        """
        from reggie.io.misc import FirstLevelName

        name = FirstLevelName()
        if not name:
            # A patch with no level list of its own falls back to retail's
            # through getResourcePaths, so reaching this means the list is
            # genuinely empty or unreadable. Leave the editor where it is
            # rather than guessing at a name.
            return False

        try:
            return bool(self.LoadLevel(name, False, 1))
        except Exception:
            # A patch whose first level cannot be opened is not a reason to
            # abandon the patch switch that already succeeded.
            return False

    def _SyncAreaComboBox(self):
        """
        Puts the area selector back in step with the area actually loaded.

        Read from globals_.Area rather than from a value captured earlier: in a
        session the area can change while a switch is being resolved, and a
        captured index would put the box back to where the editor *was* instead
        of where it is (Block C - B3).
        """
        area = getattr(globals_, 'Area', None)
        number = getattr(area, 'areanum', 0)

        try:
            index = int(number) - 1
        except (TypeError, ValueError):
            return

        if 0 <= index < self.areaComboBox.count():
            self.areaComboBox.setCurrentIndex(index)

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
    # ZoomLevels (the steps) stays a window attribute; ZoomLevel (the current
    # one) is a property forwarding to the active session since D-c.4.
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

    def showEvent(self, event):
        """
        Handler for the main window being shown (D-c.6)

        The sidebar's saved splitter positions are restored here rather than in
        the constructor: a splitter has no width until the window is laid out,
        and restoring against a zero width would clamp every saved size to
        nothing. Done once - a later show (un-minimising) must not undo a
        division the user has since dragged.

        **Deferred by a zero-length timer**, not run inline. The splitter still
        has no useful width *during* the first showEvent - measured: the saved
        width was silently dropped and the sidebar came back at its default,
        which is exactly what Zement reported (2026-08-30). Posting it to the
        event loop puts it after the first layout pass, which is the earliest
        moment the arithmetic means anything.
        """
        super().showEvent(event)

        if getattr(self, '_sidebarLayoutRestored', False):
            return

        self._sidebarLayoutRestored = True

        if self.sidebar is not None:
            QtCore.QTimer.singleShot(0, self.sidebar.restoreLayout)

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
        setSetting('MainWindowState', self.saveState(LAYOUT_VERSION))
        setSetting('MainWindowGeometry', self.saveGeometry())

        # The sidebar is deliberately not a dock, so saveState does not cover
        # it and its splitters have to be saved by hand (D-c.6).
        if self.sidebar is not None:
            self.sidebar.saveLayout()

        if hasattr(self, 'HelpBoxInstance'):
            self.HelpBoxInstance.close()

        if hasattr(self, 'TipsBoxInstance'):
            self.TipsBoxInstance.close()

        globals_.gamedef.SetLastLevel(str(self.fileSavePath))

        setSetting('AutoSaveFilePath', None)
        setSetting('AutoSaveFileData', 'x')

        # Stop every timer that could still fire after this point.
        #
        # These are parentless QTimers, so Qt does not own them - Python does,
        # and it frees them in its own order during interpreter shutdown, which
        # is not Qt's order. A timer that is still running when its target's C++
        # half has gone calls a slot on a dangling pointer, and on Windows that
        # is an access violation with no Python traceback: the process simply
        # dies after the last unrelated line of output.
        #
        # Autosave in particular reads globals_.Level and this window's own
        # fileSavePath, so it is not merely a stray callback - it dereferences
        # exactly the objects being torn down.
        #
        # This is hardening against a class of crash, not a proven fix for the
        # intermittent one Zement sees at roughly one exit in twenty-five: both
        # timers here are gated by flags (AutoSaveDirty, TilesetsAnimating) that
        # are false in the case he reported. crash.log will say whether it
        # recurs.
        self._StopBackgroundTimers()
        self._StopCollaboration()

        event.accept()

    def _StopCollaboration(self):
        """
        Ends a running session before the window is destroyed.

        Nothing did this before: the controller is created lazily and then
        simply kept, so a session's server, client and reader threads outlived
        closeEvent. Those threads deliver into the controller, which holds this
        window - so a message arriving during teardown reaches widgets whose
        C++ halves are being freed, and on Windows that is an access violation
        with no Python traceback.

        It also matches what the peers see: leaving sends a proper goodbye
        instead of dropping the connection, so the other side reports a
        participant who left rather than one who vanished.

        Best-effort and never fatal. Closing the editor has to succeed whatever
        state the session is in - a failure here would otherwise trap the user
        in a window they cannot close.
        """
        collab = getattr(self, '_collab', None)
        if collab is None:
            return

        try:
            if collab.is_active:
                collab.leave()
        except Exception:
            # Deliberately broad: this runs while the application is going
            # away, and no session fault is worth blocking that.
            pass

    def _StopBackgroundTimers(self):
        """
        Stops the timers that outlive the window, before teardown starts.

        Each is guarded separately: a timer that was never created, or already
        destroyed, must not stop the others from being stopped. Closing the
        editor has to succeed whatever state these are in.
        """
        timer = getattr(self, 'AutosaveTimer', None)
        if timer is not None:
            try:
                timer.stop()
            except (RuntimeError, AttributeError):
                # RuntimeError is PyQt's "wrapped C/C++ object has been
                # deleted", which is precisely the condition being defended
                # against - so it is expected here, not exceptional.
                pass

        # The tileset animation timer is the one with the most reach. It is a
        # *global* (globals_.TilesetAnimTimer), so it certainly outlives this
        # window; it fires every 90 ms, so the shutdown window it can land in is
        # wide; and its callback does globals_.mainWindow.scene.update() - it
        # dereferences this window and its scene directly. Nothing stopped it
        # anywhere in the codebase before now.
        #
        # Not established as *the* cause of the shutdown crash: its callback
        # returns immediately unless globals_.TilesetsAnimating is on, which is
        # a user toggle that defaults to off. Stopping it is correct either way
        # - a timer aimed at a window being destroyed should not still be
        # running - but the intermittent exit crash may yet have another source.
        anim = getattr(globals_, 'TilesetAnimTimer', None)
        if anim is not None:
            try:
                anim.stop()
            except (RuntimeError, AttributeError):
                pass

        # The status-bar warning icons each carry their own single-shot
        # dismissal timer, which can be pending when the editor is closed.
        for label in list(getattr(self, 'warningIcons', ()) or ()):
            dismiss = getattr(label, 'dismissTimer', None)
            if dismiss is None:
                continue
            try:
                dismiss.stop()
            except (RuntimeError, AttributeError):
                pass

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

        if globals_.Area.tileset0 == '' and globals_.Area.tileset1 == '' and globals_.Area.tileset2 == '' and globals_.Area.tileset3 == '':
            self.actions['swapobjectstypes'].setEnabled(False)
            self.actions['swapobjectstilesets'].setEnabled(False)

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

            # Give each node a list row if it does not already have a live one.
            #
            # Paths are the one item type ResetPalette did not rebuild rows for,
            # because the path list is filled during *parsing* - Path.add_node()
            # adds the row - and ResetPalette had only ever run straight after a
            # parse. An area switch is the first caller that breaks that: the
            # side lists are cleared, and QListWidget.clear() *destroys* the
            # QListWidgetItems, so every node was left holding a freed one.
            # Coming back, the path list stayed empty and clicking a node handed
            # that dangling pointer to setCurrentItem() - a hard crash inside
            # Qt, not a Python exception (Zement, 2026-08-28).
            #
            # Conditional, not unconditional: on a fresh load the rows already
            # exist from parsing, and rebuilding them there would give every
            # node two.
            for node in path._nodes:
                node.positionChanged = self.HandlePathPosChange

                if _list_row_is_live(node):
                    continue

                node.listitem = ListWidgetItem_SortsByOther(node, node.ListString())
                self.pathList.addItem(node.listitem)
                node.UpdateListItem()

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

    def _SelectListRowFor(self, listWidget, item):
        """Highlight an item's row in its side list, if that row still exists.

        Every caller used to do this inline as

            self.UpdateFlag = True
            someList.setCurrentItem(item.listitem)
            self.UpdateFlag = False

        which passes a raw pointer to Qt. QListWidget.clear() *destroys* the
        QListWidgetItems it holds, so an item whose list has been cleared since
        its row was made is holding freed memory - and handing that to
        setCurrentItem() is not a Python exception but a hard crash inside Qt
        (0xC0000409), which no excepthook can report.

        Reachable since areas began staying open across a switch: the lists are
        cleared on activation and rebuilt from the incoming area. Anything the
        rebuild misses lands here. Path nodes were exactly that case.
        """
        if not _list_row_is_live(item):
            return

        self.UpdateFlag = True
        try:
            listWidget.setCurrentItem(item.listitem)
        except RuntimeError:
            pass
        finally:
            self.UpdateFlag = False

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
                self._SelectListRowFor(self.entranceList, item)
                showEntrancePanel = True
                updateModeInfo = True
            elif func_ii(item, type_loc):
                self.creationTabs.setCurrentIndex(3)
                self._SelectListRowFor(self.locationList, item)
                showLocationPanel = True
                updateModeInfo = True
            elif func_ii(item, type_path):
                self.creationTabs.setCurrentIndex(4)
                self._SelectListRowFor(self.pathList, item)
                showPathPanel = True
                updateModeInfo = True
            elif func_ii(item, type_com):
                self.creationTabs.setCurrentIndex(7)
                self._SelectListRowFor(self.commentList, item)
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
        sprites = [x for x in items if isinstance(x, type_spr)]

        if sprites:
            if len(sprites) > 1:
                self.undoStack.beginMacro(globals_.trans.string(
                    'Undo', 33, '[n]', len(sprites), '[id]', type))
            try:
                for x in sprites:
                    with undo.record_property_edit(x, text=globals_.trans.string('Undo', 32, '[id]', type)):
                        x.spritedata = self.defaultDataEditor.data.copy()  # change this first or else images get messed up
                        x.SetType(type)
                    x.update()
            finally:
                if len(sprites) > 1:
                    self.undoStack.endMacro()

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
            with undo.record_property_edit(obj, text=globals_.trans.string('Undo', 34, '[id]', obj.type)):
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

                # The command performs the deletion and owns the removed items
                self.undoStack.push(undo.RemoveItemsCommand(sel))

                event.accept()
                self.levelOverview.update()
                self.SelectionUpdateFlag = False
                self.ChangeSelectionHandler()
                return

        self.levelOverview.update()

        QtWidgets.QMainWindow.keyPressEvent(self, event)

    # Area attributes covered by the Area Options dialog's undo snapshot
    _AREA_SETTINGS_ATTRS = (
        'loaded_sprites', 'force_loaded_sprites', 'timeLimit', 'startEntrance',
        'toadHouseType', 'wrapFlag', 'creditsFlag', 'faceLeftFlag',
        'unkFlag1', 'unkFlag2', 'unkVal1', 'unkVal2',
        'tileset0', 'tileset1', 'tileset2', 'tileset3',
    )

    def RefreshTilesetsFromArea(self):
        """
        (Re)loads the tilesets named by globals_.Area.tileset0-3 and refreshes
        every UI element that depends on them. Used by the Area Options dialog
        and by undo/redo of area settings.
        """
        tilesetNum = 0
        for idx, fname in enumerate((globals_.Area.tileset0, globals_.Area.tileset1,
                                     globals_.Area.tileset2, globals_.Area.tileset3)):
            if fname != '':
                tilesetNum += 1
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

        self.actions['swapobjectstypes'].setEnabled(tilesetNum != 0)
        self.actions['swapobjectstilesets'].setEnabled(tilesetNum != 0)

        self.scene.update()

        # Reset Quick Paint Tool when area settings change (tilesets may have changed)
        if hasattr(self, 'qpt_palette') and self.qpt_palette is not None:
            try:
                self.qpt_palette.reset()
            except Exception as e:
                print(f"[QPT] Warning: Could not reset QPT: {e}")

    def HandleAreaOptions(self):
        """
        Pops up the options for Area Dialogue
        """
        dlg = deferred.AreaOptionsDialog()
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        SetDirty()

        before = {attr: getattr(globals_.Area, attr) for attr in self._AREA_SETTINGS_ATTRS}

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
        globals_.Area.faceLeftFlag = dlg.LoadingTab.faceLeft.isChecked()
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

        self.RefreshTilesetsFromArea()

        after = {attr: getattr(globals_.Area, attr) for attr in self._AREA_SETTINGS_ATTRS}
        if after != before and not undo.is_recording_blocked():
            self.undoStack.push(undo.AreaSettingsCommand(
                before, after, globals_.trans.string('Undo', 51),
                refresh_tilesets=True))

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

        zones_before = undo.snapshot_zones()

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

        # Via set_action_allowed so a session's restriction is not overwritten;
        # see its docstring.
        from reggie.ui.collab_controller import set_action_allowed
        set_action_allowed('backgrounds', len(globals_.Area.zones) > 0)

        self.levelOverview.update()

        zones_after = undo.snapshot_zones()
        if zones_after != zones_before and not undo.is_recording_blocked():
            self.undoStack.push(undo.ZonesSnapshotCommand(
                zones_before, zones_after, globals_.trans.string('Undo', 50)))

    # Handles setting the backgrounds
    def HandleBG(self):
        """
        Pops up the Background settings Dialog
        """
        dlg = deferred.BGDialog()
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        SetDirty()

        zones_before = undo.snapshot_zones()

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

        zones_after = undo.snapshot_zones()
        if zones_after != zones_before and not undo.is_recording_blocked():
            self.undoStack.push(undo.ZonesSnapshotCommand(
                zones_before, zones_after, globals_.trans.string('Undo', 52)))

    def HandleScreenshot(self):
        """
        Takes a screenshot of the entire level and saves it
        """

        dlg = ScreenCapChoiceDialog()
        if dlg.exec() != QtWidgets.QDialog.DialogCode.Accepted:
            return

        screenshot_type = dlg.zoneCombo.currentIndex()
        grid_type = dlg.gridCombo.currentIndex()
        hide_background = dlg.hide_background.isChecked()
        do_save = dlg.save_img.isChecked()

        grid_type_list = [None, 'grid', 'checker']
        gt = globals_.GridType
        globals_.GridType = grid_type_list[grid_type]
        self.scene.update()

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

        # Restore the grid type
        globals_.GridType = gt
        self.scene.update()

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

        before = {'camprofiles': globals_.Area.camprofiles}
        globals_.Area.camprofiles = camprofiles
        SetDirty()

        if camprofiles != before['camprofiles'] and not undo.is_recording_blocked():
            self.undoStack.push(undo.AreaSettingsCommand(
                before, {'camprofiles': camprofiles},
                globals_.trans.string('Undo', 53)))
