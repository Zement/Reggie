"""The docked sidebar (Block D-c, phase D-c.3).

The editor's palette and its four item-property editors used to live in
`QDockWidget`s: floatable, closable, and scattered around the right edge by
whatever `MainWindowState` happened to be saved. This module replaces them with
one always-docked sidebar, VS Code style, in two of the three planned slices:

- **slice 1** - a narrow icon-only rail, the switch for slice 2.
- **slice 2** - the context area the rail drives. D-c.3 ships the *frame* and
  one page; D-d fills in the directory listing, which is the big one.
- **slice 3** - the palette and the property editors, below the others, shown
  only when a canvas tab is in front.

Which side the sidebar sits on is a setting. Flipping it re-inserts the slices in
reverse so the rail stays on the outside, which is the whole reason nothing here
may hard-code its neighbour (Zement, 2026-08-29).

Why PanelHost exists
--------------------
The four property editors were shown and hidden by calling `setVisible()` and
`isVisible()` on their *docks* - about twenty sites across window.py, plus one
`isFloating()` in spriteeditor.py. Moving the editors out and deleting the docks
would break every one of them, and rewriting twenty call sites in a phase whose
job is to move widgets is how a layout change turns into a behaviour change.

So `PanelHost` presents the same three methods and does the same job in the
sidebar. The call sites are untouched, exactly as `mainWindow.scene` kept its 87
readers in D-c.1: when many places read one thing and few write it, make the one
thing answer differently rather than editing the many.
"""

from PyQt6 import QtCore, QtGui, QtWidgets

from reggie.core import globals_
from reggie.core.dirty import setSetting, setting


#: Settings value for the sidebar living on the left / right of the window.
SIDE_LEFT = 'left'
SIDE_RIGHT = 'right'


def configured_side():
    """Which side the sidebar is on, defaulting to the left."""
    value = setting('SidebarSide', SIDE_LEFT)
    value = str(value).strip().lower() if value is not None else SIDE_LEFT
    return SIDE_RIGHT if value == SIDE_RIGHT else SIDE_LEFT


def _expandVertically(widget, depth=0):
    """Let ``widget`` and the containers inside it grow to fill their space.

    A vertical stretch factor is only half the job: Qt gives a widget the space
    the layout allots, but most widgets refuse to *use* more than their size
    hint, so a stretched panel full of tab widgets still renders at its natural
    height with the rest of the sidebar left blank. The palette is nested three
    deep - panel host, creationTabs, objAllTab/sprAllTab, then the list itself -
    and every level has to agree before the innermost list can grow (Zement,
    2026-08-29: the palette capped at ~50% of the sidebar, then ~30% once a
    property panel opened).

    Recurses only through *containers* - tab widgets, stacks, item views,
    scroll areas - and plain QWidgets, which is what the palette's pages are.
    Buttons, labels and spin boxes are left alone: making those expand would
    stretch a "Change Layer" button down the sidebar rather than the list.
    """
    if depth > 6:
        return

    policy = widget.sizePolicy()
    policy.setVerticalPolicy(QtWidgets.QSizePolicy.Policy.Expanding)
    widget.setSizePolicy(policy)

    # A maximum set elsewhere silently wins over the policy.
    if widget.maximumHeight() < QtWidgets.QWIDGETSIZE_MAX:
        widget.setMaximumHeight(QtWidgets.QWIDGETSIZE_MAX)

    growable = (QtWidgets.QTabWidget, QtWidgets.QStackedWidget,
                QtWidgets.QAbstractItemView, QtWidgets.QScrollArea,
                QtWidgets.QSplitter, QtWidgets.QGroupBox)

    for child in widget.findChildren(QtWidgets.QWidget):
        if child.parentWidget() is not widget:
            continue
        if isinstance(child, growable) or type(child) is QtWidgets.QWidget:
            _expandVertically(child, depth + 1)


#: A panel with no ceiling: as tall as the layout will let it be.
UNLIMITED = None

#: Rail button widths offered in Preferences (Zement, 2026-08-30). A stub - the
#: values are expected to change once there are real icons to size against.
RAIL_WIDTHS = (32, 48, 64)
DEFAULT_RAIL_WIDTH = 48

#: How much of a rail row the icon takes, leaving a margin around it. The rail
#: is the only place icon size follows a setting, so this lives here rather than
#: being a magic number inside the widget (Block D-d, phase D-d.1c).
RAIL_ICON_RATIO = 0.6

#: Never smaller than this, whatever the ratio works out to - a 16px icon in a
#: 32px rail is already small enough to be hard to read.
MIN_RAIL_ICON = 16

#: How much of the window a restored sidebar must leave for the canvas. A floor
#: for the canvas rather than a ceiling for the sidebar: the user is allowed a
#: very wide sidebar if that is what they dragged, and only needs protecting
#: from a saved width that would leave no level visible at all.
MIN_CANVAS_WIDTH = 320

#: How narrow slice 2 may get before its contents stop being readable. A level
#: tree is the constraint: "World 1-Castle: Creepcrack Castle" indented three
#: deep is the widest thing the sidebar routinely shows, and a column that
#: elides it into "World 1-Cas..." is a column the user cannot work from.
MIN_SLICE_TWO_WIDTH = 180

#: Below this a three-slice sidebar cannot show all three at a usable size, so
#: a saved width under it is treated as one written by a two-slice build and
#: replaced with the default. The rail plus both floors plus a little room to
#: be worth restoring at all.
MIN_THREE_SLICE_WIDTH = 460

#: What the sidebar opens at on a first run, before the user has dragged it or
#: anything has been saved. Enough for all three slices to be usable at once:
#: the rail, a level tree wide enough to read, and property editors wide enough
#: to fill in. Left to the splitter's own arithmetic until D-d.2b, which gave
#: 251px - two slices' worth, and one slice short.
DEFAULT_SIDEBAR_WIDTH = 640

#: The share of the sidebar slice 2 takes when it first appears, before the user
#: has dragged the divider. Slice 3 keeps the rest. Slightly under half because
#: the property panels are forms with a natural width, while a tree simply uses
#: whatever it is given - so the panels are the ones that would look starved.
SLICE_TWO_SHARE = 0.45


def rail_icon_size(width=None):
    """The icon size for a rail of this width (Block D-d, phase D-d.1c).

    Was a fixed 24px, which produced three complaints at once: switching the
    rail between 32, 48 and 64 grew the row but not the icon, the icon sat
    left-of-centre in the wider rows, and the unused part of the icon box showed
    as a darker rectangle inside the selection highlight (Zement, 2026-08-31).

    All three are the same fault - the icon box did not match the row - so all
    three are fixed by deriving one from the other.
    """
    if width is None:
        width = rail_width()

    return max(MIN_RAIL_ICON, int(width * RAIL_ICON_RATIO))


def rail_width():
    """The configured slice-1 width, clamped to a value we offer."""
    value = setting('RailWidth', DEFAULT_RAIL_WIDTH)
    try:
        value = int(value)
    except (TypeError, ValueError):
        return DEFAULT_RAIL_WIDTH

    return value if value in RAIL_WIDTHS else DEFAULT_RAIL_WIDTH


class Percent(float):
    """A height expressed as a percentage of the sidebar, not in pixels.

    Zement, 2026-08-30: 400px looked right on the machine it was chosen on and
    took 40% of a shorter sidebar. A panel's sensible height is a fraction of the
    space available, not a count of pixels - the same reasoning that put the
    level overview's size behind a percentage in D-c.4.

    A float subclass rather than a separate parameter, so a host takes
    ``Percent(15)`` or ``200`` in the same argument and the reader can see which
    is meant at the call site. Values above 100 are allowed and mean "taller than
    the sidebar" - the panel then scrolls, which is a legitimate thing to ask
    for.
    """

    def resolve(self, available):
        """Pixels, given the height this panel could occupy."""
        return int(round(available * float(self) / 100.0))


class _CollapsibleHost(QtWidgets.QWidget):
    """A title bar the user can click to fold, over one hosted widget.

    Shared by both kinds of host in the sidebar. Slice 2's sections and slice
    3's panels arrived from different directions - one is new, one imitates a
    QDockWidget for twenty existing call sites - but the header, the fold and
    the height limits are the same job, and Zement asked for the same treatment
    on both (2026-08-30). Keeping one implementation is what stops them drifting
    into two slightly different headers.

    Collapsing hides the body and pins this widget to its header height, so a
    folded host costs one row rather than a share of its splitter. Both
    containers re-apply their stretch after a fold, because a collapsed child
    that kept its stretch would leave a gap under its own title.
    """

    toggled = QtCore.pyqtSignal(bool)

    #: Emitted when the header's close button is pressed. The *owner* decides
    #: what closing means, since the widget inside usually belongs to something
    #: else - so this only reports the click.
    closeRequested = QtCore.pyqtSignal()

    #: Shown at the left of the header. Text rather than icons so the header
    #: needs no theme lookup and reads the same in both colour schemes.
    _ARROWS = ('▸', '▾')   # right-pointing, down-pointing

    def __init__(self, title, widget, parent=None, closable=False,
                 default_height=UNLIMITED, max_height=UNLIMITED):
        super().__init__(parent)

        self.hostTitle = title
        #: The title this host was *created* with, which is what its remembered
        #: height is keyed by. See `sectionKey`.
        self._sectionKey = title
        self.hostWidget = widget
        self._expanded = True
        self._maxHeight = max_height
        self._defaultHeight = default_height
        #: Set once the user drags this host's grip - see setDraggedHeight.
        self._dragged = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # The header is its own row: the fold button stretches across it and the
        # close button sits at the far end. A single widget would have to choose
        # between "click anywhere to fold" and "there is an X", and the first is
        # worth more than the pixels the second costs.
        self.headerRow = QtWidgets.QWidget(self)
        headerLayout = QtWidgets.QHBoxLayout(self.headerRow)
        headerLayout.setContentsMargins(0, 0, 0, 0)
        headerLayout.setSpacing(0)

        # A QPushButton, not a QToolButton. QToolButton centres its content and
        # ignores text-align on several styles, which is what made the header
        # read wrong - and worst when collapsed, with a centred title floating
        # over nothing (Zement, 2026-08-30). QPushButton honours text-align on
        # Fusion and on Windows, and `text-align: left` is the whole fix.
        self.header = QtWidgets.QPushButton(self.headerRow)
        self.header.setText('%s  %s' % (self._ARROWS[1], title))
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setFlat(True)
        self.header.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                                  QtWidgets.QSizePolicy.Policy.Fixed)
        self.header.setStyleSheet(
            'QPushButton { border: none; font-weight: bold; text-align: left;'
            ' padding: 3px 4px; }')
        self.header.toggled.connect(self.setExpanded)
        headerLayout.addWidget(self.header, 1)

        self.closeButton = QtWidgets.QToolButton(self.headerRow)
        self.closeButton.setText('✕')
        self.closeButton.setAutoRaise(True)
        self.closeButton.setToolTip('Close')
        self.closeButton.setStyleSheet(
            'QToolButton { border: none; padding: 3px 6px; }')
        self.closeButton.clicked.connect(self.closeRequested.emit)
        self.closeButton.setVisible(bool(closable))
        headerLayout.addWidget(self.closeButton, 0)

        layout.addWidget(self.headerRow)
        layout.addWidget(widget)

        # The panel widget arrives hidden in some cases (the old docks set
        # setVisible(False) on the *dock*, leaving the widget itself shown).
        # Inside a host, the host is what gets hidden, so the widget must be
        # visible or the host would show an empty box.
        widget.setVisible(True)

        self._applyMaxHeight()

    # -- title -----------------------------------------------------------

    def sectionKey(self):
        """A stable name for this host, for remembering its height by (D-d.3d).

        **Not `hostTitle`**, which is what a first version used and which the
        undo history would have broken immediately: its title carries the level
        and area ("Undo History - 01-01, Area 1"), so it changes on every area
        switch and a height saved under one would never be found again.

        The key given at construction, falling back to the first title when no
        key was passed. `setTitle` deliberately does not touch it.
        """
        return self._sectionKey

    def setSectionKey(self, key):
        """Name this host's height key explicitly.

        For a section whose *title* is not stable - the undo history's names the
        level and area it is showing, so it changes on every switch.
        """
        self._sectionKey = str(key)

    def setTitle(self, title):
        """Rename the host, keeping the fold arrow in step.

        The height key is *not* renamed with it - see `sectionKey`.
        """
        self.hostTitle = title
        self.header.setText('%s  %s' % (self._ARROWS[int(self._expanded)],
                                        title))

    # -- height limits ---------------------------------------------------

    @property
    def maxHeight(self):
        return self._maxHeight

    @property
    def defaultHeight(self):
        return self._defaultHeight

    def setMaxHeight(self, height):
        """Cap how tall this host may grow. ``UNLIMITED`` removes the cap."""
        self._maxHeight = height
        self._applyMaxHeight()

    def availableHeight(self):
        """The height a percentage is a percentage *of*: the sidebar's.

        Walks up to the sidebar rather than reading the immediate parent, which
        is the sections splitter and already shrinks as sections are added - a
        percentage of that would shift every time a neighbour appeared.
        """
        widget = self.parentWidget()
        while widget is not None:
            if isinstance(widget, Sidebar):
                return widget.height()
            widget = widget.parentWidget()

        return 0

    def _resolveHeight(self, value):
        """A configured height in pixels, or None if there is none to apply."""
        if value is UNLIMITED:
            return None

        if isinstance(value, Percent):
            available = self.availableHeight()
            if available <= 0:
                # No sidebar to be a percentage of yet. Answering None leaves
                # the limit unset until there is, rather than freezing a height
                # derived from a zero-sized window.
                return None
            return value.resolve(available)

        return int(value)

    def _applyMaxHeight(self):
        """Apply the ceiling, unless folding has one of its own in force.

        Folding sets a much smaller maximum, so this must not overwrite it -
        which is why unfolding calls back here rather than clearing the maximum
        itself. One place decides the height, in both directions.
        """
        if not self._expanded:
            self.setMaximumHeight(self.headerHeight())
            return

        resolved = self._resolveHeight(self._maxHeight)
        self.setMaximumHeight(
            QtWidgets.QWIDGETSIZE_MAX if resolved is None else resolved)

    def sizeHint(self):
        """Ask for the default height, when one was given.

        A layout gives a widget its size hint when it can, so since D-d.3d this
        is the height the host actually gets rather than a number a splitter
        divided space by. That is what `defaultHeight` always read as, and it is
        what makes Zement's "70% + 40% should scroll" true: two hosts asking for
        110% of the sidebar between them are 110% tall, and the column scrolls.

        Folded, the header alone - so a folded host takes no more room than it
        shows, which is what makes folding free space for its neighbours.
        """
        hint = super().sizeHint()

        if not self._expanded:
            hint.setHeight(self.headerHeight())
            return hint

        resolved = self._resolveHeight(self._defaultHeight)
        if resolved is not None:
            hint.setHeight(resolved)

        return hint

    def setDraggedHeight(self, height, restored=False):
        """Set the height the user dragged this host to (D-d.3d).

        Straight into ``_defaultHeight`` as a plain pixel number, so a drag and
        a configured height are the *same* mechanism rather than two that can
        disagree. It stops being a percentage in the process, which is right: a
        percentage says "this fraction of whatever the sidebar is", and someone
        who has just dragged a section to a size means that size.

        ``restored=True`` puts a *remembered* height back without marking the
        host as dragged - see `Sidebar.applySectionHeight` for why that matters.
        """
        self._defaultHeight = max(0, int(height))
        if not restored:
            self._dragged = True
        self.updateGeometry()

    def wasDragged(self):
        """Whether this host's height came from the user rather than the code.

        What decides if the height is worth saving. A section still at its
        configured default has nothing to remember, and writing it would freeze
        that default at whatever it resolved to on this screen.
        """
        return getattr(self, '_dragged', False)

    def refreshHeights(self):
        """Re-resolve percentage heights. Called when the sidebar is resized."""
        if isinstance(self._maxHeight, Percent):
            self._applyMaxHeight()

        if isinstance(self._defaultHeight, Percent):
            # A size hint is only consulted when the layout asks, so this only
            # has to invalidate it rather than push a number anywhere.
            self.updateGeometry()

    # -- folding ---------------------------------------------------------

    def isExpanded(self):
        return self._expanded

    def setExpanded(self, expanded):
        expanded = bool(expanded)
        if expanded == self._expanded:
            # Still re-sync the button: this is also the toggled() handler, and
            # a programmatic setExpanded must not fight the user's click.
            self.header.setChecked(expanded)
            return

        self._expanded = expanded
        self.hostWidget.setVisible(expanded)
        self.header.setChecked(expanded)
        self.header.setText('%s  %s' % (self._ARROWS[int(expanded)],
                                        self.hostTitle))

        self._applyMaxHeight()
        self.toggled.emit(expanded)

    def headerHeight(self):
        """How tall this host is when folded - the header row alone."""
        return self.headerRow.sizeHint().height()


class SectionHost(_CollapsibleHost):
    """One collapsible section in slice 2 (Block D-c, phase D-c.6).

    Closable by default: a section is something the user asked to see - the undo
    history, D-d's collab chat - so it needs a way back out that is not the menu
    it came from.
    """

    def __init__(self, title, widget, parent=None, closable=True,
                 default_height=UNLIMITED, max_height=UNLIMITED):
        super().__init__(title, widget, parent, closable=closable,
                         default_height=default_height, max_height=max_height)

    # Kept as aliases: the sections were written against these names before the
    # base class existed, and renaming call sites to prove a refactor happened
    # is the kind of churn that hides real changes in a diff.
    @property
    def sectionTitle(self):
        return self.hostTitle

    @property
    def sectionWidget(self):
        return self.hostWidget


class PanelHost(_CollapsibleHost):
    """Holds one slice-3 panel and answers the QDockWidget API used on it.

    Only the three members the editor actually calls on these docks:
    ``setVisible``, ``isVisible`` and ``isFloating``. Deliberately not a general
    dock emulation - a partial imitation that covers the real call sites is
    honest, whereas one that looks complete invites code to rely on parts that
    were never tested.

    ``isFloating`` answers False forever: the point of the sub-block is that
    these panels are docked, and the one caller (spriteeditor.py, minimising a
    floating editor's height) is asking exactly that question.

    **Collapsing is not hiding**, and the distinction matters here more than in
    slice 2. Twenty call sites show and hide these panels by selection - pick a
    sprite, the sprite editor appears - and folding must not disturb any of
    them: a folded panel is still ``isVisible()``, because the editor's question
    is "does this panel apply to what is selected", not "how tall is it".

    No close button: these are not panels the user opened, so there is nothing
    coherent for an X to do (Zement, 2026-08-30).
    """

    visibilityChanged = QtCore.pyqtSignal(bool)

    def __init__(self, title, widget, parent=None,
                 default_height=UNLIMITED, max_height=UNLIMITED):
        super().__init__(title, widget, parent, closable=False,
                         default_height=default_height, max_height=max_height)

        super().setVisible(False)

    @property
    def panelTitle(self):
        return self.hostTitle

    @property
    def panelWidget(self):
        return self.hostWidget

    def setVisible(self, visible):
        changed = bool(visible) != self.isVisible()
        super().setVisible(bool(visible))
        if changed:
            self.visibilityChanged.emit(bool(visible))

    def isFloating(self):
        """Always False - a hosted panel is docked by construction."""
        return False


class SectionGrip(QtWidgets.QWidget):
    """The drag handle under a section, for resizing it by hand (D-d.3d).

    A splitter gave these for free, and losing them was the one thing the
    scroll-area rewrite took away that was worth keeping (Zement, 2026-09-01:
    "the gripper to *manually* resize the panels is now gone... please bring
    back the gripper"). So they come back explicitly, and this time what the
    user drags to is **remembered** - the splitter never saved section heights,
    only slice 3's panel division, so a dragged column came back at its defaults
    on the next launch.

    Drawn as a splitter handle so it looks like the one it replaces, and it
    carries the same resize cursor.
    """

    #: How thin a section may be dragged: its header, and a little to grab.
    MIN_SECTION_HEIGHT = 40

    def __init__(self, host, column):
        super().__init__(column.body())

        self.host = host
        self.column = column
        self._pressY = None
        self._startHeight = None

        self.setCursor(QtCore.Qt.CursorShape.SplitVCursor)
        self.setFixedHeight(6)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding,
                           QtWidgets.QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        """Draw the platform's own splitter handle, so it looks native."""
        painter = QtWidgets.QStylePainter(self)
        option = QtWidgets.QStyleOptionFrame()
        option.initFrom(self)
        painter.drawPrimitive(
            QtWidgets.QStyle.PrimitiveElement.PE_IndicatorDockWidgetResizeHandle,
            option)

    def mousePressEvent(self, event):
        if event.button() != QtCore.Qt.MouseButton.LeftButton:
            return super().mousePressEvent(event)

        self._pressY = event.globalPosition().y()
        self._startHeight = self.host.height()

        # Freeze every host at the height it is showing, for the duration.
        #
        # Without this a drag only moved the *slack holder*, because that is the
        # one host the layout is free to resize - everything else is pinned to
        # its size hint, so asking a non-holder to grow changed a number nothing
        # acted on (Zement, 2026-09-01: "when I try to resize the Game Patches
        # panel via the splitter, at first it doesn't resize at all... this is
        # not the case for the other panels"). Game Patches happened to be
        # above the undo history, which was the holder; the panels that "worked"
        # were the holder itself.
        #
        # Freezing is also what a splitter does: while you are dragging one
        # boundary, the others stay where they are.
        self.column.beginDrag()
        event.accept()

    def mouseMoveEvent(self, event):
        if self._pressY is None:
            return super().mouseMoveEvent(event)

        delta = event.globalPosition().y() - self._pressY

        # A press with no real movement is a click, not a drag. Without this a
        # stray click would stamp the host's current height as a chosen one and
        # write it to settings, where it would then outrank the configured
        # default for good.
        if abs(delta) < 1:
            return

        wanted = max(self.MIN_SECTION_HEIGHT, int(self._startHeight + delta))

        # Straight to the host's own default height, which is what the layout
        # gives it - so a drag and a configured height are the same mechanism
        # rather than two that can disagree.
        self.host.setDraggedHeight(wanted)

        # `_rebuild`, not `refreshLayout`: the wanted height is enforced as a
        # real minimum on each host (see `_rebuild`), and only that re-applies
        # it. Refreshing the layout alone left the old minimum in place, so the
        # host held its previous height however far the grip was dragged.
        self.column.applyHeights()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._pressY is None:
            return super().mouseReleaseEvent(event)

        self._pressY = None
        self._startHeight = None
        self.column.endDrag()
        self.column.sectionResized.emit()
        event.accept()


class SectionColumn(QtWidgets.QScrollArea):
    """The vertical stack of sections in slice 2, which **scrolls** (D-d.3d).

    Was a `QSplitter` from D-c.6 until here, and that was the wrong container.
    A splitter's entire job is to divide its extent among its children: every
    child is always sized so the total exactly fills it. Right for two panes a
    user drags between; wrong for a stack of panels that each want a natural
    height. All three of Zement's layout bugs (2026-09-01) fell out of that one
    choice:

    - panels **shrank** rather than scrolling, because a splitter has no scroll
      and so must make its contents fit
    - **folding one freed no space**, because the folded host still held the
      height the splitter had given it
    - folding **all** of them collapsed the whole sidebar, because the cap that
      handled that case set a *maximum height* on the stacked-widget page - and
      since D-d.2b that page is a horizontal sibling of the rail, so capping its
      height capped the sidebar's

    So this is a scroll area over a plain vertical layout. Hosts keep the height
    they ask for; if the stack is taller than the viewport there is a scrollbar,
    and if it is shorter the bottom-most expanded host takes up the slack
    (Zement's choice, over leaving a visible gap).

    A `SectionGrip` sits under each host, so the heights are still draggable -
    that is what a splitter gave for free, and it was worth keeping.

    Keeps a splitter-shaped surface - ``count``, ``sectionAt``, ``indexOf``,
    ``insertWidget`` - because that is genuinely what the sidebar wants from it:
    an ordered stack addressed by position. The methods are not a shim for the
    splitter; they are the container's own vocabulary, and the splitter happened
    to share it.
    """

    #: Emitted when the user finishes dragging a grip, so the sidebar can save.
    sectionResized = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # **Not** `setWidgetResizable(True)`. That stretches the inner widget to
        # the viewport in *both* axes, so the stack could never be taller than
        # the view and so could never scroll - measured: two hosts asking for
        # 70% and 40% still came out at 591 + 253 = exactly the viewport.
        #
        # Instead the width is matched by hand in `resizeEvent` and the height
        # is left to the layout, which is the whole point: the body is as tall
        # as its hosts ask to be, and the scroll area scrolls when that is more
        # than it can show.
        self.setWidgetResizable(False)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        self._body = QtWidgets.QWidget(self)
        self._layout = QtWidgets.QVBoxLayout(self._body)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)

        #: The hosts, in order. Kept as a list rather than read back out of the
        #: layout, because the layout also holds a grip after each host and a
        #: tail stretch - so "what is in the layout" and "what the sidebar put
        #: here" stopped being the same question once the grips arrived.
        self._hosts = []
        self._grips = {}
        self._slackHolder = None

        self.setWidget(self._body)
        self._rebuild()

    def body(self):
        """The widget the hosts are laid out in. A grip parents itself here."""
        return self._body

    # -- building --------------------------------------------------------

    def _rebuild(self):
        """Lay the hosts out again, with a grip under each.

        Rebuilt wholesale on every change rather than patched: the stack is a
        handful of widgets, and the alternative is index arithmetic over a
        layout holding two kinds of thing, which is exactly the sort of code
        that goes subtly wrong when a section is inserted in the middle.
        """
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)

        holder = self._slackHolder

        for host in self._hosts:
            host.setParent(self._body)
            self._layout.addWidget(host)
            host.setVisible(True)

            # The height a host asks for has to be a *minimum*, not a hint.
            #
            # A QVBoxLayout squeezes a `Preferred` child to give a stretched
            # sibling more, and a `Minimum` child's floor is its
            # `minimumSizeHint`, not its `sizeHint` - so Game Patches sat at
            # 357px against a 422px hint, its floor being 191. That is both of
            # Zement's symptoms at once (2026-09-01): "the Game Patches panel
            # doesn't seem to be 50% of the slice height", and dragging it did
            # nothing until the drag had made up the 65px shortfall.
            #
            # So the wanted height is pushed in as a real minimum. The slack
            # holder is the exception: it is the one host allowed to grow past
            # what it asked for, which is what makes it the holder.
            host.setSizePolicy(
                QtWidgets.QSizePolicy.Policy.Preferred,
                QtWidgets.QSizePolicy.Policy.Expanding if host is holder
                else QtWidgets.QSizePolicy.Policy.Fixed)

            grip = self._grips.get(host)
            if grip is None:
                grip = SectionGrip(host, self)
                self._grips[host] = grip

            grip.setParent(self._body)
            self._layout.addWidget(grip)

            # No point offering to resize a folded section: it is its header,
            # and dragging it taller would only reveal a hidden body.
            grip.setVisible(host.isExpanded())

        # The tail stretch is what stops a short stack from spreading itself
        # over the whole viewport. Left out when a host is claiming the slack.
        holder = self._slackHolder
        if holder is not None and holder in self._hosts:
            self._layout.setStretchFactor(holder, 1)
        else:
            self._layout.addStretch(1)

        self.applyHeights()

    # -- geometry --------------------------------------------------------

    def resizeEvent(self, event):
        """Keep the body as wide as the viewport, and as tall as it wants.

        The half of `setWidgetResizable(True)` that is wanted here. Without the
        width being matched the body sits at its own size hint and the sections
        are narrower than the column; with the *height* matched too, nothing
        could ever overflow and the column could not scroll.
        """
        super().resizeEvent(event)
        self._relayout()

    def _wantedHeight(self):
        """How tall the stack actually is, measured from the hosts.

        **Not** `self._body.sizeHint()`, which was the first version and was
        wrong: a layout holding a stretch item reports a hint far larger than
        its contents (measured - two hosts wanting 675 + 506 px produced a hint
        of 4158). The body then never shrank back, so folding a section freed
        space that nothing could see.

        Adding up the hosts and their grips is the honest measurement, and it is
        a handful of integers.
        """
        total = 0
        for host in self._hosts:
            total += (host.sizeHint().height() if host.isExpanded()
                      else host.headerHeight())

            grip = self._grips.get(host)
            if grip is not None and host.isExpanded():
                total += grip.height()

        return total

    def _relayout(self):
        width = self.viewport().width()
        height = max(self._wantedHeight(), self.viewport().height())
        self._body.resize(width, height)

        # Re-run the layout explicitly. `resize` only triggers it when the size
        # actually changes, so a host whose *hint* changed inside an unchanged
        # body kept its old height - which is why Game Patches ignored its
        # configured 50% and then ignored the first part of every drag (Zement,
        # 2026-09-01). `activate()` is the layout's own "do it now".
        layout = self._body.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()

    def refreshLayout(self):
        """Re-measure after the hosts' wanted heights change.

        A fold, an unfold, an added section, or a percentage height re-resolved
        by a sidebar resize. With `setWidgetResizable(False)` nothing does this
        on its own - the body only changes size when told to.
        """
        self._relayout()

    # -- the ordered-stack surface ---------------------------------------

    def count(self):
        """How many hosts are stacked."""
        return len(self._hosts)

    def sectionAt(self, index):
        """The host at ``index``, or None.

        **Not** ``widget(index)``, which is what a QSplitter calls this: a
        QScrollArea already has a no-argument ``widget()`` returning the widget
        it scrolls, and Qt calls that itself. Overriding it with a different
        signature broke the scroll area from the inside.
        """
        return self._hosts[index] if 0 <= index < len(self._hosts) else None

    def hosts(self):
        """Every host, top to bottom."""
        return list(self._hosts)

    def gripFor(self, host):
        """The drag handle under ``host``, or None."""
        return self._grips.get(host)

    def indexOf(self, host):
        """``host``'s position, or -1. Matches QSplitter's contract."""
        return self._hosts.index(host) if host in self._hosts else -1

    def insertWidget(self, index, host):
        """Put ``host`` at ``index``, moving it if it is already here."""
        if host in self._hosts:
            self._hosts.remove(host)

        self._hosts.insert(min(index, len(self._hosts)), host)
        self._rebuild()

    def removeWidget(self, host):
        if host in self._hosts:
            self._hosts.remove(host)

        grip = self._grips.pop(host, None)
        if grip is not None:
            grip.setParent(None)
            grip.deleteLater()

        if self._slackHolder is host:
            self._slackHolder = None

        self._rebuild()

    def handleWidth(self):
        """Zero: a layout has no drag handles between its children.

        Kept because the width arithmetic asks, and answering 0 is truer than
        making every caller know which container is in use.
        """
        return 0

    # -- slack -----------------------------------------------------------

    def setSlackHolder(self, host):
        """Give leftover space to ``host``, or to the tail stretch when None.

        Zement, asked and answered 2026-09-01: when the stack is shorter than
        the viewport, the bottom-most expanded panel absorbs what is left rather
        than the column showing dead space under it.

        Done with layout stretch rather than a computed height, so the layout
        keeps it right through every resize with nothing to keep in step.
        """
        self._slackHolder = host if host in self._hosts else None
        self._rebuild()

    def applyHeights(self):
        """Push each host's wanted height back in as its minimum, and re-lay.

        The cheap half of `_rebuild`: the stack has not changed, only what its
        members want. Used by a drag, which changes one wanted height per mouse
        move and must not rebuild the whole column each time.
        """
        holder = self._slackHolder

        for host in self._hosts:
            if host is holder:
                host.setMinimumHeight(0)
                continue

            host.setMinimumHeight(
                host.sizeHint().height() if host.isExpanded()
                else host.headerHeight())

        self.refreshLayout()

    def beginDrag(self):
        """Pin every host at its shown height while one is being dragged.

        Only the slack holder is free to resize under normal layout - every
        other host is held at its size hint - so dragging a non-holder taller
        changed a number nothing acted on. Recording each host's *current*
        height as its wanted one puts them all on the same footing, and taking
        the slack away means the space the dragged host claims comes out of the
        column's total rather than being absorbed silently.
        """
        self._dragHolder = self._slackHolder

        for host in self._hosts:
            if host.isExpanded():
                host.setDraggedHeight(host.height(), restored=True)

        self.setSlackHolder(None)

    def endDrag(self):
        """Give the slack back to whichever host was holding it."""
        holder, self._dragHolder = getattr(self, '_dragHolder', None), None
        self.setSlackHolder(holder)

    def ensureVisible(self, host):
        """Scroll ``host`` into view, fully if it fits.

        Zement: "we should make certain that an activated panel moves into view
        and is fully visible".
        """
        if host is not None and host in self._hosts:
            self.ensureWidgetVisible(host)


class _CentredIconDelegate(QtWidgets.QStyledItemDelegate):
    """Draws a rail row's icon centred, and nothing else (D-d.1c).

    The rail is a `ListMode` view of icon-only rows. Qt left-aligns a
    decoration there and gives the decoration its own sub-rectangle inside the
    row, which is what produced both halves of Zement's report on 2026-08-31:
    the icon sat left of centre, and the edge of that sub-rectangle showed as a
    darker band inside the selection highlight.

    There is no `Qt.TextAlignmentRole` equivalent for decorations, so the fix
    is to paint the background through the style (keeping the platform's own
    selection and hover look, full row width) and then place the pixmap in the
    middle by hand.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        #: Where the last icon was drawn, or None before the first paint.
        self.lastIconRect = None

    def paint(self, painter, option, index):
        # Let the style paint the row itself - selection, hover and focus - so
        # the rail still looks native and the highlight covers the whole row.
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        # The icon is drawn below, so hand the style an empty row. Left in and
        # it would draw the off-centre copy this delegate exists to replace.
        opt.icon = QtGui.QIcon()
        opt.text = ''
        opt.features &= ~QtWidgets.QStyleOptionViewItem.ViewItemFeature.HasDecoration

        widget = opt.widget
        style = widget.style() if widget is not None else QtWidgets.QApplication.style()
        style.drawControl(QtWidgets.QStyle.ControlElement.CE_ItemViewItem,
                          opt, painter, widget)

        icon = index.data(QtCore.Qt.ItemDataRole.DecorationRole)
        if icon is None or icon.isNull():
            return

        size = option.decorationSize
        rect = option.rect

        # actualSize, not the requested size: an icon with no source large
        # enough returns what it really has, and centring on the requested box
        # would leave it off-centre by the difference.
        actual = icon.actualSize(size)
        x = rect.x() + (rect.width() - actual.width()) // 2
        y = rect.y() + (rect.height() - actual.height()) // 2

        mode = QtGui.QIcon.Mode.Normal
        if not (option.state & QtWidgets.QStyle.StateFlag.State_Enabled):
            mode = QtGui.QIcon.Mode.Disabled
        elif option.state & QtWidgets.QStyle.StateFlag.State_Selected:
            mode = QtGui.QIcon.Mode.Selected

        target = QtCore.QRect(x, y, actual.width(), actual.height())

        #: Where the last icon was drawn. Read by the rail's test suite, which
        #: cannot measure this from a rendered image - the offscreen style
        #: paints the whole row, so nothing in the pixels separates the icon
        #: from its highlight.
        self.lastIconRect = QtCore.QRect(target)

        icon.paint(painter, target, QtCore.Qt.AlignmentFlag.AlignCenter, mode)


class Sidebar(QtWidgets.QWidget):
    """The window's docked sidebar: the icon rail, its pages, and the panels.

    Built as a plain widget rather than a QDockWidget on purpose. The point of
    the phase is that this cannot be floated, closed or dragged to the bottom,
    and the cheapest way to guarantee that is for it not to be a dock at all.
    The window puts it beside the master container in a splitter.
    """

    def __init__(self, window):
        super().__init__(window)

        self.win = window
        self._panels = []
        self._panelStretches = []
        self._side = configured_side()

        # slice 1 - the icon rail.
        # ListMode, not IconMode (fixed D-d.1b). In IconMode an item is laid out
        # around its icon and the selection rectangle follows the *item*, which
        # sat visibly off-centre against the icon it was meant to highlight
        # (Zement, 2026-08-31). These entries are icon-only rows in a
        # fixed-width column - a list, not an icon grid - and ListMode gives
        # each row the full width, so the highlight lines up by construction.
        self.rail = QtWidgets.QListWidget(self)
        self.rail.setViewMode(QtWidgets.QListView.ViewMode.ListMode)
        self.rail.setMovement(QtWidgets.QListView.Movement.Static)
        self.rail.setFlow(QtWidgets.QListView.Flow.TopToBottom)
        self.rail.setWrapping(False)

        # Scaled from the rail width rather than fixed at 24 (D-d.1c), so the
        # icon actually grows with the 32/48/64 setting instead of only its row
        # growing around it.
        _icon = rail_icon_size()
        self.rail.setIconSize(QtCore.QSize(_icon, _icon))
        self.rail.setFixedWidth(rail_width())
        self.rail.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rail.setVerticalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # No text is ever set on a rail item - the label lives in the tooltip -
        # so nothing here has to stay readable against the highlight. That was
        # the second half of the same report: a highlighted label would have
        # been unreadable, and the answer is that there is no label.
        self.rail.setWordWrap(False)
        self.rail.setTextElideMode(QtCore.Qt.TextElideMode.ElideNone)
        self.rail.setUniformItemSizes(True)

        # A ListMode row left-aligns its decoration, so the icon sat against the
        # left edge of a full-width row - visible as an off-centre icon, and as
        # a darker rectangle where the icon box ended inside the highlight
        # (Zement, 2026-08-31, clearest at 64px). Qt offers no alignment role
        # for a decoration, so the delegate draws it centred itself.
        self.rail.setItemDelegate(_CentredIconDelegate(self.rail))

        self.rail.currentRowChanged.connect(self._handleRailChanged)

        # Watched for mouse presses, so `_clickRow` is the row that was
        # highlighted *before* the click - see `_handleRailClicked`.
        self.rail.viewport().installEventFilter(self)

        # And on a click, even when the row does not change. `currentRowChanged`
        # fires only on a *change*, which was enough while every entry had a
        # page of its own: clicking the current entry showed what was already
        # shown. Since D-d.2c four entries share the sections page, so the
        # highlight can sit on one entry while another's section is open - and
        # clicking the highlighted one has to open its section rather than do
        # nothing (Zement, 2026-09-01).
        #
        # `itemClicked` rather than `itemPressed`: a press that turns into a
        # drag off the rail should not count.
        self.rail.itemClicked.connect(self._handleRailClicked)

        # slice 2 - one page per rail entry: the directory listing, the game
        # patch list, the undo history, the collab chat.
        #
        # **Its own vertical slice, beside the panels rather than above or below
        # them** (Zement, 2026-08-31). It was stacked under slice 3 from D-c.6
        # until D-d.2b, which was the right answer while the only content was a
        # single undo history and the wrong one the moment a directory listing
        # arrived: the tree and the property panels are both tall, both wanted at
        # once, and stacked they are zero-sum - Zement's live test found the
        # endpoint, where dragging the divider pushes one of them entirely out of
        # sight. Side by side they compete for *width*, which the sidebar has
        # more of and which is set once and left alone.
        self.pages = QtWidgets.QStackedWidget(self)
        self.pages.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                                 QtWidgets.QSizePolicy.Policy.Expanding)
        self.pages.setMinimumWidth(MIN_SLICE_TWO_WIDTH)

        # Slice 2's default page is a scrolling column of collapsible sections
        # rather than one widget per rail entry (Zement, 2026-08-30). The reason
        # is what the content turns out to be: the undo history, the collab chat
        # and the directory listing are all things a user wants *at the same
        # time*, sized to taste - which is the VS Code Explorer shape, not a
        # stack where reading one hides the others.
        #
        # A `SectionColumn` since D-d.3d, a `QSplitter` before that - see that
        # class for why the splitter was the wrong container and what it cost.
        #
        # The stack stays underneath, because D-d may still want a genuinely
        # separate rail page for something that owns the whole slice. Sections
        # are simply what its first page holds.
        self.sections = SectionColumn()
        self._sections = []

        # host -> is it context-sensitive. A dict rather than a third element in
        # the `_sections` tuples, so the many places that unpack
        # `(host, stretch)` keep working.
        self._sectionContext = {}

        # host -> is it pinned above both bands (D-d.3c). Same reasoning, and
        # deliberately a second dict rather than one three-valued field: a
        # section is pinned *or* context *or* neither, but the two questions are
        # asked in different places and merging them would make every reader
        # decode an enum to ask one of them.
        self._sectionPinned = {}

        #: title -> the height the user dragged that section to (D-d.3d). Kept
        #: here as well as in settings so a section closed and re-opened within
        #: one run comes back at the height it was given, not only across a
        #: restart. Filled by restoreSectionHeights on the way up.
        self._draggedHeights = {}

        self.sections.sectionResized.connect(self.saveSectionHeights)
        self.pages.addWidget(self.sections)

        # Rail row -> page widget, and rail row -> callback. A row may have
        # either, both or (for an action entry like Preferences) only the
        # callback; see addPage. Parallel lists rather than a dict because the
        # rail is addressed by row and both are appended together.
        self._railPages = []
        self._railActions = []

        # Rail row -> a predicate answering "is this entry's own section the one
        # currently showing?", or None. Only the owner can answer that: the
        # sidebar sees an anonymous list of sections and cannot tell which entry
        # any of them belongs to. Used to stop a click on the showing entry
        # rebuilding its section (D-d.2c).
        self._railOwns = []

        # The last row that actually selected a page, so an action entry can
        # hand the highlight back rather than leaving it on a button.
        self._lastPageRow = None

        # The rail's current row at the moment the mouse went down, captured
        # before any handler can move it. `_handleRailClicked` compares against
        # it to tell "this click changed the row" - already handled by
        # currentRowChanged - from "this click was on the row already
        # highlighted", which is the case that signal never reports and which
        # this handler exists for. See `_handleRailClicked` and `eventFilter`.
        self._clickRow = None

        # The rail row currently running its activation callback, so a section
        # that callback opens knows which entry to highlight. Set and cleared
        # around the callback in `_handleRailChanged`; None at every other time,
        # which is when `showSections` falls back to inference.
        self._pendingOwnerRow = None

        # The width _restoreWidth had to cut the saved value down to, or None
        # when it did not have to. saveLayout reads it so a clamped width is
        # never written back over the wider one the user chose (D-d.1b).
        self._clampedWidth = None

        # slice 3 - the palette and the property panels, stacked vertically and
        # scrollable: four property editors plus the palette is more than fits
        # in most windows, and a panel that cannot be reached is worse than one
        # that needs scrolling to.
        self.panelArea = QtWidgets.QWidget(self)
        self._panelLayout = QtWidgets.QVBoxLayout(self.panelArea)
        self._panelLayout.setContentsMargins(2, 2, 2, 2)
        self._panelLayout.setSpacing(4)
        self._panelLayout.addStretch(0)

        self.panelScroll = QtWidgets.QScrollArea(self)
        self.panelScroll.setWidgetResizable(True)
        self.panelScroll.setWidget(self.panelArea)
        self.panelScroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.panelScroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # Slice 3 is a vertical splitter holding only the panel scroll area.
        #
        # It held slice 2 as well until D-d.2b, when slice 2 became a column of
        # its own; a splitter with one child is a plain container. Kept as a
        # splitter rather than flattened to the scroll area because the saved
        # `SidebarColumnSizes`, `_resizeColumn` and the whole "vertical division
        # inside slice 3" idea are what D-d.5 will use to put the Default
        # Properties panel below the palette. Flattening now would delete the
        # mechanism and then need it rebuilt two phases later.
        self.column = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, self)
        self.column.addWidget(self.panelScroll)
        self.column.setStretchFactor(0, 1)

        # Whether the user has dragged the column divider. Once they have, their
        # division is the one that stands: _resizeColumn stops recomputing, and
        # a restored saved split counts as dragged for the same reason.
        self._columnDragged = False
        self.column.splitterMoved.connect(self._handleColumnDragged)

        # "Empty means absent" - unchanged from D-c.6, but now it buys back
        # *width* rather than height. With no sections open the sidebar is the
        # rail plus the panels, exactly as it was before D-d.
        self.pages.setVisible(False)

        # Whether the user has dragged the slice 2 / slice 3 divider. Same rule
        # as the column: once they have, _resizeColumn leaves the width alone.
        self._widthDragged = False

        # A width restoreLayout read from settings but could not spend yet,
        # because slice 2 was still hidden. Applied by _applySliceWidth the
        # first time slice 2 is shown, then cleared.
        self._savedSliceWidth = None

        # The last width slice 2 actually had, whether computed or dragged. A
        # hidden splitter child keeps no width, so this is what re-opening a
        # section restores it to - without it the slice comes back at its
        # minimum however wide the user had made it.
        self._lastSliceWidth = None

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.splitterMoved.connect(self._handleSliceDragged)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

        self._layOutSlices()

    # -- slice order -----------------------------------------------------

    def _layOutSlices(self):
        """Insert the three slices in the order this side calls for.

        A QSplitter is ordered by insertion, so flipping sides is re-inserting
        rather than rebuilding - which is why this is a loop and not a second
        constructor. The rail stays outermost either way, so it is against the
        window edge on both sides rather than sitting in the middle.

        Reversing the whole list rather than only moving the rail is deliberate:
        the order is rail, then slice 2, then the panels, reading *inward* from
        the window edge. On the right that is the mirror image, so the panels
        stay next to the canvas on both sides - which is where the thing you are
        editing wants its property editors.
        """
        ordered = [self.rail, self.pages, self.column]
        if self._side == SIDE_RIGHT:
            ordered.reverse()

        # insertWidget at a rising index, not addWidget: a QSplitter moves a
        # widget it already holds rather than adding a second copy, so this
        # reorders on a flip and fills on the first call, with one code path.
        for index, widget in enumerate(ordered):
            self.splitter.insertWidget(index, widget)

        # The rail is fixed-width and takes no stretch; slice 2 and the panels
        # share what is left. Both get a stretch factor so a sidebar resize is
        # divided between them rather than landing entirely on one - the widths
        # themselves are set by _resizeSlices and by the user's drag.
        for index, widget in enumerate(ordered):
            self.splitter.setStretchFactor(index, 0 if widget is self.rail else 1)

    @property
    def side(self):
        return self._side

    def applySide(self, side=None):
        """Reorder this widget's own slices for ``side``. Returns True if moved.

        Only the slices. Where the sidebar itself sits in the window is
        ``ReggieWindow.PlaceSidebar``'s business, and that method calls this one
        - so calling back into it here would be mutual recursion.
        """
        wanted = configured_side() if side is None else side
        if wanted == self._side:
            return False

        self._side = wanted
        self._layOutSlices()
        return True

    # -- slice 1 / 2 -----------------------------------------------------

    def _railItemSize(self):
        """The size one rail row should claim.

        Derived from the configured rail width rather than a fixed 40x40
        (D-d.1b). The rail can be 32, 48 or 64 px wide, and a row narrower than
        the rail is what left the selection highlight not covering its icon.
        Full width, square-ish height, and the icon centres itself inside it.
        """
        width = self.rail.width() or rail_width()

        # The viewport is the rail minus its frame; claiming the full rail width
        # would overflow it and bring back a horizontal scrollbar.
        frame = self.rail.frameWidth() * 2
        width = max(16, width - frame)

        return QtCore.QSize(width, max(width, self.rail.iconSize().height() + 8))

    def _resizeRailItems(self):
        """Re-apply the row size after the rail's width changes."""
        size = self._railItemSize()
        for row in range(self.rail.count()):
            self.rail.item(row).setSizeHint(size)

    def addPage(self, icon, title, widget=None, on_activate=None,
                sections=False, is_open=None):
        """Add a rail entry, and say what selecting it does.

        Three kinds of entry, because D-d needs all three (phase D-d.1):

        - ``widget`` - the entry owns a slice-2 page of its own. The original
          behaviour.
        - ``sections=True`` - the entry selects the **sections page**, the
          splitter of collapsible sections that slice 2 shows by default. This
          is what the Directory Listing and Logs/Undo entries want: their
          content is a section among others, not a page that hides the rest.
        - ``on_activate`` - the entry is an **action**, not a page. Preferences
          opens as a tool tab in the master container and has no sidebar page at
          all, so selecting it runs a callback and the rail selection springs
          back to where it was.

        ``on_activate`` composes with the other two: an entry may both show a
        page and do something when picked.

        ``is_open`` is an optional predicate answering "is this entry's own
        section the one currently showing?". Clicking an entry whose section is
        already up is then a no-op rather than a rebuild, which matters because
        a context section is re-created on open - rebuilding would discard the
        tree's scroll position, its expanded levels and the user's selection.
        Only the owner can answer it; the sidebar sees an anonymous list.
        """
        item = QtWidgets.QListWidgetItem(self.rail)
        if icon is not None:
            item.setIcon(icon)
        item.setToolTip(title)
        item.setSizeHint(self._railItemSize())
        item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        if sections:
            page = self.sections
        elif widget is not None:
            page = widget
            self.pages.addWidget(widget)
        else:
            page = None

        # Recorded rather than derived from the index. Since D-c.6 the stack
        # also holds the sections page, which has no rail entry of its own, so
        # "rail row N is page N" stopped being true - and a mapping that is
        # nearly right is how a rail ends up selecting the wrong page as D-d
        # adds entries.
        self._railPages.append(page)
        self._railActions.append(on_activate)
        self._railOwns.append(is_open)

        if self.rail.currentRow() < 0 and page is not None:
            self.rail.setCurrentRow(self.rail.count() - 1)

        return item

    def _handleRailChanged(self, row):
        if not (0 <= row < len(self._railPages)):
            return

        # So the itemClicked that follows a *changing* click knows this one is
        # already handled. See _handleRailClicked.
        self._changedRow = row

        page = self._railPages[row]

        if page is not None:
            self._lastPageRow = row

            # Told which row asked, so `addSection` -> `showSections` puts the
            # highlight on this entry rather than on the first entry that
            # happens to share the sections page.
            self._pendingOwnerRow = row

            self.pages.setCurrentWidget(page)

            # A page entry only makes slice 2 visible when it has something to
            # show. The sections page hides itself while it holds no sections
            # (see __init__), and overriding that here would put an empty
            # column beside the palette - the thing D-c.3 spent a phase fixing.
            if page is not self.sections or self._sections:
                was_hidden = not self.pages.isVisible()
                self.pages.setVisible(True)

                # Slice 2 arriving changes how the sidebar's width divides, and
                # a hidden splitter child cannot be sized - so the division is
                # computed here, the moment it can take one (D-d.2b).
                if was_hidden:
                    self._resizeColumn()

        action = self._railActions[row]
        if action is None:
            return

        # An action entry is a button wearing a list row. Leaving it selected
        # would say "you are here" about a place the rail cannot show, so the
        # selection goes back to the last real page.
        if page is None:
            self._restoreRailSelection(row)

        try:
            action()
        except Exception:
            # A rail entry must not be able to take the sidebar down with it -
            # the same rule the patch selector refresh follows.
            import traceback
            traceback.print_exc()
        finally:
            self._pendingOwnerRow = None

    def eventFilter(self, obj, event):
        """Note which row was highlighted when a rail click started.

        The rail's own selection has already moved by the time `itemClicked`
        arrives, and `currentRowChanged` may have fired again from inside the
        activation it triggered - so neither can answer "did *this* click
        change the row". The press can.
        """
        if (obj is self.rail.viewport()
                and event.type() == QtCore.QEvent.Type.MouseButtonPress):
            self._clickRow = self.rail.currentRow()

        return super().eventFilter(obj, event)

    def _handleRailClicked(self, item):
        """A rail row was clicked, whether or not it was already current.

        `currentRowChanged` covers the changing case; this covers the rest. Both
        land in the same handler, so an entry behaves identically however the
        selection got there.
        """
        row = self.rail.row(item)
        if row < 0:
            return

        # One click is one activation. When the click also *changes* the row,
        # `currentRowChanged` has already handled it and arrives first, so
        # running it again here would activate the entry twice - which for the
        # undo history's toggle meant opening and immediately closing it, so
        # the first click appeared to do nothing.
        #
        # The test is "did the row change *because of this click*", which is
        # what `_clickRow` answers: the rail's current row as it was when the
        # press landed, before any handler could move it.
        #
        # Recording it in `mousePressEvent` rather than remembering what
        # `currentRowChanged` last saw, because that signal also fires from
        # *inside* an activation - closing a section calls `showSections`,
        # which moves the highlight - so a flag set there outlives the click
        # that caused it and swallows the next one. That is why re-opening the
        # undo history took two clicks after closing it.
        if self._clickRow != row:
            return

        # Nor may re-clicking the entry that is *already showing* rebuild its
        # section: a context section is torn down and re-created on open, so
        # doing that would throw away the tree's scroll position, its expanded
        # levels and the user's selection for no gain. Only an entry whose
        # section is not up has anything to do here - which is exactly the case
        # the bug left unreachable.
        if self._sectionOwned(row):
            return

        self._handleRailChanged(row)

    def _sectionOwned(self, row):
        """Whether row ``row``'s own section is the one currently showing.

        Asked of the *owner* rather than of the sidebar, because only the owner
        knows which widget is its section - the sidebar sees an anonymous list.
        A row with no such callback answers False, which keeps the old
        behaviour for entries that have not opted in.
        """
        owns = self._railOwns[row] if row < len(self._railOwns) else None
        if owns is None:
            return False

        try:
            return bool(owns())
        except Exception:
            return False

    def _restoreRailSelection(self, row):
        """Move the rail's highlight off an action entry.

        Back to the previously selected page entry, or the first one there is.
        Blocked, or setCurrentRow re-enters this handler and re-runs whichever
        action we are stepping away from.
        """
        target = self._lastPageRow
        if target is None or not (0 <= target < len(self._railPages)) \
                or self._railPages[target] is None:
            target = next((i for i, p in enumerate(self._railPages)
                           if p is not None), None)

        if target is None or target == row:
            return

        blocked = self.rail.blockSignals(True)
        try:
            self.rail.setCurrentRow(target)
        finally:
            self.rail.blockSignals(blocked)

    def addSection(self, title, widget, stretch=1, closable=True,
                   on_close=None, default_height=UNLIMITED,
                   max_height=UNLIMITED, context=False, pinned=False,
                   key=None):
        """Add a collapsible section to slice 2. Returns its ``SectionHost``.

        Sections stack vertically in a splitter, so several are visible at once
        and the user decides how the column is divided. ``stretch`` is the share
        of leftover space this one claims - a list-like section wants it, a
        fixed-height form does not.

        ``on_close`` is called when the header's X is pressed. Without one the X
        simply removes the section, which is right for a view the sidebar owns;
        the undo history passes its own handler so the menu tick stays in step,
        and D-d's collab section will pass one so closing the chat does not end
        the session.

        ``context`` marks the section **context-sensitive** (Zement's model,
        2026-09-01):

        - *context-sensitive* sections are mutually exclusive and sit at the
          top. Opening one closes the one before it. Game Patches, Directory
          Listing and Help are the set today.
        - *always-open* sections stack below them in the order they were opened
          and survive every context switch, including having no context section
          open at all. The undo history is the one today; logs and the collab
          chat are planned.

        ``pinned`` puts the section above *both* kinds and keeps it there
        (D-d.3c). It is a third thing again: not something the user picks, but
        something that appears because the editor's state calls for it - the
        unsaved-levels list is the one today. A pinned section cannot be
        expressed as ``context=True``, because that would make it mutually
        exclusive with the directory listing it is meant to sit above; nor as a
        plain always-open one, because those stack *below* the context section,
        and a later context section would push a pinned one down.

        This replaced an accidental split where Game Patches was a rail *page*
        (a `QStackedWidget` entry) while the tree and the undo history were
        sections. Two mechanisms that looked alike produced exactly the
        confusion Zement reported: the patch list had no section header because
        it was not a section, and the undo history appeared "attached to" the
        directory listing because a page replaced the whole splitter while a
        section merely joined it.
        """
        if context:
            # Mutually exclusive, and closed rather than hidden: a context
            # section is cheap to rebuild and its owner re-creates it on the
            # next activation, so keeping stale ones around would only make
            # `_sections` disagree with what is on screen.
            for existing, _stretch in list(self._sections):
                if self._sectionContext.get(existing):
                    self._closeSection(existing)

        host = SectionHost(title, widget, self.sections, closable=closable,
                           default_height=default_height,
                           max_height=max_height)

        # ``key`` names the section for the purpose of remembering its dragged
        # height, when its *title* is not stable enough to do it - the undo
        # history's names the level and area it is showing, so it changes on
        # every switch and a height saved under one would never be found again.
        if key is not None:
            host.setSectionKey(key)

        # The vertical policy is set by `SectionColumn._rebuild`, which is the
        # one place that knows which host is currently absorbing slack.

        # A height the user dragged this section to in an earlier session, or
        # earlier in this one, wins over the configured default (D-d.3d).
        self.applySectionHeight(host)

        if on_close is not None:
            host.closeRequested.connect(on_close)
        else:
            host.closeRequested.connect(lambda: self.removeSection(host))

        self._sectionContext[host] = bool(context)
        self._sectionPinned[host] = bool(pinned)

        # Three bands, top to bottom: pinned, context, always-open. Pinned and
        # context each hold at most one section today, so "the top of my band"
        # is found by counting the sections in the bands above it rather than
        # by sorting - which also keeps the always-open ones in their arrival
        # order, the property that makes the column stable to look at.
        if pinned:
            position = 0
        elif context:
            position = sum(1 for h, _s in self._sections
                           if self._sectionPinned.get(h))
        else:
            position = len(self._sections)

        self.sections.insertWidget(position, host)
        self._sections.insert(position, (host, stretch))

        host.toggled.connect(lambda _on: self._applySectionStretch())
        self._applySectionStretch()

        # Bring the sections page forward as well as making slice 2 visible
        # (D-d.1). Before the rail had entries the stack only ever showed this
        # page, so setVisible was enough; now a rail entry may have selected a
        # page of its own, and adding a section would otherwise reveal slice 2
        # still showing that other page - the section apparently ignored.
        self.showSections()

        # Size the column for the new total. Deliberately here and in
        # removeSection, but NOT on fold: folding should give its space to slice
        # 3 and leave it there, and re-running this would take it straight back.
        # Adding and removing change what slice 2 *is*; folding only changes how
        # much of itself it is showing.
        self._resizeColumn()

        # Scroll the new section into view (D-d.3d). Zement: "we should make
        # certain that an activated panel moves into view and is fully
        # visible" - which only became possible to get wrong once the column
        # could be taller than its viewport. Deferred a tick, because the
        # layout has not placed the host yet and a scroll to where it is *not*
        # would land somewhere arbitrary.
        QtCore.QTimer.singleShot(0, lambda: self.sections.ensureVisible(host))

        return host

    def showSections(self, owner_row=None):
        """Bring the sections page to the front of slice 2, and show it.

        ``owner_row`` is the rail row that asked for this, so the highlight
        lands on the entry the user actually picked.

        **It used to be inferred**, as "the first entry whose page is the
        sections page" - which was right while exactly one entry owned that
        page, and wrong the moment D-d.2c gave Game Patches, Directory Listing,
        Logs/Undo and Help the same one. All four then parked the highlight on
        row 0, and since `setCurrentRow` emits nothing when the row is already
        current, clicking Game Patches became a no-op: the rail said "you are
        on Game Patches" while showing the directory listing (Zement,
        2026-09-01 - "Game Patches can not be opened via the rail button",
        except right after Logs/Undo, which is an action that leaves the
        highlight elsewhere).

        Passing None keeps the old inference, which is still right for the one
        caller that has no row of its own: `addSection`, where the section may
        be opened by a menu entry rather than by the rail.
        """
        was_hidden = not self.pages.isVisible()

        self.pages.setCurrentWidget(self.sections)
        self.pages.setVisible(bool(self._sections))

        # Slice 2 coming back from hidden needs the width re-divided, and a
        # hidden splitter child cannot be sized - so this is the first moment it
        # can take one. Without it, re-opening the directory listing after
        # closing every section restored a zero-width slice: the section was
        # there and visible, and had no room to be seen in (Zement, 2026-09-01 -
        # "pressing Directory Listing in the rail does not bring it back").
        if was_hidden and self.pages.isVisible():
            self._resizeColumn()

        row = owner_row if owner_row is not None else self._pendingOwnerRow
        if row is None or not (0 <= row < len(self._railPages)) \
                or self._railPages[row] is not self.sections:
            row = next((i for i, p in enumerate(self._railPages)
                        if p is self.sections), None)

        if row is None or self.rail.currentRow() == row:
            return

        blocked = self.rail.blockSignals(True)
        try:
            self.rail.setCurrentRow(row)
            self._lastPageRow = row
        finally:
            self.rail.blockSignals(blocked)

    def sectionFor(self, widget):
        """The section holding ``widget``, or None."""
        for host, _stretch in self._sections:
            if host.sectionWidget is widget:
                return host
        return None

    def contextSection(self):
        """The open context-sensitive section, or None. At most one exists."""
        for host, _stretch in self._sections:
            if self._sectionContext.get(host):
                return host
        return None

    def _closeSection(self, host):
        """Close ``host`` the way its own X would.

        Through the owner's ``closeRequested`` handler rather than straight to
        ``removeSection``, because the owner has state to keep in step - the
        window drops its `levelTreeWidget` reference, the undo history unticks
        its menu entry. Calling removeSection directly would leave the window
        believing a section it can no longer see is still open, and its next
        "already up?" test would then refuse to re-create it.

        Deliberately **not** wrapped in try/except. An unhandled exception in a
        PyQt6 slot aborts the interpreter rather than propagating out of
        ``emit()`` - measured 2026-09-01, after writing exactly that guard and
        watching the suite exit with no traceback - so a try/except here cannot
        catch a failing handler and only reads as though it could.
        """
        host.closeRequested.emit()

        # A handler is free to do nothing, and one that leaves the section in
        # place would break exclusivity silently. This is the backstop that
        # makes the rule hold regardless of what the owner did.
        if self.sectionFor(host.sectionWidget) is host:
            self.removeSection(host)

    def removeSection(self, host):
        """Take a section out of slice 2, leaving its widget alive.

        The widget is unparented rather than deleted: a section's contents
        usually belong to something else - the collab window belongs to its
        controller - and this method's job is to stop showing it, not to end it.
        """
        for index, (candidate, _stretch) in enumerate(self._sections):
            if candidate is not host:
                continue

            widget = host.sectionWidget
            widget.setParent(None)

            self._sections.pop(index)
            self._sectionContext.pop(host, None)
            self._sectionPinned.pop(host, None)

            # Explicitly, since D-d.3d: a QSplitter dropped a child the moment
            # it was unparented, but `SectionColumn` keeps its own ordered list
            # and its grips, and neither notices a reparent. Left out, a closed
            # section stayed in the column's idea of the stack and went on
            # contributing its height to the scroll range.
            self.sections.removeWidget(host)

            host.setParent(None)
            host.deleteLater()

            self._applySectionStretch()

            # "Empty means absent" applies to the *sections page*, not to slice
            # 2 as a whole (D-d.1). Removing the last section while a rail page
            # of its own is showing must not hide that page too.
            if self.pages.currentWidget() is self.sections:
                self.pages.setVisible(bool(self._sections))

            self._resizeColumn()
            return widget

        return None

    def _applySectionStretch(self):
        """Decide which section, if any, absorbs the column's leftover space.

        Since D-d.3d the column is a scroll area rather than a splitter, so
        there is no share-of-the-total to hand out: a host is as tall as it asks
        to be, and folding one genuinely frees the space below it. What is left
        to decide is only what happens when the stack is *shorter* than the
        viewport, and the answer is the bottom-most expanded section (Zement,
        2026-09-01) - so the column never shows dead space under the stack.

        The old version divided splitter stretch between expanded sections, and
        called `_capSliceTwo`. **Both are gone.** The cap put a maximum *height*
        on `self.pages` when every section was folded - and since D-d.2b `pages`
        is a horizontal sibling of the rail, so it capped the whole sidebar's
        height and collapsed it to a strip (Zement, with a screenshot: "when all
        panels of slice 2 are collapsed, the entire sidebar collapses to a very
        small height"). Its own comment had concluded the cap was "cosmetic"
        after D-d.2b; it was not, it was the bug.
        """
        holder = None
        for host, _stretch in self._sections:
            if host.isExpanded():
                holder = host

        self.sections.setSlackHolder(holder)

        # The hosts' wanted heights have just changed - a fold, an unfold, or a
        # section arriving. The scroll area does not re-measure on its own,
        # since it is deliberately not `widgetResizable`.
        self.sections.refreshLayout()

    def _handleColumnDragged(self, _pos, _index):
        """The user moved the column divider - stop recomputing it."""
        self._columnDragged = True

    def _handleSliceDragged(self, _pos, _index):
        """The user moved the slice 2 / panels divider (D-d.2b).

        Same rule as the column, one axis over: from here on their width is the
        one that stands, and `_resizeColumn` stops re-dividing.

        Their width is also *recorded*, so closing every section and re-opening
        one restores it rather than the 180px floor a hidden splitter child
        comes back at.
        """
        self._widthDragged = True

        width = int(self.pages.width())
        if width > 0:
            self._lastSliceWidth = width

    def wantedSliceTwoHeight(self):
        """How tall slice 2 asks to be: the sum of what its sections want.

        A folded section contributes its header, an expanded one its default
        height - or its natural size hint where no default was given.

        Sized slice 2's share of the column until D-d.2b. Slice 2 now has a
        column of its own and takes its full height, so nothing consults this
        for layout; it stays because the section suites measure through it and
        it is still the honest answer to the question it asks.
        """
        if not self._sections:
            return 0

        total = 0
        for host, _stretch in self._sections:
            if not host.isExpanded():
                total += host.headerHeight()
            else:
                total += host.sizeHint().height()

        return total + self.sections.handleWidth() * max(
            0, len(self._sections) - 1)

    def _resizeColumn(self):
        """Divide the sidebar's width between slice 2 and the panels.

        Was the *height* division between the two while they shared a column.
        Since D-d.2b they are side by side, so what needs computing is how wide
        slice 2 opens at - and the answer is much simpler than the height one
        was, because a tree has no natural width to respect the way a section
        had a natural height. It gets a share, once, and the user adjusts it.

        Named for the column it no longer divides. Kept because every caller -
        addSection, removeSection, showEvent, applyRailWidth - wants exactly
        this: "the set of slices changed, re-divide". Renaming it would touch
        five call sites to say the same thing.
        """
        # A width waiting from settings takes precedence over the computed
        # share, and marks the division as the user's own once it lands.
        if self._applySliceWidth():
            return

        if not self._sections and not self.pages.isVisible():
            # Nothing in slice 2, so there is nothing to divide: the splitter
            # gives the whole width to the panels on its own.
            return

        total = self.splitter.width() - rail_width() - self.splitter.handleWidth() * 2
        if total <= 0:
            # Not laid out yet; showEvent runs this again once it is.
            return

        if self._widthDragged:
            # The user has set this division by hand, so the computed share does
            # not apply. Their width still has to be *re-applied* though, and
            # this is why the early return that used to stand here was wrong:
            # closing every section hides slice 2, and a hidden splitter child
            # keeps no width - so re-opening one brought the slice back at its
            # 180px floor rather than at the width the user chose (measured in a
            # real boot, 2026-09-01).
            if self._lastSliceWidth and self.pages.isVisible():
                width = min(self._lastSliceWidth,
                            max(0, total - MIN_SLICE_TWO_WIDTH))
                if width >= MIN_SLICE_TWO_WIDTH:
                    self._setSliceSizes(width, total - width)
            return

        wanted = max(MIN_SLICE_TWO_WIDTH, int(total * SLICE_TWO_SHARE))

        # Never so wide that the panels are squeezed below their own floor. On a
        # narrow sidebar this is the binding constraint, and it is why the share
        # is a maximum rather than a promise.
        wanted = min(wanted, max(0, total - MIN_SLICE_TWO_WIDTH))
        if wanted <= 0:
            return

        self._setSliceSizes(wanted, total - wanted)

    def _setSliceSizes(self, slice_two, panels):
        """Apply a slice 2 / panels division, without it counting as a drag.

        Blocked, because setSizes emits splitterMoved - the signal that marks
        the division as user-dragged. Without this the first computed division
        would mark itself as the user's own and every later one would be
        refused, which is how a section ends up frozen at whatever width it
        first got.
        """
        self._lastSliceWidth = slice_two

        blocked = self.splitter.blockSignals(True)
        try:
            sizes = [rail_width(), slice_two, panels]
            if self._side == SIDE_RIGHT:
                sizes.reverse()
            self.splitter.setSizes(sizes)
        finally:
            self.splitter.blockSignals(blocked)

    # -- slice 3 ---------------------------------------------------------

    def addPanel(self, title, widget, stretch=0,
                 default_height=UNLIMITED, max_height=UNLIMITED):
        """Put a widget in slice 3 and return the host standing in for its dock.

        ``stretch`` gives a panel the leftover vertical space. The palette wants
        it - it is a scrolling list of objects, so extra height is directly more
        of the thing the user came for - while the property editors are forms of
        a fixed size that would only gain padding. With every panel at zero the
        space below them is simply dead, which is what the first D-c.3 build
        looked like.
        """
        host = PanelHost(title, widget, self.panelArea,
                         default_height=default_height, max_height=max_height)

        # Folding a panel changes how much room the ones below it get, so the
        # layout has to be told - otherwise a folded panel's share stays blank.
        host.toggled.connect(lambda _on: self._applyPanelStretch())

        # Before the trailing stretch, so the panels stay top-aligned and any
        # space no panel claims collects at the bottom rather than between them.
        self._panelLayout.insertWidget(self._panelLayout.count() - 1, host, stretch)
        self._panels.append(host)
        self._panelStretches.append(stretch)

        if stretch:
            # A stretched panel only fills if its own contents will expand into
            # the space; the default policy for most widgets is to stay at their
            # size hint however much room the layout offers.
            host.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                               QtWidgets.QSizePolicy.Policy.Expanding)
            _expandVertically(widget)

        return host

    def relaxPanelHeights(self):
        """Re-apply the expanding policy to every stretched panel's contents.

        Called once the palette's tabs have actually been filled - addPanel gets
        the tab widget empty and the builder populates it afterwards, so the
        recursion has to happen at the end rather than at the moment the panel
        is added.
        """
        for host, stretch in zip(self._panels, self._panelStretches):
            if stretch:
                _expandVertically(host.panelWidget)

    def showEvent(self, event):
        super().showEvent(event)

        # The column has no height until the sidebar is shown, so a section
        # added during the window's construction could not be sized then. This
        # is the first moment the arithmetic means anything.
        self.refreshHeights()
        self._resizeColumn()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        # Percentage heights are percentages *of this widget*, so they mean
        # something different after every resize.
        self.refreshHeights()

    def refreshHeights(self):
        """Re-resolve every host's percentage heights against the new size."""
        for host, _stretch in self._sections:
            host.refreshHeights()

        for host in self._panels:
            host.refreshHeights()

        # A percentage is of the *sidebar's* height, so a resize changes every
        # host's wanted height at once - and the column has to be re-measured
        # against the new total or a stack that has just become too tall will
        # not have grown a scrollbar (D-d.3d).
        self.sections.refreshLayout()

        # And re-divide, because the splitter will not do it on its own: it
        # reads a size hint once and never looks again.
        self._resizeColumn()

    def applyRailWidth(self):
        """Re-read the rail width setting, for the settings dialog to call."""
        width = rail_width()
        self.rail.setFixedWidth(width)

        # The icon follows the rail too (D-d.1c). Without this, switching
        # between 32, 48 and 64 grew the row and left the icon at its old size -
        # which is exactly what Zement saw: "only the section reserved for the
        # icon grows, not the actual icon".
        icon = rail_icon_size(width)
        self.rail.setIconSize(QtCore.QSize(icon, icon))

        # The rows are sized from the rail's width, so they have to follow it
        # (D-d.1b). Without this a narrower rail keeps wide rows and the
        # highlight runs off the side again.
        self._resizeRailItems()

    # -- remembering the layout ------------------------------------------

    def saveSectionHeights(self):
        """Remember what the user dragged each section to (D-d.3d).

        **Keyed by title, not by position.** Sections come and go - the context
        band replaces one with another every time the rail is clicked - so a
        list of heights by index would hand the Directory Listing's height to
        whatever happened to be in slot 1 next launch.

        Only *dragged* heights are written. A section still at its configured
        default has nothing worth remembering, and writing it would freeze the
        default at whatever pixel value it resolved to on this screen - so
        changing a percentage in the code would then have no effect on anyone
        who had ever run the old one.

        The splitter never saved these at all: `SidebarColumnSizes` is slice 3's
        panel division, so a dragged column came back at its defaults on the
        next launch. Zement asked for the grip back "which then also gets
        remembered in settings.ini" - the remembering is new.
        """
        heights = dict(self._draggedHeights)

        for host, _stretch in self._sections:
            if host.wasDragged():
                heights[host.sectionKey()] = int(host.height())

        # Kept on the sidebar as well as in settings, so a section closed and
        # re-opened within one run comes back at the height the user gave it
        # rather than only across a restart.
        self._draggedHeights = heights

        if heights:
            # `Title=300|Other=150`, not the dict itself. QSettings round-trips
            # a dict as an opaque `@Variant(\0\0\0\b...)` blob, which would
            # break the rule saveLayout states a few lines down and follows
            # everywhere else: "stored as plain lists rather than Qt's opaque
            # saveState blobs, so a settings file stays readable and a bad value
            # can be corrected by hand". Zement edits these by hand, which is
            # how this feature was asked for in the first place.
            setSetting('SidebarSectionHeights', '|'.join(
                '%s=%d' % (title, height)
                for title, height in sorted(heights.items())))

    def restoreSectionHeights(self):
        """Read back what ``saveSectionHeights`` wrote."""
        stored = setting('SidebarSectionHeights', None)

        if isinstance(stored, str):
            pairs = []
            for chunk in stored.split('|'):
                title, _sep, height = chunk.rpartition('=')
                # rpartition, not partition: a section title may contain '=',
                # and the height never does.
                if title:
                    pairs.append((title, height))
        elif isinstance(stored, dict):
            # A settings file written by the first build of this feature, which
            # stored the dict directly. Read, then replaced by a readable string
            # on the next save - no migration step needed.
            pairs = list(stored.items())
        else:
            return

        clean = {}
        for title, height in pairs:
            try:
                value = int(height)
            except (TypeError, ValueError):
                continue

            # A height taller than any sidebar is a settings file written on a
            # much bigger screen, or edited by hand into nonsense. Dropped
            # rather than clamped: the configured default is a better answer
            # than an arbitrary ceiling.
            if 0 < value <= 4000:
                clean[str(title).strip()] = value

        self._draggedHeights = clean

    def applySectionHeight(self, host):
        """Give ``host`` its remembered height, if it has one.

        ``restored=True``, so the host does **not** count as dragged. That
        distinction is the whole point: `saveSectionHeights` only writes heights
        the user chose, and marking a restored one as dragged made a restore
        indistinguishable from a drag - so the first stored value re-saved
        itself on every launch, and the configured percentage could never be
        reached again (Zement, 2026-09-01: "the Game Patches panel doesn't seem
        to be 50% of the slice height").

        Worse than it sounds, because the loop is self-sustaining: once any
        height reached the file, restore -> mark dragged -> save -> restore kept
        it there for good, and editing the percentage in the code did nothing.
        """
        height = self._draggedHeights.get(host.sectionKey())
        if height:
            host.setDraggedHeight(height, restored=True)

    def saveLayout(self):
        """Write the sidebar's own splitter positions to settings.

        ``QMainWindow.saveState`` covers docks and toolbars, and the sidebar is
        deliberately neither - so its splitters have to be saved by hand or
        every launch starts from the default division. Zement's complaint about
        earlier Reggie versions was exactly this: resizing the same panels at
        every start.

        Three numbers, all of which the user sets by dragging:

        - the **sidebar's width** - the split between the sidebar and the canvas
        - the **slice split** - how that width divides between slice 2 and the
          panels (D-d.2b; before that the two shared a column and this was a
          height)
        - the **column split** - how slice 3's own height divides, which is one
          number today and becomes meaningful again in D-d.5

        Stored as plain lists rather than Qt's opaque ``saveState`` blobs, so a
        settings file stays readable and a bad value can be corrected by hand.
        """
        # Only when the column actually has a height. A hidden or unlaid widget
        # reports zero, and saving that would overwrite a division the user set
        # in an earlier session with a number that means nothing.
        sizes = [int(n) for n in self.column.sizes()]
        if sizes and all(n > 0 for n in sizes):
            setSetting('SidebarColumnSizes', sizes)

        # The slice division, saved as slice 2's width alone rather than the
        # whole list. The rail's width is a setting of its own and the panels
        # take the remainder, so one number is the whole of what the user chose
        # - and it survives a rail resize or a side flip, which a list of three
        # absolute widths would not.
        # `_lastSliceWidth` rather than `pages.width()` when slice 2 is hidden:
        # a hidden widget reports a stale number, and closing every section
        # before quitting would otherwise save whatever it happened to hold.
        slice_two = int(self.pages.width()) if self.pages.isVisible() else 0
        if slice_two <= 0:
            slice_two = int(self._lastSliceWidth or 0)

        if slice_two > 0:
            setSetting('SidebarSliceTwoWidth', slice_two)

        self.saveSectionHeights()

        window = self.win
        splitter = getattr(window, 'centralSplitter', None)
        if splitter is None or splitter.indexOf(self) == -1 or self.width() <= 0:
            return

        width = int(self.width())

        # Do not overwrite a wider saved width with one the restore clamped.
        # Without this, one launch in a smaller window permanently shrinks what
        # the user had set, and every launch after that shrinks it again.
        #
        # **The test is what the restore did, not what the window looks like
        # now** (fixed D-d.1b). This used to recompute the clamp against the
        # splitter's *current* width, which is only the same number when the
        # window has not been resized since. The real sequence is:
        #
        #   restore at 800px  -> 620 clamped to 480
        #   user maximises    -> splitter 1920, sidebar still 480
        #   closeEvent        -> clamp recomputed as 1600; 480 < 1600, so the
        #                        guard did not fire and 480 was saved
        #
        # So the ratchet survived in exactly the case it was written for: a
        # window that grows after the restore. Zement, 2026-08-31 - "settings.ini
        # holds the correct values and yet it still restores a wrong size".
        #
        # `_clampedWidth` is set by _restoreWidth when it had to cut the saved
        # value, and cleared the moment the user drags the divider themselves.
        previous = setting('SidebarWidth', None)
        try:
            previous = int(previous) if previous is not None else None
        except (TypeError, ValueError):
            previous = None

        # Note the test is for *equality*, not "at most". A width the clamp
        # produced is one exact number; anything else - including something
        # narrower - is the user having moved the divider since, and theirs is
        # the value to keep. An earlier `width <= self._clampedWidth` also
        # suppressed a deliberate drag to something smaller, which would have
        # made the sidebar impossible to narrow in a small window.
        if (previous is not None and previous > width
                and self._clampedWidth is not None
                and width == self._clampedWidth):
            # This width is the clamp's doing, not the user's. Keep what they
            # asked for, so the next launch in a big enough window gets it.
            return

        setSetting('SidebarWidth', width)

    def _restoreWidth(self, retry=True):
        """Put the sidebar back to its saved width. True if it happened.

        Split out from ``restoreLayout`` so the retry below can re-run *only*
        this: the column restore has already happened by then, and repeating it
        would undo it.
        """
        width = setting('SidebarWidth', None)
        splitter = getattr(self.win, 'centralSplitter', None)

        if splitter is None:
            return False

        # No saved width - a first run, or a settings file from before the
        # sidebar existed. Left to the splitter until D-d.2b, which produced 251
        # px from the children's size hints: fine for two slices, and much too
        # narrow for three (measured: rail 48, slice 2 at its 180 floor, and 68
        # px of panels - the property editors squeezed to nothing on first
        # launch). So the first-run width is stated rather than inferred.
        if width is None:
            width = DEFAULT_SIDEBAR_WIDTH

        # A width saved by a pre-D-d.2b build is a *two*-slice width, and
        # restoring it into three slices leaves the panels unusable - Zement's
        # own settings.ini holds 251, which divides as rail 48, tree 180 and 23
        # px of property editors.
        #
        # Widened rather than migrated on a version check: no version is
        # recorded for this key, and "too narrow to hold its own slices" is
        # both the real condition and one that stays correct if the floors ever
        # change. A user who genuinely wants a sidebar this narrow gets it back
        # by dragging, and that drag is saved.
        try:
            width = int(width)
        except (TypeError, ValueError):
            return False

        if width < MIN_THREE_SLICE_WIDTH:
            width = DEFAULT_SIDEBAR_WIDTH

        index = splitter.indexOf(self)
        if width <= 0 or index == -1:
            return False

        total = splitter.width()

        # Two ways the splitter's width is not yet the one to clamp against,
        # and both need the same answer: wait a turn.
        #
        #   1. `total <= 0` - not laid out at all.
        #   2. The window is maximized (or full screen) but the layout still
        #      reports the *pre-maximize* size. Measured 2026-08-31: with the
        #      window maximized on a 1920px screen, the restore posted from
        #      showEvent still saw a 533px splitter, so a saved 620 was clamped
        #      to 267 and the sidebar came back a third of the width it should
        #      have been. Zement: "settings.ini seems to hold the correct values
        #      and yet it still restores a wrong size... smaller sizes work".
        #      Smaller ones work because they fall under even the stale clamp.
        #
        # Case 2 is the one the original `total <= 0` test missed: the splitter
        # has a perfectly valid width, it is just the wrong one.
        # `total <= 0` is not the only "no real layout yet" value: a splitter
        # that has never been shown reports Qt's default 100px, which is a
        # perfectly ordinary number and would clamp the sidebar to almost
        # nothing. Anything narrower than one usable canvas plus the rail is not
        # a window the user is looking at.
        unlaid = total <= max(MIN_CANVAS_WIDTH, rail_width() * 2)

        if unlaid or (retry and self._maximizePending(total)):
            # One retry on the next turn of the event loop, not a loop: if it is
            # still wrong then, something else is going on and quietly spinning
            # would hide it. Silently dropping the saved width is how it came
            # back at the default (Zement, 2026-08-30).
            if retry:
                QtCore.QTimer.singleShot(
                    0, lambda: self._restoreWidth(retry=False))
                return False

            if unlaid:
                return False

        # Leave the canvas a usable strip, but no more than that. An earlier
        # version capped at half the window and produced a ratchet (Zement,
        # 2026-08-30): the clamp ran while the window was still at an
        # intermediate size, and closeEvent then saved the clamped number - so a
        # 1920px window restored a sidebar at 640 and shrank it again on every
        # launch. Two things fix it, and both are needed:
        #
        #   - clamp against a *minimum for the canvas* rather than a share of
        #     the window, so an intermediate width costs nothing, and
        #   - never save a width the clamp produced (see saveLayout).
        canvas_floor = min(MIN_CANVAS_WIDTH, total // 2)
        allowed = max(0, total - canvas_floor)

        if width > allowed:
            # Remember that this width is not the user's choice but the clamp's,
            # so saveLayout does not write it back over the wider value they
            # actually asked for. Recomputing the clamp at save time cannot tell
            # the difference once the window has been resized (D-d.1b).
            self._clampedWidth = allowed
            width = allowed
        else:
            self._clampedWidth = None

        other = total - width
        splitter.setSizes([width, other] if index == 0 else [other, width])
        return True

    def _maximizePending(self, total):
        """Whether the window is maximized but the layout has not caught up.

        Qt sets the maximized *state* before the resize reaches the layout, so
        a restore posted from showEvent can run against the window's previous,
        smaller geometry. Comparing the splitter against the screen tells the
        two apart: a genuinely maximized window fills it, a stale one does not.

        Conservative on purpose - any doubt (no window handle, no screen, not
        maximized) answers False, so the restore proceeds as it always did.
        """
        window = self.win
        if window is None or not hasattr(window, 'windowState'):
            return False

        state = window.windowState()
        maximized = bool(
            state & (QtCore.Qt.WindowState.WindowMaximized
                     | QtCore.Qt.WindowState.WindowFullScreen))
        if not maximized:
            return False

        handle = window.windowHandle()
        screen = handle.screen() if handle is not None else None
        if screen is None:
            screen = QtWidgets.QApplication.primaryScreen()
        if screen is None:
            return False

        available = screen.availableGeometry().width()
        if available <= 0:
            return False

        # A generous margin: window frame, and the splitter is inset from the
        # window by whatever chrome sits beside it. Only a width that is *far*
        # short of the screen counts as stale.
        return total < (available * 3) // 4

    def _handleSidebarResized(self, _pos, _index):
        """The user dragged the sidebar/canvas divider.

        Their drag is the authority from then on, so a clamp recorded earlier
        must stop suppressing the save - otherwise deliberately narrowing the
        sidebar in a small window would never be remembered.
        """
        self._clampedWidth = None

    def restoreLayout(self):
        """Put back what ``saveLayout`` wrote. Silent when there is nothing.

        Every value is re-checked against the current window rather than
        trusted: a sidebar sized on a 4K screen must not be restored onto a
        laptop as a sidebar wider than the window.
        """
        # First, so a section restored below already has its remembered height.
        self.restoreSectionHeights()

        sizes = setting('SidebarColumnSizes', None)
        if sizes:
            try:
                sizes = [int(n) for n in sizes]
            except (TypeError, ValueError):
                sizes = None

            # A zero is what gets saved for a widget that was hidden or not yet
            # laid out. Restoring it would be harmless but pointless, and
            # treating it as "the user chose this" would stop _resizeColumn ever
            # sizing what arrives later. So a zero means "nothing to restore".
            if sizes and 0 in sizes:
                sizes = None

            # The length test also discards the pre-D-d.2b value, where this
            # setting held two numbers because slice 2 lived in this splitter.
            # A settings file written by an older build heals itself on the
            # first save rather than needing a migration.
            if sizes and len(sizes) == self.column.count() and sum(sizes) > 0:
                blocked = self.column.blockSignals(True)
                try:
                    self.column.setSizes(sizes)
                finally:
                    self.column.blockSignals(blocked)

                # Set here rather than left to splitterMoved, which is blocked
                # above: a restored split is the user's own division from last
                # time, so recomputing over it would throw away the thing this
                # method exists to bring back.
                self._columnDragged = True

        self._restoreSliceWidth()
        self._restoreWidth()

    def _restoreSliceWidth(self):
        """Put slice 2 back to its saved width (D-d.2b).

        Deliberately *not* applied to the splitter here. Slice 2 is hidden while
        it holds no sections, and setting sizes on a splitter with a hidden
        child does nothing at all - the widths would be silently discarded and
        the first section to open would get the computed share instead of the
        user's. So the number is remembered and `_applySliceWidth` spends it
        when slice 2 next becomes visible.
        """
        width = setting('SidebarSliceTwoWidth', None)
        try:
            width = int(width) if width is not None else None
        except (TypeError, ValueError):
            width = None

        if width is not None and width > 0:
            self._savedSliceWidth = width

    def _applySliceWidth(self):
        """Spend a restored slice 2 width, once, when it can actually take.

        Returns True if it was applied. A restored width counts as the user's
        own division, so it also stops `_resizeColumn` recomputing over it -
        the same rule the column split follows.
        """
        width = self._savedSliceWidth
        if width is None or not self.pages.isVisible():
            return False

        total = self.splitter.width() - rail_width() - self.splitter.handleWidth() * 2
        if total <= 0:
            return False

        # Re-checked against this window rather than trusted, for the same
        # reason the sidebar's own width is: a division saved on a wide screen
        # must not leave the panels with nothing on a narrow one.
        width = max(MIN_SLICE_TWO_WIDTH,
                    min(width, max(0, total - MIN_SLICE_TWO_WIDTH)))
        if width <= 0 or width >= total:
            return False

        self._savedSliceWidth = None
        self._widthDragged = True

        self._setSliceSizes(width, total - width)

        return True

    def _applyPanelStretch(self):
        """Give the stretch to the expanded panels only.

        Slice 3 is a box layout rather than a splitter, so folding is simpler
        here than in slice 2: a folded panel is already capped to its header, and
        this only has to stop it claiming stretch it can no longer use. Without
        it the palette would fold and leave its share of the column blank rather
        than passing it to the panels below.
        """
        for host, stretch in zip(self._panels, self._panelStretches):
            index = self._panelLayout.indexOf(host)
            if index != -1:
                self._panelLayout.setStretch(
                    index, stretch if host.isExpanded() else 0)

    def setPanelsEnabled(self, enabled):
        """Show or hide slice 3 as a whole.

        The panels describe the level in front, so with no canvas tab there is
        nothing for them to describe. Hiding the scroll area rather than each
        host keeps the individual visibility - which selection drives - intact
        for when a canvas comes back.
        """
        self.panelScroll.setVisible(bool(enabled))

    @property
    def panels(self):
        return list(self._panels)
