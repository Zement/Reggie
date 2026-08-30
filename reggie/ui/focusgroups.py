"""Keyboard focus groups (Block D-c.6).

Qt's focus chain is flat and global: Tab walks every focusable widget in the
window in creation order, with no notion of a region. That was tolerable while
the editor was a canvas and a few docks, but the D-c shell made the chain long
enough for the wandering to be obvious - Tab through the sidebar and it
continues into the master tab bar, then the toolbar, then back (Zement,
2026-08-30).

The fix is a *focus group*: a container whose Tab chain wraps around inside it,
with Ctrl+Tab / Ctrl+Shift+Tab moving between groups. That is the shape most
editors use, and it is the one Zement asked for.

Both keys are handled by a single event filter on the *application*, which is
the only place that reliably sees them:

* Ctrl+Tab never reaches ``focusNextPrevChild`` at all (measured), and a
  focused child may consume it first.

* Plain Tab is delivered to the focus widget, not to its ancestors, so a filter
  installed on the group widget does not see it. An earlier version of this
  module did exactly that, and its test passed only because the probe group had
  nothing focusable after it - so Qt's own wrap-around was indistinguishable
  from the one under test.
"""

from PyQt6 import QtCore, QtGui, QtWidgets


def _isTabKey(event):
    """True for Tab and Backtab, which is what Shift+Tab arrives as."""
    return event.key() in (QtCore.Qt.Key.Key_Tab, QtCore.Qt.Key.Key_Backtab)


def _isForward(event):
    """Backtab, or Tab with Shift held, means backwards."""
    if event.key() == QtCore.Qt.Key.Key_Backtab:
        return False
    return not (event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier)


def focusableWithin(root):
    """
    The widgets inside ``root`` that Tab can land on, in focus-chain order.

    Qt's own order is authoritative here - it accounts for setTabOrder calls
    and for layout direction - so this walks ``nextInFocusChain`` rather than
    inventing an order from the widget tree.
    """
    if root is None:
        return []

    found = []
    widget = root
    # nextInFocusChain is a cycle, so stopping when it comes back around is
    # what bounds the walk. A guard count is kept anyway: a malformed chain
    # would otherwise hang the UI, which is a far worse failure than a Tab
    # that does nothing.
    for _ in range(10000):
        widget = widget.nextInFocusChain()
        if widget is None or widget is root:
            break
        if not _acceptsFocus(widget):
            continue
        if root.isAncestorOf(widget):
            found.append(widget)

    return found


def _acceptsFocus(widget):
    """Whether Tab would actually stop on this widget right now."""
    policy = widget.focusPolicy()
    if not (policy & QtCore.Qt.FocusPolicy.TabFocus):
        return False
    # A folded section's children are hidden but still in the chain; landing on
    # one would move focus somewhere invisible.
    return widget.isVisible() and widget.isEnabled()


def wrapWithinGroup(group, forward):
    """
    Keeps Tab inside ``group`` when it would otherwise leave.

    Returns True if focus was moved (and the keypress should be swallowed),
    False to let Qt handle the move itself - which is the right answer
    everywhere except the two ends, because Qt's own move respects setTabOrder
    and this one would not.
    """
    order = focusableWithin(group)
    if len(order) < 2:
        # Nothing to cycle between; let Qt do whatever it would have done.
        return False

    current = QtWidgets.QApplication.focusWidget()
    if current not in order:
        return False

    index = order.index(current)

    if forward and index == len(order) - 1:
        order[0].setFocus(QtCore.Qt.FocusReason.TabFocusReason)
        return True
    if not forward and index == 0:
        order[-1].setFocus(QtCore.Qt.FocusReason.TabFocusReason)
        return True

    return False


class FocusGroupManager(QtCore.QObject):
    """
    Owns the list of groups and the Ctrl+Tab move between them.

    Groups are registered in the order the user should meet them. Registration
    is deliberately by *widget*, not by name lookup, so a group whose widget is
    destroyed simply stops being offered rather than raising.
    """

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._groups = []   # list of (name, widget)
        app.installEventFilter(self)

    def addGroup(self, name, widget):
        """Registers ``widget`` as a focus group. Returns it, for convenience."""
        if widget is None:
            return None

        for existing in self._groups:
            if existing[1] is widget:
                return widget

        self._groups.append((name, widget))
        return widget

    def groupNames(self):
        return [name for name, widget in self._groups if _alive(widget)]

    def groupWidget(self, name):
        """The widget registered under ``name``, or None."""
        for group_name, widget in self._groups:
            if group_name == name and _alive(widget):
                return widget
        return None

    def groupFor(self, widget):
        """The name of the group containing ``widget``, or None."""
        while widget is not None:
            for name, group in self._groups:
                if group is widget:
                    return name
            widget = widget.parentWidget()
        return None

    def eventFilter(self, obj, event):
        """
        Handles both Tab keys, from one filter on the application.

        Installed on the application rather than on each group widget because
        neither key reliably reaches a group-level filter: Ctrl+Tab may be
        consumed by the focused child first, and plain Tab is delivered to the
        focus widget, not to its ancestors.
        """
        if event.type() != QtCore.QEvent.Type.KeyPress or not _isTabKey(event):
            return False

        forward = _isForward(event)

        if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
            return self.moveToAdjacentGroup(forward)

        # Plain Tab: wrap inside whichever group currently holds focus.
        current = QtWidgets.QApplication.focusWidget()
        name = self.groupFor(current)
        if name is None:
            return False

        group = self.groupWidget(name)
        if group is None:
            return False

        return wrapWithinGroup(group, forward)

    def moveToAdjacentGroup(self, forward=True):
        """
        Moves focus to the first focusable widget of the next (or previous)
        group that has one. Returns whether focus actually moved.
        """
        usable = [(name, widget) for name, widget in self._groups
                  if _alive(widget) and widget.isVisible()]
        if not usable:
            return False

        current = QtWidgets.QApplication.focusWidget()
        index = self._indexOf(usable, current)

        step = 1 if forward else -1
        # Start from the group after the current one. If focus is nowhere in
        # particular, an index of -1 makes the forward case start at 0.
        for offset in range(1, len(usable) + 1):
            candidate = usable[(index + step * offset) % len(usable)]
            order = focusableWithin(candidate[1])
            if not order:
                # An empty group is skipped rather than swallowing the keypress:
                # a collapsed sidebar should not be a dead end.
                continue
            target = order[0] if forward else order[-1]
            target.setFocus(QtCore.Qt.FocusReason.TabFocusReason)
            return True

        return False

    @staticmethod
    def _indexOf(usable, widget):
        while widget is not None:
            for i, (_, group) in enumerate(usable):
                if group is widget:
                    return i
            widget = widget.parentWidget()
        return -1


def _alive(widget):
    """
    Whether a registered widget still exists.

    PyQt raises RuntimeError - not AttributeError - when the C++ object behind
    a wrapper has been deleted, so this cannot be a getattr check.
    """
    try:
        widget.objectName()
    except RuntimeError:
        return False
    return True


def install(window):
    """
    Registers the window's focus groups, in the order Ctrl+Tab visits them.

    Called once, after the sidebar and toolbar exist.
    """
    app = QtWidgets.QApplication.instance()
    if app is None:
        return None

    manager = FocusGroupManager(app)

    sidebar = getattr(window, 'sidebar', None)
    if sidebar is not None:
        # The three slices are separate groups: Zement's rule is that each
        # slice is a panel group in its own right, so Tab stays inside the
        # palette rather than continuing into the undo history below it.
        manager.addGroup('sidebar.rail', getattr(sidebar, 'rail', None))
        manager.addGroup('sidebar.pages', getattr(sidebar, 'pages', None))
        manager.addGroup('sidebar.panels', getattr(sidebar, 'panelScroll', None))

    manager.addGroup('tabs', getattr(window, 'tabs', None))
    manager.addGroup('toolbar', getattr(window, 'toolbar', None))

    window.focusGroups = manager
    return manager
