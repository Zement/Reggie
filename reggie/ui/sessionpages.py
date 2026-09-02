"""Session-bound pages - the five per-area dialogs (Block D-d, phase D-d.4).

D-c.5 made a dialog into a page. This makes a page know which *area* it is for.

The two are not the same problem, and the difference is the whole phase. A modal
dialog is safe by construction: ``exec()`` spins its own event loop with the rest
of the editor disabled, so between the user pressing OK and the handler writing
the values, nothing can change which session is active. Every one of the five
per-area handlers relies on that without saying so - they read
``globals_.Area``, ``self.undoStack``, ``self.scene`` and ``SetDirty()``, and all
four resolve through whichever session is in front.

Make one of those a page the user can leave, and "the session in front" and "the
session this form was opened for" become two different things. Then:

    Open Area Settings for area 1, switch to area 2, press OK
        -> area 1's values are written into area 2
        -> the undo command lands on area 2's stack
        -> area 2's tilesets are reloaded from area 1's names

Nothing raises. Nothing looks wrong. The damage is visible the next time area 1
is opened and is not what the user left there. **Zone settings is worse**: it
calls ``scene.removeItem``/``addItem``, and since D-c.1 the scene is per session,
so applying it against the wrong one moves ``ZoneItem``s between two live scenes
- the "wrapped C/C++ object has been deleted" crash class from D-b.

**The fix is not to rewrite the ~50 write sites.** It is to make them right, by
pointing the proxy at the bound session for the length of the apply. That keeps
the diff in ``window.py`` to a cut at the ``exec()`` line, five times, with not
one line of the apply bodies changed - which is what makes this phase reviewable
at all.

Plan: BLOCK_D_D_4_SESSION_PAGES.md, BLOCK_D_D_DIRECTORY.md §3.4.
"""

from reggie.core import globals_


class SessionBoundPage:
    """Binds one page's apply to one session.

    Not a widget. The hosting already exists - ``tooltabs.ToolTabHost`` reparents
    a ``QDialog`` into a tab and intercepts its three ways of finishing - and a
    second widget beside it would be a second answer to "what does closing a page
    mean", which is how a shell ends up with two that disagree.

    So this is the binding only: which session, and what "apply" does to it.
    """

    def __init__(self, window, session, apply_callback, key=None, title=''):
        self.win = window
        self.session = session
        self.apply_callback = apply_callback
        self.key = key
        self.title = title

    # -- the rule -----------------------------------------------------------

    def isAlive(self):
        """False once the bound session has been closed.

        A page whose session is disposed cannot apply: its ``area`` is a dead
        object and its scene's items have been released. Checked rather than
        assumed, because the page outlives arbitrary user actions and closing a
        tab is one of them.
        """
        manager = globals_.get_session_manager()
        if manager is None or self.session is None:
            return False
        return self.session in manager.sessions

    def applyNow(self, dialog):
        """Run the apply against the bound session, whatever is in front.

        The temporary activation is silent (``notify=False``): the state
        bindings move so the apply body reads the right area, and the three
        window callbacks - canvas, undo menu, toolbar - are skipped so the user
        does not watch their tab flick to another area and back.

        The restore is a ``finally`` because leaving the editor pointed at a
        session the user is not looking at is worse than whatever went wrong in
        the apply: every subsequent edit would land in the wrong area. And it
        re-reads the active session at apply time rather than trusting one
        captured at construction, because a page lives across arbitrary user
        actions and the session that was in front when it opened may have been
        closed since.
        """
        manager = globals_.get_session_manager()
        if manager is None or self.apply_callback is None:
            return False

        if not self.isAlive():
            # The level this form was for is gone. Silently doing nothing is
            # right here: the alternative is writing into whatever happens to be
            # active, which is the exact bug this class exists to prevent.
            return False

        previous = manager.active

        if previous is self.session:
            # Nothing to move. Worth short-circuiting rather than activating a
            # session that is already active: activate() clears the Dirty
            # override and bumps the serial, and doing that twice for one apply
            # is a change with no reason behind it.
            self.apply_callback(dialog)
            return True

        manager.activate(self.session, notify=False)
        try:
            self.apply_callback(dialog)
        finally:
            # `previous` may have been closed by the apply itself, or by
            # anything that ran during it. activate() raises ValueError for a
            # session it does not own - inside a finally, that would mask the
            # apply's own exception, which is the worst possible place for it.
            if previous is not None and previous not in manager.sessions:
                previous = manager.active if manager.active in manager.sessions \
                    else None

            manager.activate(previous, notify=False)

        return True
