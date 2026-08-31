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
        from reggie.io.misc import GetKeybind

        # File
        self.CreateAction(
            'newlevel', self.win.HandleNewLevel, GetIcon('new'),
            globals_.trans.stringOneLine('MenuItems', 0), globals_.trans.stringOneLine('MenuItems', 1),
            GetKeybind('newlevel'),
        )

        self.CreateAction(
            'openfromname', self.win.HandleOpenFromName, GetIcon('open'),
            globals_.trans.stringOneLine('MenuItems', 2), globals_.trans.stringOneLine('MenuItems', 3),
            GetKeybind('openfromname'),
        )

        self.CreateAction(
            'openfromfile', self.win.HandleOpenFromFile, GetIcon('openfromfile'),
            globals_.trans.stringOneLine('MenuItems', 4), globals_.trans.stringOneLine('MenuItems', 5),
            GetKeybind('openfromfile'),
        )

        self.CreateAction(
            'openrecent', None, GetIcon('recent'),
            globals_.trans.stringOneLine('MenuItems', 6), globals_.trans.stringOneLine('MenuItems', 7),
            None,
        )

        self.CreateAction(
            'save', self.win.HandleSave, GetIcon('save'),
            globals_.trans.stringOneLine('MenuItems', 8), globals_.trans.stringOneLine('MenuItems', 9),
            GetKeybind('save'),
        )

        self.CreateAction(
            'saveas', self.win.HandleSaveAs, GetIcon('saveas'),
            globals_.trans.stringOneLine('MenuItems', 10), globals_.trans.stringOneLine('MenuItems', 11),
            GetKeybind('saveas'),
        )

        self.CreateAction(
            'savecopyas', self.win.HandleSaveCopyAs, GetIcon('savecopyas'),
            globals_.trans.stringOneLine('MenuItems', 128), globals_.trans.stringOneLine('MenuItems', 129),
            GetKeybind('savecopyas'),
        )

        self.CreateAction(
            'metainfo', self.win.HandleInfo, GetIcon('info'),
            globals_.trans.stringOneLine('MenuItems', 12), globals_.trans.stringOneLine('MenuItems', 13),
            GetKeybind('metainfo'),
        )

        # Checkable since D-c.6: the undo history is a sidebar section rather
        # than a window, so the entry is a toggle and has to report whether the
        # section is up - a section has no close button of its own to say so.
        self.CreateAction(
            'undohistory', self.win.HandleShowUndoHistory, GetIcon('undo'),
            globals_.trans.stringOneLine('Undo', 0), globals_.trans.stringOneLine('Undo', 1),
            GetKeybind('undohistory'), True,
        )

        self.CreateAction(
            # No dedicated icon ships for this; 'spritelist' reads as a
            # participant list and avoids adding an asset the next block's UI
            # redesign would replace anyway.
            'collaborate', self.win.HandleCollaborate, GetIcon('spritelist'),
            'Collaborate...', 'Host or join a collaborative editing session',
            GetKeybind('collaborate'),
        )

        # 'changegamedef' (Change Game) and 'changegamepath' (Change Game Path)
        # were removed in Block D-d, phase D-d.1b. A patch is reached from the
        # Patch Manager or from the sidebar's Game Patches page now, and having
        # three entry points to one action was the thing D-d set out to end.
        #
        # `HandleChangeGamePath` itself is KEPT - `LoadGameDef` calls it
        # directly the first time a patch is opened without a Stage folder, so
        # it is a first-run flow, not only a menu command.

        self.CreateAction(
            'patchmanager', self.win.HandlePatchManager, GetIcon('game'),
            'Patch Manager', 'Manage folder paths for all game patches',
            GetKeybind('patchmanager'),
        )

        self.CreateAction(
            'screenshot', self.win.HandleScreenshot, GetIcon('screenshot'),
            globals_.trans.stringOneLine('MenuItems', 14), globals_.trans.stringOneLine('MenuItems', 15),
            GetKeybind('screenshot'),
        )

        self.CreateAction(
            'preferences', self.win.HandlePreferences, GetIcon('settings'),
            globals_.trans.stringOneLine('MenuItems', 18), globals_.trans.stringOneLine('MenuItems', 19),
            GetKeybind('preferences'),
        )

        self.CreateAction(
            'exit', self.win.HandleExit, GetIcon('delete'),
            globals_.trans.stringOneLine('MenuItems', 20), globals_.trans.stringOneLine('MenuItems', 21),
            GetKeybind('exit'),
        )

        # Edit
        self.CreateAction(
            'selectall', self.win.SelectAll, GetIcon('selectall'),
            globals_.trans.stringOneLine('MenuItems', 22), globals_.trans.stringOneLine('MenuItems', 23),
            GetKeybind('selectall'),
        )

        self.CreateAction(
            'deselect', self.win.Deselect, GetIcon('deselect'),
            globals_.trans.stringOneLine('MenuItems', 24), globals_.trans.stringOneLine('MenuItems', 25),
            GetKeybind('deselect'),
        )

        self.CreateAction(
            'undo', self.win.Undo, GetIcon('undo'),
            globals_.trans.stringOneLine('MenuItems', 124), globals_.trans.stringOneLine('MenuItems', 125),
            GetKeybind('undo'),
        )

        self.CreateAction(
            'redo', self.win.Redo, GetIcon('redo'),
            globals_.trans.stringOneLine('MenuItems', 126), globals_.trans.stringOneLine('MenuItems', 127),
            GetKeybind('redo'),
        )

        self.CreateAction(
            'cut', self.win.Cut, GetIcon('cut'),
            globals_.trans.stringOneLine('MenuItems', 26), globals_.trans.stringOneLine('MenuItems', 27),
            GetKeybind('cut'),
        )

        self.CreateAction(
            'copy', self.win.Copy, GetIcon('copy'),
            globals_.trans.stringOneLine('MenuItems', 28), globals_.trans.stringOneLine('MenuItems', 29),
            GetKeybind('copy'),
        )

        self.CreateAction(
            'paste', self.win.Paste, GetIcon('paste'),
            globals_.trans.stringOneLine('MenuItems', 30), globals_.trans.stringOneLine('MenuItems', 31),
            GetKeybind('paste'),
        )

        self.CreateAction(
            'shiftitems', self.win.ShiftItems, GetIcon('move'),
            globals_.trans.stringOneLine('MenuItems', 32), globals_.trans.stringOneLine('MenuItems', 33),
            GetKeybind('shiftitems'),
        )

        self.CreateAction(
            'mergelocations', self.win.MergeLocations, GetIcon('merge'),
            globals_.trans.stringOneLine('MenuItems', 34), globals_.trans.stringOneLine('MenuItems', 35),
            GetKeybind('mergelocations'),
        )

        self.CreateAction(
            'swapobjectstilesets', self.win.SwapObjectsTilesets, GetIcon('swap'),
            globals_.trans.stringOneLine('MenuItems', 104), globals_.trans.stringOneLine('MenuItems', 105),
            GetKeybind('swapobjectstilesets'),
        )

        self.CreateAction(
            'swapobjectstypes', self.win.SwapObjectsTypes, GetIcon('swap'),
            globals_.trans.stringOneLine('MenuItems', 106), globals_.trans.stringOneLine('MenuItems', 107),
            GetKeybind('swapobjectstypes'),
        )

        self.CreateAction(
            'diagnostic', self.win.HandleDiagnostics, GetIcon('diagnostics'),
            globals_.trans.stringOneLine('MenuItems', 36), globals_.trans.stringOneLine('MenuItems', 37),
            GetKeybind('diagnostic'),
        )

        self.CreateAction(
            'freezeobjects', self.win.HandleObjectsFreeze, GetIcon('objectsfreeze'),
            globals_.trans.stringOneLine('MenuItems', 38), globals_.trans.stringOneLine('MenuItems', 39),
            GetKeybind('freezeobjects'), True,
        )

        self.CreateAction(
            'freezesprites', self.win.HandleSpritesFreeze, GetIcon('spritesfreeze'),
            globals_.trans.stringOneLine('MenuItems', 40), globals_.trans.stringOneLine('MenuItems', 41),
            GetKeybind('freezesprites'), True,
        )

        self.CreateAction(
            'freezeentrances', self.win.HandleEntrancesFreeze, GetIcon('entrancesfreeze'),
            globals_.trans.stringOneLine('MenuItems', 42), globals_.trans.stringOneLine('MenuItems', 43),
            GetKeybind('freezeentrances'), True,
        )

        self.CreateAction(
            'freezelocations', self.win.HandleLocationsFreeze, GetIcon('locationsfreeze'),
            globals_.trans.stringOneLine('MenuItems', 44), globals_.trans.stringOneLine('MenuItems', 45),
            GetKeybind('freezelocations'), True,
        )

        self.CreateAction(
            'freezepaths', self.win.HandlePathsFreeze, GetIcon('pathsfreeze'),
            globals_.trans.stringOneLine('MenuItems', 46), globals_.trans.stringOneLine('MenuItems', 47),
            GetKeybind('freezepaths'), True,
        )

        self.CreateAction(
            'freezecomments', self.win.HandleCommentsFreeze, GetIcon('commentsfreeze'),
            globals_.trans.stringOneLine('MenuItems', 114), globals_.trans.stringOneLine('MenuItems', 115),
            GetKeybind('freezecomments'), True,
        )

        # View
        self.CreateAction(
            'showlay0', self.win.HandleUpdateLayer0, GetIcon('layer0'),
            globals_.trans.stringOneLine('MenuItems', 48), globals_.trans.stringOneLine('MenuItems', 49),
            GetKeybind('showlay0'), True,
        )

        self.CreateAction(
            'showlay1', self.win.HandleUpdateLayer1, GetIcon('layer1'),
            globals_.trans.stringOneLine('MenuItems', 50), globals_.trans.stringOneLine('MenuItems', 51),
            GetKeybind('showlay1'), True,
        )

        self.CreateAction(
            'showlay2', self.win.HandleUpdateLayer2, GetIcon('layer2'),
            globals_.trans.stringOneLine('MenuItems', 52), globals_.trans.stringOneLine('MenuItems', 53),
            GetKeybind('showlay2'), True,
        )

        self.CreateAction(
            'tileanim', self.win.HandleTilesetAnimToggle, GetIcon('animation'),
            globals_.trans.stringOneLine('MenuItems', 108), globals_.trans.stringOneLine('MenuItems', 109),
            GetKeybind('tileanim'), True,
        )

        self.CreateAction(
            'collisions', self.win.HandleCollisionsToggle, GetIcon('collisions'),
            globals_.trans.stringOneLine('MenuItems', 110), globals_.trans.stringOneLine('MenuItems', 111),
            GetKeybind('collisions'), True,
        )

        self.CreateAction(
            'realview', self.win.HandleRealViewToggle, GetIcon('realview'),
            globals_.trans.stringOneLine('MenuItems', 118), globals_.trans.stringOneLine('MenuItems', 119),
            GetKeybind('realview'), True,
        )

        self.CreateAction(
            'showsprites', self.win.HandleSpritesVisibility, GetIcon('sprites'),
            globals_.trans.stringOneLine('MenuItems', 54), globals_.trans.stringOneLine('MenuItems', 55),
            GetKeybind('showsprites'), True,
        )

        self.CreateAction(
            'showspriteimages', self.win.HandleSpriteImages, GetIcon('sprites'),
            globals_.trans.stringOneLine('MenuItems', 56), globals_.trans.stringOneLine('MenuItems', 57),
            GetKeybind('showspriteimages'), True,
        )

        self.CreateAction(
            'showlocations', self.win.HandleLocationsVisibility, GetIcon('locations'),
            globals_.trans.stringOneLine('MenuItems', 58), globals_.trans.stringOneLine('MenuItems', 59),
            GetKeybind('showlocations'), True,
        )

        self.CreateAction(
            'showcomments', self.win.HandleCommentsVisibility, GetIcon('comments'),
            globals_.trans.stringOneLine('MenuItems', 116), globals_.trans.stringOneLine('MenuItems', 117),
            GetKeybind('showcomments'), True,
        )

        self.CreateAction(
            'showpaths', self.win.HandlePathsVisibility, GetIcon('paths'),
            globals_.trans.stringOneLine('MenuItems', 130), globals_.trans.stringOneLine('MenuItems', 131),
            GetKeybind('showpaths'), True,
        )

        self.CreateAction(
            'grid', self.win.HandleSwitchGrid, GetIcon('grid'),
            globals_.trans.stringOneLine('MenuItems', 60), globals_.trans.stringOneLine('MenuItems', 61),
            GetKeybind('grid'),
        )

        self.CreateAction(
            'uiscaling', self.win.HandleUIScaling, None,
            'UI Scaling...', 'Adjust UI and font scaling for better readability',
            GetKeybind('uiscaling'),
        )

        self.CreateAction(
            'zoommax', self.win.HandleZoomMax, GetIcon('zoommax'),
            globals_.trans.stringOneLine('MenuItems', 62), globals_.trans.stringOneLine('MenuItems', 63),
            GetKeybind('zoommax'),
        )

        self.CreateAction(
            'zoomin', self.win.HandleZoomIn, GetIcon('zoomin'),
            globals_.trans.stringOneLine('MenuItems', 64), globals_.trans.stringOneLine('MenuItems', 65),
            GetKeybind('zoomin'),
        )

        self.CreateAction(
            'zoomactual', self.win.HandleZoomActual, GetIcon('zoomactual'),
            globals_.trans.stringOneLine('MenuItems', 66), globals_.trans.stringOneLine('MenuItems', 67),
            GetKeybind('zoomactual'),
        )

        self.CreateAction(
            'zoomout', self.win.HandleZoomOut, GetIcon('zoomout'),
            globals_.trans.stringOneLine('MenuItems', 68), globals_.trans.stringOneLine('MenuItems', 69),
            GetKeybind('zoomout'),
        )

        self.CreateAction(
            'zoommin', self.win.HandleZoomMin, GetIcon('zoommin'),
            globals_.trans.stringOneLine('MenuItems', 70), globals_.trans.stringOneLine('MenuItems', 71),
            GetKeybind('zoommin'),
        )

        # Show Overview and Show Palette are added later

        # Settings
        self.CreateAction(
            'areaoptions', self.win.HandleAreaOptions, GetIcon('area'),
            globals_.trans.stringOneLine('MenuItems', 72), globals_.trans.stringOneLine('MenuItems', 73),
            GetKeybind('areaoptions'),
        )

        self.CreateAction(
            'zones', self.win.HandleZones, GetIcon('zones'),
            globals_.trans.stringOneLine('MenuItems', 74), globals_.trans.stringOneLine('MenuItems', 75),
            GetKeybind('zones'),
        )

        self.CreateAction(
            'backgrounds', self.win.HandleBG, GetIcon('background'),
            globals_.trans.stringOneLine('MenuItems', 76), globals_.trans.stringOneLine('MenuItems', 77),
            GetKeybind('backgrounds'),
        )

        self.CreateAction(
            'camprofiles', self.win.HandleCameraProfiles, GetIcon('camprofile'),
            globals_.trans.stringOneLine('MenuItems', 140), globals_.trans.stringOneLine('MenuItems', 141),
            GetKeybind('camprofiles'),
        )

        self.CreateAction(
            'addarea', self.win.HandleAddNewArea, GetIcon('add'),
            globals_.trans.stringOneLine('MenuItems', 78), globals_.trans.stringOneLine('MenuItems', 79),
            GetKeybind('addarea'),
        )

        self.CreateAction(
            'importarea', self.win.HandleImportArea, GetIcon('import'),
            globals_.trans.stringOneLine('MenuItems', 80), globals_.trans.stringOneLine('MenuItems', 81),
            GetKeybind('importarea'),
        )

        self.CreateAction(
            'deletearea', self.win.HandleDeleteArea, GetIcon('delete'),
            globals_.trans.stringOneLine('MenuItems', 82), globals_.trans.stringOneLine('MenuItems', 83),
            GetKeybind('deletearea'),
        )

        self.CreateAction(
            'reloadgfx', self.win.ReloadTilesets, GetIcon('reload-tilesets'),
            globals_.trans.stringOneLine('MenuItems', 84), globals_.trans.stringOneLine('MenuItems', 85),
            GetKeybind('reloadgfx'),
        )

        self.CreateAction(
            'reloaddata', self.win.ReloadSpritedata, GetIcon('reload-spritedata'),
            globals_.trans.stringOneLine('MenuItems', 138), globals_.trans.stringOneLine('MenuItems', 139),
            GetKeybind('reloaddata'),
        )

        # Help actions are created later

        # Configure them
        self.win.actions['openrecent'].setMenu(self.win.RecentMenu)

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
        fmenu.addAction(self.win.actions['undohistory'])
        fmenu.addSeparator()
        fmenu.addAction(self.win.actions['collaborate'])
        fmenu.addSeparator()
        fmenu.addAction(self.win.actions['patchmanager'])
        fmenu.addAction(self.win.actions['screenshot'])
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
        vmenu.addAction(self.win.actions['showpaths'])
        vmenu.addAction(self.win.actions['showcomments'])
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

        # Registered by name so whole menus can be enabled or disabled as a
        # group (Block D-c), the way single actions already can. Keyed on the
        # untranslated names rather than the menu titles, which change with the
        # language and would make callers depend on the translation.
        self.win.menus = {
            'file': fmenu,
            'edit': emenu,
            'view': vmenu,
            'level': lmenu,
            'help': hmenu,
        }


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

        # The patch combo box and its toolbar were removed in Block D-d, phase
        # D-d.1b. Switching patch is the sidebar's Game Patches page now, and
        # the Patch Manager's; a third control that did the same thing is what
        # made the two lists able to disagree in the first place (f7).
        #
        # The attribute stays and stays None: `collab_controller` and
        # `RefreshPatchSelector` both reach for it with getattr and handle its
        # absence, and the preferences toolbar toggle can still be turned on for
        # a control that no longer exists without anything noticing.
        self.win.patchComboBox = None
    def SetupHelpMenu(self, menu=None):
        """
        Creates the help menu.
        """
        from reggie.ui.ui import GetIcon
        from reggie.io.misc import GetKeybind

        self.CreateAction('infobox', self.win.AboutBox, GetIcon('reggie'), globals_.trans.stringOneLine('MenuItems', 86),
                          globals_.trans.string('MenuItems', 87), GetKeybind('infobox'))
        self.CreateAction('helpbox', self.win.HelpBox, GetIcon('contents'), globals_.trans.stringOneLine('MenuItems', 88),
                          globals_.trans.string('MenuItems', 89), GetKeybind('helpbox'))
        self.CreateAction('tipbox', self.win.TipBox, GetIcon('tips'), globals_.trans.stringOneLine('MenuItems', 90),
                          globals_.trans.string('MenuItems', 91), GetKeybind('tipbox'))
        self.CreateAction('aboutqt', QtWidgets.QApplication.instance().aboutQt, GetIcon('qt'), globals_.trans.stringOneLine('MenuItems', 92),
                          globals_.trans.string('MenuItems', 93), GetKeybind('aboutqt'))

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
                'tileanim',
                'collisions',
                'realview',
            ), (
                'showsprites',
                'showspriteimages',
                'showlocations',
                'showpaths',
            ), (
                'areaoptions',
                'camprofiles',
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
