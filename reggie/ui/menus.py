"""Menu / toolbar / action construction extracted from ``ReggieWindow`` (Phase 2).

Fifth and largest extraction of the ``ReggieWindow`` breakup (see
_docs/plan/REFACTORING_ANALYSIS.md): ~640 lines building the actions, menubar,
help menu and toolbar. It references ~60 window handler methods as ``QAction``
triggers — all reached via ``self.win.<Handler>``. The three methods that call
each other (``CreateAction``, ``SetupHelpMenu``, ``addToolbarButtons``) call
through ``self.<name>`` because they now live together on this controller.

``self.<x>`` was rewritten to ``self.win.<x>`` mechanically (AST-driven, so only
real ``self`` references were touched), EXCEPT calls among the three sibling
methods above. ``ReggieWindow.SetupActionsAndMenus`` drives this via
``MenuBuilder(self).createMenubar()``; the window keeps thin delegators for the
sibling methods that other code calls (``SetupHelpMenu``).
"""

import sys

from PyQt6 import QtCore, QtGui, QtWidgets

from reggie.core import globals_
from reggie.core.dirty import setting
from libs import lib_versions

# GetIcon comes from ``ui``; reggie.py defers importing ``ui`` until after the
# QApplication exists, so we import GetIcon lazily inside the methods here to
# keep the same startup ordering (MenuBuilder is only used post-QApplication).


class MenuBuilder:
    """Builds the editor's actions, menubar, help menu and toolbar."""

    def __init__(self, win):
        self.win = win

    def CreateAction(self, shortname, function, icon, text, statustext, shortcut, toggle=False):
        """
        Helper function to create an action
        """

        # parent the QAction to the window (self is the MenuBuilder)
        if icon is not None:
            act = QtGui.QAction(icon, text, self.win)
        else:
            act = QtGui.QAction(text, self.win)

        if shortcut is not None: act.setShortcut(shortcut)
        if statustext is not None: act.setStatusTip(statustext)
        if toggle:
            act.setCheckable(True)
        if function is not None: act.triggered.connect(function)

        self.win.actions[shortname] = act

    def createMenubar(self):
        """
        Create actions, a menubar and a toolbar
        """
        from reggie.ui.ui import GetIcon

        # File
        self.CreateAction(
            'newlevel', self.win.HandleNewLevel, GetIcon('new'),
            globals_.trans.stringOneLine('MenuItems', 0), globals_.trans.stringOneLine('MenuItems', 1),
            QtGui.QKeySequence.StandardKey.New,
        )

        self.CreateAction(
            'openfromname', self.win.HandleOpenFromName, GetIcon('open'),
            globals_.trans.stringOneLine('MenuItems', 2), globals_.trans.stringOneLine('MenuItems', 3),
            QtGui.QKeySequence.StandardKey.Open,
        )

        self.CreateAction(
            'openfromfile', self.win.HandleOpenFromFile, GetIcon('openfromfile'),
            globals_.trans.stringOneLine('MenuItems', 4), globals_.trans.stringOneLine('MenuItems', 5),
            QtGui.QKeySequence('Ctrl+Shift+O'),
        )

        self.CreateAction(
            'openrecent', None, GetIcon('recent'),
            globals_.trans.stringOneLine('MenuItems', 6), globals_.trans.stringOneLine('MenuItems', 7),
            None,
        )

        self.CreateAction(
            'save', self.win.HandleSave, GetIcon('save'),
            globals_.trans.stringOneLine('MenuItems', 8), globals_.trans.stringOneLine('MenuItems', 9),
            QtGui.QKeySequence.StandardKey.Save,
        )

        self.CreateAction(
            'saveas', self.win.HandleSaveAs, GetIcon('saveas'),
            globals_.trans.stringOneLine('MenuItems', 10), globals_.trans.stringOneLine('MenuItems', 11),
            QtGui.QKeySequence.StandardKey.SaveAs,
        )

        self.CreateAction(
            'savecopyas', self.win.HandleSaveCopyAs, GetIcon('savecopyas'),
            globals_.trans.stringOneLine('MenuItems', 128), globals_.trans.stringOneLine('MenuItems', 129),
            None,
        )

        self.CreateAction(
            'metainfo', self.win.HandleInfo, GetIcon('info'),
            globals_.trans.stringOneLine('MenuItems', 12), globals_.trans.stringOneLine('MenuItems', 13),
            QtGui.QKeySequence('Ctrl+Alt+I'),
        )

        self.CreateAction(
            'changegamedef', None, GetIcon('game'),
            globals_.trans.stringOneLine('MenuItems', 98), globals_.trans.stringOneLine('MenuItems', 99),
            None,
        )

        self.CreateAction(
            'patchmanager', self.win.HandlePatchManager, GetIcon('game'),
            'Patch Manager', 'Manage folder paths for all game patches',
            None,
        )

        self.CreateAction(
            'screenshot', self.win.HandleScreenshot, GetIcon('screenshot'),
            globals_.trans.stringOneLine('MenuItems', 14), globals_.trans.stringOneLine('MenuItems', 15),
            QtGui.QKeySequence('Ctrl+Alt+S'),
        )

        self.CreateAction(
            'changegamepath', self.win.HandleChangeGamePath, GetIcon('folderpath'),
            globals_.trans.stringOneLine('MenuItems', 16), globals_.trans.stringOneLine('MenuItems', 17),
            QtGui.QKeySequence('Ctrl+Alt+G'),
        )

        self.CreateAction(
            'preferences', self.win.HandlePreferences, GetIcon('settings'),
            globals_.trans.stringOneLine('MenuItems', 18), globals_.trans.stringOneLine('MenuItems', 19),
            QtGui.QKeySequence('Ctrl+Alt+P'),
        )

        self.CreateAction(
            'exit', self.win.HandleExit, GetIcon('delete'),
            globals_.trans.stringOneLine('MenuItems', 20), globals_.trans.stringOneLine('MenuItems', 21),
            QtGui.QKeySequence('Ctrl+Q'),
        )

        # Edit
        self.CreateAction(
            'selectall', self.win.SelectAll, GetIcon('selectall'),
            globals_.trans.stringOneLine('MenuItems', 22), globals_.trans.stringOneLine('MenuItems', 23),
            QtGui.QKeySequence.StandardKey.SelectAll,
        )

        self.CreateAction(
            'deselect', self.win.Deselect, GetIcon('deselect'),
            globals_.trans.stringOneLine('MenuItems', 24), globals_.trans.stringOneLine('MenuItems', 25),
            QtGui.QKeySequence('Ctrl+D'),
        )

        self.CreateAction(
            'undo', self.win.Undo, GetIcon('undo'),
            globals_.trans.stringOneLine('MenuItems', 124), globals_.trans.stringOneLine('MenuItems', 125),
            QtGui.QKeySequence.StandardKey.Undo,
        )

        self.CreateAction(
            'redo', self.win.Redo, GetIcon('redo'),
            globals_.trans.stringOneLine('MenuItems', 126), globals_.trans.stringOneLine('MenuItems', 127),
            QtGui.QKeySequence.StandardKey.Redo,
        )

        self.CreateAction(
            'cut', self.win.Cut, GetIcon('cut'),
            globals_.trans.stringOneLine('MenuItems', 26), globals_.trans.stringOneLine('MenuItems', 27),
            QtGui.QKeySequence.StandardKey.Cut,
        )

        self.CreateAction(
            'copy', self.win.Copy, GetIcon('copy'),
            globals_.trans.stringOneLine('MenuItems', 28), globals_.trans.stringOneLine('MenuItems', 29),
            QtGui.QKeySequence.StandardKey.Copy,
        )

        self.CreateAction(
            'paste', self.win.Paste, GetIcon('paste'),
            globals_.trans.stringOneLine('MenuItems', 30), globals_.trans.stringOneLine('MenuItems', 31),
            QtGui.QKeySequence.StandardKey.Paste,
        )

        self.CreateAction(
            'shiftitems', self.win.ShiftItems, GetIcon('move'),
            globals_.trans.stringOneLine('MenuItems', 32), globals_.trans.stringOneLine('MenuItems', 33),
            QtGui.QKeySequence('Ctrl+Shift+S'),
        )

        self.CreateAction(
            'mergelocations', self.win.MergeLocations, GetIcon('merge'),
            globals_.trans.stringOneLine('MenuItems', 34), globals_.trans.stringOneLine('MenuItems', 35),
            QtGui.QKeySequence('Ctrl+Shift+E'),
        )

        self.CreateAction(
            'swapobjectstilesets', self.win.SwapObjectsTilesets, GetIcon('swap'),
            globals_.trans.stringOneLine('MenuItems', 104), globals_.trans.stringOneLine('MenuItems', 105),
            QtGui.QKeySequence('Ctrl+Shift+L'),
        )

        self.CreateAction(
            'swapobjectstypes', self.win.SwapObjectsTypes, GetIcon('swap'),
            globals_.trans.stringOneLine('MenuItems', 106), globals_.trans.stringOneLine('MenuItems', 107),
            QtGui.QKeySequence('Ctrl+Shift+Y'),
        )

        self.CreateAction(
            'diagnostic', self.win.HandleDiagnostics, GetIcon('diagnostics'),
            globals_.trans.stringOneLine('MenuItems', 36), globals_.trans.stringOneLine('MenuItems', 37),
            QtGui.QKeySequence('Ctrl+Shift+D'),
        )

        self.CreateAction(
            'freezeobjects', self.win.HandleObjectsFreeze, GetIcon('objectsfreeze'),
            globals_.trans.stringOneLine('MenuItems', 38), globals_.trans.stringOneLine('MenuItems', 39),
            QtGui.QKeySequence('Ctrl+Shift+1'), True,
        )

        self.CreateAction(
            'freezesprites', self.win.HandleSpritesFreeze, GetIcon('spritesfreeze'),
            globals_.trans.stringOneLine('MenuItems', 40), globals_.trans.stringOneLine('MenuItems', 41),
            QtGui.QKeySequence('Ctrl+Shift+2'), True,
        )

        self.CreateAction(
            'freezeentrances', self.win.HandleEntrancesFreeze, GetIcon('entrancesfreeze'),
            globals_.trans.stringOneLine('MenuItems', 42), globals_.trans.stringOneLine('MenuItems', 43),
            QtGui.QKeySequence('Ctrl+Shift+3'), True,
        )

        self.CreateAction(
            'freezelocations', self.win.HandleLocationsFreeze, GetIcon('locationsfreeze'),
            globals_.trans.stringOneLine('MenuItems', 44), globals_.trans.stringOneLine('MenuItems', 45),
            QtGui.QKeySequence('Ctrl+Shift+4'), True,
        )

        self.CreateAction(
            'freezepaths', self.win.HandlePathsFreeze, GetIcon('pathsfreeze'),
            globals_.trans.stringOneLine('MenuItems', 46), globals_.trans.stringOneLine('MenuItems', 47),
            QtGui.QKeySequence('Ctrl+Shift+5'), True,
        )

        self.CreateAction(
            'freezecomments', self.win.HandleCommentsFreeze, GetIcon('commentsfreeze'),
            globals_.trans.stringOneLine('MenuItems', 114), globals_.trans.stringOneLine('MenuItems', 115),
            QtGui.QKeySequence('Ctrl+Shift+9'), True,
        )

        # View
        self.CreateAction(
            'showlay0', self.win.HandleUpdateLayer0, GetIcon('layer0'),
            globals_.trans.stringOneLine('MenuItems', 48), globals_.trans.stringOneLine('MenuItems', 49),
            QtGui.QKeySequence('Ctrl+1'), True,
        )

        self.CreateAction(
            'showlay1', self.win.HandleUpdateLayer1, GetIcon('layer1'),
            globals_.trans.stringOneLine('MenuItems', 50), globals_.trans.stringOneLine('MenuItems', 51),
            QtGui.QKeySequence('Ctrl+2'), True,
        )

        self.CreateAction(
            'showlay2', self.win.HandleUpdateLayer2, GetIcon('layer2'),
            globals_.trans.stringOneLine('MenuItems', 52), globals_.trans.stringOneLine('MenuItems', 53),
            QtGui.QKeySequence('Ctrl+3'), True,
        )

        self.CreateAction(
            'tileanim', self.win.HandleTilesetAnimToggle, GetIcon('animation'),
            globals_.trans.stringOneLine('MenuItems', 108), globals_.trans.stringOneLine('MenuItems', 109),
            QtGui.QKeySequence('Ctrl+7'), True,
        )

        self.CreateAction(
            'collisions', self.win.HandleCollisionsToggle, GetIcon('collisions'),
            globals_.trans.stringOneLine('MenuItems', 110), globals_.trans.stringOneLine('MenuItems', 111),
            QtGui.QKeySequence('Ctrl+8'), True,
        )

        self.CreateAction(
            'realview', self.win.HandleRealViewToggle, GetIcon('realview'),
            globals_.trans.stringOneLine('MenuItems', 118), globals_.trans.stringOneLine('MenuItems', 119),
            QtGui.QKeySequence('Ctrl+9'), True,
        )

        self.CreateAction(
            'showsprites', self.win.HandleSpritesVisibility, GetIcon('sprites'),
            globals_.trans.stringOneLine('MenuItems', 54), globals_.trans.stringOneLine('MenuItems', 55),
            QtGui.QKeySequence('Ctrl+4'), True,
        )

        self.CreateAction(
            'showspriteimages', self.win.HandleSpriteImages, GetIcon('sprites'),
            globals_.trans.stringOneLine('MenuItems', 56), globals_.trans.stringOneLine('MenuItems', 57),
            QtGui.QKeySequence('Ctrl+6'), True,
        )

        self.CreateAction(
            'showlocations', self.win.HandleLocationsVisibility, GetIcon('locations'),
            globals_.trans.stringOneLine('MenuItems', 58), globals_.trans.stringOneLine('MenuItems', 59),
            QtGui.QKeySequence('Ctrl+5'), True,
        )

        self.CreateAction(
            'showcomments', self.win.HandleCommentsVisibility, GetIcon('comments'),
            globals_.trans.stringOneLine('MenuItems', 116), globals_.trans.stringOneLine('MenuItems', 117),
            None, True,
        )

        self.CreateAction(
            'showpaths', self.win.HandlePathsVisibility, GetIcon('paths'),
            globals_.trans.stringOneLine('MenuItems', 130), globals_.trans.stringOneLine('MenuItems', 131),
            QtGui.QKeySequence('Ctrl+*'), True,
        )

        self.CreateAction(
            'grid', self.win.HandleSwitchGrid, GetIcon('grid'),
            globals_.trans.stringOneLine('MenuItems', 60), globals_.trans.stringOneLine('MenuItems', 61),
            QtGui.QKeySequence('Ctrl+G'),
        )

        self.CreateAction(
            'uiscaling', self.win.HandleUIScaling, None,
            'UI Scaling...', 'Adjust UI and font scaling for better readability',
            None,
        )

        self.CreateAction(
            'zoommax', self.win.HandleZoomMax, GetIcon('zoommax'),
            globals_.trans.stringOneLine('MenuItems', 62), globals_.trans.stringOneLine('MenuItems', 63),
            QtGui.QKeySequence('Ctrl+PgDown'),
        )

        self.CreateAction(
            'zoomin', self.win.HandleZoomIn, GetIcon('zoomin'),
            globals_.trans.stringOneLine('MenuItems', 64), globals_.trans.stringOneLine('MenuItems', 65),
            QtGui.QKeySequence.StandardKey.ZoomIn,
        )

        self.CreateAction(
            'zoomactual', self.win.HandleZoomActual, GetIcon('zoomactual'),
            globals_.trans.stringOneLine('MenuItems', 66), globals_.trans.stringOneLine('MenuItems', 67),
            QtGui.QKeySequence('Ctrl+0'),
        )

        self.CreateAction(
            'zoomout', self.win.HandleZoomOut, GetIcon('zoomout'),
            globals_.trans.stringOneLine('MenuItems', 68), globals_.trans.stringOneLine('MenuItems', 69),
            QtGui.QKeySequence.StandardKey.ZoomOut,
        )

        self.CreateAction(
            'zoommin', self.win.HandleZoomMin, GetIcon('zoommin'),
            globals_.trans.stringOneLine('MenuItems', 70), globals_.trans.stringOneLine('MenuItems', 71),
            QtGui.QKeySequence('Ctrl+PgUp'),
        )

        # Show Overview and Show Palette are added later

        # Settings
        self.CreateAction(
            'areaoptions', self.win.HandleAreaOptions, GetIcon('area'),
            globals_.trans.stringOneLine('MenuItems', 72), globals_.trans.stringOneLine('MenuItems', 73),
            QtGui.QKeySequence('Ctrl+Alt+A'),
        )

        self.CreateAction(
            'zones', self.win.HandleZones, GetIcon('zones'),
            globals_.trans.stringOneLine('MenuItems', 74), globals_.trans.stringOneLine('MenuItems', 75),
            QtGui.QKeySequence('Ctrl+Alt+Z'),
        )

        self.CreateAction(
            'backgrounds', self.win.HandleBG, GetIcon('background'),
            globals_.trans.stringOneLine('MenuItems', 76), globals_.trans.stringOneLine('MenuItems', 77),
            QtGui.QKeySequence('Ctrl+Alt+B'),
        )

        self.CreateAction(
            'camprofiles', self.win.HandleCameraProfiles, GetIcon('camprofile'),
            globals_.trans.stringOneLine('MenuItems', 140), globals_.trans.stringOneLine('MenuItems', 141),
            QtGui.QKeySequence('Ctrl+Alt+C'),
        )

        self.CreateAction(
            'addarea', self.win.HandleAddNewArea, GetIcon('add'),
            globals_.trans.stringOneLine('MenuItems', 78), globals_.trans.stringOneLine('MenuItems', 79),
            QtGui.QKeySequence('Ctrl+Alt+N'),
        )

        self.CreateAction(
            'importarea', self.win.HandleImportArea, GetIcon('import'),
            globals_.trans.stringOneLine('MenuItems', 80), globals_.trans.stringOneLine('MenuItems', 81),
            QtGui.QKeySequence('Ctrl+Alt+O'),
        )

        self.CreateAction(
            'deletearea', self.win.HandleDeleteArea, GetIcon('delete'),
            globals_.trans.stringOneLine('MenuItems', 82), globals_.trans.stringOneLine('MenuItems', 83),
            QtGui.QKeySequence('Ctrl+Alt+D'),
        )

        self.CreateAction(
            'reloadgfx', self.win.ReloadTilesets, GetIcon('reload-tilesets'),
            globals_.trans.stringOneLine('MenuItems', 84), globals_.trans.stringOneLine('MenuItems', 85),
            QtGui.QKeySequence('Ctrl+Shift+R'),
        )

        self.CreateAction(
            'reloaddata', self.win.ReloadSpritedata, GetIcon('reload-spritedata'),
            globals_.trans.stringOneLine('MenuItems', 138), globals_.trans.stringOneLine('MenuItems', 139),
            # No shortcut for now...
            None
        )

        # Help actions are created later

        # Configure them
        self.win.actions['openrecent'].setMenu(self.win.RecentMenu)
        self.win.actions['changegamedef'].setMenu(self.win.GameDefMenu)

        self.win.actions['collisions'].setChecked(globals_.CollisionsShown)
        self.win.actions['realview'].setChecked(globals_.RealViewEnabled)

        self.win.actions['showsprites'].setChecked(globals_.SpritesShown)
        self.win.actions['showspriteimages'].setChecked(globals_.SpriteImagesShown)
        self.win.actions['showlocations'].setChecked(globals_.LocationsShown)
        self.win.actions['showcomments'].setChecked(globals_.CommentsShown)
        self.win.actions['showpaths'].setChecked(globals_.PathsShown)

        self.win.actions['freezeobjects'].setChecked(globals_.ObjectsFrozen)
        self.win.actions['freezesprites'].setChecked(globals_.SpritesFrozen)
        self.win.actions['freezeentrances'].setChecked(globals_.EntrancesFrozen )
        self.win.actions['freezelocations'].setChecked(globals_.LocationsFrozen)
        self.win.actions['freezepaths'].setChecked(globals_.PathsFrozen)
        self.win.actions['freezecomments'].setChecked(globals_.CommentsFrozen)

        self.win.actions['undo'].setEnabled(False)
        self.win.actions['redo'].setEnabled(False)
        self.win.actions['cut'].setEnabled(False)
        self.win.actions['copy'].setEnabled(False)
        self.win.actions['paste'].setEnabled(False)
        self.win.actions['shiftitems'].setEnabled(False)
        self.win.actions['mergelocations'].setEnabled(False)
        self.win.actions['deselect'].setEnabled(False)

        ####
        menubar = QtWidgets.QMenuBar()
        self.win.setMenuBar(menubar)

        fmenu = menubar.addMenu(globals_.trans.string('Menubar', 0))
        fmenu.addAction(self.win.actions['newlevel'])
        fmenu.addAction(self.win.actions['openfromname'])
        fmenu.addAction(self.win.actions['openfromfile'])
        fmenu.addAction(self.win.actions['openrecent'])
        fmenu.addSeparator()
        fmenu.addAction(self.win.actions['save'])
        fmenu.addAction(self.win.actions['saveas'])
        fmenu.addAction(self.win.actions['savecopyas'])
        fmenu.addAction(self.win.actions['metainfo'])
        fmenu.addSeparator()
        fmenu.addAction(self.win.actions['changegamedef'])
        fmenu.addAction(self.win.actions['patchmanager'])
        fmenu.addAction(self.win.actions['screenshot'])
        fmenu.addAction(self.win.actions['changegamepath'])
        fmenu.addAction(self.win.actions['preferences'])
        fmenu.addSeparator()
        fmenu.addAction(self.win.actions['exit'])

        emenu = menubar.addMenu(globals_.trans.string('Menubar', 1))
        emenu.addAction(self.win.actions['selectall'])
        emenu.addAction(self.win.actions['deselect'])
        emenu.addSeparator()
        emenu.addAction(self.win.actions['undo'])
        emenu.addAction(self.win.actions['redo'])
        emenu.addSeparator()
        emenu.addAction(self.win.actions['cut'])
        emenu.addAction(self.win.actions['copy'])
        emenu.addAction(self.win.actions['paste'])
        emenu.addSeparator()
        emenu.addAction(self.win.actions['shiftitems'])
        emenu.addAction(self.win.actions['mergelocations'])
        emenu.addAction(self.win.actions['swapobjectstilesets'])
        emenu.addAction(self.win.actions['swapobjectstypes'])
        emenu.addSeparator()
        emenu.addAction(self.win.actions['diagnostic'])
        emenu.addSeparator()
        emenu.addAction(self.win.actions['freezeobjects'])
        emenu.addAction(self.win.actions['freezesprites'])
        emenu.addAction(self.win.actions['freezeentrances'])
        emenu.addAction(self.win.actions['freezelocations'])
        emenu.addAction(self.win.actions['freezepaths'])
        emenu.addAction(self.win.actions['freezecomments'])

        vmenu = menubar.addMenu(globals_.trans.string('Menubar', 2))
        vmenu.addAction(self.win.actions['showlay0'])
        vmenu.addAction(self.win.actions['showlay1'])
        vmenu.addAction(self.win.actions['showlay2'])
        vmenu.addAction(self.win.actions['tileanim'])
        vmenu.addAction(self.win.actions['collisions'])
        vmenu.addAction(self.win.actions['realview'])
        vmenu.addSeparator()
        vmenu.addAction(self.win.actions['showsprites'])
        vmenu.addAction(self.win.actions['showspriteimages'])
        vmenu.addAction(self.win.actions['showlocations'])
        vmenu.addAction(self.win.actions['showcomments'])
        vmenu.addAction(self.win.actions['showpaths'])
        vmenu.addSeparator()
        vmenu.addAction(self.win.actions['grid'])
        vmenu.addAction(self.win.actions['uiscaling'])
        vmenu.addSeparator()
        vmenu.addAction(self.win.actions['zoommax'])
        vmenu.addAction(self.win.actions['zoomin'])
        vmenu.addAction(self.win.actions['zoomactual'])
        vmenu.addAction(self.win.actions['zoomout'])
        vmenu.addAction(self.win.actions['zoommin'])
        vmenu.addSeparator()
        # self.levelOverviewDock.toggleViewAction() is added here later
        # so we assign it to self.vmenu
        self.win.vmenu = vmenu

        lmenu = menubar.addMenu(globals_.trans.string('Menubar', 3))
        lmenu.addAction(self.win.actions['areaoptions'])
        lmenu.addAction(self.win.actions['camprofiles'])
        lmenu.addAction(self.win.actions['zones'])
        lmenu.addAction(self.win.actions['backgrounds'])
        lmenu.addSeparator()
        lmenu.addAction(self.win.actions['addarea'])
        lmenu.addAction(self.win.actions['importarea'])
        lmenu.addAction(self.win.actions['deletearea'])
        lmenu.addSeparator()
        lmenu.addAction(self.win.actions['reloadgfx'])
        lmenu.addAction(self.win.actions['reloaddata'])

        hmenu = menubar.addMenu(globals_.trans.string('Menubar', 4))
        self.SetupHelpMenu(hmenu)
        
        # create a toolbar
        self.win.toolbar = self.win.addToolBar(globals_.trans.string('Menubar', 5))
        self.win.toolbar.setObjectName('MainToolbar')
        
        # Check user preference for toolbar layout
        # Default: combined on Windows, separate on other platforms
        toolbar_separate = setting('ToolbarSeparate')
        if toolbar_separate is None:
            toolbar_separate = sys.platform != 'win32'
        
        # Add menubar to toolbar if combined mode is selected (and not on macOS)
        # On macOS, the menubar is always integrated into the system menu bar
        if not toolbar_separate and sys.platform == 'win32':
            menubar.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred, menubar.sizePolicy().verticalPolicy())
            self.win.toolbar.addWidget(menubar)

        # Add buttons to the toolbar
        self.addToolbarButtons()

        # Add the area combo box
        self.win.areaComboBox = QtWidgets.QComboBox()
        self.win.areaComboBox.activated.connect(self.win.HandleSwitchArea)
        self.win.toolbar.addWidget(self.win.areaComboBox)

        # Add the patch combo box (check if enabled in preferences)
        if setting('ToolbarActs') in (None, 'None', 'none', '', 0):
            # Default: enabled
            show_patches = True
        else:
            toggled = setting('ToolbarActs')
            show_patches = toggled.get('gamepatches', True)
        
        if show_patches:
            self.win.patchToolbar = self.win.addToolBar(globals_.trans.string('Menubar', 6))
            self.win.patchToolbar.setObjectName('PatchToolbar')
            self.win.patchComboBox = QtWidgets.QComboBox()
            self.win.patchComboBox.setMinimumWidth(200)
            self.win.patchComboBox.activated.connect(self.win.HandleSwitchPatch)
            self.win.patchToolbar.addWidget(self.win.patchComboBox)
        else:
            self.win.patchComboBox = None
    def SetupHelpMenu(self, menu=None):
        """
        Creates the help menu.
        """
        from reggie.ui.ui import GetIcon

        self.CreateAction('infobox', self.win.AboutBox, GetIcon('reggie'), globals_.trans.stringOneLine('MenuItems', 86),
                          globals_.trans.string('MenuItems', 87), QtGui.QKeySequence('Ctrl+Shift+I'))
        self.CreateAction('helpbox', self.win.HelpBox, GetIcon('contents'), globals_.trans.stringOneLine('MenuItems', 88),
                          globals_.trans.string('MenuItems', 89), QtGui.QKeySequence('Ctrl+Shift+H'))
        self.CreateAction('tipbox', self.win.TipBox, GetIcon('tips'), globals_.trans.stringOneLine('MenuItems', 90),
                          globals_.trans.string('MenuItems', 91), QtGui.QKeySequence('Ctrl+Shift+T'))
        self.CreateAction('aboutqt', QtWidgets.QApplication.instance().aboutQt, GetIcon('qt'), globals_.trans.stringOneLine('MenuItems', 92),
                          globals_.trans.string('MenuItems', 93), QtGui.QKeySequence('Ctrl+Shift+Q'))

        if menu is None:
            menu = QtWidgets.QMenu(globals_.trans.string('Menubar', 4))
        menu.addAction(self.win.actions['infobox'])
        menu.addAction(self.win.actions['helpbox'])
        menu.addAction(self.win.actions['tipbox'])
        menu.addSeparator()
        menu.addAction(self.win.actions['aboutqt'])
        menu.addSeparator()

        if lib_versions["nsmblib-updated"] is not None:
            value = str(lib_versions["nsmblib-updated"])
            version = int(value[:4]), int(value[4:6]), int(value[6:8]), int(value[8:10])
            nsmblib_info_text = "Using NSMBLib Updated %d.%d.%d.%d" % version
        elif lib_versions["nsmblib"] is not None:
            nsmblib_info_text = "Using NSMBLib %d" % lib_versions["nsmblib"]
        else:
            nsmblib_info_text = "Not using NSMBLib"

        if lib_versions["cython"] is not None:
            cython_info_text = "Using Cython %s" % lib_versions["cython"]
        else:
            cython_info_text = "Not using Cython"

        menu.addAction("Using Python %d.%d.%d" % sys.version_info[:3]).setEnabled(False)
        menu.addAction("Using PyQt %s" % QtCore.PYQT_VERSION_STR).setEnabled(False)
        menu.addAction("Using Qt %s" % QtCore.QT_VERSION_STR).setEnabled(False)
        menu.addAction(cython_info_text).setEnabled(False)
        menu.addAction(nsmblib_info_text).setEnabled(False)

        return menu
    def addToolbarButtons(self):
        """
        Reads from the Preferences file and adds the appropriate options to the toolbar
        """
        # First, define groups. Each group is isolated by separators.
        Groups = (
            (
                'newlevel',
                'openfromname',
                'openfromfile',
                'openrecent',
                'save',
                'saveas',
                'savecopyas',
                'metainfo',
                'screenshot',
                'changegamepath',
                'preferences',
                'exit',
            ), (
                'selectall',
                'deselect',
            ), (
                'cut',
                'copy',
                'paste',
            ), (
                'shiftitems',
                'mergelocations',
            ), (
                'freezeobjects',
                'freezesprites',
                'freezeentrances',
                'freezelocations',
                'freezepaths',
            ), (
                'diagnostic',
            ), (
                'zoommax',
                'zoomin',
                'zoomactual',
                'zoomout',
                'zoommin',
            ), (
                'grid',
            ), (
                'showlay0',
                'showlay1',
                'showlay2',
            ), (
                'showsprites',
                'showspriteimages',
                'showlocations',
                'showpaths',
            ), (
                'areaoptions',
                'zones',
                'backgrounds',
            ), (
                'addarea',
                'importarea',
                'deletearea',
            ), (
                'reloadgfx',
                'reloaddata',
            ), (
                'infobox',
                'helpbox',
                'tipbox',
                'aboutqt',
            ),
        )

        # Determine which keys are activated
        if setting('ToolbarActs') in (None, 'None', 'none', '', 0):
            # Get the default settings
            toggled = {}
            for List in (globals_.FileActions, globals_.EditActions, globals_.ViewActions, globals_.SettingsActions, globals_.HelpActions):
                for name, activated, key in List:
                    toggled[key] = activated
        else:
            # Get the settings from the .ini
            toggled = setting('ToolbarActs')
            newToggled = {}  # here, I'm replacing QStrings with python strings
            for key in toggled:
                newToggled[str(key)] = toggled[key]
            toggled = newToggled

        # Add each to the toolbar if toggled[key]
        for group in Groups:
            addedButtons = False
            for key in group:
                if key in toggled and toggled[key]:
                    act = self.win.actions[key]
                    self.win.toolbar.addAction(act)
                    addedButtons = True
            if addedButtons:
                self.win.toolbar.addSeparator()
