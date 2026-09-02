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
from reggie.ui.tooltabs import ToolTabHost


#: Sort key for a tab that is not a canvas - tool tabs go after every level.
TOOL_TAB_GROUP = '￿'

#: How narrow a tab may be squeezed before the bar scrolls instead (D-d.3d).
#: Wide enough for `01-01: Area 3` plus its close button, which is the longest
#: label the editor generates on its own - a longer one elides, which is what
#: elision is for. Was 90 while the label read `01-01: 3`.
MIN_TAB_WIDTH = 120

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

        # A floor under how narrow a tab may be squeezed (D-d.3d). Zement,
        # 2026-09-01: "if there are too many tabs, the tabs shrink to fit the
        # total width of the Master Container, instead of showing a scrollbar.
        # This is a problem, as the tabs immediately become too small to read."
        #
        # `setUsesScrollButtons(True)` was already set and was not enough on its
        # own: Qt only reaches for the scroll buttons once the tabs are at their
        # *minimum* size, and with ElideRight and no minimum that is almost
        # nothing - so the names became unreadable long before anything
        # scrolled. Giving the bar a real minimum is what makes the scroll
        # buttons the thing that happens instead of the shrinking.
        #
        # ElideRight stays: it is the right answer for one over-long name, and
        # was only wrong as a substitute for scrolling.
        self.tabBar().setMinimumWidth(0)
        self.tabBar().setStyleSheet(
            'QTabBar::tab { min-width: %dpx; }' % MIN_TAB_WIDTH)

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
        """The session shown by tab ``index``, or None for a tool tab.

        Tool tabs (D-c.5) carry their ``ToolTabHost`` as tab data, so the check
        is "is this a session" rather than "is there data". Returning a host
        here would hand a widget to every caller that expects a session - and
        several of them go straight on to read ``.file_path``.
        """
        if index < 0 or index >= self.count():
            return None

        data = self.tabBar().tabData(index)
        return None if isinstance(data, ToolTabHost) else data

    def toolAt(self, index):
        """The tool host shown by tab ``index``, or None for a canvas tab."""
        if index < 0 or index >= self.count():
            return None

        data = self.tabBar().tabData(index)
        return data if isinstance(data, ToolTabHost) else None

    def indexOfTool(self, host):
        for index in range(self.count()):
            if self.toolAt(index) is host:
                return index
        return -1

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

    def tabTitleFor(self, session, dirty_marker=True):
        """This session's tab label.

        ``dirty_marker=False`` gives the name alone. D-d.4's session-bound pages
        put this in *their* tab titles - "Area Settings (02-05: Area 3)" - to
        make the binding visible, and there the marker would be a lie: a form's
        tab is not itself unsaved, and it would go stale the moment the level was
        saved from anywhere else, since nothing repaints a tool tab's title.
        """
        name = os.path.splitext(os.path.basename(session.file_path or ''))[0]
        if not name:
            name = globals_.trans.string('WindowTitle', 0)

        areas = getattr(session.level, 'areas', None) or ()
        if len(areas) > 1:
            # "02-05: Area 3", not "02-05: 3" (Zement, 2026-09-01). The bare
            # number read as part of the level's name on a narrow tab; the word
            # costs five characters, and the tabs scroll now rather than
            # shrinking, so those five characters no longer come out of every
            # other tab's width.
            name = '%s: %s' % (name, globals_.trans.string(
                'AreaCombobox', 0, '[num]', session.area_num))

        return ('* ' + name) if (dirty_marker and session.dirty) else name

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

        # The level overview belongs to a canvas; over a tool tab it would float
        # above a settings form showing the last level's shape.
        self._syncOverlayVisibility()

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
        host = self.toolAt(index)
        if host is not None:
            # Through the manager, not removeTab: the dialog has cleanup to run
            # and the manager owns the one-instance-per-kind bookkeeping. A tab
            # closed behind its back would leave the kind marked open forever.
            #
            # A tab's X is a dismissal, not a confirmation - so nothing is
            # applied, exactly as Cancel would not.
            self.win.toolTabs.closeTool(host.key, apply=False)
            return

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

    # -- tool tabs (D-c.5) -----------------------------------------------

    def addToolTab(self, host, title):
        """Append a tool tab. Always after every canvas tab.

        Appending is enough to keep the ordering rule: ``sync()`` places canvas
        tabs at positions 0..n-1 and never moves a tab it does not own, so tool
        tabs stay in the block above n as canvases come and go. That holds in
        manual-order mode too, where the user can drag canvas tabs among
        themselves but a tool tab dragged into the middle is simply where they
        put it - deliberate, since the mode's whole point is that a tab the user
        moved is left where they moved it.
        """
        index = self.addTab(host, title)
        self.tabBar().setTabData(index, host)

        # A tool tab is a real tab, so the bar has to be up even if the only
        # canvas is still the placeholder - otherwise Preferences would open
        # into a page with no way back to it.
        self.tabBar().show()

        return index

    def removeToolTab(self, host):
        index = self.indexOfTool(host)
        if index == -1:
            return

        # removeTab does not destroy the page; ToolTabManager owns the host's
        # lifetime and disposes of it after this returns.
        self.removeTab(index)

        if self._placeholder is not None and self.count() <= 1:
            # Back to nothing but the placeholder - hide the bar again, per
            # showPlaceholder's reasoning.
            self.tabBar().hide()

    def showTool(self, host):
        index = self.indexOfTool(host)
        if index == -1:
            return False

        if self.currentIndex() != index:
            self.setCurrentIndex(index)

        return True

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

    def _syncOverlayVisibility(self):
        """Hide the level overview while a tool tab is in front.

        Its own visibility setting still wins - the View menu's toggle must not
        be undone by visiting Preferences - so this only takes it away over a
        tool tab and gives it back over a canvas.
        """
        if self.overlay is None:
            return

        on_canvas = self.toolAt(self.currentIndex()) is None
        self.overlay.setVisible(on_canvas and self.overlay.isEnabledByUser())

        if on_canvas:
            self._positionOverlay()

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
