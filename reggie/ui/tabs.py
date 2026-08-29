"""The master container - the tab bar over open sessions (Block D-c, phase D-c.2).

D-c.1 gave every session its own scene and view; the window still showed exactly
one of them as its central widget, swapped on activation. This module puts a
``QTabWidget`` in that place, so the sessions that were already open in parallel
become *visible* in parallel.

Two rules shape the whole file.

**The session set is the truth, the tabs are a view of it.** ``SessionManager``
decides which sessions exist and which one is active; this widget renders that
and reports user intent back. It never opens or closes a session by itself - it
asks the window to, and re-syncs from whatever the manager then says. That is
what keeps the tab bar honest when a session appears from somewhere the user did
not click: a collab peer's area switch, Add Area, a patch change.

**Ordering is a policy, not a history.** With ``TabsDraggable`` off - the default
- tab order is a pure function of the open sessions: grouped by game patch, then
by level ID ascending. Nothing the user does reorders it. With the setting on,
that same order is the starting point, and the first manual drag switches the
container to manual ordering permanently, after which new tabs are appended. The
two are separate modes rather than one mode with an exception, so that a tab the
user deliberately moved is never silently re-sorted (Zement, 2026-08-29).

Tool tabs (D-c.5's dialogs-as-tabs) always sort after every canvas tab. None
exist yet; the comparator is written for them now because retrofitting a sort key
is how sort orders end up inconsistent.
"""

import os
import re

from PyQt6 import QtCore, QtWidgets

from reggie.core import globals_
from reggie.core.dirty import setting


#: Sort key for a tab that is not a canvas - tool tabs go after every level.
TOOL_TAB_GROUP = '￿'

#: Matches the numbered stage names the sort orders by: 01-01, 03-C, W1-04 ...
_LEVEL_ID = re.compile(r'^(?:W?(\d+))\s*-\s*(\d+|[A-Za-z]+)')


def level_sort_key(file_path):
    """A sort key ordering level filenames by world, then by level id.

    Retail and patch stages are named ``01-01``, ``01-02``, ``01-C`` and so on,
    which neither string order nor natural number order gets right on its own:
    ``01-10`` must follow ``01-2``, and the lettered stages (castle, ghost house)
    must land after the numbered ones rather than between ``01-1`` and ``01-2``.

    Anything that does not parse sorts after everything that does, alphabetically
    - a custom level keeps a stable, predictable place at the end instead of
    disappearing into the middle of a numbered run.
    """
    name = os.path.splitext(os.path.basename(file_path or ''))[0]

    match = _LEVEL_ID.match(name)
    if match is None:
        return (1, name.lower(), 0, '')

    world = int(match.group(1))
    rest = match.group(2)

    if rest.isdigit():
        # (0, n, '') sorts before (1, 0, 'c'), so numbered stages precede
        # lettered ones within a world.
        return (0, world, (0, int(rest)), '')

    return (0, world, (1, 0), rest.lower())


class MasterTabWidget(QtWidgets.QTabWidget):
    """The window's central widget: one tab per open session.

    Owns no session state. ``sync()`` rebuilds the tab set from the manager and
    is safe to call at any time - it is the single path by which the tabs come to
    match reality, so every event that could change the session set ends in it.
    """

    def __init__(self, window):
        super().__init__(window)

        self.win = window
        self._syncing = False
        self._manualOrder = False
        self._placeholder = None

        self.setDocumentMode(True)
        self.setTabsClosable(True)
        self.setMovable(bool(setting('TabsDraggable', False)))
        self.setElideMode(QtCore.Qt.TextElideMode.ElideRight)
        self.setUsesScrollButtons(True)

        self.currentChanged.connect(self._handleCurrentChanged)
        self.tabCloseRequested.connect(self._handleCloseRequested)
        self.tabBar().tabMoved.connect(self._handleTabMoved)

        # The level overview floats over the canvas (D-c.4) rather than living
        # in a dock. Parented here so it moves with the canvas area and is
        # clipped by it; positioned by _positionOverlay on every resize.
        self.overlay = None
        self.overlayMargin = 12

    # -- reading the tabs ------------------------------------------------

    def sessionAt(self, index):
        """The session shown by tab ``index``, or None for a tool tab."""
        if index < 0 or index >= self.count():
            return None
        return self.tabBar().tabData(index)

    def indexOfSession(self, session):
        for index in range(self.count()):
            if self.sessionAt(index) is session:
                return index
        return -1

    def canvasTabCount(self):
        return sum(1 for i in range(self.count()) if self.sessionAt(i) is not None)

    # -- the placeholder -------------------------------------------------

    def showPlaceholder(self, view):
        """Show ``view`` as the only page, with no tab bar.

        There is a window before there is a session: this widget is built in the
        window's constructor and the first level is opened later, and a headless
        run may open none at all. Rather than let the container be empty - which
        would leave the ~87 sites reading ``mainWindow.view`` pointing at a
        widget in no layout - the window's fallback view fills it.

        The tab bar is hidden while it is up, because a single unnamed tab the
        user cannot act on is worse than no tab bar. ``sync()`` removes the
        placeholder as soon as a real session arrives.
        """
        if self._placeholder is view:
            return

        self._placeholder = view
        index = self.addTab(view, '')
        self.tabBar().setTabData(index, None)
        self.tabBar().hide()

    def _dropPlaceholder(self):
        if self._placeholder is None:
            return

        index = self.indexOf(self._placeholder)
        if index != -1:
            # removeTab does not destroy the page; the window still owns its
            # fallback view and will hand it back if every session closes.
            self.removeTab(index)

        self._placeholder = None
        self.tabBar().show()

    def showSession(self, session):
        """Bring a session's tab to the front. Returns False if it has none."""
        index = self.indexOfSession(session)
        if index == -1:
            return False

        if self.currentIndex() != index:
            self.setCurrentIndex(index)

        return True

    # -- ordering --------------------------------------------------------

    def _sortKey(self, session):
        """Group by patch, then order by level id - see the module docstring."""
        patch = getattr(session, 'patch_name', None)
        if not patch:
            # One patch is loadable at a time today, so every session shares a
            # group. Written per-session anyway: D-d makes several reachable,
            # and a comparator that assumes one group is the kind of thing that
            # silently keeps working while producing the wrong order.
            patch = getattr(globals_.gamedef, 'name', '') or ''

        return (str(patch).lower(),
                level_sort_key(session.file_path),
                session.area_num)

    def _orderedSessions(self, manager):
        sessions = manager.sessions

        if self._manualOrder:
            # Keep the order already on screen; anything not yet shown - a
            # session opened since the last sync - goes to the end.
            known = [self.sessionAt(i) for i in range(self.count())]
            ordered = [s for s in known if s in sessions]
            ordered += [s for s in sessions if s not in ordered]
            return ordered

        return sorted(sessions, key=self._sortKey)

    # -- writing the tabs ------------------------------------------------

    def tabTitleFor(self, session):
        name = os.path.splitext(os.path.basename(session.file_path or ''))[0]
        if not name:
            name = globals_.trans.string('WindowTitle', 0)

        areas = getattr(session.level, 'areas', None) or ()
        if len(areas) > 1:
            name = '%s: %d' % (name, session.area_num)

        return ('* ' + name) if session.dirty else name

    def sync(self):
        """Make the tabs match the manager. The only path that touches them.

        Rebuilds in place rather than clearing and refilling: a page belongs to
        its session, and removing every tab would reparent every view for no
        reason. Signals are blocked throughout, because moving tabs about fires
        ``currentChanged`` for indices that are mid-rearrangement - acting on
        those would activate whichever session happened to be passing.
        """
        manager = globals_.get_session_manager()
        if manager is None or self._syncing:
            return

        self._syncing = True
        blocked = self.blockSignals(True)
        try:
            wanted = self._orderedSessions(manager)

            if wanted:
                self._dropPlaceholder()

            # Drop the tabs whose sessions are gone first, so that the positions
            # the loop below moves tabs to are positions in the final set. Going
            # backwards keeps the indices behind the cursor valid.
            for index in range(self.count() - 1, -1, -1):
                session = self.sessionAt(index)
                if session is not None and session not in wanted:
                    # removeTab does not destroy the page - dispose() owns the
                    # view's lifetime - so this is safe whichever happens first.
                    self.removeTab(index)

            for position, session in enumerate(wanted):
                index = self.indexOfSession(session)

                if index == -1:
                    index = self.insertTab(position, session.view,
                                           self.tabTitleFor(session))
                    self.tabBar().setTabData(index, session)
                elif index != position:
                    self.tabBar().moveTab(index, position)

            for index, session in enumerate(wanted):
                self.setTabText(index, self.tabTitleFor(session))
                self.setTabToolTip(index, session.file_path or '')

            if manager.active is not None:
                index = self.indexOfSession(manager.active)
                if index != -1:
                    self.setCurrentIndex(index)

            self._updateCloseButtons()
        finally:
            self.blockSignals(blocked)
            self._syncing = False

    def _updateCloseButtons(self):
        """Disable the close button on the last canvas tab.

        Zement's rule is that one area stays loaded at all times, so the last
        canvas tab cannot be closed. Disabling the button says so before the
        click - a refusal the user can trigger is a worse experience than a
        control that is visibly unavailable.
        """
        lone = self.canvasTabCount() <= 1
        bar = self.tabBar()

        for index in range(self.count()):
            if self.sessionAt(index) is None:
                continue

            for side in (QtWidgets.QTabBar.ButtonPosition.RightSide,
                         QtWidgets.QTabBar.ButtonPosition.LeftSide):
                button = bar.tabButton(index, side)
                if button is not None:
                    button.setEnabled(not lone)

    def refreshTitles(self):
        """Re-read the tab labels without touching the tab set.

        Cheap enough to call whenever the dirty flag might have moved, which is
        what keeps the ``*`` marker honest.
        """
        manager = globals_.get_session_manager()
        if manager is None:
            return

        for index in range(self.count()):
            session = self.sessionAt(index)
            if session is not None:
                self.setTabText(index, self.tabTitleFor(session))

    def applySettings(self):
        """Re-read TabsDraggable, for the settings dialog to call."""
        draggable = bool(setting('TabsDraggable', False))
        self.setMovable(draggable)

        if not draggable and self._manualOrder:
            # Turning dragging off returns to the sorted order, and forgets that
            # the user had ever reordered - otherwise the manual arrangement
            # would lie dormant and reappear when the setting came back on.
            self._manualOrder = False
            self.sync()

    # -- user intent -----------------------------------------------------

    def _handleCurrentChanged(self, index):
        if self._syncing:
            return

        session = self.sessionAt(index)
        if session is None:
            return

        manager = globals_.get_session_manager()
        if manager is None or manager.active is session:
            return

        # Through the window, not manager.activate(): switching tabs has to do
        # everything an area switch does - rebuild the side lists, retitle,
        # reset the overview - and ActivateSession is where that lives.
        self.win.ActivateSession(session)

        # Each page is its own view with its own scrollbars, and the overlay is
        # placed against the visible one's viewport - so it has to be re-placed
        # when the page underneath it changes.
        self._positionOverlay()

    def _handleCloseRequested(self, index):
        session = self.sessionAt(index)
        if session is None:
            self.removeTab(index)
            return

        if self.canvasTabCount() <= 1:
            # The button is disabled, so this is unreachable by clicking. Kept
            # because tabCloseRequested can also arrive from a shortcut or a
            # middle-click depending on style, and the rule is the rule.
            return

        self.win.CloseSession(session)

    def _handleTabMoved(self, to_index, from_index):
        """The first manual drag switches the container to manual ordering."""
        if self._syncing or self._manualOrder:
            return

        self._manualOrder = True

    # -- the canvas overlay ----------------------------------------------

    def setOverlay(self, widget):
        """Float a widget over a corner of the canvas area.

        Used for the level overview (D-c.4), which was a dock the user had to
        position and could lose behind the window. Over the canvas it is always
        where the canvas is, and it costs no layout space.

        Deliberately a plain child rather than a Qt::Tool window: a real window
        would sit above the editor when the editor is not focused, which is what
        made the floating overview annoying in the first place.

        Returns the CanvasOverlay frame wrapping ``widget`` - which owns the
        corner, the size and the background, so this container's job stays "one
        tab per session".
        """
        from reggie.ui.overlay import CanvasOverlay

        if widget is None:
            self.overlay = None
            return None

        self.overlay = CanvasOverlay(self, widget, margin=self.overlayMargin)
        self.overlay.show()
        self.overlay.raise_()
        self._positionOverlay()

        return self.overlay

    def _positionOverlay(self):
        if self.overlay is None:
            return
        self.overlay.reposition()

    def applyOverlaySettings(self):
        """Re-read the overlay's corner and size settings."""
        if self.overlay is not None:
            self.overlay.applySettings()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._positionOverlay()

    def showEvent(self, event):
        super().showEvent(event)
        # The viewport has no useful geometry until the container is shown, and
        # _availableRect measures against it - so the first placement has to
        # happen here rather than at construction.
        self._positionOverlay()
