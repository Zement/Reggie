import base64

from PyQt6 import QtWidgets, QtGui, QtCore

from reggie.core import globals_
from reggie.core.tiles import RenderObject, TilesetTile
from reggie.ui.ui import ListWidgetWithToolTipSignal
from reggie.io.misc import LoadSpriteData, LoadSpriteListData, LoadSpriteCategories
from reggie.ui.spriteeditor import SpriteEditorWidget
from reggie.ui.overlay import canvas_overlay_colour
from reggie.core.dirty import setting, setSetting

class LevelOverviewWidget(QtWidgets.QWidget):
    """
    Widget that shows an overview of the level and can be clicked to move the view
    """
    moveIt = QtCore.pyqtSignal(float, float)

    def __init__(self):
        """
        Constructor for the level overview widget
        """
        QtWidgets.QWidget.__init__(self)
        self.setSizePolicy(
            QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Policy.MinimumExpanding, QtWidgets.QSizePolicy.Policy.MinimumExpanding))
        
        # Set minimum height to ensure visibility when docked
        self.setMinimumHeight(80)

        # Shared with the sub-tab flyout and every future canvas overlay, so the
        # things floating over the canvas cannot drift apart; the reasoning for
        # the roles lives on canvas_overlay_colour(). It is also the first of the
        # theme colours to be retired; see "Retire the old theming engine" in
        # DEFERRED_ITEMS.md for the other 44.
        self._bgcolor = canvas_overlay_colour()
        self.bgbrush = QtGui.QBrush(self._bgcolor)
        self.objbrush = QtGui.QBrush(globals_.theme.color('overview_object'))
        self.viewbrush = QtGui.QBrush(globals_.theme.color('overview_zone_fill'))
        self.view = QtCore.QRectF()
        self.spritebrush = QtGui.QBrush(globals_.theme.color('overview_sprite'))
        self.entrancebrush = QtGui.QBrush(globals_.theme.color('overview_entrance'))
        self.locationbrush = QtGui.QBrush(globals_.theme.color('overview_location_fill'))
        self.pathbrush = QtGui.QBrush(globals_.theme.color('overview_path'))

        self.Reset()

        # The white rectangle showing where the canvas is looking. These four
        # were plain attributes fed by whichever view's scrollbars last fired,
        # so with tabs open every area drew the same rectangle - the position of
        # whichever one was scrolled most recently (Zement, 2026-08-29).
        #
        # They are properties now, derived from the ACTIVE view rather than
        # stored: every session's view already knows its own scroll position and
        # size, so reading it cannot go stale, and there is no fifth copy of the
        # state to keep in step. The setters are kept because XScrollChange and
        # friends still assign them, and they write the fallback used before any
        # view exists.
        self._xposlocator = 0
        self._yposlocator = 0
        self._hlocator = 50
        self._wlocator = 80
        self.mainWindowScale = 1

    @staticmethod
    def _mappedBounds(item, transform):
        """An item's scene rect through ``transform``, or None if it is dead.

        An area keeps its own lists - Area.zones, .locations, each path's nodes
        - and those outlive the scene the items were in, so an item whose
        session has been closed is still in the list while its C++ object is
        not. Touching one raises RuntimeError.

        That matters more here than almost anywhere: this runs from paintEvent,
        and an exception in a paint handler is what the D-b.4 unbreakable loop
        was made of - the error box's nested event loop repaints, which raises
        again. Zement's host log for 2026-08-29 shows exactly that, starting
        from a ZoneItem in CalcSize.
        """
        try:
            return transform.mapRect(item.sceneBoundingRect())
        except RuntimeError:
            return None

    def setBackgroundAlpha(self, alpha):
        """Set how opaque this widget's own background is (Block D-c).

        The overlay frame paints a translucent background, but this widget then
        fills its whole rect before drawing the level - so without matching the
        alpha here the frame's transparency would be entirely hidden behind an
        opaque overview. Only the background: the level drawing itself stays at
        full strength, which is the point of fading the background at all.
        """
        colour = QtGui.QColor(self._bgcolor)
        colour.setAlpha(max(0, min(255, int(alpha))))
        self.bgbrush = QtGui.QBrush(colour)
        self.update()

    def _activeView(self):
        """The view the locator should describe, or None."""
        window = getattr(globals_, 'mainWindow', None)
        return getattr(window, 'view', None) if window is not None else None

    @property
    def Xposlocator(self):
        view = self._activeView()
        if view is None:
            return self._xposlocator
        try:
            return view.XScrollBar.value()
        except RuntimeError:
            # The view was destroyed with its session; fall back rather than
            # take a repaint down.
            return self._xposlocator

    @Xposlocator.setter
    def Xposlocator(self, value):
        self._xposlocator = value

    @property
    def Yposlocator(self):
        view = self._activeView()
        if view is None:
            return self._yposlocator
        try:
            return view.YScrollBar.value()
        except RuntimeError:
            return self._yposlocator

    @Yposlocator.setter
    def Yposlocator(self, value):
        self._yposlocator = value

    @property
    def Wlocator(self):
        view = self._activeView()
        if view is None:
            return self._wlocator
        try:
            return view.viewport().width()
        except RuntimeError:
            return self._wlocator

    @Wlocator.setter
    def Wlocator(self, value):
        self._wlocator = value

    @property
    def Hlocator(self):
        view = self._activeView()
        if view is None:
            return self._hlocator
        try:
            return view.viewport().height()
        except RuntimeError:
            return self._hlocator

    @Hlocator.setter
    def Hlocator(self, value):
        self._hlocator = value

    def Reset(self):
        """
        Resets the max and scale variables
        """
        self.maxX = 100
        self.maxY = 40
        self.Rescale()

    def mouseMoveEvent(self, event):
        """
        Handles mouse movement over the widget
        """
        QtWidgets.QWidget.mouseMoveEvent(self, event)

        if event.buttons() == QtCore.Qt.MouseButton.LeftButton:
            self.moveIt.emit(event.pos().x() * self.posmult, event.pos().y() * self.posmult)

    def mousePressEvent(self, event):
        """
        Handles mouse pressing events over the widget
        """
        QtWidgets.QWidget.mousePressEvent(self, event)

        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.moveIt.emit(event.pos().x() * self.posmult, event.pos().y() * self.posmult)

    def paintEvent(self, event):
        """
        Paints the level overview widget
        """
        if not getattr(globals_.Area, '_is_loaded', False):
            # Fixes a race where this widget is painted after the level is
            # created but before it is loaded.
            #
            # Tested on _is_loaded rather than on any single attribute, because
            # the attributes appear one at a time. Area.unload() deletes layers,
            # sprites, entrances, locations and paths; Area.load() restores
            # layers first and sprites nine lines later, so 'layers exists' does
            # not mean 'sprites exists' - and CalcSize reads all five.
            #
            # It is reachable rather than theoretical: loadNewGameDef() drives a
            # QProgressDialog, whose setValue() pumps the event loop, and a
            # patch switch reloads four tilesets inside that window. Zement's
            # client logged this ~50 times during a patch download.
            return

        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        self.CalcSize()
        self.Rescale()

        painter.fillRect(event.rect(), self.bgbrush)
        painter.scale(self.scale, self.scale)

        transform = QtGui.QTransform() / 24

        dr = painter.drawRect
        fr = painter.fillRect

        b = self.viewbrush
        painter.setPen(QtGui.QPen(globals_.theme.color('overview_zone_lines'), 1))

        for zone in globals_.Area.zones:
            rect = self._mappedBounds(zone, transform)
            if rect is None:
                continue
            fr(rect, b)
            dr(rect)

        b = self.objbrush

        for layer in globals_.Area.layers:
            for obj in layer:
                fr(obj.LevelRect, b)

        b = self.spritebrush

        for sprite in globals_.Area.sprites:
            fr(sprite.LevelRect, b)

        b = self.entrancebrush

        for ent in globals_.Area.entrances:
            fr(ent.LevelRect, b)

        b = self.locationbrush
        painter.setPen(QtGui.QPen(globals_.theme.color('overview_location_lines'), 1))

        for location in globals_.Area.locations:
            rect = self._mappedBounds(location, transform)
            if rect is None:
                continue
            fr(rect, b)
            dr(rect)

        b = self.pathbrush

        for path in globals_.Area.paths:
            for node in path._nodes:
                rect = self._mappedBounds(node, transform)
                if rect is not None:
                    fr(rect, b)

            # TODO: Draw the path lines

        painter.setPen(QtGui.QPen(globals_.theme.color('overview_viewbox'), 1))

        # The rectangle showing where the canvas is looking.
        #
        # Deliberately NOT clipped to the level extent. A first attempt at the
        # empty-level bug clipped it there, which broke the working case badly:
        # the rectangle is free to sit anywhere the canvas can scroll to, which
        # is well outside the bounding box of the placed items, so clipping made
        # it shrink to nothing as it moved and refuse to pass the last object
        # (Zement, 2026-08-29). The empty-level case is fixed in CalcSize, where
        # it belongs - by giving an empty level a real extent instead of zero.
        scalar = 1 / (24 * self.mainWindowScale)
        painter.drawRect(QtCore.QRectF(
            scalar * self.Xposlocator, scalar * self.Yposlocator,
            scalar * self.Wlocator, scalar * self.Hlocator
        ))

        self._paintPeerViews(painter)

    def setPeerViews(self, views):
        """
        The rectangles other collaborators are looking at.

        `views` is [{'x', 'y', 'w', 'h', 'color', 'nick'}] in scene
        coordinates. Held as plain data rather than as widget state, so the
        overview needs to know nothing about sessions and simply draws what it
        was last given.
        """
        self._peer_views = list(views or ())
        self.update()

    def _paintPeerViews(self, painter):
        """
        Draws each collaborator's viewport in their own colour.

        Dashed, so a peer's rectangle is never mistaken for your own solid one
        even when the two overlap almost exactly - which is the normal case
        when two people are working on the same part of a level.

        Drawn twice: a white dashed rectangle just outside, then the peer's
        colour just inside it. The overview is a dense, mostly-pale picture of
        the level, and a single thin coloured line disappeared into it. The
        white outline gives the colour something constant to sit against
        whatever it happens to cross, which a heavier line would not - that
        would only cover more of the map.
        """
        views = getattr(self, '_peer_views', None)
        if not views:
            return

        # The pen is not scaled by the painter's transform, so the two outlines
        # are one *device* pixel apart at any zoom. In overview units that is
        # 1/scale, which is what keeps them adjacent rather than overlapping.
        offset = 1.0 / self.scale if self.scale else 1.0

        # The same 1/24 scene-to-overview conversion the local box uses, but
        # without mainWindowScale: a peer's rectangle already arrives in scene
        # coordinates, so their zoom is baked in.
        for view in views:
            try:
                rect = QtCore.QRectF(
                    view['x'] / 24.0, view['y'] / 24.0,
                    view['w'] / 24.0, view['h'] / 24.0)
            except (KeyError, TypeError, ZeroDivisionError):
                continue

            if rect.width() <= 0 or rect.height() <= 0:
                continue

            color = QtGui.QColor(str(view.get('color') or ''))
            if not color.isValid():
                color = QtGui.QColor('#3daee9')

            painter.setPen(QtGui.QPen(QtGui.QColor('#ffffff'), 1,
                                      QtCore.Qt.PenStyle.DashLine))
            painter.drawRect(rect.adjusted(-offset, -offset, offset, offset))

            painter.setPen(QtGui.QPen(color, 1, QtCore.Qt.PenStyle.DashLine))
            painter.drawRect(rect)

    def CalcSize(self):
        """
        Calculates self.maxX and self.maxY.
        """
        if globals_.Area is None:
            # fixes race condition where this widget's size is calculated
            # after the level is created, but before it's loaded
            self.maxX = 100
            self.maxY = 40
            return

        transform = QtGui.QTransform() / 24
        rect = QtCore.QRectF()

        for zone in globals_.Area.zones:
            mapped = self._mappedBounds(zone, transform)
            if mapped is not None:
                rect |= mapped

        for layer in globals_.Area.layers:
            for obj in layer:
                rect |= obj.LevelRect

        for sprite in globals_.Area.sprites:
            rect |= sprite.LevelRect

        for ent in globals_.Area.entrances:
            rect |= ent.LevelRect

        for location in globals_.Area.locations:
            mapped = self._mappedBounds(location, transform)
            if mapped is not None:
                rect |= mapped

        for path in globals_.Area.paths:
            for node in path._nodes:
                rect |= node.LevelRect

        if rect.isNull():
            # Nothing placed yet, so there is no level geometry to measure. The
            # old code left maxX/maxY at 0 here, which made Rescale divide the
            # widget width by 45 - an enormous scale - and the viewport
            # rectangle then drew far larger than the widget holding it. Zement
            # reports this has been so since the Reggie 1.0 days.
            #
            # A default the size of one screen of level gives an empty canvas
            # the same proportions a level with one object in the corner has,
            # which is what it should look like.
            self.maxX = 100
            self.maxY = 40
            return

        _, _, self.maxX, self.maxY = rect.getCoords()

    def Rescale(self):
        """
        Calculates self.scale and self.posmult.
        """
        x_scale = self.width() / (self.maxX + 45)
        y_scale = self.height() / (self.maxY + 25)

        self.scale = max(0.002, min(x_scale, y_scale))
        self.posmult = 24 / self.scale


class ObjectPickerWidget(QtWidgets.QListView):
    """
    Widget that shows a list of available objects
    """

    def __init__(self):
        """
        Initializes the widget
        """
        QtWidgets.QListView.__init__(self)
        self.setFlow(QtWidgets.QListView.Flow.LeftToRight)
        self.setLayoutMode(QtWidgets.QListView.LayoutMode.SinglePass)
        self.setMovement(QtWidgets.QListView.Movement.Static)
        self.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.setWrapping(True)

        self.models = [
            ObjectPickerWidget.ObjectListModel(),
            ObjectPickerWidget.ObjectListModel(),
            ObjectPickerWidget.ObjectListModel(),
            ObjectPickerWidget.ObjectListModel(),
        ]

        self.setModel(self.models[0])

        self.setItemDelegate(ObjectPickerWidget.ObjectItemDelegate())

        self.clicked.connect(self.HandleObjReplace)

    def LoadFromTilesets(self):
        """
        Renders all the object previews
        """
        for i in range(4):
            self.models[i].LoadFromTileset(i)

    def ShowTileset(self, id_):
        """
        Shows a specific tileset in the picker
        """
        sel = self.currentIndex().row()
        self.setModel(self.models[id_])
        self.setCurrentIndex(self.model().index(sel, 0, QtCore.QModelIndex()))

    def currentChanged(self, current, previous):
        """
        Throws a signal when the selected object changed
        """
        self.ObjChanged.emit(current.row())

    def HandleObjReplace(self, index):
        """
        Throws a signal when the selected object is used as a replacement
        """
        if QtWidgets.QApplication.keyboardModifiers() == QtCore.Qt.KeyboardModifier.AltModifier:
            self.ObjReplace.emit(index.row())

    ObjChanged = QtCore.pyqtSignal(int)
    ObjReplace = QtCore.pyqtSignal(int)

    class ObjectItemDelegate(QtWidgets.QAbstractItemDelegate):
        """
        Handles tileset objects and their rendering
        """

        def __init__(self):
            """
            Initializes the delegate
            """
            QtWidgets.QAbstractItemDelegate.__init__(self)

        def paint(self, painter, option, index):
            """
            Paints an object
            """
            if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())

            p = index.model().data(index, QtCore.Qt.ItemDataRole.DecorationRole)
            painter.drawPixmap(option.rect.x() + 2, option.rect.y() + 2, p)
            # painter.drawText(option.rect, str(index.row()))

        def sizeHint(self, option, index):
            """
            Returns the size for the object
            """
            p = index.model().data(index, QtCore.Qt.ItemDataRole.UserRole)
            return p
            # return QtCore.QSize(76,76)

    class ObjectListModel(QtCore.QAbstractListModel):
        """
        Model containing all the objects in a tileset
        """

        def __init__(self):
            """
            Initializes the model
            """
            self.items = []
            self.ritems = []
            self.itemsize = []
            QtCore.QAbstractListModel.__init__(self)

            # for i in range(256):
            #    self.items.append(None)
            #    self.ritems.append(None)

        def rowCount(self, parent=None):
            """
            Required by Qt
            """
            return len(self.items)

        def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
            """
            Get what we have for a specific row
            """
            if not index.isValid(): return None
            n = index.row()
            if n < 0: return None
            if n >= len(self.items): return None

            if role == QtCore.Qt.ItemDataRole.DecorationRole:
                return self.ritems[n]

            if role == QtCore.Qt.ItemDataRole.BackgroundRole:
                return QtWidgets.QApplication.instance().palette().base()

            if role == QtCore.Qt.ItemDataRole.UserRole:
                return self.itemsize[n]

            if role == QtCore.Qt.ItemDataRole.ToolTipRole:
                return self.tooltips[n]

            return None

        def LoadFromTileset(self, idx):
            """
            Renders all the object previews for the model
            """
            if globals_.ObjectDefinitions[idx] is None: return

            self.beginResetModel()

            self.items = []
            self.ritems = []
            self.itemsize = []
            self.tooltips = []
            defs = globals_.ObjectDefinitions[idx]

            for i in range(256):
                if defs[i] is None: break
                obj = RenderObject(idx, i, defs[i].width, defs[i].height, True)
                self.items.append(obj)

                pm = QtGui.QPixmap(defs[i].width * 24, defs[i].height * 24)
                pm.fill(QtCore.Qt.GlobalColor.transparent)
                p = QtGui.QPainter()
                p.begin(pm)
                y = 0
                isAnim = False

                for row in obj:
                    x = 0
                    for tile_num in row:
                        if tile_num > 0:
                            tile = globals_.Tiles[tile_num]
                            if tile is None:
                                p.drawPixmap(x, y, globals_.Overrides[globals_.OVERRIDE_UNKNOWN].getCurrentTile())
                            elif isinstance(tile.main, QtGui.QImage):
                                p.drawImage(x, y, tile.main)
                            else:
                                p.drawPixmap(x, y, tile.main)

                            if isinstance(tile, TilesetTile) and tile.isAnimated: isAnim = True
                        x += 24
                    y += 24
                p.end()

                self.ritems.append(pm)
                self.itemsize.append(QtCore.QSize(defs[i].width * 24 + 4, defs[i].height * 24 + 4))
                # `or ()` because ObjDesc starts as None and only one code path
                # fills it (LoadGameDef). An abort there - the user cancelling
                # the "pick a Stage folder" prompt at boot - used to leave it
                # None and crash here with "argument of type 'NoneType' is not
                # iterable", before the window existed. LoadGameDef now loads it
                # before that prompt; this is the belt to that braces, and costs
                # a tooltip rather than the editor.
                if (idx == 0) and (i in (globals_.ObjDesc or ())):
                    if isAnim:
                        self.tooltips.append(globals_.trans.string('Objects', 4, '[id]', i, '[desc]', globals_.ObjDesc[i]))
                    else:
                        self.tooltips.append(globals_.trans.string('Objects', 3, '[id]', i, '[desc]', globals_.ObjDesc[i]))
                elif isAnim:
                    self.tooltips.append(globals_.trans.string('Objects', 2, '[id]', i))
                else:
                    self.tooltips.append(globals_.trans.string('Objects', 1, '[id]', i))

            self.endResetModel()


class StampChooserWidget(QtWidgets.QListView):
    """
    Widget that shows a list of available stamps
    """
    selectionChangedSignal = QtCore.pyqtSignal()

    def __init__(self):
        """
        Initializes the widget
        """
        QtWidgets.QListView.__init__(self)

        self.setFlow(QtWidgets.QListView.Flow.LeftToRight)
        self.setLayoutMode(QtWidgets.QListView.LayoutMode.SinglePass)
        self.setMovement(QtWidgets.QListView.Movement.Static)
        self.setResizeMode(QtWidgets.QListView.ResizeMode.Adjust)
        self.setWrapping(True)

        self.model = StampListModel()
        self.setModel(self.model)

        self.setItemDelegate(StampChooserWidget.StampItemDelegate())

    class StampItemDelegate(QtWidgets.QStyledItemDelegate):
        """
        Handles stamp rendering
        """

        def __init__(self):
            """
            Initializes the delegate
            """
            QtWidgets.QStyledItemDelegate.__init__(self)

        def createEditor(self, parent, option, index):
            """
            Creates a stamp name editor
            """
            return QtWidgets.QLineEdit(parent)

        def setEditorData(self, editor, index):
            """
            Sets the data for the stamp name editor from the data at index
            """
            editor.setText(index.model().data(index, QtCore.Qt.ItemDataRole.UserRole + 1))

        def setModelData(self, editor, model, index):
            """
            Set the data in the model for the data at index
            """
            index.model().setData(index, editor.text())

        def paint(self, painter, option, index):
            """
            Paints a stamp
            """

            if option.state & QtWidgets.QStyle.StateFlag.State_Selected:
                painter.fillRect(option.rect, option.palette.highlight())

            painter.drawPixmap(option.rect.x() + 2, option.rect.y() + 2, index.model().data(index, QtCore.Qt.ItemDataRole.DecorationRole))

        def sizeHint(self, option, index):
            """
            Returns the size for the stamp
            """
            return index.model().data(index, QtCore.Qt.ItemDataRole.DecorationRole).size() + QtCore.QSize(4, 4)

    def addStamp(self, stamp):
        """
        Adds a stamp
        """
        self.model.addStamp(stamp)

    def removeStamp(self, stamp):
        """
        Removes a stamp
        """
        self.model.removeStamp(stamp)

    def currentlySelectedStamp(self):
        """
        Returns the currently selected stamp
        """
        idxobj = self.currentIndex()
        if idxobj.row() == -1: return
        return self.model.items[idxobj.row()]

    def selectionChanged(self, selected, deselected):
        """
        Called when the selection changes.
        """
        val = super().selectionChanged(selected, deselected)
        self.selectionChangedSignal.emit()
        return val


class StampListModel(QtCore.QAbstractListModel):
    """
    Model containing all the stamps
    """

    def __init__(self):
        """
        Initializes the model
        """
        QtCore.QAbstractListModel.__init__(self)

        self.items = []  # list of Stamp objects

    def rowCount(self, parent=None):
        """
        Required by Qt
        """
        return len(self.items)

    def data(self, index, role=QtCore.Qt.ItemDataRole.DisplayRole):
        """
        Get what we have for a specific row
        """
        if not index.isValid(): return None
        n = index.row()
        if n < 0: return None
        if n >= len(self.items): return None

        if role == QtCore.Qt.ItemDataRole.DecorationRole:
            return self.items[n].Icon

        elif role == QtCore.Qt.ItemDataRole.BackgroundRole:
            return QtWidgets.QApplication.instance().palette().base()

        elif role == QtCore.Qt.ItemDataRole.UserRole:
            return self.items[n].Name

        elif role == QtCore.Qt.ItemDataRole.StatusTipRole:
            return self.items[n].Name

        else:
            return None

    def setData(self, index, value, role=QtCore.Qt.ItemDataRole.DisplayRole):
        """
        Set data for a specific row
        """
        if not index.isValid(): return None
        n = index.row()
        if n < 0: return None
        if n >= len(self.items): return None

        if role == QtCore.Qt.ItemDataRole.UserRole:
            self.items[n].Name = value

    def addStamp(self, stamp):
        """
        Adds a stamp
        """

        # Start resetting
        self.beginResetModel()

        # Add the stamp to self.items
        self.items.append(stamp)

        # Finish resetting
        self.endResetModel()

    def removeStamp(self, stamp):
        """
        Removes a stamp
        """

        # Start resetting
        self.beginResetModel()

        # Remove the stamp from self.items
        self.items.remove(stamp)

        # Finish resetting
        self.endResetModel()


class Stamp:
    """
    Class that represents a stamp in the list
    """

    def __init__(self, ReggieClip=None, Name=''):
        """
        Initializes the stamp
        """

        self.ReggieClip = ReggieClip
        self.Name = Name
        self.Icon = self.render()

    def renderPreview(self):
        """
        Renders the stamp preview
        """

        minX, minY, maxX, maxY = 24576, 12288, 0, 0

        layers, sprites = globals_.mainWindow.getEncodedObjects(self.ReggieClip)

        # Go through the sprites and find the maxs and mins
        for spr in sprites:

            br = spr.getFullRect()

            x1 = br.topLeft().x()
            y1 = br.topLeft().y()
            x2 = x1 + br.width()
            y2 = y1 + br.height()

            if x1 < minX: minX = x1
            if x2 > maxX: maxX = x2
            if y1 < minY: minY = y1
            if y2 > maxY: maxY = y2

        # Go through the objects and find the maxs and mins
        for layer in layers:
            for obj in layer:
                x1 = (obj.objx * 24)
                x2 = x1 + (obj.width * 24)
                y1 = (obj.objy * 24)
                y2 = y1 + (obj.height * 24)

                if x1 < minX: minX = x1
                if x2 > maxX: maxX = x2
                if y1 < minY: minY = y1
                if y2 > maxY: maxY = y2

        # Calculate offset amounts (snap to 24x24 increments)
        offsetX = int(minX // 24) * 24
        offsetY = int(minY // 24) * 24
        drawOffsetX = offsetX - minX
        drawOffsetY = offsetY - minY

        # Go through the things again and shift them by the offset amount
        for spr in sprites:
            spr.objx -= offsetX / 1.5
            spr.objy -= offsetY / 1.5
        for layer in layers:
            for obj in layer:
                obj.objx -= offsetX // 24
                obj.objy -= offsetY // 24

        # Calculate the required pixmap size
        pixmapSize = (maxX - minX, maxY - minY)

        # Create the pixmap, and a painter
        pix = QtGui.QPixmap(int(pixmapSize[0]), int(pixmapSize[1]))
        pix.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pix)
        painter.setRenderHint(painter.RenderHint.Antialiasing)

        # Paint all objects
        objw, objh = int(pixmapSize[0] // 24) + 1, int(pixmapSize[1] // 24) + 1
        for layer in reversed(layers):
            tmap = []
            for i in range(objh):
                tmap.append([-1] * objw)
            for obj in layer:
                startx = int(obj.objx)
                starty = int(obj.objy)

                desty = starty
                for row in obj.objdata:
                    destrow = tmap[desty]
                    destx = startx
                    for tile in row:
                        if tile > 0:
                            destrow[destx] = tile
                        destx += 1
                    desty += 1

                painter.save()
                desty = 0
                for row in tmap:
                    destx = 0
                    for tile in row:
                        if tile > 0:
                            if globals_.Tiles[tile] is None: continue
                            r = globals_.Tiles[tile].main
                            painter.drawPixmap(int(destx + drawOffsetX), int(desty + drawOffsetY), r)
                        destx += 24
                    desty += 24
                painter.restore()

        # Paint all sprites
        for spr in sprites:
            offx = ((spr.objx + spr.ImageObj.xOffset) * 1.5) + drawOffsetX
            offy = ((spr.objy + spr.ImageObj.yOffset) * 1.5) + drawOffsetY

            painter.save()
            painter.translate(offx, offy)

            spr.paint(painter, None, None, True)

            painter.restore()

            # Paint any auxiliary things
            for aux in spr.ImageObj.aux:
                painter.save()
                painter.translate(
                    offx + aux.x(),
                    offy + aux.y(),
                )

                aux.paint(painter, None, None)

                painter.restore()

        # End painting
        painter.end()
        del painter

        # Scale it
        maxW, maxH = 96, 96
        w, h = pix.width(), pix.height()
        if w > h and w > maxW:
            pix = pix.scaledToWidth(maxW)
        elif h > w and h > maxH:
            pix = pix.scaledToHeight(maxH)

        # Return it
        return pix

    def render(self):
        """
        Renders the stamp icon, preview AND text
        """

        # Get the preview icon
        prevIcon = self.renderPreview()

        # Calculate the total size of the icon
        textSize = self.calculateTextSize(self.Name)
        totalWidth = max(prevIcon.width(), textSize.width())
        totalHeight = prevIcon.height() + 2 + textSize.height()

        # Make a pixmap and painter
        pix = QtGui.QPixmap(int(totalWidth), int(totalHeight))
        pix.fill(QtCore.Qt.GlobalColor.transparent)
        painter = QtGui.QPainter(pix)

        # Draw the preview
        iconXOffset = (totalWidth - prevIcon.width()) / 2
        painter.drawPixmap(int(iconXOffset), 0, prevIcon)

        # Draw the text
        textRect = QtCore.QRectF(0, prevIcon.height() + 2, totalWidth, textSize.height())
        painter.setFont(QtGui.QFont())
        painter.setPen(QtCore.Qt.GlobalColor.gray)
        painter.drawText(textRect, QtCore.Qt.AlignmentFlag.AlignTop | QtCore.Qt.TextFlag.TextWordWrap, self.Name)

        # Return the pixmap
        return pix

    @staticmethod
    def calculateTextSize(text):
        """
        Calculates the size of text. Crops to 96 pixels wide.
        """
        fontMetrics = QtGui.QFontMetrics(QtGui.QFont())
        fontRect = fontMetrics.boundingRect(QtCore.QRect(0, 0, 96, 48), QtCore.Qt.TextFlag.TextWordWrap, text)
        w, h = fontRect.width(), fontRect.height()
        return QtCore.QSizeF(min(w, 96), h)

    def update(self):
        """
        Updates the stamp icon
        """
        self.Icon = self.render()


class SpritePickerWidget(QtWidgets.QTreeWidget):
    """
    Widget that shows a list of available sprites
    """

    # Signal emitted with (current, total) during batch loading; total=-1 means done
    loadingProgress = QtCore.pyqtSignal(int, int)

    def __init__(self):
        """
        Initializes the widget
        """
        super().__init__()
        self.setColumnCount(1)
        self.setHeaderHidden(True)
        self.setIndentation(16)
        self.currentItemChanged.connect(self.HandleItemChange)
        
        # Set icon size for sprite images
        self.setIconSize(QtCore.QSize(48, 48))

        # Load setting for showing sprite images
        self.show_sprite_images = setting('ShowSpriteListImages', False)

        # Batch loading state
        self._batch_queue = []      # list of (item, sprite_id) pending render
        self._batch_timer = QtCore.QTimer(self)
        self._batch_timer.setInterval(0)  # fire as fast as possible between events
        self._batch_timer.timeout.connect(self._processBatch)
        self._batch_total = 0

        LoadSpriteData()
        LoadSpriteListData()
        LoadSpriteCategories()
        self.LoadItems()

    def UpdateSpriteNames(self):
        """
        Updates all spritenames
        """
        for viewname, view, nodelist in globals_.SpriteCategories:
            for cnode in nodelist:
                for i in range(cnode.childCount()):
                    snode = cnode.child(i)

                    if snode == self.NoSpritesFound:
                        # Don't change the name of the "no sprites found" marker
                        continue

                    id_ = snode.data(0, QtCore.Qt.ItemDataRole.UserRole)

                    if 0 <= id_ < globals_.NumSprites and globals_.Sprites[id_] is not None:
                        sdef = globals_.Sprites[id_]
                    else:
                        sdef = None

                    if sdef is None:
                        name = 'UNKNOWN'
                    else:
                        name = sdef.name

                    snode.setText(0, globals_.trans.string('Sprites', 18, '[id]', id_, '[name]', name))

    def LoadItems(self):
        """
        Loads tree widget items
        """
        self.clear()

        for viewname, view, nodelist in globals_.SpriteCategories:
            for n in nodelist: nodelist.remove(n)
            for catname, category in view:
                cnode = QtWidgets.QTreeWidgetItem()
                cnode.setText(0, catname)
                cnode.setData(0, QtCore.Qt.ItemDataRole.UserRole, -1)

                isSearch = (catname == globals_.trans.string('Sprites', 16))
                if isSearch:
                    self.SearchResultsCategory = cnode
                    SearchableItems = []

                for id_ in category:
                    snode = QtWidgets.QTreeWidgetItem()
                    if id_ == 9999:
                        snode.setText(0, globals_.trans.string('Sprites', 17))
                        snode.setData(0, QtCore.Qt.ItemDataRole.UserRole, -2)
                        self.NoSpritesFound = snode
                    else:
                        if 0 <= id_ < globals_.NumSprites and globals_.Sprites[id_] is not None:
                            sdef = globals_.Sprites[id_]
                        else:
                            sdef = None

                        if sdef is None:
                            sname = "UNKNOWN"
                        else:
                            sname = sdef.name

                        snode.setText(0, globals_.trans.string('Sprites', 18, '[id]', id_, '[name]', sname))
                        snode.setData(0, QtCore.Qt.ItemDataRole.UserRole, id_)

                    if isSearch:
                        SearchableItems.append(snode)

                    cnode.addChild(snode)

                self.addTopLevelItem(cnode)
                cnode.setHidden(True)
                nodelist.append(cnode)

        self.ShownSearchResults = SearchableItems
        self.NoSpritesFound.setHidden(True)

        self.itemClicked.connect(self.HandleSprReplace)

        self.SwitchView(globals_.SpriteCategories[0])
        
        # Connect to itemExpanded signal to render search results when expanded
        self.itemExpanded.connect(self.onItemExpanded)

    def clearAllIcons(self):
        """
        Removes sprite icons from every item in the tree.
        """
        null_icon = QtGui.QIcon()
        def clearRecursive(item):
            item.setIcon(0, null_icon)
            for i in range(item.childCount()):
                clearRecursive(item.child(i))
        for i in range(self.topLevelItemCount()):
            clearRecursive(self.topLevelItem(i))

    def _collectVisibleItems(self):
        """
        Returns a list of (item, sprite_id) for all visible sprite items.
        """
        result = []
        def collectRecursive(item):
            sprite_id = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if sprite_id is not None and sprite_id >= 0:
                result.append((item, sprite_id))
            for i in range(item.childCount()):
                collectRecursive(item.child(i))
        for i in range(self.topLevelItemCount()):
            top = self.topLevelItem(i)
            if not top.isHidden():
                collectRecursive(top)
        return result

    def _startBatchQueue(self, items):
        """
        Starts (or restarts) the batch rendering queue with the given list of
        (item, sprite_id) pairs. Emits loadingProgress signals as work proceeds.
        """
        # Cancel any in-progress batch
        self._batch_timer.stop()
        self._batch_queue = list(items)
        self._batch_total = len(self._batch_queue)
        if self._batch_total == 0:
            self.loadingProgress.emit(0, -1)
            return
        self.loadingProgress.emit(0, self._batch_total)
        self._batch_timer.start()

    def _processBatch(self):
        """
        Processes a small batch of sprite renders per timer tick to keep the UI responsive.
        """
        BATCH_SIZE = 5
        if not self._batch_queue:
            self._batch_timer.stop()
            self.loadingProgress.emit(self._batch_total, -1)
            return

        for _ in range(BATCH_SIZE):
            if not self._batch_queue:
                break
            item, sprite_id = self._batch_queue.pop(0)
            self.updateSpriteImageForItem(item, sprite_id)

        done = self._batch_total - len(self._batch_queue)
        if self._batch_queue:
            self.loadingProgress.emit(done, self._batch_total)
        else:
            self._batch_timer.stop()
            self.loadingProgress.emit(self._batch_total, -1)

    def SwitchView(self, view):
        """
        Changes the selected sprite view
        """
        for i in range(self.topLevelItemCount()):
            self.topLevelItem(i).setHidden(True)

        for node in view[2]:
            node.setHidden(False)
        
        # Queue images for newly visible items (only if scene is ready)
        if self.show_sprite_images:
            from reggie.core import spritelib as SLib
            if SLib.Tiles and not all(tile is None for tile in SLib.Tiles):
                self._startBatchQueue(self._collectVisibleItems())
    
    def updateItemsInCategory(self, category_item):
        """
        Updates sprite images for all items in a category
        """
        items = []
        for i in range(category_item.childCount()):
            item = category_item.child(i)
            sprite_id = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if sprite_id is not None and sprite_id >= 0:
                items.append((item, sprite_id))
        self._startBatchQueue(items)

    def HandleItemChange(self, current, previous):
        """
        Throws a signal when the selected object changed
        """
        if current is None: return
        id_ = current.data(0, QtCore.Qt.ItemDataRole.UserRole)
        if id_ != -1:
            self.SpriteChanged.emit(id_)

    def SetSearchString(self, searchfor):
        """
        Shows the items containing that string
        """
        check = self.SearchResultsCategory

        rawresults = self.findItems(searchfor, QtCore.Qt.MatchFlag.MatchContains | QtCore.Qt.MatchFlag.MatchRecursive)
        results = list(filter((lambda x: x.parent() == check), rawresults))

        for x in self.ShownSearchResults: x.setHidden(True)
        for x in results: x.setHidden(False)
        self.ShownSearchResults = results

        self.NoSpritesFound.setHidden(bool(results))
        self.SearchResultsCategory.setExpanded(True)

    def onItemExpanded(self, item):
        """
        Called when a tree item is expanded - render images for that category
        """
        if not self.show_sprite_images:
            return
        
        from reggie.core import spritelib as SLib
        if not (SLib.Tiles and not all(tile is None for tile in SLib.Tiles)):
            return

        # Only render if it's the search results category
        if hasattr(self, 'SearchResultsCategory') and item == self.SearchResultsCategory:
            self.updateItemsInCategory(item)

    def HandleSprReplace(self, item, column):
        """
        Throws a signal when the selected sprite is used as a replacement
        """
        if QtWidgets.QApplication.keyboardModifiers() == QtCore.Qt.KeyboardModifier.AltModifier:
            id_ = item.data(0, QtCore.Qt.ItemDataRole.UserRole)
            if id_ != -1:
                self.SpriteReplace.emit(id_)

    def toggleSpriteImages(self, state):
        """
        Toggles the display of sprite images in the list
        """
        # state is 0 (unchecked) or 2 (checked) from stateChanged signal
        self.show_sprite_images = state == 2
        setSetting('ShowSpriteListImages', self.show_sprite_images)

        if not self.show_sprite_images:
            # Cancel any pending batch and remove all icons
            self._batch_timer.stop()
            self._batch_queue = []
            self.loadingProgress.emit(0, -1)
            self.clearAllIcons()
            return

        # Load images: only if scene is ready (tiles loaded)
        from reggie.core import spritelib as SLib
        if SLib.Tiles and not all(tile is None for tile in SLib.Tiles):
            self._startBatchQueue(self._collectVisibleItems())

    def updateSpriteImageForItem(self, item, sprite_id):
        """
        Updates the sprite image for a specific tree item.
        Uses a temporary scene to avoid artifacts on the main canvas.
        """
        if not self.show_sprite_images:
            return
        
        try:
            from reggie.core.levelitems import SpriteItem
            from reggie.core.raw_data import RawData
            
            if globals_.Area is None:
                return
            
            temp_sprite = None
            temp_scene = None
            try:
                temp_data = RawData(b'\x00\x00\x00\x00\x00\x00\x00\x00', format=RawData.Format.Vanilla)
                temp_sprite = SpriteItem(sprite_id, 0, 0, temp_data)
            except:
                return
            
            try:
                # Use a temporary scene instead of the main scene to avoid rendering artifacts
                temp_scene = QtWidgets.QGraphicsScene()
                temp_scene.addItem(temp_sprite)
            except:
                return
            
            img = None
            try:
                # Render from the temporary scene, not the main scene
                img = self._renderSpriteIcon(temp_sprite, temp_scene)
                if img is None:
                    return
            except:
                return
            finally:
                try:
                    if temp_sprite is not None and temp_scene is not None:
                        temp_scene.removeItem(temp_sprite)
                except:
                    pass
            
            background = QtGui.QPixmap(48, 48)
            background.fill(globals_.theme.color('bg'))
            
            scaled_img = img.scaled(
                48, 48,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation
            )
            
            scaled_pixmap = QtGui.QPixmap.fromImage(scaled_img)
            
            painter = QtGui.QPainter(background)
            try:
                x = (48 - scaled_pixmap.width()) // 2
                y = (48 - scaled_pixmap.height()) // 2
                painter.drawPixmap(x, y, scaled_pixmap)
            finally:
                painter.end()
            
            item.setIcon(0, QtGui.QIcon(background))
        except:
            pass

    def _renderSpriteIcon(self, sprite, scene):
        """
        Renders a sprite icon from a temporary scene.
        This avoids using the main scene which can cause zoom artifacts.
        """
        # Constants from renderInLevelIcon
        maxSize = QtCore.QSize(256, 256)
        marginPct = 0.08
        maxMargin = 96

        # Get the full bounding rectangle
        br = sprite.getFullRect()

        # Expand the rect to add extra margins
        marginX = br.width() * marginPct
        marginY = br.height() * marginPct
        marginX = min(marginX, maxMargin)
        marginY = min(marginY, maxMargin)
        br.setX(br.x() - marginX)
        br.setY(br.y() - marginY)
        br.setWidth(br.width() + marginX)
        br.setHeight(br.height() + marginY)

        # Take the screenshot from the temporary scene
        ScreenshotImage = QtGui.QImage(br.size().toSize(), QtGui.QImage.Format.Format_ARGB32)
        ScreenshotImage.fill(QtCore.Qt.GlobalColor.transparent)

        RenderPainter = QtGui.QPainter(ScreenshotImage)
        scene.render(
            RenderPainter,
            QtCore.QRectF(0, 0, br.width(), br.height()),
            br,
        )
        RenderPainter.end()

        # Shrink if too big
        final = ScreenshotImage
        if ScreenshotImage.width() > maxSize.width() or ScreenshotImage.height() > maxSize.height():
            final = ScreenshotImage.scaled(
                maxSize,
                QtCore.Qt.AspectRatioMode.KeepAspectRatio,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )

        return final

    SpriteChanged = QtCore.pyqtSignal(int)
    SpriteReplace = QtCore.pyqtSignal(int)


class SpriteList(QtWidgets.QWidget):
    """
    Sprite list viewer
    """

    # These are straight from the spritedata xml
    # Don't translate these
    idtypes = (
        "Star Set", "Rotation", "Two Way Line", "Water Ball", "Mushroom",
        "Group", "Bolt", "Target Event", "Triggering Event", "Collection",
        "Location", "Physics", "Message", "Path", "Path Movement", "Red Coin",
        "Hill", "Stretch", "Ray", "Coaster", "Bubble Cannon", "Burner",
        "Wiggling", "Panel", "Colony", "Entrance", "Path Node"
    )

    def __init__(self):
        super().__init__()

        self.searchbox = QtWidgets.QLineEdit()
        self.searchbox.textEdited.connect(self.search)

        self.filterbox = QtWidgets.QComboBox()
        self.filterbox.currentIndexChanged.connect(self.filter)

        self.is_batch_add = False

        # Set of row ids
        self.SearchResults = set()

        # A QTableWidget that also selects the current sprite when Space or
        # Enter/Return is pressed.
        class SpriteTableWidget(QtWidgets.QTableWidget):
            def keyPressEvent(self, event):
                if event.key() in (QtCore.Qt.Key.Key_Space, QtCore.Qt.Key.Key_Return, QtCore.Qt.Key.Key_Enter):
                    if self.currentItem() is not None:
                        SpriteList.moveToSprite(self.currentItem())

                super().keyPressEvent(event)

        self.table = SpriteTableWidget(0, len(globals_.trans.stringList('Sprites', 23)) + 1)
        headers = [globals_.trans.string('Sprites', 21), globals_.trans.string('Sprites', 22)] + list(globals_.trans.stringList('Sprites', 23)[1:])
        self.table.setHorizontalHeaderLabels(headers)
        self.table.verticalHeader().setVisible(False) # hide row numbers

        # A table claims Tab for "next cell", so it never reaches the focus
        # chain and Tab behaves like an arrow key. The rows are navigated with
        # the arrow keys here, so hand Tab back to the focus chain.
        self.table.setTabKeyNavigation(False)
        self.table.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeMode.Stretch)
        self.table.setSortingEnabled(True)
        self.table.setMouseTracking(True) # for 'entered' signal
        self.table.itemDoubleClicked.connect(self.moveToSprite)
        self.table.itemEntered.connect(self.toolTip)

        # populate filter box
        self.filterbox.addItems(globals_.trans.stringList('Sprites', 23))

        # Make a layout
        search_label = QtWidgets.QLabel(globals_.trans.string('Sprites', 19) + ":")
        filter_label = QtWidgets.QLabel(globals_.trans.string('Sprites', 20) + ":")

        layout = QtWidgets.QGridLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(search_label, 0, 0)
        layout.addWidget(self.searchbox, 0, 1)

        layout.addWidget(filter_label, 1, 0)
        layout.addWidget(self.filterbox, 1, 1)

        # colspan = 2, since we want the table to use both
        # columns
        layout.addWidget(self.table, 2, 0, 1, 2)

        self.setLayout(layout)

    def search(self, text):
        """
        Search the table
        """
        if text == "":
            # Optimisation for when no search is given -> show everything
            for row in range(self.table.rowCount()):
                self.table.setRowHidden(row, False)

            self.SearchResults = set(range(self.table.rowCount()))
            return

        results = self.table.findItems(text, QtCore.Qt.MatchFlag.MatchContains | QtCore.Qt.MatchFlag.MatchRecursive)
        rows = set(item.row() for item in results if item is not None)

        for row in range(self.table.rowCount()):
            self.table.setRowHidden(row, row not in rows)

        self.SearchResults = rows

    def filter(self, newidx):
        """
        Filters all search results
        """
        for row in self.SearchResults:
            self.filterRow(row, newidx)

        # Only show columns 0 (id), 1 (name) and newidx + 1 (the filtered column)
        for col in range(self.table.columnCount()):
            if col in (0, 1, newidx + 1):
                self.table.showColumn(col)
            else:
                self.table.hideColumn(col)

    def filterRow(self, row, filteridx = 0):
        """
        Filters one row of the table.
        """
        # Special case: no filtering
        if filteridx == 0:
            self.table.setRowHidden(row, False)
            return

        # Get the sprite defintion and the id type that is filtered by.
        filtertype = self.idtypes[filteridx - 1]
        sprite = self.table.item(row, 0).data(QtCore.Qt.ItemDataRole.UserRole)

        if 0 <= sprite.type < globals_.NumSprites and globals_.Sprites[sprite.type] is not None:
            sdef = globals_.Sprites[sprite.type]
        else:
            # No sprite definition -> hide
            self.table.setRowHidden(row, True)
            return

        # Loop over every field of the sprite and hide every row whose sprite
        # has no fields with the correct idtype.
        for field in sdef.fields:
            # Only values (1) and lists (2) have idtypes, so ignore the other
            # fields.
            if field[0] < 1 or field[0] > 2:
                continue

            # The idtype is the last element in the field tuple.
            if field[-2] == filtertype:
                self.table.setRowHidden(row, False)
                return

        # No field had the correct id type, so hide this row.
        self.table.setRowHidden(row, True)

    def updateItems(self):
        self.search(self.searchbox.text())
        self.filter(self.filterbox.currentIndex())

    def getRowFor(self, sprite):
        """
        Returns the row number for a given sprite, or -1 if no row exists.
        """
        for i in range(self.table.rowCount()):
            id_item = self.table.item(i, 0)
            if id_item.data(QtCore.Qt.ItemDataRole.UserRole) == sprite:
                return i

        return -1

    def prepareBatchAdd(self):
        """
        Disables sorting, because sorting every time a new element is added is
        pretty bad performance-wise. We'll sort them once afterwards.
        """
        self.is_batch_add = True
        self.table.setSortingEnabled(False)

    def endBatchAdd(self):
        """
        Re-enables sorting after a batch adding is finished.
        """
        self.is_batch_add = False
        self.table.resizeRowsToContents()
        self.table.setSortingEnabled(True)
        self.updateItems()

    def addSprite(self, sprite):
        """
        Adds a sprite to the table
        """
        if not self.is_batch_add:
            # temporarily disable sorting so our new row
            # gets added properly
            self.table.setSortingEnabled(False)

        # add a new row
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Add the sprite id
        id_item = QtWidgets.QTableWidgetItem()
        id_item.setData(QtCore.Qt.ItemDataRole.DisplayRole, sprite.type)
        id_item.setData(QtCore.Qt.ItemDataRole.UserRole, sprite)
        id_item.setFlags(id_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 0, id_item)

        # Also add the sprite name
        name_item = QtWidgets.QTableWidgetItem(sprite.name)
        name_item.setData(QtCore.Qt.ItemDataRole.UserRole, sprite)
        name_item.setFlags(name_item.flags() & ~QtCore.Qt.ItemFlag.ItemIsEditable)
        self.table.setItem(row, 1, name_item)

        if not self.is_batch_add:
            # Profiling shows that this function is quite expensive, so if we're
            # in a batch add, don't resize the rows until the very end.
            self.table.resizeRowsToContents()

        # Add an id for every idtype. These items should not be editable or
        # selectable.
        mask = ~(QtCore.Qt.ItemFlag.ItemIsEditable | QtCore.Qt.ItemFlag.ItemIsSelectable)
        ids = self.getIDsFor(sprite)

        for col, idtype in enumerate(self.idtypes):
            id_values = ids.get(idtype, "")

            if len(id_values) == 1:
                id_values = id_values[0]

            entry_item = QtWidgets.QTableWidgetItem(str(id_values))
            entry_item.setFlags(entry_item.flags() & mask)

            self.table.setItem(row, 2 + col, entry_item)

        # re-enable sorting
        if not self.is_batch_add:
            self.table.setSortingEnabled(True)
            self.updateItems()

    def updateSprite(self, sprite):
        """
        Updates the IDs of the given sprite
        """
        ids = self.getIDsFor(sprite)

        # Temporarily disable sorting so our updates happen to the same row.
        self.table.setSortingEnabled(False)
        row = self.getRowFor(sprite)

        # A sprite with no row here has nothing to update. getRowFor returns -1,
        # and table.item(-1, column) returns None, so the loop below would raise
        # AttributeError on setText - which is what a collaboration client saw
        # for every property edit before synced sprites were registered with
        # this table. Guarding here as well keeps a bookkeeping gap from turning
        # an edit into a traceback.
        if row < 0:
            self.table.setSortingEnabled(True)
            return

        # Skip the first columns (the id and name)
        for i in range(2, self.table.columnCount()):
            id_values = ids.get(self.idtypes[i - 2], [""])

            if len(id_values) == 1:
                id_values = id_values[0]

            item = self.table.item(row, i)
            if item is None:
                continue

            item.setText(str(id_values))

        # re-enable sorting
        self.table.setSortingEnabled(True)

    def takeSprite(self, sprite):
        """
        Removes a sprite from the table
        """
        row = self.getRowFor(sprite)

        if row < 0:
            return

        self.table.removeRow(row)

        # Update search results
        if row in self.SearchResults:
            self.SearchResults = set(x if x < row else x - 1 for x in self.SearchResults if x != row)

    def clear(self):
        """
        Clears the sprite list.
        """
        # Ensure all rows are removed. For some reason, just calling the
        # 'clearContents' method does not remove the underlying items, causing
        # way too many items to be searched after a few Area switches.
        for i in range(self.table.rowCount() - 1, -1, -1):
            self.table.removeRow(i)

        self.table.clearContents()
        self.searchbox.setText("")
        self.filterbox.setCurrentIndex(0)
        self.SearchResults = set()

    def toolTip(self, item):
        """
        Creates a tooltip for the item
        """
        sprite = item.data(QtCore.Qt.ItemDataRole.UserRole)

        if sprite is None:
            return

        img = sprite.renderInLevelIcon()
        byteArray = QtCore.QByteArray()
        buf = QtCore.QBuffer(byteArray)
        img.save(buf, 'PNG')
        byteObj = bytes(byteArray)
        b64 = base64.b64encode(byteObj).decode('utf-8')

        item.setToolTip(
            '<img src="data:image/png;base64,' + b64 + '" />'
        )

    # TODO: Consider moving this to the SpriteItem class
    @staticmethod
    def moveToSprite(item):
        """
        Moves the view to the sprite and selects it.
        """
        sprite = item.data(QtCore.Qt.ItemDataRole.UserRole)

        if sprite is None:
            return

        sprite.ensureVisible(xMargin=192, yMargin=192)
        sprite.scene().clearSelection()
        sprite.setSelected(True)

    @staticmethod
    def getIDsFor(sprite):
        """
        Returns an (idtype, [values]) dict for every
        idtype this sprite has
        """
        if not (0 <= sprite.type < globals_.NumSprites) or globals_.Sprites[sprite.type] is None:
            return {}

        sdef = globals_.Sprites[sprite.type]
        res = {}
        decoder = SpriteEditorWidget.PropertyDecoder()
        data = sprite.spritedata

        for field in sdef.fields:
            # Only values (1) and fields (2) have idtypes, so ignore all other
            # fields.
            if field[0] < 1 or field[0] > 2:
                continue

            # The idtype is the last element in the field tuple, bit is the
            # third element in the field tuple (for both list and value).
            idtype = field[-2]

            # No id type specified
            if idtype is None:
                continue

            value = decoder.retrieve(data, field[2])

            try:
                res[idtype].append(value)
            except KeyError:
                res[idtype] = [value]

        return res

    # Functions that are passed on to self.table
    def selectionModel(self):
        return self.table.selectionModel()

    def row(self, item):
        return self.table.row(item)
