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

from PyQt6 import QtCore, QtGui, QtWidgets

from reggie.core import globals_
from reggie.core.dirty import setting
from reggie.ui.overlay import CanvasWidget, OVERLAY_CORNER_RADIUS
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


#: Background of a form button that is being looked at (D-d.4b). A colour of its
#: own rather than the palette's Highlight, because Highlight is also what a
#: *checked* button uses and the two states have to be told apart at a glance.
#: Zement picked this yellow on 2026-09-03, replacing the placeholder amber.
#:
#: The hover shade is lighter(115), which on a colour already at full value can
#: only raise the saturation - a small shift, but the pressed shade is a normal
#: darker(115), so the three states still read apart.
VISITING_COLOUR = '#f2ff00'


class SubTabBar(CanvasWidget):
    """The floating bar of an area's forms (D-d.4b).

    Zement drew two options, 2026-09-02: icons *behind* the tab label, or a
    small bar below the tab. This is the second, and the reason is stronger than
    preference. Icons in the label make a tab's width depend on how many forms
    are open, so tabs would resize as forms come and go and the tab under the
    pointer would move - the class of problem D-d.3d fixed with MIN_TAB_WIDTH,
    reintroduced as a feature.

    **It floats.** A full-width row in the layout took a strip of height from
    the canvas for the life of the tab (Zement, 2026-09-02: "should float
    on-top of the canvas, not influencing its size"). So it is a plain child
    positioned by hand and raised above the page - the same shape ``CanvasOverlay``
    takes for the level overview, and for the same reason: it costs no layout
    space and is always where the canvas is.

    **Always visible over its own tab**, all six buttons, whether or not a form
    is open. An earlier version showed only the open ones, which made the bar
    grow and shrink as forms came and went and gave a user with nothing open no
    way in at all.

    Three states, his, and each is a *background*, so they read from the icon
    rather than from its label:

    ==========  =============================================  ================
    Unloaded    no form of this kind for this area yet         flat, toggled off
    Loaded      built and holding edits, canvas on show        toggled on
    Visiting    this form is what the tab is showing           amber
    ==========  =============================================  ================
    """

    #: The five, in the order the Level menu lists them. Icon names are the ones
    #: the menu actions already use, so a theme that restyles the menu restyles
    #: this with nothing to update.
    ENTRIES = (
        ('areasettings', 'area', 'AreaDlg'),
        ('zonesettings', 'zones', 'ZonesDlg'),
        ('backgrounds', 'background', 'BGDlg'),
        ('cameraprofiles', 'camprofile', 'CamProfsDlg'),
        ('levelinformation', 'info', 'InfoDlg'),
    )

    #: Distance from the top-left corner of the canvas.
    MARGIN = 8

    #: The buttons paint their own backgrounds over the whole frame, so a
    #: palette Window colour is never seen. CanvasWidget fills with a real
    #: brush in paintEvent instead - see its docstring.
    PAINTS_OWN_BACKGROUND = True

    def __init__(self, stack, parent=None):
        super().__init__(parent, margin=self.MARGIN)

        self.stack = stack
        self.buttons = {}

        # No frame: the background is a rounded rect painted at the configured
        # alpha, and a styled panel border around it would be drawn at full
        # strength - a hard edge floating over the canvas with a faded fill
        # inside it, which is what Zement saw when only the border appeared to
        # respond to the setting (2026-09-03).
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        # The canvas button returns the tab to what it is named after. Kept as a
        # button rather than "click the tab again", which Zement offered as the
        # alternative: a tab click already means "come to this area", and giving
        # it a second meaning depending on what the area is showing is the kind
        # of overload that is invisible until it surprises someone. A sixth icon
        # is one more thing on screen and no more things to know.
        self.canvasButton = self._makeButton()
        self.canvasButton.clicked.connect(self._showCanvas)
        layout.addWidget(self.canvasButton)

        for key, _icon, _title in self.ENTRIES:
            button = self._makeButton()
            button.clicked.connect(
                lambda _checked=False, _k=key: self._activate(_k))

            self.buttons[key] = button
            layout.addWidget(button)

        # No stretch: the bar is sized by its buttons, not by its parent
        # (Zement, 2026-09-02 - "the width should be restricted to what's needed
        # by the buttons"). A stretch item here is what made it full width.
        self._loadIcons()
        self.adjustSize()

        # The overview's opacity setting governs both of these now (Zement,
        # 2026-09-03): they are two things floating over the same canvas, and
        # one of them being solid while the other faded reads as a mistake
        # rather than a choice.
        self._applyOpacity()

    def applySettings(self):
        """Re-read the shared canvas-overlay settings.

        Called from the same place the overview is told, so a change in
        Preferences reaches both without the caller knowing there are two.
        """
        self._applyOpacity()
        self.reposition()

    def _makeButton(self):
        button = QtWidgets.QToolButton(self)
        button.setCheckable(True)
        button.setAutoRaise(True)
        button.setFocusPolicy(QtCore.Qt.FocusPolicy.NoFocus)
        return button

    def _loadIcons(self):
        """Icons and tooltips, resolved late.

        The theme and the translations are loaded during boot, and a stack can
        be built before either - the headless suites construct windows in
        several orders. A bar with no icons is a usable bar; one that raised
        during construction would take the tab with it.
        """
        from reggie.ui.ui import GetIcon

        # `objects` is the palette's own icon, so the button that returns to the
        # level is marked with the thing the level is made of. There is no
        # `view` icon in the set - Zement noticed the canvas was the one sub-tab
        # without one - and inventing art here would be worse than reusing the
        # one that already means "the level".
        try:
            self.canvasButton.setIcon(GetIcon('objects'))
            self.canvasButton.setToolTip(globals_.trans.string('MenuItems', 164))
        except Exception:
            self.canvasButton.setText('#')

        for key, icon, title_key in self.ENTRIES:
            button = self.buttons[key]
            try:
                button.setIcon(GetIcon(icon))
                button.setToolTip(globals_.trans.string(title_key, 0))
            except Exception:
                button.setText(key[:1].upper())

    # -- state ------------------------------------------------------------

    def stateOf(self, key):
        """``'visiting'``, ``'loaded'`` or ``'unloaded'`` for one button.

        The three states in one place, so the styling below and the suites
        agree about what each means rather than each deciding for itself.
        """
        if self.stack.currentKey() == key:
            return 'visiting'
        return 'loaded' if key in self.stack.pages else 'unloaded'

    def refresh(self):
        """Redraw the three states.

        Called from every ``SessionPageStack`` method that can change what is
        open or on show, which is what keeps the bar from needing anyone else to
        remember it.
        """
        for key, button in self.buttons.items():
            state = self.stateOf(key)

            # Every button is always shown (Zement, 2026-09-02): the bar is the
            # way *in* to a form, so hiding the ones not yet opened hid the
            # entrance. Only the background says what has been loaded.
            button.setVisible(True)
            button.setChecked(state != 'unloaded')
            self._paint(button, state)

        showing_canvas = self.stack.isShowingCanvas()
        self.canvasButton.setChecked(True)
        self._paint(self.canvasButton,
                    'visiting' if showing_canvas else 'loaded')

        self.adjustSize()
        self.reposition()

    @staticmethod
    def _paint(button, state):
        """One button's background, by state.

        Only *visiting* needs painting. Unloaded and Loaded are the style's own
        unchecked and checked appearances, which is the point of using a
        checkable button for them: "toggled off" and "toggled on" then look the
        way this platform's toggles look, rather than the way one colour choice
        here guesses they should.

        A stylesheet rather than a palette role, because ``QToolButton`` in
        autoRaise mode paints its own background from the style for the checked
        and hover cases, and a palette colour underneath it is simply not drawn.

        **Every state it claims, it must spell out.** A stylesheet takes over
        the drawing of the property it names, so a rule that sets `background`
        with no `:hover` of its own leaves Qt with nothing to paint on the way
        *out* of a hover - the button keeps the hot look after the pointer has
        gone, which is the bug Zement saw (2026-09-03). Listing hover and
        pressed alongside is what hands the widget a background for every state
        it can be in. The ``:checked`` selector is there for the same reason:
        without it the style repaints over the visiting colour the moment the
        button is checked, which every visiting button is.
        """
        if state != 'visiting':
            button.setStyleSheet('')
            return

        button.setStyleSheet(
            'QToolButton { background: %(c)s; border: none; '
            'border-radius: %(r)dpx; }'
            'QToolButton:checked { background: %(c)s; }'
            'QToolButton:hover { background: %(h)s; }'
            'QToolButton:pressed { background: %(p)s; }'
            % {'c': VISITING_COLOUR,
               'r': OVERLAY_CORNER_RADIUS,
               'h': QtGui.QColor(VISITING_COLOUR).lighter(115).name(),
               'p': QtGui.QColor(VISITING_COLOUR).darker(115).name()})

    # -- placement --------------------------------------------------------

    def reposition(self):
        """Sit under this area's own tab, over the canvas rather than above it.

        Left-aligned with the tab it belongs to (Zement, 2026-09-02), so the bar
        reads as hanging from that tab rather than as a fixed decoration in the
        page's corner - which matters once several tabs are open and each has
        its own bar.

        Held inside the canvas *viewport* by one margin on each side (Zement,
        2026-09-03). The margin matters at both ends and for different reasons:
        the first tab sits flush against the window edge, where an aligned bar
        looks unfinished rather than deliberate; the last one would otherwise
        land on the view's own scrollbar, which is what the viewport rectangle
        exists to keep clear of.
        """
        parent = self.parentWidget()
        if parent is None:
            return

        area = self._availableRect()
        if area.width() <= 0:
            area = parent.rect()

        left_limit = area.left() + self.margin
        right_limit = area.right() - self.width() - self.margin + 1

        x = left_limit

        tabs = self.stack.tabs
        index = tabs.indexOfSession(self.stack.session) if tabs is not None else -1
        if index != -1:
            # Both offsets are measured against the *tab widget*, not mapped
            # widget-to-widget. mapTo(parent) walks up through the central
            # splitter, so it picks up the sidebar's width on the way and lands
            # the bar hundreds of pixels to the right - measured at x=597 for
            # the leftmost tab. Subtracting one offset from the other keeps the
            # whole sum inside the container that owns both.
            bar = tabs.tabBar()
            tab_left = bar.mapTo(tabs, bar.tabRect(index).topLeft()).x()
            page_left = parent.mapTo(tabs, QtCore.QPoint(0, 0)).x()

            x = tab_left - page_left

        # max() last, so a viewport too narrow for the bar leaves it at the left
        # margin rather than off the left edge.
        self.move(int(max(left_limit, min(x, right_limit))),
                  area.top() + self.margin)
        self.raise_()

    # -- clicks -----------------------------------------------------------

    def _activate(self, key):
        """Show a form, opening it first if this area has not got one yet.

        Because every button is always present, a click is "open it" as often
        as it is "show it" - which is the point of showing them all, and is why
        this asks the window rather than only the stack.
        """
        if self.stack.showPage(key):
            return

        window = getattr(globals_, 'mainWindow', None)
        opener = getattr(window, 'OpenSessionPageByKey', None)
        if opener is not None:
            opener(self.stack.session, key)

        self.refresh()

    def _showCanvas(self):
        self.stack.showCanvas()


class _StackContainer(QtWidgets.QWidget):
    """One area's tab page: its stack, with the flyout floating over it.

    Exists only to keep the floating bar placed. A layout cannot do it - the
    bar is deliberately *not* in one - so the container tells it where to sit
    whenever its own geometry changes, which is the same arrangement
    ``MasterTabWidget`` uses for the level overview.
    """

    def __init__(self, stack):
        super().__init__()
        self.stack = stack

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.stack.bar().reposition()

    def showEvent(self, event):
        super().showEvent(event)
        # Nothing has useful geometry until the page is shown, so the first
        # placement has to happen here rather than at construction.
        self.stack.bar().reposition()


class SessionPageStack:
    """One session's tab content: its canvas, plus whatever forms it has open.

    D-d.4 gave the five per-area forms a *binding* to their session; this gives
    them a *place*. Before it, a form was a top-level tool tab and there was one
    per kind, so opening Area Settings for area 2 replaced area 1's - throwing
    away a form the user was filling in. Zement's correction, 2026-09-02: the
    forms belong to the area, not to the editor.

    The arrangement is a ``QStackedWidget`` whose **page 0 is always the
    canvas**. That is what makes "close the form" have an obvious meaning and
    removes any empty-tab state to design: there is always something under the
    tab, and it is the thing the tab is named after.

    Owns nothing. The canvas belongs to the session and each form belongs to its
    own ``SessionBoundPage``; this holds the arrangement and can be dropped
    without taking either with it.
    """

    def __init__(self, session, tabs):
        self.session = session
        self.tabs = tabs
        self.pages = {}          # tool key -> the form widget

        self._container = _StackContainer(self)

        self._stack = QtWidgets.QStackedWidget(self._container)
        self._stack.addWidget(session.view)

        layout = QtWidgets.QVBoxLayout(self._container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._stack)

        # The flyout lives *inside* the session's own content area rather than
        # under the master tab bar as a whole. Same place on screen, and it is
        # per session by construction, so a bar can never show one area's forms
        # while another area's tab is in front - which a single shared bar would
        # have to be rebuilt on every tab switch to avoid.
        #
        # A plain child rather than a row in the layout above, so it floats over
        # the canvas instead of taking a strip of height from it for the life of
        # the tab (Zement, 2026-09-02). Same shape CanvasOverlay takes, for the
        # same reason.
        self._bar = SubTabBar(self, self._container)
        self._bar.refresh()
        self._bar.show()

    # -- the container ---------------------------------------------------

    def container(self):
        return self._container

    def bar(self):
        return self._bar

    def canvas(self):
        return self._stack.widget(0)

    def detach(self):
        """Let go of the canvas without destroying it.

        ``EditorSession.dispose`` deletes the view itself, and a container that
        still parents it would be deleting a widget out from under the session.
        So the canvas is un-parented back to nobody here, and the rest goes.
        """
        canvas = self.canvas()
        if canvas is not None:
            canvas.setParent(None)

        # The forms are owned by their tool hosts, not by this - the same rule
        # the collaboration window follows. Un-parent rather than delete, so a
        # closing session cannot take a form's widget with it before its owner
        # has finished with it.
        for widget in self.pages.values():
            if widget is not None:
                widget.setParent(None)

        self.pages.clear()

        self._container.setParent(None)
        self._container.deleteLater()

    # -- forms -----------------------------------------------------------

    def addPage(self, key, widget):
        """Put a form into this session's stack and show it.

        Replacing an existing form of the same kind *for this session* is
        correct and is not the behaviour D-d.4b removes: one Area Settings form
        per area is the rule, so asking again for the same area means "show me
        the one I opened".
        """
        existing = self.pages.get(key)
        if existing is not None and existing is not widget:
            self.removePage(key)

        if self._stack.indexOf(widget) == -1:
            self._stack.addWidget(widget)

        self.pages[key] = widget
        self._stack.setCurrentWidget(widget)
        self._bar.refresh()
        self.insetPages()
        self._syncOverlay()
        return widget

    def insetPages(self):
        """Keep the forms clear of the floating bar.

        The bar is allowed to overlap the *canvas* - it is a small strip over a
        scrolling picture, and that is the point of floating it. It must not
        overlap a **form**, where it would sit on top of a tab widget's own tabs
        (Zement, 2026-09-02, image 1: "the flyout bar overlaps with all 5 forms
        pages").

        A top margin on each form rather than a shorter stack, so the canvas
        keeps the full height it had before the bar existed and only the pages
        that need the room give it up.
        """
        top = self._bar.sizeHint().height() + 2 * self._bar.margin

        for widget in self.pages.values():
            if widget is None:
                continue

            layout = widget.layout()
            if layout is None:
                widget.setContentsMargins(0, top, 0, 0)
                continue

            left, _, right, bottom = layout.getContentsMargins()
            layout.setContentsMargins(left, top, right, bottom)

    def removePage(self, key):
        """Take a form out and fall back to the canvas.

        Returns the widget, still alive, so the caller decides its fate - the
        forms are owned by their tool hosts, exactly as the collaboration window
        is owned by its controller rather than by the tab showing it.
        """
        widget = self.pages.pop(key, None)
        if widget is None:
            return None

        index = self._stack.indexOf(widget)
        if index != -1:
            self._stack.removeWidget(widget)

        self.showCanvas()
        self._bar.refresh()
        return widget

    def pageKeys(self):
        return list(self.pages)

    # -- what is on show -------------------------------------------------

    def showCanvas(self):
        self._stack.setCurrentIndex(0)
        self._bar.refresh()
        self._syncOverlay()

    def showPage(self, key):
        widget = self.pages.get(key)
        if widget is None:
            return False

        self._stack.setCurrentWidget(widget)
        self._bar.refresh()
        self._syncOverlay()
        return True

    def _syncOverlay(self):
        """Take the level overview away over a form, and give it back.

        The container owns that rule - it applies to tool tabs too - so this
        asks rather than deciding. Guarded because a stack can outlive nothing
        and predate everything: the headless suites build these in several
        orders.
        """
        syncer = getattr(self.tabs, '_syncOverlayVisibility', None)
        if syncer is not None:
            syncer()

    def currentKey(self):
        """The key of the form on show, or None when the canvas is."""
        current = self._stack.currentWidget()
        if current is self.canvas():
            return None

        for key, widget in self.pages.items():
            if widget is current:
                return key
        return None

    def isShowingCanvas(self):
        return self.currentKey() is None


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

        # session -> SessionPageStack (D-d.4b). A session's tab page is a stack
        # whose page 0 is its canvas and whose other pages are that session's
        # open forms, so a form can take the tab's content area without the tab
        # itself moving or changing what it names.
        self._stacks = {}

    # -- the per-session page stack (D-d.4b) -----------------------------

    def stackFor(self, session, create=True):
        """The page stack behind a session's tab.

        Built on demand and cached, because a session's canvas is itself built
        on first access - asking for a stack must not be what forces a view into
        existence for a session that has none yet.
        """
        stack = self._stacks.get(session)
        if stack is not None or not create:
            return stack

        stack = SessionPageStack(session, self)
        self._stacks[session] = stack
        return stack

    def pageFor(self, session):
        """What to insert as this session's tab page.

        One place, so the answer cannot differ between ``sync`` and the code
        that later swaps a form in.
        """
        return self.stackFor(session).container()

    def canvasAt(self, index):
        """The canvas view shown by tab ``index``, or None for a tool tab.

        The counterpart to ``sessionAt`` for callers that want the widget rather
        than the session. Since D-d.4b the page is the session's stack, so
        ``widget(index)`` is no longer the view - and "which canvas is this tab
        showing" is a question worth being able to ask directly rather than by
        reaching through two containers at each call site.
        """
        session = self.sessionAt(index)
        if session is None:
            return None

        stack = self._stacks.get(session)
        return stack.canvas() if stack is not None else None

    def currentCanvas(self):
        """The canvas of the tab in front, or None over a tool tab or a form."""
        stack = self._stacks.get(self.sessionAt(self.currentIndex()))
        if stack is None or not stack.isShowingCanvas():
            return None
        return stack.canvas()

    def dropStackFor(self, session):
        """Forget a closed session's stack.

        Called from ``removeToolTab``'s sibling path in ``sync`` and from the
        window when a session is disposed. The stack owns nothing but the
        arrangement - the canvas belongs to the session and the forms to their
        pages - so this drops a reference rather than destroying anything.
        """
        stack = self._stacks.pop(session, None)
        if stack is not None:
            stack.detach()

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
                    self.dropStackFor(session)

            for position, session in enumerate(wanted):
                index = self.indexOfSession(session)

                if index == -1:
                    # The page is the session's stack, not its view directly
                    # (D-d.4b): a form takes the tab's content area without the
                    # tab moving or changing what it names.
                    index = self.insertTab(position, self.pageFor(session),
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
        """Hide the level overview while anything but a canvas is in front.

        Its own visibility setting still wins - the View menu's toggle must not
        be undone by visiting Preferences - so this only takes it away and gives
        it back, and never changes what the user asked for.

        Two cases now. A tool tab has no level to summarise (D-c.5), and since
        D-d.4b so does an area showing one of its forms: the overview would
        float over a settings dialog describing a canvas nobody can see
        (Zement, 2026-09-02). ``currentCanvas()`` answers both at once - it is
        None over a tool tab and over a form alike.
        """
        if self.overlay is None:
            return

        on_canvas = self.currentCanvas() is not None
        self.overlay.setVisible(on_canvas and self.overlay.isEnabledByUser())

        if on_canvas:
            self._positionOverlay()

    def applyOverlaySettings(self):
        """Re-read the settings shared by everything floating over the canvas.

        Two things now, not one: the level overview and every area's sub-tab
        flyout. The opacity setting governs both (Zement, 2026-09-03) - one
        solid while the other is faded reads as a mistake rather than a choice -
        so one call reaches both and the caller need not know there are two.

        The bars are told first. The overview starts below whatever shares its
        corner, so it has to measure a bar that has already taken its new size.
        """
        for stack in self._stacks.values():
            stack.bar().applySettings()

        if self.overlay is not None:
            self.overlay.applySettings()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._syncOverlayVisibility()

    def showEvent(self, event):
        super().showEvent(event)
        # The viewport has no useful geometry until the container is shown, and
        # _availableRect measures against it - so the first placement has to
        # happen here rather than at construction.
        self._syncOverlayVisibility()

    def changeEvent(self, event):
        """Put the overview back after the window state changes (D-d.6).

        Zement, 2026-09-04: the overview was occasionally missing from a canvas
        tab, "might be minimizing Reginald to the task bar", and "changing tabs"
        brought it back. Changing tabs is what runs `_syncOverlayVisibility`,
        which is the clue: the overview had been hidden or left behind, and only
        that call put it right.

        The cause is not established - it could not be reproduced offscreen, and
        a minimise there is not a real one. What is certain is that every path
        which *fixes* it is this one call, and that the events which could lose
        it were only ever repositioning. So they sync instead, and this adds the
        window-state change to them.

        Cheap and idempotent: it reads a setting and sets a visibility that is
        usually already right.
        """
        super().changeEvent(event)

        if event.type() in (QtCore.QEvent.Type.WindowStateChange,
                            QtCore.QEvent.Type.ActivationChange):
            self._syncOverlayVisibility()
