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

#: Size as a fraction of the canvas, and the range the user may drag within.
#
# Both axes are clamped by the same three numbers. The first version clamped
# only the height, so the overlay could be dragged as wide as the window while
# refusing to be dragged as tall (Zement, 2026-08-29).
MIN_SIZE_PCT = 5.0
MAX_SIZE_PCT = 25.0
DEFAULT_SIZE_PCT = 15.0

# Kept as aliases: several call sites and the suites read the height names, and
# the two axes genuinely share one range.
MIN_HEIGHT_PCT = MIN_SIZE_PCT
MAX_HEIGHT_PCT = MAX_SIZE_PCT
DEFAULT_HEIGHT_PCT = DEFAULT_SIZE_PCT

#: Default opacity of the overlay's background, as a percentage.
MIN_OPACITY_PCT = 5.0
MAX_OPACITY_PCT = 100.0
DEFAULT_OPACITY_PCT = 20.0


def configured_corner():
    value = setting('OverviewCorner', 'bottomright')
    value = str(value).strip().lower() if value is not None else 'bottomright'
    return value if value in CORNERS else 'bottomright'


def _clamped_pct(name, default, low=MIN_SIZE_PCT, high=MAX_SIZE_PCT):
    try:
        value = float(setting(name, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))


def configured_height_pct():
    return _clamped_pct('OverviewHeightPct', DEFAULT_SIZE_PCT)


def configured_width_pct():
    """The width as a share of the canvas.

    Defaults to the height in *pixels* scaled by the canvas aspect, so an
    untouched overlay is the same shape as the level view it summarises - which
    is what makes its viewport rectangle read naturally. Expressed as a
    percentage of the width, that is just the height percentage again, since
    both are shares of the same rectangle.
    """
    return _clamped_pct('OverviewWidthPct', DEFAULT_SIZE_PCT)


def configured_opacity_pct():
    """Background opacity, or 100 when the setting is off.

    Off means opaque rather than invisible: the setting turns *transparency*
    on and off, and the natural reading of "background opacity: off" is "no
    see-through background", not "no background".
    """
    enabled = setting('OverviewTranslucent', True)
    if isinstance(enabled, str):
        enabled = enabled.strip().lower() not in ('false', '0', 'no', '')
    if not enabled:
        return 100.0

    return _clamped_pct('OverviewOpacityPct', DEFAULT_OPACITY_PCT,
                        MIN_OPACITY_PCT, MAX_OPACITY_PCT)


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


def _canvasSiblings(parent):
    """Every canvas overlay sharing a canvas with a child of ``parent``.

    Searched from the **tab container** down rather than among ``parent``'s own
    children, because the two kinds do not share a parent: the overview is a
    child of the container, a sub-tab flyout of one page inside it. A search of
    either one's siblings alone finds only itself.
    """
    top = parent
    for _ in range(4):
        if hasattr(top, 'currentCanvas'):
            break
        nxt = top.parentWidget()
        if nxt is None:
            break
        top = nxt

    return top.findChildren(CanvasWidget)


class CanvasWidget(QtWidgets.QFrame):
    """Base for anything that floats over the canvas.

    Lifted out of ``CanvasOverlay`` at D-d.4b, when the sub-tab flyout became
    the second such thing and immediately grew the two problems the overview had
    already solved: it looked wrong against the canvas without a background of
    its own, and it collided with whatever else was floating in the same corner
    (Zement, 2026-09-03).

    What lives here is what every canvas overlay needs and none of them should
    solve twice:

    - **the translucent background**, at the user's configured opacity, going
      solid on hover
    - **the rectangle to sit in** - the canvas *viewport*, not the container,
      so nothing lands on the scrollbars
    - **corner placement with a margin**, and the stacking that keeps two
      overlays in one corner off each other

    Zement asked for exactly this consolidation and named the next caller: a
    hotkey info panel to replace the one QPT carries.
    """

    #: True for a subclass whose children paint over the palette's background -
    #: the sub-tab flyout's buttons do. Those get their fill from ``paintEvent``
    #: with a real brush instead, since a palette colour under an opaque child
    #: is simply not visible.
    PAINTS_OWN_BACKGROUND = False

    def __init__(self, parent, margin=12):
        super().__init__(parent)

        self.margin = margin
        self._backgroundBrush = None

        self.setFrameShape(QtWidgets.QFrame.Shape.StyledPanel)
        self.setAutoFillBackground(True)

        # A background of its own, so the widget is not invisible against the
        # canvas - Zement's report, 2026-08-29. Qt-native rather than from the
        # theme file: the theme's `bg` is the canvas colour, which is exactly
        # what it must NOT match. Mid/Dark come from the running palette, so
        # this follows a light or dark system theme without a setting.
        self._baseColour = self.palette().color(QtGui.QPalette.ColorRole.Mid)
        self._hovered = False
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_Hover, True)

    # -- opacity ---------------------------------------------------------

    def _applyOpacity(self):
        """Paint the background at the configured opacity.

        An alpha on the background colour rather than setWindowOpacity or a
        QGraphicsOpacityEffect: both of those fade the *contents* too, and what
        is drawn on top is the part that must stay readable - it is the
        background the user wants out of the way. Alpha on the brush leaves the
        contents at full strength.

        Hovering restores full opacity, so pointing at the thing to use it makes
        it solid. Focus would be the better trigger, but these frames are not
        focusable and giving one focus would steal it from the canvas mid-edit;
        hover is what Zement offered as sufficient, and it is also the correct
        choice here.
        """
        colour = QtGui.QColor(self._baseColour)
        alpha = int(255 * configured_opacity_pct() / 100.0)

        if not self._hovered:
            colour.setAlpha(alpha)

        palette = self.palette()
        palette.setColor(QtGui.QPalette.ColorRole.Window, colour)
        self.setPalette(palette)

        # A translucent background needs the parent painted behind it, which
        # autoFillBackground alone does not arrange.
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground,
                          colour.alpha() < 255)

        # Palette-driven fill only where nothing else paints over it. A frame
        # whose children draw their own backgrounds - the sub-tab flyout's
        # buttons - hides the palette entirely, so those paint the brush
        # themselves in paintEvent. Turning autoFill *off* there is what stops
        # Qt filling the rect opaquely underneath (Zement, 2026-09-03: the
        # opacity "seems to be applied to the icons or maybe the border, but
        # not the background color").
        self.setAutoFillBackground(not self.PAINTS_OWN_BACKGROUND)

        self._backgroundBrush = QtGui.QBrush(colour)
        self._opacityApplied(255 if self._hovered else alpha)
        self.update()

    def paintEvent(self, event):
        """Fill the background at the configured alpha, then paint as usual.

        A QBrush drawn here rather than a palette colour, for the reason the
        level overview already had to solve once: the alpha has to land on the
        *background* and nothing else. A palette Window colour is painted by
        each child under its own content, so the icons faded and the background
        did not - the opposite of what the setting means.
        """
        if self.PAINTS_OWN_BACKGROUND and self._backgroundBrush is not None:
            painter = QtGui.QPainter(self)
            painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(self._backgroundBrush)
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 4, 4)
            painter.end()

        super().paintEvent(event)

    def _opacityApplied(self, alpha):
        """Hook for subclasses whose contents paint their own background."""

    def enterEvent(self, event):
        super().enterEvent(event)
        self._hovered = True
        self._applyOpacity()

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._hovered = False
        self._applyOpacity()

    # -- the rectangle to sit in -----------------------------------------

    def _availableRect(self):
        """The canvas area to sit within, excluding any scrollbars.

        The parent is the tab container, whose page holds a QGraphicsView with
        its own scrollbars. Sitting over them makes them unusable and looks like
        a misalignment - Zement reported a 3-4px overlap - so the view's
        viewport is the rectangle that counts, not the container's full width.
        """
        parent = self.parentWidget()
        if parent is None:
            return QtCore.QRect()

        rect = parent.rect()
        page = self._canvasWidget(parent)

        viewport = getattr(page, 'viewport', None)
        if viewport is not None:
            # Map the viewport into the container's coordinates: the page sits
            # below the tab bar, so its origin is not the container's.
            vp = viewport()
            top_left = vp.mapTo(parent, QtCore.QPoint(0, 0))
            rect = QtCore.QRect(top_left, vp.size())

        return rect

    @staticmethod
    def _canvasWidget(parent):
        """The QGraphicsView behind ``parent``, whatever kind of parent it is.

        Two kinds now, and they are found differently. The overview is a child
        of the **tab container**, which knows which canvas is in front and
        answers ``currentCanvas()``. The sub-tab flyout is a child of one
        **page**, which holds exactly one canvas and has no such method - so
        asking it for `currentCanvas` returns nothing and the rectangle silently
        falls back to the page's full width. That is not cosmetic: the fallback
        is 16px wider than the viewport, which is exactly the scrollbar the bar
        was landing on (Zement, 2026-09-03).
        """
        current_canvas = getattr(parent, 'currentCanvas', None)
        if current_canvas is not None:
            found = current_canvas()
            if found is not None:
                return found

        stack = getattr(parent, 'stack', None)
        canvas = getattr(stack, 'canvas', None)
        if canvas is not None:
            return canvas()

        if hasattr(parent, 'currentWidget'):
            return parent.currentWidget()

        return None

    # -- stacking --------------------------------------------------------

    def globalRect(self):
        """This widget's geometry in screen coordinates.

        Overlays over one canvas can have *different parents* - the overview is
        a child of the tab container, a sub-tab flyout of one page inside it -
        so their raw geometries are in different coordinate systems and
        comparing them directly is meaningless. Everything that compares two
        overlays goes through here.
        """
        return QtCore.QRect(self.mapToGlobal(QtCore.QPoint(0, 0)), self.size())

    def topOverlap(self, band):
        """How far down to start, to clear anything already inside ``band``.

        ``band`` is where this overlay wants to sit, in **screen** coordinates.
        Anything else floating over the canvas that would intersect it pushes
        the answer down past its own bottom edge.

        Rectangles rather than corner names, and that distinction is the fix for
        Zement's 2026-09-03 report that top-right still collided. The first
        version asked "is anything anchored in *my* corner", and the flyout's
        anchor is the top **left** - so a top-right overview matched nothing and
        moved not at all. But the flyout is not really cornered: it follows its
        own tab along the top edge, so with enough tabs open it reaches the
        right-hand side too, which is exactly the case he photographed. What
        matters is whether the two would overlap, and only a rectangle can say.

        Only the vertical direction is offset. Two things side by side would
        each be somewhere unpredictable; stacked, the one that was there first
        keeps its place.
        """
        parent = self.parentWidget()
        if parent is None:
            return 0

        offset = 0
        for sibling in _canvasSiblings(parent):
            if sibling is self or not sibling.isVisible():
                continue
            if sibling.stacksBelow(self):
                continue

            rect = sibling.globalRect()
            if not rect.intersects(band):
                continue

            offset = max(offset, rect.bottom() - band.top() + 1 + sibling.margin)

        return offset

    def stacksBelow(self, other):
        """True if ``other`` should be the one to move.

        Default: nothing moves for anything, and the subclass that is willing
        to give way says so. The flyout is fixed to its tab, so the overview is
        the one that yields.
        """
        return False


class CanvasOverlay(CanvasWidget):
    """A frame pinned to a corner of the canvas, holding one widget.

    Owns the placement and the size; the widget inside knows nothing about
    either. Kept separate from MasterTabWidget so that the container's job stays
    "one tab per session" and this one's stays "where does the overview sit".
    """

    def __init__(self, parent, content, margin=12):
        super().__init__(parent, margin)

        self.content = content
        self._corner = configured_corner()

        # False until a drag or a settings change has sized this frame, so
        # reposition() knows whether the current geometry means anything. See
        # the note in reposition().
        self._userSized = False

        # Whether the user wants this overlay at all, as opposed to whether it
        # happens to be on screen right now. The two part company over a tool
        # tab (D-c.5), where the overlay is taken away without the View menu's
        # toggle changing - so the toggle's state is tracked here rather than
        # read back from isVisible(), which would answer "no" for the wrong
        # reason and leave the menu entry unticked after a visit to Preferences.
        self._userVisible = True

        self._applyOpacity()

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)
        layout.addWidget(content)

        content.setParent(self)
        content.show()

        self.grip = _ResizeGrip(self)
        self.grip.show()
        self.grip.raise_()

    def stacksBelow(self, other):
        """The overview yields; the flyout is pinned to its tab and cannot."""
        return True

    def _opacityApplied(self, alpha):
        content_bg = getattr(self.content, 'setBackgroundAlpha', None)
        if content_bg is not None:
            content_bg(alpha)

    # -- visibility ------------------------------------------------------

    def setUserVisible(self, visible):
        """The View menu's toggle. Records the intent, then acts on it.

        What the menu drives, so that the tool-tab hide can borrow the overlay
        away and give it back without the menu entry ever being wrong.
        """
        self._userVisible = bool(visible)
        self.setVisible(self._userVisible)

    def isEnabledByUser(self):
        return self._userVisible

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
        self._applyOpacity()

        # Settings win over a previous drag: the user has just said what size
        # they want, so the drag's _userSized claim is stale.
        self._userSized = False

        area = self._availableRect()
        if area.width() > 0 and area.height() > 0:
            self.resize(self.preferredSize(area))

        self.reposition()

    def preferredSize(self, area):
        """The frame's size for a canvas of ``area``, from the percentages."""
        return self._clampSize(area.height() * configured_height_pct() / 100.0,
                               area.width() * configured_width_pct() / 100.0,
                               area)

    def _clampSize(self, height, width, area):
        """Hold both axes inside the allowed percentage range.

        Both, on the same three numbers. The first version clamped only the
        height, so the overlay refused to be dragged taller than 20% while
        happily being dragged as wide as the whole window.
        """
        min_h = area.height() * MIN_SIZE_PCT / 100.0
        max_h = area.height() * MAX_SIZE_PCT / 100.0
        min_w = area.width() * MIN_SIZE_PCT / 100.0
        max_w = area.width() * MAX_SIZE_PCT / 100.0

        # The percentage range wins, but never at the cost of spilling out of a
        # window too small for it.
        max_h = min(max_h, area.height() - 2 * self.margin)
        max_w = min(max_w, area.width() - 2 * self.margin)

        return QtCore.QSize(int(max(1, min(max(min_w, width), max_w))),
                            int(max(1, min(max(min_h, height), max_h))))

    def resizeToPixels(self, width, height):
        """Resize from a drag, clamped to the allowed percentage range."""
        area = self._availableRect()
        if area.height() <= 0 or area.width() <= 0:
            return

        self._userSized = True
        self.resize(self._clampSize(height, width, area))
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

    def reposition(self):
        """Move to the configured corner of the canvas, and place the grip."""
        area = self._availableRect()
        if area.width() <= 0 or area.height() <= 0:
            return

        # Size from the settings until the user has actually resized it. The
        # first version only re-sized when width OR height was <= 1, which never
        # fired: a QFrame with a layout takes a sensible *height* from its
        # child's size hint while its width stays at the minimum, so the frame
        # booted one pixel wide and only corrected once something else forced a
        # resize (Zement, 2026-08-29). A flag is the honest test of "has the
        # user chosen a size", rather than inferring it from the geometry.
        if not self._userSized:
            self.resize(self.preferredSize(area))

        size = self.size()

        margin = self.margin
        left = area.left() + margin
        top = area.top() + margin
        right = area.right() - size.width() - margin + 1
        bottom = area.bottom() - size.height() - margin + 1

        x = left if 'left' in self._corner else max(left, right)

        # Start below anything that would overlap where this wants to sit - the
        # sub-tab flyout, when the overview is in a top corner (Zement,
        # 2026-09-03). Only the top corners can collide: the flyout hangs from
        # the tab bar, so it is always along the top edge.
        #
        # Asked with the rectangle this would occupy, not with a corner name.
        # The flyout follows its own tab horizontally, so it is not in a corner
        # at all - with enough tabs open it reaches the right-hand side, which
        # is the case a corner-name test missed entirely.
        if 'top' in self._corner:
            parent = self.parentWidget()
            band = QtCore.QRect(
                parent.mapToGlobal(QtCore.QPoint(int(x), int(top))), size)
            top += self.topOverlap(band)

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
