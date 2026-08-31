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
        self.hostWidget = widget
        self._expanded = True
        self._maxHeight = max_height
        self._defaultHeight = default_height

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

    def setTitle(self, title):
        """Rename the host, keeping the fold arrow in step."""
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

        This is what a splitter divides its space by, so a default height is
        expressed as a size hint rather than as a fixed height - it is a
        starting point the user can then drag away from, not a rule.
        """
        hint = super().sizeHint()

        if self._expanded:
            resolved = self._resolveHeight(self._defaultHeight)
            if resolved is not None:
                hint.setHeight(resolved)

        return hint

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

        # Slice 2's default page is a splitter of collapsible sections rather
        # than one widget per rail entry (Zement, 2026-08-30). The reason is
        # what the content turns out to be: the undo history, the collab chat
        # and the directory listing are all things a user wants *at the same
        # time*, sized to taste - which is the VS Code Explorer shape, not a
        # stack where reading one hides the others.
        #
        # The stack stays underneath, because D-d may still want a genuinely
        # separate rail page for something that owns the whole slice. Sections
        # are simply what its first page holds.
        self.sections = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
        self.sections.setChildrenCollapsible(False)
        self._sections = []

        # host -> is it context-sensitive. A dict rather than a third element in
        # the `_sections` tuples, so the many places that unpack
        # `(host, stretch)` keep working.
        self._sectionContext = {}
        self.pages.addWidget(self.sections)

        # Rail row -> page widget, and rail row -> callback. A row may have
        # either, both or (for an action entry like Preferences) only the
        # callback; see addPage. Parallel lists rather than a dict because the
        # rail is addressed by row and both are appended together.
        self._railPages = []
        self._railActions = []

        # The last row that actually selected a page, so an action entry can
        # hand the highlight back rather than leaving it on a button.
        self._lastPageRow = None

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
                sections=False):
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

        if self.rail.currentRow() < 0 and page is not None:
            self.rail.setCurrentRow(self.rail.count() - 1)

        return item

    def _handleRailChanged(self, row):
        if not (0 <= row < len(self._railPages)):
            return

        page = self._railPages[row]

        if page is not None:
            self._lastPageRow = row
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
                   max_height=UNLIMITED, context=False):
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

        if on_close is not None:
            host.closeRequested.connect(on_close)
        else:
            host.closeRequested.connect(lambda: self.removeSection(host))

        self._sectionContext[host] = bool(context)

        # Context-sensitive sections go to the top, always-open ones below in
        # the order they arrived. Since there is at most one context section,
        # index 0 is the whole of "the top".
        if context:
            self.sections.insertWidget(0, host)
            self._sections.insert(0, (host, stretch))
        else:
            self.sections.addWidget(host)
            self._sections.append((host, stretch))

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

        return host

    def showSections(self):
        """Bring the sections page to the front of slice 2, and show it.

        Also moves the rail's highlight to the entry that owns the sections
        page, if one has been added, so the rail does not claim a different
        page is showing. Blocked, or the row change re-enters the handler.
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
        """Give the space to the expanded sections only.

        Re-applied after every fold rather than set once: a collapsed section
        that kept its stretch would hold on to a share of the column and leave a
        gap under its header, which is the thing folding is meant to remove.
        """
        for index, (host, stretch) in enumerate(self._sections):
            self.sections.setStretchFactor(
                index, stretch if host.isExpanded() else 0)

        self._capSliceTwo()

    def _capSliceTwo(self):
        """Shrink slice 2 to its headers when every section in it is folded.

        Written for the stacked layout, where slice 2 kept its share of the
        *height* however small its sections folded to and the palette below
        never saw the space released (Zement, 2026-08-30). Since D-d.2b slice 2
        is its own column and can no longer take height from anything, so the
        cap is now cosmetic: it stops a stack of folded headers from sitting in
        a full-height empty column.

        Still worth keeping, and still runs from `_applySectionStretch` - the
        one place every fold, unfold, add and remove already passes through.
        """
        if not self._sections:
            self.pages.setMaximumHeight(QtWidgets.QWIDGETSIZE_MAX)
            return

        if any(host.isExpanded() for host, _stretch in self._sections):
            self.pages.setMaximumHeight(QtWidgets.QWIDGETSIZE_MAX)
            return

        # Every section folded: slice 2 is worth exactly its stack of headers,
        # plus the splitter handles between them.
        headers = sum(host.headerHeight() for host, _stretch in self._sections)
        handles = self.sections.handleWidth() * max(0, len(self._sections) - 1)
        self.pages.setMaximumHeight(headers + handles)

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
