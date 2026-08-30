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

    def _applyMaxHeight(self):
        """Apply the ceiling, unless folding has one of its own in force.

        Folding sets a much smaller maximum, so this must not overwrite it -
        which is why unfolding calls back here rather than clearing the maximum
        itself. One place decides the height, in both directions.
        """
        if not self._expanded:
            self.setMaximumHeight(self.headerHeight())
        elif self._maxHeight is UNLIMITED:
            self.setMaximumHeight(QtWidgets.QWIDGETSIZE_MAX)
        else:
            self.setMaximumHeight(int(self._maxHeight))

    def sizeHint(self):
        """Ask for the default height, when one was given.

        This is what a splitter divides its space by, so a default height is
        expressed as a size hint rather than as a fixed height - it is a
        starting point the user can then drag away from, not a rule.
        """
        hint = super().sizeHint()
        if self._expanded and self._defaultHeight is not UNLIMITED:
            hint.setHeight(int(self._defaultHeight))
        return hint

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

        # slice 2 - one page per rail entry. Empty until D-d fills it in, so it
        # asks for nothing: a stretch factor here would hand a third of the
        # column to a widget with nothing in it, which is what squeezed the
        # palette into half the sidebar and then a third of it once a property
        # panel appeared (Zement, 2026-08-29).
        self.pages = QtWidgets.QStackedWidget(self)
        self.pages.setSizePolicy(QtWidgets.QSizePolicy.Policy.Preferred,
                                 QtWidgets.QSizePolicy.Policy.Preferred)

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
        self.pages.addWidget(self.sections)

        # Rail row -> page widget. The sections page above is deliberately not
        # in it: it is what slice 2 shows by default, not something the rail
        # selects.
        self._railPages = []

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

        # slices 2 and 3 share a column, split vertically so the user decides
        # how much of it the panels get.
        #
        # **Slice 3 goes on top** (Zement, 2026-08-30). The palette and the item
        # property editors are the most frequently used things in the sidebar,
        # and with slice 2 above them every section D-d adds would push them
        # further down - out of sight, or squeezed to nothing at the bottom.
        # Putting them first means slice 2 grows downward into space slice 3 is
        # not using, rather than displacing it.
        self.column = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical, self)
        self.column.addWidget(self.panelScroll)
        self.column.addWidget(self.pages)

        # **Slice 3 takes the leftover space; slice 2 takes what it asks for.**
        # Not an even split (Zement, 2026-08-30: a single 400px undo section
        # filled half the sidebar). The two want different things from height:
        # the palette is a scrolling list, so more of it is directly more of
        # what the user came for, while a section has a default height it wants
        # and nothing useful to do with the rest.
        #
        # So slice 2 is sized to the sum of its sections and slice 3 absorbs the
        # remainder. Both of Zement's rules follow from that one: an empty slice
        # 2 asks for nothing, and each section added adds its own height to what
        # it asks for.
        self.column.setStretchFactor(0, 1)
        self.column.setStretchFactor(1, 0)

        # Slice 2 held nothing until D-c.6, and giving space to an empty widget
        # was what squeezed the palette into a third of the sidebar. Now that it
        # has sections, it hides itself while it has none instead - the same
        # protection, expressed as "empty means absent" rather than as a stretch
        # factor that would have to be undone the moment content arrived.
        self.pages.setVisible(False)

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

        # Recorded rather than derived from the index. Since D-c.6 the stack
        # also holds the sections page, which has no rail entry of its own, so
        # "rail row N is page N" stopped being true - and a mapping that is
        # nearly right is how a rail ends up selecting the wrong page as D-d
        # adds entries.
        self._railPages.append(widget)

        if self.rail.currentRow() < 0:
            self.rail.setCurrentRow(0)

        return item

    def _handleRailChanged(self, row):
        if 0 <= row < len(self._railPages):
            self.pages.setCurrentWidget(self._railPages[row])

    def addSection(self, title, widget, stretch=1, closable=True,
                   on_close=None, default_height=UNLIMITED,
                   max_height=UNLIMITED):
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
        """
        host = SectionHost(title, widget, self.sections, closable=closable,
                           default_height=default_height,
                           max_height=max_height)

        if on_close is not None:
            host.closeRequested.connect(on_close)
        else:
            host.closeRequested.connect(lambda: self.removeSection(host))
        self.sections.addWidget(host)
        self._sections.append((host, stretch))

        host.toggled.connect(lambda _on: self._applySectionStretch())
        self._applySectionStretch()

        self.pages.setVisible(True)

        # Size the column for the new total. Deliberately here and in
        # removeSection, but NOT on fold: folding should give its space to slice
        # 3 and leave it there, and re-running this would take it straight back.
        # Adding and removing change what slice 2 *is*; folding only changes how
        # much of itself it is showing.
        self._resizeColumn()

        return host

    def sectionFor(self, widget):
        """The section holding ``widget``, or None."""
        for host, _stretch in self._sections:
            if host.sectionWidget is widget:
                return host
        return None

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
            host.setParent(None)
            host.deleteLater()

            self._applySectionStretch()
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

        Capping each *section* is not enough, and this is the bug Zement found
        (2026-08-30): the sections live inside `pages`, which is one half of the
        `column` splitter, and that splitter keeps slice 2's share of the height
        however small the sections inside it become. So the palette below never
        saw the space folding was supposed to release.

        The cap has to be lifted again the moment anything unfolds, which is why
        this runs from `_applySectionStretch` - the one place every fold, unfold,
        add and remove already passes through.
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

    def wantedSliceTwoHeight(self):
        """How tall slice 2 asks to be: the sum of what its sections want.

        A folded section contributes its header, an expanded one its default
        height - or its natural size hint where no default was given. This is
        what makes Zement's two rules one rule: an empty slice 2 wants nothing,
        and adding a section adds that section's height to what it wants.
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
        """Cap slice 2 at half the column, however much it asks for.

        The *sizing* is done by the splitter itself - stretch 1/0 plus each
        section's size hint - and measurement says so:

            stretch 1/1, hint 400   -> [29, 967]   <- Zement's bug
            stretch 1/0, hint 400   -> [596, 400]  <- what is wanted
            stretch 1/0, no hint    -> [786, 210]

        So this does not re-derive what the splitter already gets right. Its one
        job is the ceiling: a stack of sections with generous defaults must not
        be able to push the palette out of the way, and no amount of stretch
        expresses "up to half".
        """
        total = self.column.height()
        if total <= 0:
            # Not laid out yet; showEvent runs this again once it is.
            return

        wanted = self.wantedSliceTwoHeight()
        if wanted <= total // 2:
            # Within the ceiling - leave the splitter's own arithmetic alone,
            # including any size the user has dragged it to.
            return

        self.column.setSizes([total - total // 2, total // 2])

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
        self._resizeColumn()

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
