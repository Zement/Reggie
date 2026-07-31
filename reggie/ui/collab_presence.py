"""
Drawing other people on the canvas (Block C - B1, phase 8).

One cursor per peer, and an optional flash where somebody clicked. Both are
QGraphicsItems in the level scene, so they pan and zoom with the level without
any coordinate bookkeeping here.

Two decisions worth stating, because both are easy to get wrong:

- **A cursor does not scale with the zoom.** ItemIgnoresTransformations keeps
  it the same size on screen at every zoom level, which is what a pointer
  should do; a cursor that grew with the level would swamp the canvas at high
  zoom and vanish at low.

- **Nothing here belongs to the level.** These items are never in Area's lists,
  never referenced by the ref map, and never reach the undo stack, so a peer's
  cursor cannot be selected, moved, saved or undone. They are removed wholesale
  when a session ends.

Theme: the label uses the palette's tooltip colours rather than fixed ones, so
it stays readable in both the light and dark Qt themes. The peer's own colour
is used only for the pointer and the label's border, where it identifies who is
who and is not being read as text.
"""

from PyQt6 import QtCore, QtGui, QtWidgets


# Above every level item. The highest in levelitems.py is a zone at 50000.
PRESENCE_Z = 60000

# How long a click flash stays visible, and how often it is redrawn while
# fading. 450 ms is long enough to notice without lingering over the canvas.
CLICK_FADE_MS = 450
CLICK_FRAME_MS = 40

# A cursor disappears if its owner stops sending. Comfortably longer than the
# presence send interval, so an idle peer does not flicker.
CURSOR_IDLE_MS = 8000


def _color(value, fallback='#3daee9'):
    """
    A QColor from a peer's colour string, falling back if it is unusable.

    The colour arrives over the network, so it is untrusted: an invalid string
    must not raise in the middle of a paint.
    """
    color = QtGui.QColor(str(value or ''))
    if not color.isValid():
        color = QtGui.QColor(fallback)
    return color


class PeerCursor(QtWidgets.QGraphicsItem):
    """
    One peer's pointer, with their nickname beside it.
    """

    def __init__(self, nick, color):
        super().__init__()
        self._nick = str(nick or '')
        self._color = _color(color)
        self._font = QtGui.QFont()
        self._font.setPointSize(8)

        self.setZValue(PRESENCE_Z)
        self.setFlag(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
            True)
        # Presence is decoration: it must never intercept a click meant for the
        # level, and it must never become the selection.
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
        self.setFlag(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        self._metrics = QtGui.QFontMetrics(self._font)
        self._recomputeBounds()

    def setNick(self, nick):
        nick = str(nick or '')
        if nick == self._nick:
            return
        self.prepareGeometryChange()
        self._nick = nick
        self._recomputeBounds()
        self.update()

    def setColor(self, color):
        self._color = _color(color)
        self.update()

    def _recomputeBounds(self):
        width = self._metrics.horizontalAdvance(self._nick) if self._nick else 0
        height = self._metrics.height()
        # The arrow occupies roughly 14x18 from the origin; the label sits to
        # its right with a small gap and its own padding.
        self._label_rect = QtCore.QRectF(16, 10, width + 8, height + 2)
        self._bounds = QtCore.QRectF(0, 0, 16, 20).united(
            self._label_rect).adjusted(-1, -1, 2, 2)

    def boundingRect(self):
        return self._bounds

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        # The arrow. Outlined in a contrasting colour so it stays visible over
        # both dark tilesets and light backgrounds.
        arrow = QtGui.QPolygonF([
            QtCore.QPointF(0, 0),
            QtCore.QPointF(0, 15),
            QtCore.QPointF(4, 11.5),
            QtCore.QPointF(6.5, 17),
            QtCore.QPointF(9, 16),
            QtCore.QPointF(6.5, 10.5),
            QtCore.QPointF(11, 10.5),
        ])
        painter.setPen(QtGui.QPen(QtGui.QColor(0, 0, 0, 160), 1))
        painter.setBrush(self._color)
        painter.drawPolygon(arrow)

        if not self._nick:
            return

        palette = QtWidgets.QApplication.palette()
        background = palette.toolTipBase().color()
        background.setAlpha(230)

        painter.setPen(QtGui.QPen(self._color, 1))
        painter.setBrush(background)
        painter.drawRoundedRect(self._label_rect, 3, 3)

        painter.setFont(self._font)
        painter.setPen(palette.toolTipText().color())
        painter.drawText(self._label_rect,
                         int(QtCore.Qt.AlignmentFlag.AlignCenter), self._nick)


class ClickFlash(QtWidgets.QGraphicsItem):
    """
    A ring that expands and fades where a peer clicked.

    Removes itself when the animation finishes, so nothing has to track it.
    """

    def __init__(self, color, on_finished=None):
        super().__init__()
        self._color = _color(color)
        self._progress = 0.0
        self._on_finished = on_finished

        self.setZValue(PRESENCE_Z - 1)
        self.setAcceptedMouseButtons(QtCore.Qt.MouseButton.NoButton)
        self.setFlag(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations,
            True)

        self._timer = QtCore.QTimer()
        self._timer.setInterval(CLICK_FRAME_MS)
        self._timer.timeout.connect(self._advance)
        self._steps = max(1, CLICK_FADE_MS // CLICK_FRAME_MS)
        self._step = 0
        self._timer.start()

    def boundingRect(self):
        return QtCore.QRectF(-16, -16, 32, 32)

    def _advance(self):
        self._step += 1
        self._progress = min(1.0, self._step / self._steps)
        self.update()

        if self._progress >= 1.0:
            self.stop()
            if self._on_finished is not None:
                self._on_finished(self)

    def stop(self):
        """
        Stops the animation. Safe to call more than once, and required before
        dropping the item: a running timer would keep it alive and keep
        repainting a scene it no longer belongs to.
        """
        if self._timer.isActive():
            self._timer.stop()

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)

        radius = 4 + 10 * self._progress
        color = QtGui.QColor(self._color)
        color.setAlphaF(max(0.0, 1.0 - self._progress))

        painter.setPen(QtGui.QPen(color, 2))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QtCore.QPointF(0, 0), radius, radius)


class PresenceOverlay:
    """
    Owns every presence item in one scene.

    The controller hands it decoded presence payloads and roster updates; it
    decides what is on screen. Keeping that here rather than in the controller
    means the "is a session running" logic and the "what does a cursor look
    like" logic do not end up interleaved.
    """

    def __init__(self, scene):
        self.scene = scene
        self._cursors = {}     # session_id -> PeerCursor
        self._flashes = []
        self._roster = {}      # session_id -> {'nick', 'color'}
        self._show_cursors = True
        self._show_clicks = True

        # Drops cursors whose owner has gone quiet - a peer that crashes or
        # loses its connection mid-move would otherwise leave a cursor pinned
        # to the canvas for the rest of the session.
        self._idle_timer = QtCore.QTimer()
        self._idle_timer.setInterval(2000)
        self._idle_timer.timeout.connect(self._dropIdleCursors)
        self._idle_timer.start()

    # -- configuration ------------------------------------------------------

    def setPreferences(self, show_cursors, show_clicks):
        """
        Applies the local display preferences. These are the *receiving* side's
        choice and deliberately do not stop anything being sent, so turning
        cursors off does not make you invisible to everyone else.
        """
        self._show_cursors = bool(show_cursors)
        self._show_clicks = bool(show_clicks)

        if not self._show_cursors:
            self._clearCursors()

    def setRoster(self, participants):
        """
        Learns each peer's nickname and colour, and forgets anyone who left.
        """
        self._roster = {}
        for entry in participants or ():
            session_id = str(entry.get('session_id') or '')
            if not session_id:
                continue
            self._roster[session_id] = {
                'nick': str(entry.get('nick') or ''),
                'color': entry.get('color'),
            }

        for session_id, cursor in list(self._cursors.items()):
            info = self._roster.get(session_id)
            if info is None:
                self._removeCursor(session_id)
                continue
            cursor.setNick(info['nick'])
            cursor.setColor(info['color'])

    # -- incoming presence --------------------------------------------------

    def showCursor(self, session_id, x, y):
        if not self._show_cursors or self.scene is None:
            return

        session_id = str(session_id or '')
        if not session_id:
            return

        cursor = self._cursors.get(session_id)

        # A cursor destroyed by a scene rebuild leaves a live Python wrapper
        # with no C++ object, and every call on it raises. Detect that here so
        # the peer simply gets a new cursor rather than disappearing until they
        # next go idle.
        if cursor is not None and not self._isAlive(cursor):
            self._cursors.pop(session_id, None)
            cursor = None

        try:
            if cursor is None:
                info = self._roster.get(session_id, {})
                cursor = PeerCursor(info.get('nick', ''), info.get('color'))
                self.scene.addItem(cursor)
                self._cursors[session_id] = cursor

            cursor.setPos(x, y)
            cursor.setVisible(True)
            cursor.setData(0, QtCore.QDateTime.currentMSecsSinceEpoch())
        except RuntimeError:
            self._cursors.pop(session_id, None)

    def showClick(self, session_id, x, y):
        if not self._show_clicks or self.scene is None:
            return

        info = self._roster.get(str(session_id or ''), {})
        flash = ClickFlash(info.get('color'), on_finished=self._removeFlash)
        flash.setPos(x, y)
        self.scene.addItem(flash)
        self._flashes.append(flash)

    def peerLeft(self, session_id):
        self._removeCursor(str(session_id or ''))

    # -- teardown -----------------------------------------------------------

    def clear(self):
        """
        Removes everything. Called when a session ends, and before the scene is
        rebuilt by a level load - a cursor left behind would be an item in a
        scene the level no longer matches.
        """
        self._clearCursors()

        for flash in list(self._flashes):
            self._removeFlash(flash)
        self._flashes = []

    def shutdown(self):
        self._idle_timer.stop()
        self.clear()
        self.scene = None

    # -- internals ----------------------------------------------------------

    def _clearCursors(self):
        for session_id in list(self._cursors):
            self._removeCursor(session_id)

    def _removeCursor(self, session_id):
        cursor = self._cursors.pop(session_id, None)
        if cursor is None:
            return
        self._detach(cursor)

    def _removeFlash(self, flash):
        try:
            flash.stop()
        except RuntimeError:
            pass
        if flash in self._flashes:
            self._flashes.remove(flash)
        self._detach(flash)

    @staticmethod
    def _isAlive(item):
        """
        Whether an item's C++ object still exists.

        QGraphicsScene.clear() deletes the items in it, and ours are in the
        level scene, so this is the normal state after a level load - not an
        error worth reporting.
        """
        try:
            item.scene()
            return True
        except RuntimeError:
            return False

    def _detach(self, item):
        """
        Takes an item out of the scene, tolerating one that is already gone.

        Loading a level calls QGraphicsScene.clear(), which *deletes* every
        item in it - including ours, since they live in the same scene. The
        Python wrappers survive that with no C++ object behind them, and
        touching one raises RuntimeError. Catching it here rather than making
        every caller clear the overlay first keeps a missed call site from
        turning into a crash.
        """
        try:
            if self.scene is not None and item.scene() is self.scene:
                self.scene.removeItem(item)
        except RuntimeError:
            pass

    def _dropIdleCursors(self):
        now = QtCore.QDateTime.currentMSecsSinceEpoch()
        for session_id, cursor in list(self._cursors.items()):
            if not self._isAlive(cursor):
                # Destroyed underneath us by a scene rebuild.
                self._cursors.pop(session_id, None)
                continue

            last = cursor.data(0)
            if last is None:
                continue
            if now - int(last) > CURSOR_IDLE_MS:
                self._removeCursor(session_id)
