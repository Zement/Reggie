"""The canvas overlay frame (Block D-c, phase D-c.5).

The level overview stopped being a dock in D-c.4 and became a plain child of the
tab container, floating over the canvas. This module gives it the things a dock
used to provide for free and an overlay has to be given by hand: somewhere to
sit, a size the user chooses, and a background of its own.

Three points shaped it.

**A corner, not a position.** The overview is pinned to one of the four corners
rather than dragged freely, so it can never be lost off-screen or half behind a
scrollbar, and so it survives a window resize without arithmetic on where it used
to be. Which corner is a setting.

**Resize from the inward corner.** A frame pinned to the bottom-right can only
grow up and to the left, so its grip belongs on the top-left - the corner facing
into the canvas. The grip moves to whichever corner faces inward for the chosen
position (Zement, 2026-08-29).

**Height in percent of the canvas, not pixels.** The overview is a scaled picture
of the whole level, so what matters is how much of the window it takes; a pixel
height that looks right on one monitor is wrong on the next. Clamped to 3-20%,
defaulting to 6%.
"""

from PyQt6 import QtCore, QtGui, QtWidgets

from reggie.core.dirty import setting


#: Where the overlay can sit. Stored in settings as these strings.
CORNERS = ('topleft', 'topright', 'bottomleft', 'bottomright')

#: Height as a fraction of the canvas, and the range the user may drag within.
MIN_HEIGHT_PCT = 3.0
MAX_HEIGHT_PCT = 20.0
DEFAULT_HEIGHT_PCT = 6.0

#: The overlay keeps a 16:9-ish shape unless dragged; width follows height.
DEFAULT_ASPECT = 2.4


def configured_corner():
    value = setting('OverviewCorner', 'bottomright')
    value = str(value).strip().lower() if value is not None else 'bottomright'
    return value if value in CORNERS else 'bottomright'


def configured_height_pct():
    try:
        value = float(setting('OverviewHeightPct', DEFAULT_HEIGHT_PCT))
    except (TypeError, ValueError):
        value = DEFAULT_HEIGHT_PCT
    return max(MIN_HEIGHT_PCT, min(MAX_HEIGHT_PCT, value))


def configured_width_pct():
    try:
        value = float(setting('OverviewWidthPct', DEFAULT_HEIGHT_PCT * DEFAULT_ASPECT))
    except (TypeError, ValueError):
        value = DEFAULT_HEIGHT_PCT * DEFAULT_ASPECT
    # Wide enough to be a picture, never so wide it becomes the canvas.
    return max(MIN_HEIGHT_PCT, min(80.0, value))


class _ResizeGrip(QtWidgets.QWidget):
    """A corner drag handle that resizes the frame it belongs to.

    QSizeGrip cannot serve: it resizes the *window*, and grows down-and-right
    from a top-left origin. An overlay pinned to a corner has to grow the other
    way - the pinned corner stays put and the opposite edge moves.
    """

    GRIP = 14

    def __init__(self, frame):
        super().__init__(frame)

        self.frame = frame
        self._origin = None
        self._startSize = None

        self.setFixedSize(self.GRIP, self.GRIP)
        self.setCursor(QtCore.Qt.CursorShape.SizeFDiagCursor)
        self.setToolTip('Drag to resize the level overview')

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        colour = self.palette().color(QtGui.QPalette.ColorRole.Mid)
        painter.setPen(QtGui.QPen(colour, 1))

        # Three short diagonals, the conventional grip look. Drawn toward the
        # corner the grip actually sits in, so it reads as "pull this way".
        for offset in (3, 6, 9):
            painter.drawLine(offset, self.GRIP - 1, self.GRIP - 1, offset)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._origin = event.globalPosition().toPoint()
            self._startSize = self.frame.size()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._origin is None:
            return

        delta = event.globalPosition().toPoint() - self._origin

        # The grip faces into the canvas, so dragging *toward* the pinned corner
        # shrinks. Which axis inverts depends on the corner the frame sits in.
        corner = self.frame.corner
        dx = -delta.x() if 'right' in corner else delta.x()
        dy = -delta.y() if 'bottom' in corner else delta.y()

        self.frame.resizeToPixels(self._startSize.width() + dx,
                                  self._startSize.height() + dy)
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._origin is not None:
            self._origin = None
            self.frame.saveSize()
            event.accept()


class CanvasOverlay(QtWidgets.QFrame):
    """A frame pinned to a corner of the canvas, holding one widget.

    Owns the placement and the size; the widget inside knows nothing about
    either. Kept separate from MasterTabWidget so that the container's job stays
    "one tab per session" and this one's stays "where does the overview sit".
    """

    def __init__(self, parent, content, margin=12):
        super().__init__(parent)

        self.content = content
        self.margin = margin
        self._corner = configured_corner()

        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setAutoFillBackground(True)

        # A background of its own, so the overview is not invisible against the
        # canvas - Zement's report, 2026-08-29. Qt-native rather than from the
        # theme file: the theme's `bg` is the canvas colour, which is exactly
        # what it must NOT match. Mid/Dark come from the running palette, so
        # this follows a light or dark system theme without a setting.
        palette = self.palette()
        base = palette.color(QtGui.QPalette.ColorRole.Mid)
        palette.setColor(QtGui.QPalette.ColorRole.Window, base)
        self.setPalette(palette)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(content)

        content.setParent(self)
        content.show()

        self.grip = _ResizeGrip(self)
        self.grip.show()
        self.grip.raise_()

    # -- placement -------------------------------------------------------

    @property
    def corner(self):
        return self._corner

    def applySettings(self):
        """Re-read the corner and size settings, resize and reposition.

        The size is re-read too, not only the corner: Preferences can change the
        height, and repositioning alone would keep whatever the last drag left.
        """
        self._corner = configured_corner()

        area = self._availableRect()
        if area.width() > 0 and area.height() > 0:
            self.resize(self.preferredSize(area))

        self.reposition()

    def preferredSize(self, area):
        """The frame's size for a canvas of ``area``, from the percentages."""
        height = area.height() * configured_height_pct() / 100.0
        width = area.width() * configured_width_pct() / 100.0

        # Never larger than the space it sits in, whatever the settings say -
        # a small window must not be entirely covered by the overview.
        return QtCore.QSize(
            int(max(60, min(width, area.width() - 2 * self.margin))),
            int(max(40, min(height, area.height() - 2 * self.margin))))

    def resizeToPixels(self, width, height):
        """Resize from a drag, clamped to the allowed percentage range."""
        area = self._availableRect()
        if area.height() <= 0 or area.width() <= 0:
            return

        min_h = area.height() * MIN_HEIGHT_PCT / 100.0
        max_h = area.height() * MAX_HEIGHT_PCT / 100.0
        min_w = area.width() * MIN_HEIGHT_PCT / 100.0
        max_w = area.width() * 80.0 / 100.0

        height = max(min_h, min(max_h, height))
        width = max(min_w, min(max_w, width))

        self.resize(int(width), int(height))
        self.reposition()

    def saveSize(self):
        """Store the current size as percentages of the canvas."""
        from reggie.core.dirty import setSetting

        area = self._availableRect()
        if area.height() <= 0 or area.width() <= 0:
            return

        setSetting('OverviewHeightPct',
                   round(self.height() * 100.0 / area.height(), 2))
        setSetting('OverviewWidthPct',
                   round(self.width() * 100.0 / area.width(), 2))

    def _availableRect(self):
        """The canvas area to sit within, excluding any scrollbars.

        The parent is the tab container, whose page is a QGraphicsView with its
        own scrollbars. Sitting over them makes them unusable and looks like a
        misalignment - Zement reported a 3-4px overlap - so the view's viewport
        is the rectangle that counts, not the container's full width.
        """
        parent = self.parentWidget()
        if parent is None:
            return QtCore.QRect()

        rect = parent.rect()

        page = parent.currentWidget() if hasattr(parent, 'currentWidget') else None
        viewport = getattr(page, 'viewport', None)
        if viewport is not None:
            # Map the viewport into the container's coordinates: the page sits
            # below the tab bar, so its origin is not the container's.
            vp = viewport()
            top_left = vp.mapTo(parent, QtCore.QPoint(0, 0))
            rect = QtCore.QRect(top_left, vp.size())

        return rect

    def reposition(self):
        """Move to the configured corner of the canvas, and place the grip."""
        area = self._availableRect()
        if area.width() <= 0 or area.height() <= 0:
            return

        size = self.size()
        if size.width() <= 1 or size.height() <= 1:
            size = self.preferredSize(area)
            self.resize(size)

        margin = self.margin
        left = area.left() + margin
        top = area.top() + margin
        right = area.right() - size.width() - margin + 1
        bottom = area.bottom() - size.height() - margin + 1

        x = left if 'left' in self._corner else max(left, right)
        y = top if 'top' in self._corner else max(top, bottom)

        self.move(int(x), int(y))
        self._placeGrip()

    def _placeGrip(self):
        """Put the grip on the corner facing into the canvas.

        Pinned bottom-right, the frame can only grow up and left, so the handle
        belongs top-left. Each corner mirrors accordingly, and the cursor shape
        follows so the diagonal points the way the drag will go.
        """
        grip = self.grip.GRIP
        inner_left = 'right' in self._corner
        inner_top = 'bottom' in self._corner

        self.grip.move(1 if inner_left else self.width() - grip - 1,
                       1 if inner_top else self.height() - grip - 1)

        # FDiag is "\", BDiag is "/". Top-left and bottom-right share one; the
        # other two share the mirror.
        diagonal = (QtCore.Qt.CursorShape.SizeFDiagCursor
                    if inner_left == inner_top
                    else QtCore.Qt.CursorShape.SizeBDiagCursor)
        self.grip.setCursor(diagonal)
        self.grip.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._placeGrip()
