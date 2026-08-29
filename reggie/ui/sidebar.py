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

from PyQt6 import QtCore, QtWidgets

from reggie.core import globals_
from reggie.core.dirty import setting


#: Settings value for the sidebar living on the left / right of the window.
SIDE_LEFT = 'left'
SIDE_RIGHT = 'right'


def configured_side():
    """Which side the sidebar is on, defaulting to the left."""
    value = setting('SidebarSide', SIDE_LEFT)
    value = str(value).strip().lower() if value is not None else SIDE_LEFT
    return SIDE_RIGHT if value == SIDE_RIGHT else SIDE_LEFT


class PanelHost(QtWidgets.QWidget):
    """Holds one panel widget and answers the QDockWidget API used on it.

    Only the three members the editor actually calls on these docks:
    ``setVisible``, ``isVisible`` and ``isFloating``. Deliberately not a general
    dock emulation - a partial imitation that covers the real call sites is
    honest, whereas one that looks complete invites code to rely on parts that
    were never tested.

    ``isFloating`` answers False forever: the point of the sub-block is that
    these panels are docked, and the one caller (spriteeditor.py, minimising a
    floating editor's height) is asking exactly that question.
    """

    visibilityChanged = QtCore.pyqtSignal(bool)

    def __init__(self, title, widget, parent=None):
        super().__init__(parent)

        self.panelTitle = title
        self.panelWidget = widget

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self.titleLabel = QtWidgets.QLabel(title)
        self.titleLabel.setStyleSheet('font-weight: bold;')
        layout.addWidget(self.titleLabel)
        layout.addWidget(widget)

        # The panel widget arrives hidden in some cases (the docks set
        # setVisible(False) on the *dock*, leaving the widget itself shown).
        # Inside a host, the host is what gets hidden, so the widget must be
        # visible or the host would show an empty box.
        widget.setVisible(True)

        super().setVisible(False)

    def setVisible(self, visible):
        changed = bool(visible) != self.isVisible()
        super().setVisible(bool(visible))
        if changed:
            self.visibilityChanged.emit(bool(visible))

    def isFloating(self):
        """Always False - a hosted panel is docked by construction."""
        return False


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
        self._side = configured_side()

        # slice 1 - the icon rail.
        self.rail = QtWidgets.QListWidget(self)
        self.rail.setViewMode(QtWidgets.QListView.ViewMode.IconMode)
        self.rail.setMovement(QtWidgets.QListView.Movement.Static)
        self.rail.setFlow(QtWidgets.QListView.Flow.TopToBottom)
        self.rail.setWrapping(False)
        self.rail.setIconSize(QtCore.QSize(24, 24))
        self.rail.setFixedWidth(44)
        self.rail.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.rail.currentRowChanged.connect(self._handleRailChanged)

        # slice 2 - one page per rail entry.
        self.pages = QtWidgets.QStackedWidget(self)

        # slice 3 - the palette and the property panels, stacked vertically and
        # scrollable: four property editors plus the palette is more than fits
        # in most windows, and a panel that cannot be reached is worse than one
        # that needs scrolling to.
        self.panelArea = QtWidgets.QWidget(self)
        self._panelLayout = QtWidgets.QVBoxLayout(self.panelArea)
        self._panelLayout.setContentsMargins(2, 2, 2, 2)
        self._panelLayout.setSpacing(4)
        self._panelLayout.addStretch(1)

        self.panelScroll = QtWidgets.QScrollArea(self)
        self.panelScroll.setWidgetResizable(True)
        self.panelScroll.setWidget(self.panelArea)
        self.panelScroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.panelScroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarPolicy.ScrollBarAsNeeded)

        # slices 2 and 3 share a column, split vertically so the user decides
        # how much of it the panels get.
        self.column = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, self)
        self.column.addWidget(self.pages)
        self.column.addWidget(self.panelScroll)
        self.column.setStretchFactor(0, 1)
        self.column.setStretchFactor(1, 2)

        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.splitter)

        self._layOutSlices()

    # -- slice order -----------------------------------------------------

    def _layOutSlices(self):
        """Insert the slices in the order this side calls for.

        A QSplitter is ordered by insertion, so flipping sides is re-inserting
        rather than rebuilding - which is why this is a loop and not a second
        constructor. The rail stays outermost either way, so it is against the
        window edge on both sides rather than sitting in the middle.
        """
        ordered = [self.rail, self.column]
        if self._side == SIDE_RIGHT:
            ordered.reverse()

        # insertWidget at a rising index, not addWidget: a QSplitter moves a
        # widget it already holds rather than adding a second copy, so this
        # reorders on a flip and fills on the first call, with one code path.
        for index, widget in enumerate(ordered):
            self.splitter.insertWidget(index, widget)

        self.splitter.setStretchFactor(
            0 if self._side == SIDE_LEFT else 1, 0)
        self.splitter.setStretchFactor(
            1 if self._side == SIDE_LEFT else 0, 1)

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

    def addPage(self, icon, title, widget):
        """Add a rail entry and the slice-2 page it selects."""
        item = QtWidgets.QListWidgetItem(self.rail)
        if icon is not None:
            item.setIcon(icon)
        item.setToolTip(title)
        item.setSizeHint(QtCore.QSize(40, 40))
        item.setTextAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)

        self.pages.addWidget(widget)

        if self.rail.currentRow() < 0:
            self.rail.setCurrentRow(0)

        return item

    def _handleRailChanged(self, row):
        if 0 <= row < self.pages.count():
            self.pages.setCurrentIndex(row)

    # -- slice 3 ---------------------------------------------------------

    def addPanel(self, title, widget, stretch=0):
        """Put a widget in slice 3 and return the host standing in for its dock.

        ``stretch`` gives a panel the leftover vertical space. The palette wants
        it - it is a scrolling list of objects, so extra height is directly more
        of the thing the user came for - while the property editors are forms of
        a fixed size that would only gain padding. With every panel at zero the
        space below them is simply dead, which is what the first D-c.3 build
        looked like.
        """
        host = PanelHost(title, widget, self.panelArea)

        # Before the trailing stretch, so the panels stay top-aligned and any
        # space no panel claims collects at the bottom rather than between them.
        self._panelLayout.insertWidget(self._panelLayout.count() - 1, host, stretch)
        self._panels.append(host)

        if stretch:
            # A stretched panel only fills if its own contents will expand into
            # the space; the default policy for most widgets is to stay at their
            # size hint however much room the layout offers.
            host.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                               QtWidgets.QSizePolicy.Policy.Expanding)
            widget.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                                 QtWidgets.QSizePolicy.Policy.Expanding)

        return host

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
