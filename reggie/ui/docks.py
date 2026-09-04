"""Dock / panel construction extracted from ``ReggieWindow`` (Phase 2).

Builds the level-overview, sprite/entrance/path/location editor docks and the
palette (object/sprite/stamp/event tabs). ~420 lines; the most widget-heavy
extraction. References ~30 window handler methods as signal targets (all via
``self.win.<Handler>``) and sets ~60 window widget attributes (``self.win.<w>``).

The widget classes are imported lazily at the top of the method: reggie.py
injects them into its own module globals at runtime (``global`` decls in
``main()`` + deferred ``from ... import``), so this module must import them for
itself; doing it in-method preserves the QApplication-before-``ui`` ordering.

``ReggieWindow.__init2__`` drives this via ``DockBuilder(self).SetupDocksAndPanels()``.
"""

from PyQt6 import QtCore, QtGui, QtWidgets

from reggie.core import globals_

Qt = QtCore.Qt


class DockBuilder:
    """Builds the editor's dock widgets and the creation palette."""

    def __init__(self, win):
        self.win = win

    def SetupDocksAndPanels(self):
        """
        Sets up the dock widgets and panels
        """
        from reggie.ui.ui import GetIcon, ListWidgetWithToolTipSignal, IconsOnlyTabBar
        from reggie.ui.sidelists import StampChooserWidget, SpriteList, SpritePickerWidget, ObjectPickerWidget, LevelOverviewWidget
        from reggie.ui.spriteeditor import SpriteEditorWidget
        from reggie.ui.editors import LocationEditorWidget, PathNodeEditorWidget, EntranceEditorWidget
        from reggie.io.misc import LoadSpriteCategories, GetKeybind
        from reggie.ui.sidebar import Sidebar

        # The docked sidebar (D-c.3). Built first so the panels below can be
        # placed into it as they are created, rather than made as docks and
        # moved afterwards - which would leave the dock objects alive and
        # save/restore state for panels that are no longer docks.
        self.win.sidebar = Sidebar(self.win)
        self.win.PlaceSidebar()

        # Level overview (D-c.4): floats over the bottom-right of the canvas
        # instead of living in a dock the user has to place and can lose behind
        # the window. It costs no layout space and is always where the canvas is.
        self.win.levelOverview = LevelOverviewWidget()
        self.win.levelOverview.moveIt.connect(self.win.HandleOverviewClick)
        overlayFrame = self.win.tabs.setOverlay(self.win.levelOverview)

        # A dock gave away toggleViewAction() for free; an overlay needs the
        # action made by hand. Two-way, so the menu entry reports the state
        # rather than only setting it.
        #
        # Toggles the *frame*, not the overview inside it: hiding only the inner
        # widget would leave its bordered background sitting on the canvas as an
        # empty box.
        act = QtGui.QAction(globals_.trans.string('MenuItems', 94), self.win)
        act.setCheckable(True)
        act.setChecked(True)
        # setUserVisible, not setVisible: a tool tab in front hides the overlay
        # without the menu's intent changing, and only the former keeps the two
        # apart (D-c.5).
        act.toggled.connect(overlayFrame.setUserVisible)
        act.setShortcut(GetKeybind('leveloverview'))
        act.setIcon(GetIcon('overview'))
        act.setStatusTip(globals_.trans.string('MenuItems', 95))
        # Register so the keybind editor (SetKeybind) can update the shortcut
        self.win.actions['leveloverview'] = act
        self.win.vmenu.addAction(act)

        # No levelOverviewDock alias: nothing outside this builder ever used it
        # (only a stale comment in menus.py mentions it), so keeping the name
        # would suggest a dock that no longer exists.

        # The four item-property editors (D-c.3). These were QDockWidgets, each
        # floating and separately closable; they are now panels in slice 3 of
        # the sidebar.
        #
        # The `...EditorDock` attributes keep their names and are PanelHosts,
        # which answer setVisible / isVisible / isFloating exactly as the docks
        # did. That is what leaves the ~20 sites in window.py that drive these
        # panels - the whole selection-to-panel protocol - untouched by the move.
        self.win.spriteDataEditor = SpriteEditorWidget()
        self.win.spriteDataEditor.DataUpdate.connect(self.win.SpriteDataUpdated)
        self.win.spriteEditorDock = self.win.sidebar.addPanel(
            globals_.trans.string('SpriteDataEditor', 0), self.win.spriteDataEditor)

        self.win.entranceEditor = EntranceEditorWidget()
        self.win.entranceEditorDock = self.win.sidebar.addPanel(
            globals_.trans.string('EntranceDataEditor', 24), self.win.entranceEditor)

        self.win.pathEditor = PathNodeEditorWidget()
        self.win.pathEditorDock = self.win.sidebar.addPanel(
            globals_.trans.string('PathDataEditor', 10), self.win.pathEditor)

        self.win.locationEditor = LocationEditorWidget()
        self.win.locationEditorDock = self.win.sidebar.addPanel(
            globals_.trans.string('LocationDataEditor', 12), self.win.locationEditor)

        # create the palette (D-c.3: a sidebar panel, not a dock)
        tabs = QtWidgets.QTabWidget()
        tabs.setTabBar(IconsOnlyTabBar())
        tabs.setIconSize(QtCore.QSize(16, 16))
        tabs.currentChanged.connect(self.win.CreationTabChanged)
        self.win.creationTabs = tabs

        # stretch=1: the palette takes the vertical space the property editors
        # do not want. It is a scrolling list of objects, so height is directly
        # more of what the user came for; the editors are fixed-size forms that
        # would only gain padding.
        dock = self.win.sidebar.addPanel(
            globals_.trans.string('MenuItems', 96), tabs, stretch=1)
        self.win.creationDock = dock
        dock.setVisible(True)

        # A dock gave away toggleViewAction() for free; a panel host needs the
        # action made by hand. Checkable and kept in step with the panel, so the
        # menu entry still reports the state rather than only setting it.
        act = QtGui.QAction(globals_.trans.string('MenuItems', 96), self.win)
        act.setCheckable(True)
        act.setChecked(True)
        act.toggled.connect(dock.setVisible)
        dock.visibilityChanged.connect(act.setChecked)
        act.setShortcut(GetKeybind('palette'))
        act.setIcon(GetIcon('palette'))
        act.setStatusTip(globals_.trans.string('MenuItems', 97))
        # Register so the keybind editor (SetKeybind) can update the shortcut
        self.win.actions['palette'] = act
        self.win.vmenu.addAction(act)

        # object choosing tabs
        tsicon = GetIcon('objects')

        self.win.objAllTab = QtWidgets.QTabWidget()
        self.win.objAllTab.currentChanged.connect(self.win.ObjTabChanged)
        tabs.addTab(self.win.objAllTab, tsicon, '')
        tabs.setTabToolTip(0, globals_.trans.string('Palette', 13))

        self.win.objTS0Tab = QtWidgets.QWidget()
        self.win.objTS1Tab = QtWidgets.QWidget()
        self.win.objTS2Tab = QtWidgets.QWidget()
        self.win.objTS3Tab = QtWidgets.QWidget()
        self.win.objAllTab.addTab(self.win.objTS0Tab, tsicon, '1')
        self.win.objAllTab.addTab(self.win.objTS1Tab, tsicon, '2')
        self.win.objAllTab.addTab(self.win.objTS2Tab, tsicon, '3')
        self.win.objAllTab.addTab(self.win.objTS3Tab, tsicon, '4')

        oel = QtWidgets.QVBoxLayout(self.win.objTS0Tab)
        self.win.createObjectLayout = oel

        ll = QtWidgets.QHBoxLayout()
        layerChangeStr = globals_.trans.string('Palette', 38)
        self.win.objUseLayer0 = QtWidgets.QRadioButton('0')
        self.win.objUseLayer0.setToolTip(globals_.trans.string('Palette', 1) + layerChangeStr)
        self.win.objUseLayer1 = QtWidgets.QRadioButton('1')
        self.win.objUseLayer1.setToolTip(globals_.trans.string('Palette', 2) + layerChangeStr)
        self.win.objUseLayer2 = QtWidgets.QRadioButton('2')
        self.win.objUseLayer2.setToolTip(globals_.trans.string('Palette', 3) + layerChangeStr)

        self.win.layerChangeButton = QtWidgets.QPushButton(globals_.trans.string('Palette', 36))
        self.win.layerChangeButton.clicked.connect(self.win.ChangeSelectionLayer)
        self.win.layerChangeButton.setEnabled(False)

        ll.addWidget(QtWidgets.QLabel(globals_.trans.string('Palette', 0)))
        ll.addWidget(self.win.objUseLayer0)
        ll.addWidget(self.win.objUseLayer1)
        ll.addWidget(self.win.objUseLayer2)
        ll.addStretch(1)
        ll.addWidget(self.win.layerChangeButton)
        oel.addLayout(ll)

        lbg = QtWidgets.QButtonGroup(self.win)
        lbg.addButton(self.win.objUseLayer0, 0)
        lbg.addButton(self.win.objUseLayer1, 1)
        lbg.addButton(self.win.objUseLayer2, 2)
        lbg.buttonClicked.connect(lambda button: self.win.LayerChoiceChanged(lbg.id(button)))
        self.win.LayerButtonGroup = lbg

        self.win.objPicker = ObjectPickerWidget()
        self.win.objPicker.ObjChanged.connect(self.win.ObjectChoiceChanged)
        self.win.objPicker.ObjReplace.connect(self.win.ObjectReplace)
        oel.addWidget(self.win.objPicker, 1)

        # sprite tab
        self.win.sprAllTab = QtWidgets.QTabWidget()
        self.win.sprAllTab.currentChanged.connect(self.win.SprTabChanged)
        tabs.addTab(self.win.sprAllTab, GetIcon('sprites'), '')
        tabs.setTabToolTip(1, globals_.trans.string('Palette', 14))

        # sprite tab: add
        self.win.sprPickerTab = QtWidgets.QWidget()
        self.win.sprAllTab.addTab(self.win.sprPickerTab, GetIcon('spritesadd'), globals_.trans.string('Palette', 25))

        spl = QtWidgets.QVBoxLayout(self.win.sprPickerTab)
        self.win.sprPickerLayout = spl

        svpl = QtWidgets.QHBoxLayout()
        svpl.addWidget(QtWidgets.QLabel(globals_.trans.string('Palette', 4)))

        sspl = QtWidgets.QHBoxLayout()
        sspl.addWidget(QtWidgets.QLabel(globals_.trans.string('Palette', 5)))

        LoadSpriteCategories()
        viewpicker = QtWidgets.QComboBox()
        for view in globals_.SpriteCategories:
            viewpicker.addItem(view[0])
        viewpicker.currentIndexChanged.connect(self.win.SelectNewSpriteView)

        self.win.spriteViewPicker = viewpicker
        svpl.addWidget(viewpicker, 1)

        self.win.spriteSearchTerm = QtWidgets.QLineEdit()
        self.win.spriteSearchTerm.textChanged.connect(self.win.NewSearchTerm)
        sspl.addWidget(self.win.spriteSearchTerm, 1)

        spl.addLayout(svpl)
        spl.addLayout(sspl)

        self.win.spriteSearchLayout = sspl

        self.win.sprPicker = SpritePickerWidget()
        self.win.sprPicker.SpriteChanged.connect(self.win.SpriteChoiceChanged)
        self.win.sprPicker.SpriteReplace.connect(self.win.SpriteReplace)
        self.win.sprPicker.SwitchView(globals_.SpriteCategories[0])
        
        # Add checkbox for showing sprite images
        showImagesCheckbox = QtWidgets.QCheckBox(globals_.trans.string('Sprites', 24))
        showImagesCheckbox.stateChanged.connect(self.win.sprPicker.toggleSpriteImages)
        # Block signals while setting initial state to avoid rendering during initialization
        showImagesCheckbox.blockSignals(True)
        showImagesCheckbox.setChecked(self.win.sprPicker.show_sprite_images)
        showImagesCheckbox.blockSignals(False)
        spl.addWidget(showImagesCheckbox)

        # Loading progress label (hidden when not loading)
        self.win.spriteImagesLoadingLabel = QtWidgets.QLabel()
        self.win.spriteImagesLoadingLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.win.spriteImagesLoadingLabel.hide()
        self.win.sprPicker.loadingProgress.connect(self.win._onSpriteImageLoadingProgress)

        spl.addWidget(self.win.sprPicker, 1)

        spl.addWidget(self.win.spriteImagesLoadingLabel)

        self.win.defaultPropButton = QtWidgets.QPushButton(globals_.trans.string('Palette', 6))
        self.win.defaultPropButton.setEnabled(False)
        self.win.defaultPropButton.clicked.connect(self.win.ShowDefaultProps)

        sdpl = QtWidgets.QHBoxLayout()
        sdpl.addStretch(1)
        sdpl.addWidget(self.win.defaultPropButton)
        sdpl.addStretch(1)
        spl.addLayout(sdpl)

        # default sprite data editor
        ddock = QtWidgets.QDockWidget(globals_.trans.string('Palette', 7), self.win)
        ddock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable)
        ddock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        ddock.setObjectName('defaultprops')  # needed for the state to save/restore correctly
        ddock.move(100, 100) # offset the dock from the top-left corner

        self.win.defaultDataEditor = SpriteEditorWidget(True)
        self.win.defaultDataEditor.setVisible(False)
        ddock.setWidget(self.win.defaultDataEditor)

        self.win.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, ddock)
        ddock.setVisible(False)
        ddock.setFloating(True)
        self.win.defaultPropDock = ddock

        # sprite tab: current
        self.win.sprEditorTab = QtWidgets.QWidget()
        self.win.sprAllTab.addTab(self.win.sprEditorTab, GetIcon('spritelist'), globals_.trans.string('Palette', 26))

        spel = QtWidgets.QVBoxLayout(self.win.sprEditorTab)
        self.win.sprEditorLayout = spel

        slabel = QtWidgets.QLabel(globals_.trans.string('Palette', 11))
        slabel.setWordWrap(True)
        self.win.spriteList = SpriteList()

        spel.addWidget(slabel)
        spel.addWidget(self.win.spriteList)

        # entrance tab
        self.win.entEditorTab = QtWidgets.QWidget()
        tabs.addTab(self.win.entEditorTab, GetIcon('entrances'), '')
        tabs.setTabToolTip(2, globals_.trans.string('Palette', 15))

        eel = QtWidgets.QVBoxLayout(self.win.entEditorTab)
        self.win.entEditorLayout = eel

        elabel = QtWidgets.QLabel(globals_.trans.string('Palette', 8))
        elabel.setWordWrap(True)
        self.win.entranceList = ListWidgetWithToolTipSignal()
        self.win.entranceList.itemActivated.connect(self.win.HandleEntranceSelectByList)
        self.win.entranceList.toolTipAboutToShow.connect(self.win.HandleEntranceToolTipAboutToShow)
        self.win.entranceList.setSortingEnabled(True)

        eel.addWidget(elabel)
        eel.addWidget(self.win.entranceList)

        # locations tab
        self.win.locEditorTab = QtWidgets.QWidget()
        tabs.addTab(self.win.locEditorTab, GetIcon('locations'), '')
        tabs.setTabToolTip(3, globals_.trans.string('Palette', 16))

        locL = QtWidgets.QVBoxLayout(self.win.locEditorTab)
        self.win.locEditorLayout = locL

        Llabel = QtWidgets.QLabel(globals_.trans.string('Palette', 12))
        Llabel.setWordWrap(True)
        self.win.locationList = ListWidgetWithToolTipSignal()
        self.win.locationList.itemActivated.connect(self.win.HandleLocationSelectByList)
        self.win.locationList.toolTipAboutToShow.connect(self.win.HandleLocationToolTipAboutToShow)
        self.win.locationList.setSortingEnabled(True)

        locL.addWidget(Llabel)
        locL.addWidget(self.win.locationList)

        # paths tab
        self.win.pathEditorTab = QtWidgets.QWidget()
        tabs.addTab(self.win.pathEditorTab, GetIcon('paths'), '')
        tabs.setTabToolTip(4, globals_.trans.string('Palette', 17))

        pathel = QtWidgets.QVBoxLayout(self.win.pathEditorTab)
        self.win.pathEditorLayout = pathel

        pathlabel = QtWidgets.QLabel(globals_.trans.string('Palette', 9))
        pathlabel.setWordWrap(True)
        deselectbtn = QtWidgets.QPushButton(globals_.trans.string('Palette', 10))
        deselectbtn.clicked.connect(self.win.DeselectPathSelection)
        self.win.pathList = ListWidgetWithToolTipSignal()
        self.win.pathList.itemActivated.connect(self.win.HandlePathSelectByList)
        self.win.pathList.toolTipAboutToShow.connect(self.win.HandlePathToolTipAboutToShow)
        self.win.pathList.setSortingEnabled(True)

        pathel.addWidget(pathlabel)
        pathel.addWidget(deselectbtn)
        pathel.addWidget(self.win.pathList)

        # events tab
        self.win.eventEditorTab = QtWidgets.QWidget()
        tabs.addTab(self.win.eventEditorTab, GetIcon('events'), '')
        tabs.setTabToolTip(5, globals_.trans.string('Palette', 18))

        eventel = QtWidgets.QGridLayout(self.win.eventEditorTab)

        eventlabel = QtWidgets.QLabel(globals_.trans.string('Palette', 20))
        eventNotesLabel = QtWidgets.QLabel(globals_.trans.string('Palette', 21))
        self.win.eventNotesEditor = QtWidgets.QLineEdit()
        self.win.eventNotesEditor.textEdited.connect(self.win.handleEventNotesEdit)

        self.win.eventChooser = QtWidgets.QTreeWidget()
        self.win.eventChooser.setColumnCount(2)
        self.win.eventChooser.setHeaderLabels((globals_.trans.string('Palette', 22), globals_.trans.string('Palette', 23)))
        self.win.eventChooser.itemClicked.connect(self.win.handleEventTabItemClick)
        self.win.eventChooserItems = []
        flags = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled
        for id in range(64):
            itm = QtWidgets.QTreeWidgetItem()
            itm.setFlags(flags)
            itm.setCheckState(0, Qt.CheckState.Unchecked)
            itm.setText(0, globals_.trans.string('Palette', 24, '[id]', str(id + 1)))
            itm.setText(1, '')
            self.win.eventChooser.addTopLevelItem(itm)
            self.win.eventChooserItems.append(itm)
            if id == 0: itm.setSelected(True)

        eventel.addWidget(eventlabel, 0, 0, 1, 2)
        eventel.addWidget(eventNotesLabel, 1, 0)
        eventel.addWidget(self.win.eventNotesEditor, 1, 1)
        eventel.addWidget(self.win.eventChooser, 2, 0, 1, 2)

        # stamps tab
        self.win.stampTab = QtWidgets.QWidget()
        tabs.addTab(self.win.stampTab, GetIcon('stamp'), '')
        tabs.setTabToolTip(6, globals_.trans.string('Palette', 19))

        stampLabel = QtWidgets.QLabel(globals_.trans.string('Palette', 27))

        stampAddBtn = QtWidgets.QPushButton(globals_.trans.string('Palette', 28))
        stampAddBtn.clicked.connect(self.win.handleStampsAdd)
        stampAddBtn.setEnabled(False)
        self.win.stampAddBtn = stampAddBtn  # so we can enable/disable it later
        stampRemoveBtn = QtWidgets.QPushButton(globals_.trans.string('Palette', 29))
        stampRemoveBtn.clicked.connect(self.win.handleStampsRemove)
        stampRemoveBtn.setEnabled(False)
        self.win.stampRemoveBtn = stampRemoveBtn  # so we can enable/disable it later

        menu = QtWidgets.QMenu()
        menu.addAction(globals_.trans.string('Palette', 31), self.win.handleStampsOpen)  # Open Set...
        menu.addAction(globals_.trans.string('Palette', 32), self.win.handleStampsSave)  # Save Set As...
        stampToolsBtn = QtWidgets.QToolButton()
        stampToolsBtn.setText(globals_.trans.string('Palette', 30))
        stampToolsBtn.setMenu(menu)
        stampToolsBtn.setPopupMode(QtWidgets.QToolButton.ToolButtonPopupMode.InstantPopup)
        stampToolsBtn.setSizePolicy(stampAddBtn.sizePolicy())
        stampToolsBtn.setMinimumHeight(stampAddBtn.height() // 20)

        stampNameLabel = QtWidgets.QLabel(globals_.trans.string('Palette', 35))
        self.win.stampNameEdit = QtWidgets.QLineEdit()
        self.win.stampNameEdit.setEnabled(False)
        self.win.stampNameEdit.textChanged.connect(self.win.handleStampNameEdited)

        nameLayout = QtWidgets.QHBoxLayout()
        nameLayout.addWidget(stampNameLabel)
        nameLayout.addWidget(self.win.stampNameEdit)

        self.win.stampChooser = StampChooserWidget()
        self.win.stampChooser.selectionChangedSignal.connect(self.win.handleStampSelectionChanged)

        stampL = QtWidgets.QGridLayout()
        stampL.addWidget(stampLabel, 0, 0, 1, 3)
        stampL.addWidget(stampAddBtn, 1, 0)
        stampL.addWidget(stampRemoveBtn, 1, 1)
        stampL.addWidget(stampToolsBtn, 1, 2)
        stampL.addLayout(nameLayout, 2, 0, 1, 3)
        stampL.addWidget(self.win.stampChooser, 3, 0, 1, 3)
        self.win.stampTab.setLayout(stampL)

        # comments tab
        self.win.commentsTab = QtWidgets.QWidget()
        tabs.addTab(self.win.commentsTab, GetIcon('comments'), '')
        tabs.setTabToolTip(7, globals_.trans.string('Palette', 33))

        cel = QtWidgets.QVBoxLayout()
        self.win.commentsTab.setLayout(cel)

        clabel = QtWidgets.QLabel(globals_.trans.string('Palette', 34))
        clabel.setWordWrap(True)

        self.win.commentList = ListWidgetWithToolTipSignal()
        self.win.commentList.itemActivated.connect(self.win.HandleCommentSelectByList)
        self.win.commentList.toolTipAboutToShow.connect(self.win.HandleCommentToolTipAboutToShow)
        self.win.commentList.setSortingEnabled(True)

        cel.addWidget(clabel)
        cel.addWidget(self.win.commentList)

        # Set the current tab to the Object tab
        self.win.CreationTabChanged(0)

        # Let the palette's contents grow into the sidebar, now that they exist
        # (Block D-c). Here rather than in addPanel: the palette's tab widget is
        # handed over empty and filled across the ~300 lines above, so anything
        # recursing into it earlier would find nothing to relax. Every level
        # from the panel host down to the innermost list has to agree before the
        # list can use the height, which is why one setSizePolicy on the panel
        # was not enough.
        self.win.sidebar.relaxPanelHeights()

        # Slice 1 gets its entries (D-d.1). Last, because the Game Patches page
        # is a real widget and the rail's first entry selects a page as soon as
        # it is added.
        self.buildRail()

    def buildRail(self):
        """Fill slice 1, the icon rail (Block D-d, phase D-d.1).

        The set comes from Zement's brief: Game Patches, Directory Listing,
        (Puzzle Next later), Logs/Undo, Help, Preferences. Provisional - entries
        are expected to be added as the later phases land.

        **Every rail entry that shows something in slice 2 opens a section**
        (Zement's model, 2026-09-01). Game Patches was a rail *page* until then -
        a `QStackedWidget` entry rather than a section - and that accidental
        split is what produced two of his four reports: the patch list had no
        collapsible header because it was not a section, and the undo history
        looked "attached to" the directory listing because a page replaced the
        whole splitter while a section merely joined it.

        So there are two kinds of entry left:

        - **Game Patches**, **Directory Listing** and **Help** open
          *context-sensitive* sections: mutually exclusive, always on top.
        - **Preferences** is an action - it opens as a tool tab in the master
          container and has no sidebar content at all. **Logs/Undo** is also an
          action, but one that opens an *always-open* section, which stacks
          below the context section and survives every switch between them.
        """
        sidebar = self.win.sidebar
        if sidebar is None:
            return

        # Lazy, like the other reggie.ui imports here: reggie.py defers `ui`
        # until after the QApplication exists (the Block A lesson).
        from reggie.ui.ui import GetIcon

        trans = globals_.trans.string

        # big=True (D-d.1c): the 'sm' icons are 16px source art, so a rail
        # asking for 38px (64 * 0.6) would upscale a 16px bitmap - soft, and
        # never actually larger than 16. The 'lg' set is 48px, which covers
        # every rail width. This is why "only the section reserved for the icon
        # grows, not the actual icon" (Zement, 2026-08-31).
        def icon(name):
            return GetIcon(name, True)

        # `is_open` on each: clicking the entry whose section is already showing
        # must not rebuild it, or the tree loses its scroll position, its
        # expanded levels and the selection. Each answers for its own widget,
        # which is the only thing the sidebar cannot work out for itself.
        def showing(attr):
            def check():
                widget = getattr(self.win, attr, None)
                return (widget is not None
                        and sidebar.sectionFor(widget) is not None)
            return check

        # The widget an entry's section holds, read live: a context section is
        # rebuilt every time it opens, so a stored reference would be the one
        # from last time. This is what lets a click *inside* a panel move the
        # highlight onto its entry (D-d.6).
        def owns(attr):
            return lambda: getattr(self.win, attr, None)

        # -- Game Patches ------------------------------------------------
        sidebar.addPage(icon('game'), trans('MenuItems', 142),
                        sections=True,
                        on_activate=self._showGamePatches,
                        is_open=showing('patchListWidget'),
                        owns_widget=owns('patchListWidget'))

        # -- Directory Listing --------------------------------------------
        sidebar.addPage(icon('folderpath'), trans('MenuItems', 143),
                        sections=True,
                        on_activate=self._showDirectoryListing,
                        is_open=showing('levelTreeWidget'),
                        owns_widget=owns('levelTreeWidget'))

        # -- Logs / Undo --------------------------------------------------
        # A toggle: selecting it opens the undo history, selecting it again
        # closes it. `toggles=True` is what lets the second click through -
        # `is_open` alone would swallow it, since its other job is stopping a
        # re-click from rebuilding a section that is already up.
        #
        # It still needs `is_open`, so the highlight can follow the panel: the
        # entry used to have none, and so stayed lit over a panel it had just
        # closed (Zement, 2026-09-04).
        sidebar.addPage(icon('undo'), trans('MenuItems', 144),
                        sections=True,
                        on_activate=self._showUndoHistory,
                        is_open=showing('undoHistoryView'),
                        owns_widget=owns('undoHistoryView'),
                        toggles=True)

        # -- Collaborate --------------------------------------------------
        # One entry for both halves of collaboration (D-d.5): with no session
        # running it opens the host/join dialog, and with one it opens the
        # roster and chat. Zement ranked a single panel first (2026-09-02); one
        # *entry* is what that preference is actually about, and it costs
        # nothing, while one *panel* would mean reworking the join path's
        # exec()/collectResult() handshake and the discovery thread's shutdown.
        #
        # A toggle like Logs/Undo while a session is running, so the same pair:
        # `toggles` lets the closing click through, `is_open` lets the highlight
        # follow the panel.
        #
        # 'spritelist' is what the Collaborate menu action already uses, so the
        # rail and the menu name the same thing with the same picture.
        sidebar.addPage(icon('spritelist'), trans('MenuItems', 165),
                        sections=True,
                        on_activate=self._showCollaboration,
                        is_open=self._collabPanelOpen,
                        owns_widget=self._collabPanelWidget,
                        toggles=True)

        # -- Help ---------------------------------------------------------
        sidebar.addPage(icon('help'), trans('MenuItems', 88),
                        sections=True,
                        on_activate=self._showHelp,
                        is_open=showing('helpTreeWidget'),
                        owns_widget=owns('helpTreeWidget'))

        # -- Preferences --------------------------------------------------
        sidebar.addPage(icon('settings'), trans('MenuItems', 18),
                        on_activate=self.win.HandlePreferences)

    def _showGamePatches(self):
        """Open the Game Patches section unless it is already up."""
        self.win.ShowGamePatches()

    def _showDirectoryListing(self):
        """Open the directory listing section unless it is already up (D-d.2).

        Not a toggle, for the same reason the undo entry is not: selecting a
        rail category should never *hide* the thing it names.
        """
        self.win.ShowDirectoryListing()

    def _showHelp(self):
        """Open the Help section unless it is already up (D-d.2c)."""
        self.win.ShowHelpSection()

    def _showCollaboration(self):
        """Open the collaboration panel, or the host/join dialog (D-d.5)."""
        self.win.ShowCollaboration()

    def _collabPanelWidget(self):
        """The widget the collaboration section holds, or None.

        The controller's status window: it owns it for the life of the session,
        and the section merely shows it.
        """
        controller = getattr(self.win, '_collab', None)
        return getattr(controller, 'status_window', None) \
            if controller is not None else None

    def _collabPanelOpen(self):
        """Whether the collaboration panel is showing.

        Asked of the controller, which owns the window the section holds - and
        answering False with no controller is right, since a session that has
        never started has no panel to be showing.
        """
        controller = getattr(self.win, '_collab', None)
        if controller is None:
            return False

        window = getattr(controller, 'status_window', None)
        if window is None:
            return False

        sidebar = getattr(self.win, 'sidebar', None)
        return sidebar is not None and sidebar.sectionFor(window) is not None

    def _showUndoHistory(self):
        """Toggle the undo history section (Zement, 2026-09-01).

        A *toggle*, unlike the context entries, and the asymmetry is the point.
        Clicking a context entry means "show me this instead of that", so
        closing on a second click would leave slice 2 with nothing selected.
        An always-open section has no "instead": it is either there or not, and
        the rail entry is the switch. "Clicking on Undo History rail button
        while the panel is open should *close* the panel."
        """
        if self.win.sidebar is None:
            return

        self.win.HandleShowUndoHistory()
