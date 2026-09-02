"""Dialogs-as-tabs - the tool tabs in the master container (Block D-c, phase D-c.5).

D-c.2 put a tab per open session in the middle of the window. This adds the
other kind of tab the brief asks for: the dialogs the user *inhabits* rather
than *answers* become pages beside the canvases instead of windows on top of
them.

Four were converted here - Preferences, the Patch Manager, the undo history and
the collaboration status window. **D-c.6 moved the undo history on again**, out
of a tab and into a sidebar section, and the collaboration window follows it in
D-d. The rule that sorted them is not the same as the rule that places them: a
dialog you inhabit stops being modal, and *then* how wide it is decides whether
it wants a tab or a sidebar column. Preferences and the Patch Manager are wide,
multi-column layouts and stay tabs; the undo list and a chat log are narrow and
are better beside the canvas than covering it.

The survey counted 24 modal dialogs. Only four are here, and the rule that
picked them (§3.4 of the plan) is worth restating because it is what keeps this
from becoming a 24-way rewrite:

    A dialog you return to and work in becomes a tab.
    A dialog you answer and dismiss stays modal.

The right-hand column - Area settings, Zone settings, Level information, Swap
objects - are small forms whose callers read their fields on the line after
``exec()`` returns. Inverting one to a signal shape buys nothing, because the
caller has nothing else to do while it is open.

**Why a QDialog can be a page at all.** A ``QDialog`` is a ``QWidget``; the
modality lives in ``exec()``, not in the class. Reparent one into a layout,
never call ``exec()``, and it is an ordinary panel. That is what makes this
phase small: not one of the four dialogs is rewritten, and the two that carry
real logic - the Patch Manager's downloads and the collab status window's
roster - keep every line of it.

What does need handling is the three ways a dialog says "I am done", since none
of them mean what they used to:

- ``accept()`` / ``reject()`` - the dialogs' own Close and Cancel buttons call
  these, and on a parentless dialog they would just hide the widget, leaving an
  empty tab behind. ``ToolTabHost`` intercepts both and closes the tab instead.
- ``done(code)`` - what both of the above funnel into, so it is the one that is
  actually hooked.
- ``closeEvent`` - the Patch Manager cleans up temp directories there, so the
  host has to let that run rather than route around it.

**A tool tab owns its dialog's lifetime.** Closing the tab calls ``close()`` on
the page, which runs whatever ``closeEvent`` it has, and then drops the
reference. Preferences is the exception the other way round: its caller reads
its widgets *after* it closes, so the host lets a caller take the result
first - see ``ToolTabManager.closeTool``.
"""

from PyQt6 import QtCore, QtWidgets


#: Identifies a tool tab and the single instance of it. One tab per kind: a
#: second Preferences page would be two editors of one settings file, and the
#: user asking for it a second time means "show me the one I opened".
PREFERENCES = 'preferences'
PATCH_MANAGER = 'patchmanager'
COLLABORATE = 'collaborate'

#: The five per-area forms (D-d.4). One key each, so the shell's existing
#: one-tab-per-kind rule gives **one Area Settings page at a time, not one per
#: session** - asking for it on area 2 while area 1's page is open replaces it.
#:
#: A page per session was considered and rejected: four identically-named tabs
#: with the user choosing between them by tab order. Replacing is also what
#: Preferences and the Patch Manager already do when asked for twice, so it is
#: the shell's established answer rather than a new one. Which session a page is
#: bound to is put in its tab title instead - see ``ReggieWindow.OpenSessionPage``.
AREA_SETTINGS = 'areasettings'
ZONE_SETTINGS = 'zonesettings'
BACKGROUNDS = 'backgrounds'
CAMERA_PROFILES = 'cameraprofiles'
LEVEL_INFORMATION = 'levelinformation'

#: Every key above, for the teardown that closes a session's pages with it.
SESSION_PAGE_KEYS = (AREA_SETTINGS, ZONE_SETTINGS, BACKGROUNDS,
                     CAMERA_PROFILES, LEVEL_INFORMATION)

#: The undo history was a tool tab in D-c.5 and moved to a sidebar section in
#: D-c.6 - a full-width tab made you leave the level to reach a thing you use
#: *while* looking at the level. The key is kept so a saved layout or a stale
#: call naming it resolves to something rather than raising, and so the move is
#: visible here rather than looking like the feature was dropped.
UNDO_HISTORY = 'undohistory'


class ToolTabHost(QtWidgets.QWidget):
    """Wraps one dialog so it can live as a page in the master container.

    A thin container rather than a reparent-in-place, for two reasons. It gives
    the dialog's ``done``/``accept``/``reject`` somewhere to be intercepted
    without patching the dialog class itself - four dialogs, four different
    authors, and monkeypatching each would be four places to break. And it lets
    the host outlive a dialog that closes itself, so the tab's removal is one
    path rather than a race between the page dying and the tab noticing.
    """

    #: Emitted when the wrapped dialog asked to be closed, with its key and
    #: whether the user confirmed (OK) rather than dismissed (Cancel/Close).
    #: The distinction is Preferences' whole contract: OK writes a hundred
    #: settings, Cancel writes none.
    closeRequested = QtCore.pyqtSignal(str, bool)

    def __init__(self, key, dialog, parent=None, owns_dialog=True):
        super().__init__(parent)

        self.key = key
        self.dialog = dialog
        self._closing = False

        # Whether closing the tab disposes of the dialog. True for the three
        # the shell builds on demand; False for the collaboration window, which
        # the collab controller owns for the length of a session - closing its
        # tab puts it away, it does not end the session.
        self.owns_dialog = bool(owns_dialog)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(dialog)

        # A dialog carries window flags that mean nothing to a child widget and
        # cause a real one on some styles - Qt::Dialog on a widget inside a
        # layout has been seen to force a separate top-level. Clearing it is
        # cheaper and more reliable than trusting the reparent alone.
        dialog.setWindowFlags(QtCore.Qt.WindowType.Widget)

        if isinstance(dialog, QtWidgets.QDialog):
            # The grip resizes a window; there is no window to resize any more,
            # and it would sit in the page's corner doing nothing.
            dialog.setSizeGripEnabled(False)

        # A dialog sized for a window it no longer is would force the whole tab
        # container wider than the screen - the Patch Manager asks for 1200x700.
        # The page must be free to shrink; its own scroll areas handle the rest.
        dialog.setMinimumSize(0, 0)

        self._hookDone(dialog)

        dialog.show()

    def _hookDone(self, dialog):
        """Route the dialog's three ways of finishing into ``closeRequested``.

        ``done`` is the funnel: ``accept`` and ``reject`` both call it, so
        replacing that one bound method catches every button the dialog owns,
        including any the dialog wires up itself. Bound on the *instance* rather
        than the class so nothing leaks to a second, still-modal use of the same
        dialog class elsewhere in the editor.
        """
        original = dialog.done

        accepted = int(QtWidgets.QDialog.DialogCode.Accepted)

        def done(code, _original=original):
            if self._closing:
                # Reached from closeTool's own close() - let the dialog finish
                # normally rather than asking to be closed a second time.
                _original(code)
                return

            self.closeRequested.emit(self.key, int(code) == accepted)

        dialog.done = done

    def closeDialog(self):
        """Close the wrapped dialog for real, running its own cleanup.

        The Patch Manager deletes its temp directories in ``closeEvent``, so
        this goes through ``close()`` rather than deleting the widget, and lets
        each dialog decide what closing means for it.

        **It does not delete the dialog.** The collaboration window is owned by
        the collab controller and outlives its tab: closing the tab puts the
        roster and chat away, it does not end the session. Reopening from the
        menu brings the same window back with its chat log intact. Ownership of
        the widget stays where it was, which is the whole reason this host is a
        wrapper rather than a reparent.
        """
        self._closing = True
        try:
            # Unparented first either way: the host is about to be deleted, and
            # a dialog left as its child would go with it - which is right for
            # the three the shell owns and wrong for the one it does not. Doing
            # it uniformly and then deleting explicitly keeps the two cases one
            # line apart instead of one lifetime apart.
            self.dialog.setParent(None)
            self.dialog.close()

            if self.owns_dialog:
                self.dialog.deleteLater()
        finally:
            self._closing = False


class ToolTabManager(QtCore.QObject):
    """Owns the open tool tabs and the one-instance-per-kind rule.

    Lives on the window, beside the ``SessionManager``, and has the same shape:
    it decides what exists, and ``MasterTabWidget`` renders that. The tabs
    widget asks it about a page rather than the other way round, which is what
    keeps the "sessions are the truth" rule from D-c.2 intact - tool tabs are
    simply a second source of truth for a second kind of tab, not an exception
    inside the first.
    """

    def __init__(self, window):
        super().__init__(window)

        self.win = window
        self._hosts = {}

    # -- reading ---------------------------------------------------------

    def isOpen(self, key):
        return key in self._hosts

    def host(self, key):
        return self._hosts.get(key)

    def dialog(self, key):
        host = self._hosts.get(key)
        return host.dialog if host is not None else None

    @property
    def keys(self):
        return list(self._hosts)

    # -- opening ---------------------------------------------------------

    def openTool(self, key, factory, title, owns=True):
        """Show the tool tab for ``key``, building it with ``factory`` if new.

        Returns the host. ``factory`` is called at most once per open tab, which
        is what makes "Preferences" idempotent: asking twice brings the existing
        page forward with whatever the user had already typed into it, rather
        than throwing that away for a fresh copy.
        """
        host = self._hosts.get(key)

        if host is None:
            dialog = factory()
            if dialog is None:
                return None

            host = ToolTabHost(key, dialog, owns_dialog=owns)
            host.closeRequested.connect(self._handleCloseRequested)
            self._hosts[key] = host

            self.win.tabs.addToolTab(host, title)

        self.win.tabs.showTool(host)
        return host

    # -- closing ---------------------------------------------------------

    def _handleCloseRequested(self, key, confirmed):
        """A dialog's own button. Apply only if it was the confirming one."""
        self.closeTool(key, apply=confirmed)

    def closeTool(self, key, apply=True):
        """Close the tool tab for ``key``.

        ``apply`` is what makes Preferences work as a tab at all. Its caller
        reads a hundred widget values *after* the dialog closes, so the reading
        has to happen before the page is gone - the callback registered in
        ``_applyCallbacks`` runs first, with the dialog still whole, and only
        then is the tab removed. Passing ``apply=False`` skips it, which is what
        a Cancel means.
        """
        host = self._hosts.get(key)
        if host is None:
            return

        if apply:
            callback = self._applyCallbacks.get(key)
            if callback is not None:
                callback(host.dialog)
        elif key in SESSION_PAGE_KEYS:
            # A cancelled per-area form still has cleanup to do - the zone dialog
            # previews live, so dismissing it has to repaint what it was
            # previewing - and the binding has to be dropped either way. Told
            # explicitly rather than left to the apply callback, because
            # "cancelled" and "never confirmed" are the same thing to a page and
            # must not be the same thing as "applied".
            cancel = getattr(self.win, '_cancelSessionPage', None)
            if cancel is not None:
                cancel(key, host.dialog)

        # Remove the tab before closing the dialog: closing can run cleanup that
        # re-enters (the Patch Manager's temp-directory sweep touches the file
        # system, and a message box there would spin the event loop), and a tab
        # still holding a half-closed page is the kind of thing that produced
        # D-b's "wrapped C/C++ object has been deleted" crashes.
        self.win.tabs.removeToolTab(host)
        self._hosts.pop(key, None)

        host.closeDialog()
        host.setParent(None)
        host.deleteLater()

    def closeAll(self, apply=False):
        """Close every tool tab - for window shutdown.

        Applies nothing by default: a window closing is not the user pressing OK
        in Preferences, and writing settings from a page nobody confirmed would
        be a surprise.
        """
        for key in list(self._hosts):
            self.closeTool(key, apply=apply)

    # -- what "OK" means, per tool ---------------------------------------

    @property
    def _applyCallbacks(self):
        """The per-tool "the user confirmed" handlers, resolved lazily.

        A property rather than a dict built in ``__init__`` so that a window
        under construction - or a headless test with a stub window - does not
        have to have every handler in place before the manager exists.
        """
        callbacks = {
            PREFERENCES: getattr(self.win, 'ApplyPreferences', None),
        }

        # The five per-area forms (D-d.4) all apply the same way: through the
        # binding that says *which session*, never against whatever is active.
        # One callback per key rather than one shared one, because closeTool
        # passes only the dialog and the page has to be found by key.
        router = getattr(self.win, '_applySessionPage', None)
        if router is not None:
            for key in SESSION_PAGE_KEYS:
                callbacks[key] = lambda dialog, _k=key: router(_k, dialog)

        return callbacks
