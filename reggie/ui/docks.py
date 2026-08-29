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
        self.win.tabs.setOverlay(self.win.levelOverview)

        # A dock gave away toggleViewAction() for free; an overlay needs the
        # action made by hand. Two-way, so the menu entry reports the state
        # rather than only setting it.
        act = QtGui.QAction(globals_.trans.string('MenuItems', 94), self.win)
        act.setCheckable(True)
        act.setChecked(True)
        act.toggled.connect(self.win.levelOverview.setVisible)
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
