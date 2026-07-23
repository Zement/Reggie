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
        from reggie.io.misc import LoadSpriteCategories
        # level overview
        dock = QtWidgets.QDockWidget(globals_.trans.string('MenuItems', 94), self.win)
        dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable)
        # dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setObjectName('leveloverview')  # needed for the state to save/restore correctly

        self.win.levelOverview = LevelOverviewWidget()
        self.win.levelOverview.moveIt.connect(self.win.HandleOverviewClick)
        self.win.levelOverviewDock = dock
        dock.setWidget(self.win.levelOverview)

        self.win.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.setVisible(True)
        act = dock.toggleViewAction()
        act.setShortcut(QtGui.QKeySequence('Ctrl+M'))
        act.setIcon(GetIcon('overview'))
        act.setStatusTip(globals_.trans.string('MenuItems', 95))
        self.win.vmenu.addAction(act)

        # create the sprite editor panel
        dock = QtWidgets.QDockWidget(globals_.trans.string('SpriteDataEditor', 0), self.win)
        dock.setVisible(False)
        dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setObjectName('spriteeditor')  # needed for the state to save/restore correctly
        dock.move(100, 100) # offset the dock from the top-left corner

        self.win.spriteDataEditor = SpriteEditorWidget()
        self.win.spriteDataEditor.DataUpdate.connect(self.win.SpriteDataUpdated)
        dock.setWidget(self.win.spriteDataEditor)
        self.win.spriteEditorDock = dock

        self.win.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.setFloating(True)

        # create the entrance editor panel
        dock = QtWidgets.QDockWidget(globals_.trans.string('EntranceDataEditor', 24), self.win)
        dock.setVisible(False)
        dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setObjectName('entranceeditor')  # needed for the state to save/restore correctly
        dock.move(100, 100) # offset the dock from the top-left corner

        self.win.entranceEditor = EntranceEditorWidget()
        dock.setWidget(self.win.entranceEditor)
        self.win.entranceEditorDock = dock

        self.win.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.setFloating(True)

        # create the path node editor panel
        dock = QtWidgets.QDockWidget(globals_.trans.string('PathDataEditor', 10), self.win)
        dock.setVisible(False)
        dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setObjectName('pathnodeeditor')  # needed for the state to save/restore correctly
        dock.move(100, 100) # offset the dock from the top-left corner

        self.win.pathEditor = PathNodeEditorWidget()
        dock.setWidget(self.win.pathEditor)
        self.win.pathEditorDock = dock

        self.win.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.setFloating(True)

        # create the location editor panel
        dock = QtWidgets.QDockWidget(globals_.trans.string('LocationDataEditor', 12), self.win)
        dock.setVisible(False)
        dock.setFeatures(QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setObjectName('locationeditor')  # needed for the state to save/restore correctly
        dock.move(100, 100) # offset the dock from the top-left corner

        self.win.locationEditor = LocationEditorWidget()
        dock.setWidget(self.win.locationEditor)
        self.win.locationEditorDock = dock

        self.win.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.setFloating(True)

        # create the palette
        dock = QtWidgets.QDockWidget(globals_.trans.string('MenuItems', 96), self.win)
        dock.setFeatures(
            QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetMovable | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetFloatable | QtWidgets.QDockWidget.DockWidgetFeature.DockWidgetClosable)
        dock.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        dock.setObjectName('palette')  # needed for the state to save/restore correctly

        self.win.creationDock = dock
        act = dock.toggleViewAction()
        act.setShortcut(QtGui.QKeySequence('Ctrl+P'))
        act.setIcon(GetIcon('palette'))
        act.setStatusTip(globals_.trans.string('MenuItems', 97))
        self.win.vmenu.addAction(act)

        self.win.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        dock.setVisible(True)

        # add tabs to it
        tabs = QtWidgets.QTabWidget()
        tabs.setTabBar(IconsOnlyTabBar())
        tabs.setIconSize(QtCore.QSize(16, 16))
        tabs.currentChanged.connect(self.win.CreationTabChanged)
        dock.setWidget(tabs)
        self.win.creationTabs = tabs

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
        self.win.objUseLayer0 = QtWidgets.QRadioButton('0')
        self.win.objUseLayer0.setToolTip(globals_.trans.string('Palette', 1))
        self.win.objUseLayer1 = QtWidgets.QRadioButton('1')
        self.win.objUseLayer1.setToolTip(globals_.trans.string('Palette', 2))
        self.win.objUseLayer2 = QtWidgets.QRadioButton('2')
        self.win.objUseLayer2.setToolTip(globals_.trans.string('Palette', 3))

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
